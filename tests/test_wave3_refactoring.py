"""
tests/test_wave3_refactoring.py
Wave 3 리팩토링(Pose 스키마 단일화, GlobalJobManager 큐 통합, 옵션 삼위일체, LoraLoader 체이닝, legacy 로스터 메타 분리) 계약 테스트.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, List

from batch_generator import create_parser
from plepa_engine.config import PROJECTS_DIR, ROOT_DIR
from plepa_engine.models import (
    CharacterAppearance,
    CharacterConfig,
    GenerationResult,
    GenerationTarget,
    LoraConfig,
    PoseEntry,
)
from plepa_engine.services import job_manager as jm_mod
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_options import GENERATION_OPTION_SPECS, resolve_workflow_loras
from plepa_engine.services.generation_service import GenerationParams
from plepa_engine.services.job_manager import GlobalJobManager
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.services.schemas import PoseItemSchema
from plepa_engine.workflow_templates import build_sdxl_workflow
from plepa_gui.components.option_controls import normalize_option_values


def test_pose_entry_and_schema_unification_on_all_sdxl_db_keys():
    """실제 data/sdxl_pose_database.json 전 키가 PoseEntry.from_dict 및 PoseItemSchema와 100% 호환·왕복되는지 검증."""
    db_path = ROOT_DIR / "data" / "sdxl_pose_database.json"
    raw_db = json.loads(db_path.read_text(encoding="utf-8"))

    validated_count = 0
    for sec_name, sec_items in raw_db.items():
        if sec_name.startswith("_") or not isinstance(sec_items, dict):
            continue
        for raw_code, raw_entry in sec_items.items():
            if not isinstance(raw_entry, dict):
                continue
            code = default_pose_service.normalize_code(str(raw_code))
            entry = PoseEntry.from_dict(code, sec_name, raw_entry)
            schema = PoseItemSchema.from_pose_entry(entry)
            restored = schema.to_pose_entry(code=code, section=sec_name)

            assert restored.code == entry.code
            assert restored.section == entry.section
            assert restored.label == entry.label
            assert restored.prompt == entry.prompt
            assert restored.status == entry.status
            assert restored.is_active == entry.is_active
            assert restored.mob_shadow == entry.mob_shadow
            validated_count += 1

    assert validated_count >= 150


def test_workflow_lora_chaining_and_conditional_bypass():
    """Lora 미지정 시 그래프 무변경(0노드 차이) 바이패스 및 지정 시 LoraLoader 직렬 체이닝을 검증."""
    common_kwargs: dict[str, Any] = dict(
        positive_prompt="1girl, smile",
        negative_prompt="bad quality",
        output_prefix="test_bypass",
        seed=42,
        use_face_detailer=False,
        use_freeu=True,
        ref_image_name=None,
    )
    wf_none = build_sdxl_workflow(**common_kwargs)
    wf_empty = build_sdxl_workflow(**common_kwargs, loras=[])
    wf_off = build_sdxl_workflow(**common_kwargs, lora_name="none")

    assert wf_none == wf_empty == wf_off
    assert all(
        n.get("class_type") != "LoraLoader"
        for n in wf_none.values()
        if isinstance(n, dict)
    )

    wf_chained = build_sdxl_workflow(
        **common_kwargs,
        loras=[("style_a.safetensors", 0.7), ("detail_b.safetensors", 0.45)],
    )
    lora_nodes = [
        (nid, n) for nid, n in wf_chained.items()
        if isinstance(n, dict) and n.get("class_type") == "LoraLoader"
    ]
    assert len(lora_nodes) == 2

    ckpt_id = next(nid for nid, n in wf_chained.items() if n.get("class_type") == "CheckpointLoaderSimple")
    first_id, first_node = lora_nodes[0]
    second_id, second_node = lora_nodes[1]
    assert first_node["inputs"]["lora_name"] == "style_a.safetensors"
    assert first_node["inputs"]["strength_model"] == 0.7
    assert first_node["inputs"]["model"] == [ckpt_id, 0]
    assert first_node["inputs"]["clip"] == [ckpt_id, 1]

    assert second_node["inputs"]["lora_name"] == "detail_b.safetensors"
    assert second_node["inputs"]["strength_clip"] == 0.45
    assert second_node["inputs"]["model"] == [first_id, 0]
    assert second_node["inputs"]["clip"] == [first_id, 1]

    clip_skip_node = next(n for n in wf_chained.values() if n.get("class_type") == "CLIPSetLastLayer")
    assert clip_skip_node["inputs"]["clip"] == [second_id, 1]

    freeu_node = next(n for n in wf_chained.values() if n.get("class_type") == "FreeU")
    assert freeu_node["inputs"]["model"] == [second_id, 0]


def test_resolve_workflow_loras_precedence():
    """resolve_workflow_loras의 캐릭터·파라미터 우선순위 및 multi-LoRA 파싱 검증."""
    char = CharacterConfig(
        prefix="t",
        name="테스트",
        gender="female",
        appearance=CharacterAppearance(face_and_hair="black hair", physique="slim", outfit="uniform"),
        lora=LoraConfig(name="char_main.safetensors", weight=0.75),
        loras=[LoraConfig(name="char_extra.safetensors", weight=0.5)],
    )
    assert resolve_workflow_loras(char, GenerationParams(character_expr="t")) == [
        ("char_main.safetensors", 0.75),
        ("char_extra.safetensors", 0.5),
    ]
    assert resolve_workflow_loras(char, GenerationParams(character_expr="t", lora="none")) == []
    assert resolve_workflow_loras(
        char, GenerationParams(character_expr="t", lora="a.safetensors, b.safetensors:0.6", lora_weight=0.9)
    ) == [("a.safetensors", 0.9), ("b.safetensors", 0.6)]


def test_global_job_manager_fifo_censor_only_and_progress_callback(monkeypatch):
    """GlobalJobManager.enqueue_censor_only와 on_progress 콜백의 순차 FIFO 직렬화 검증."""
    mgr = GlobalJobManager()
    active_count = 0
    max_concurrent = 0
    lock = threading.Lock()
    events: List[str] = []
    done = threading.Event()

    def fake_run_batch(params, on_progress=None, is_cancelled=None, quiet=True):
        nonlocal active_count, max_concurrent
        with lock:
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
        try:
            time.sleep(0.02)
            target = GenerationTarget(
                code="000", section="emotions", label="일반",
                assembled_prompt="p", is_nude=False, output_filename="aya_000_일반.webp",
            )
            res = GenerationResult(target=target, success=True, duration_sec=0.02)
            if on_progress:
                on_progress(1, 1, res)
            return [res]
        finally:
            with lock:
                active_count -= 1

    monkeypatch.setattr(jm_mod.default_generation_service, "run_batch", fake_run_batch)

    mgr.enqueue_job(
        GenerationParams(character_expr="aya", pose_expr="000", roster="campus"),
        label="job1",
        on_progress=lambda c, t, r: events.append(f"p:{r.target.code}"),
    )
    mgr.enqueue_censor_only(
        roster="campus",
        character_expr="aya",
        label="censor1",
        on_complete=lambda _res, _err: done.set(),
    )
    assert done.wait(timeout=3.0)
    assert max_concurrent == 1
    assert events == ["p:000"]
    history = mgr.get_status()["job_history"]
    assert len(history) == 2
    assert all(h["status"] == "done" for h in history)


def test_trinity_option_controls_normalization_and_cli_toggles():
    """CLI 신규 QC 토글과 GUI option_controls 값 정규화 계약 검증."""
    parser = create_parser()
    args_off = parser.parse_args(["--no-qc", "--no-retry-qc-failed", "--prompt-alert-threshold", "5", "--include-legacy"])
    assert args_off.auto_qc is False
    assert args_off.retry_qc_failed is False
    assert args_off.prompt_alert_threshold == 5
    assert args_off.include_legacy is True

    raw_state = {s["field"]: s["default"] for s in GENERATION_OPTION_SPECS}
    raw_state.update({"seed": 1234.0, "max_retries": "4", "lora": "  ", "ref_weight": "0.65"})
    normalized = normalize_option_values(GENERATION_OPTION_SPECS, raw_state)
    assert normalized["seed"] == 1234 and isinstance(normalized["seed"], int)
    assert normalized["max_retries"] == 4 and isinstance(normalized["max_retries"], int)
    assert normalized["lora"] is None
    assert normalized["ref_weight"] == 0.65


def test_legacy_five_rosters_metadata_isolation():
    """구형 5개 로스터 roster.json status=legacy 메타데이터 분리 및 명시적 접근 호환성 검증."""
    for r in ("default", "maid", "man", "don", "murim"):
        meta_file = PROJECTS_DIR / r / "roster.json"
        assert meta_file.is_file(), f"legacy 메타파일 누락: {meta_file}"
        assert default_character_service.is_legacy_roster(r) is True
        assert default_character_service.get_roster_status(r) == "legacy"

    assert default_character_service.is_legacy_roster("campus") is False
    assert "campus" in default_character_service.list_rosters()
