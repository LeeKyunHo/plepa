"""
tests/test_wave4b2_service_modules.py
Wave 4-B2: 서비스 레이어 4대 모듈 · workflow_templates · novelchat_validator 분해 후
plepa_engine/ 전 모듈 <=350L / 전 함수 <=120L / Allowlist 0건 계약 및 핵심 불변식 회귀 테스트.
"""

from __future__ import annotations

import ast
import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

import plepa_engine.services.generation_service as gen_svc_mod
from plepa_engine.checkpoint_service import CheckpointProfile
from plepa_engine.config import ROOT_DIR
from plepa_engine.models import PoseEntry
from plepa_engine.services.asset_helpers import restore_trash_bundle
from plepa_engine.services.asset_service import AssetService, default_asset_service
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
    GenerationService,
    default_generation_service,
    resolve_effective_sdxl_params,
    resolve_workflow_loras,
)
from plepa_engine.services.health_service import DiagnosticResult, HealthService, format_diagnostics_table
from plepa_engine.services.novelchat_validator import validate_novelchat_markdown
from plepa_engine.services.pose_service import PoseService, SECTION_METADATA, default_pose_service
from plepa_engine.workflow_templates import build_sdxl_workflow
from tests.test_contract_guards import (
    _FUNCTION_LINE_RATCHET_CAPS,
    _MODULE_LINE_RATCHET_CAPS,
    _REVERSE_LAYER_ALLOWLIST,
)


def test_plepa_engine_ast_zero_violations_and_allowlist_cleared():
    """plepa_engine/ 하위 전체(legacy 제외) <=350L, <=120L 및 Allowlist 0건 달성을 검증합니다."""
    engine_root = ROOT_DIR / "plepa_engine"
    py_files = sorted(p for p in engine_root.rglob("*.py") if "legacy" not in p.parts)
    assert len(py_files) >= 65

    for p in py_files:
        src = p.read_text(encoding="utf-8")
        lines = src.splitlines()
        rel = p.relative_to(ROOT_DIR).as_posix()
        assert len(lines) <= 350, f"{rel} 350줄 초과 ({len(lines)}L)"
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno is not None:
                fn_len = node.end_lineno - node.lineno + 1
                assert fn_len <= 120, f"{rel}::{node.name} 120줄 초과 ({fn_len}L)"

    assert not any(k.startswith("plepa_engine/") for k in _MODULE_LINE_RATCHET_CAPS)
    assert not any(k[0].startswith("plepa_engine/") for k in _FUNCTION_LINE_RATCHET_CAPS)
    assert len(_REVERSE_LAYER_ALLOWLIST) == 0


def test_workflow_templates_lora_bypass_and_chaining_invariant():
    """LoRA 미지정 시 0노드 무변경 바이패스 및 다중 LoRA 직렬 체이닝 계약을 검증합니다."""
    wf_plain = build_sdxl_workflow("pos", "neg", "pref", seed=42, ref_image_name="ref.webp")
    plain_classes = [n["class_type"] for n in wf_plain.values() if isinstance(n, dict)]
    assert "LoraLoader" not in plain_classes
    assert plain_classes[0] == "CheckpointLoaderSimple"
    ipa_node = next(n for n in wf_plain.values() if n.get("class_type") == "IPAdapterUnifiedLoader")
    freeu_id = next(nid for nid, n in wf_plain.items() if isinstance(n, dict) and n.get("class_type") == "FreeU")
    assert ipa_node["inputs"]["model"] == [freeu_id, 0]
    assert any(n.get("class_type") == "FaceDetailer" for n in wf_plain.values())

    wf_lora = build_sdxl_workflow(
        "pos", "neg", "pref", seed=42,
        loras=[("style_a.safetensors", 0.75), ("char_b.safetensors", 0.6)],
    )
    lora_nodes = [(nid, n) for nid, n in wf_lora.items() if n.get("class_type") == "LoraLoader"]
    assert len(lora_nodes) == 2
    assert lora_nodes[0][1]["inputs"]["lora_name"] == "style_a.safetensors"
    assert lora_nodes[0][1]["inputs"]["model"] == ["1", 0]
    assert lora_nodes[1][1]["inputs"]["lora_name"] == "char_b.safetensors"
    assert lora_nodes[1][1]["inputs"]["model"] == [lora_nodes[0][0], 0]


def test_generation_service_priority_dryrun_and_manifest_isolation(tmp_path):
    """설정 우선순위(params > conf > profile), dry-run 매니페스트 무누수 및 mock 실행을 검증합니다."""
    profile = CheckpointProfile(
        name="Test", engine="sdxl",
        width=832, height=1216, steps=28, cfg=4.0, sampler="dpmpp_2m", scheduler="karras",
        quality_positive="q", quality_negative="n", match_patterns=[".*"],
    )
    conf = {"sdxl_ckpt": "ckpt_a.safetensors", "sdxl_steps": 32, "sdxl_cfg": 5.5}
    p_default = GenerationParams(character_expr="aya", width=960)
    w, h, s, c, smp, sch = resolve_effective_sdxl_params(p_default, conf, profile)
    assert (w, h, s, c, smp, sch) == (960, 1216, 32, 5.5, "dpmpp_2m", "karras")

    # 일회성 ckpt 오버라이드 시 다른 ckpt의 saved conf(steps=32) 무시하고 해당 profile 우선
    p_override = GenerationParams(character_expr="aya", ckpt="other.safetensors")
    _, _, s2, c2, _, _ = resolve_effective_sdxl_params(p_override, conf, profile)
    assert (s2, c2) == (28, 4.0)

    out_root = tmp_path / "dry_out"
    dry_params = GenerationParams(
        character_expr="aya", pose_expr="000,034", roster="campus",
        dry_run=True, out_dir=str(out_root),
    )
    dry_results = default_generation_service.run_batch(dry_params, quiet=True)
    assert len(dry_results) == 2
    assert all(r.success for r in dry_results)
    assert not list(out_root.rglob("_batch_manifest.json"))

    mock_out = tmp_path / "mock_out"
    mock_params = GenerationParams(
        character_expr="aya", pose_expr="000", roster="campus",
        mock=True, overwrite=True, out_dir=str(mock_out),
    )
    mock_res = default_generation_service.run_batch(mock_params, quiet=True)
    assert len(mock_res) == 1 and mock_res[0].success and mock_res[0].image_path.is_file()
    manifests = list(mock_out.rglob("_batch_manifest.json"))
    assert len(manifests) == 1


def test_generation_service_mock_patch_forwarding(tmp_path):
    """generation_service.ComfyClient / validate_generated_image 패치가 generation/ 실행기에 전파되는지 검증."""
    calls = []

    class _FakeComfy:
        def __init__(self, host="127.0.0.1:8188"):
            self.host = host
        def check_connection(self):
            return True
        def session(self):
            return MagicMock(__enter__=lambda s: s, __exit__=lambda s, *a: False)
        def generate_image(self, workflow, output_path, **kwargs):
            Image.new("RGB", (64, 64), (180, 180, 180)).save(output_path, "WEBP")
            return output_path

    def _spy_validate(image, **kwargs):
        calls.append(kwargs)
        return True, "", {"persons": 2, "heads": 2, "faces": 1, "hands": 2}

    params = GenerationParams(
        character_expr="aya", pose_expr="109", roster="campus",
        overwrite=True, auto_qc=True, out_dir=str(tmp_path / "qc_out"),
    )
    with patch("plepa_engine.services.generation_service.ComfyClient", _FakeComfy), \
         patch("plepa_engine.services.generation_service.validate_generated_image", side_effect=_spy_validate):
        results = GenerationService().run_batch(params, quiet=True)

    assert len(results) == 1 and results[0].success and results[0].qc_passed
    assert len(calls) == 1
    assert calls[0]["is_two_person"] is True
    assert calls[0]["allow_partner_head"] is True


def test_pose_health_asset_and_novelchat_service_contracts(tmp_path):
    """PoseService, HealthService, AssetService, novelchat_validator 분해 후 계약을 검증합니다."""
    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    assert len(db) >= 175
    assert "emotions" in SECTION_METADATA
    assert len(default_pose_service.resolve_pose_codes("000..002", db, roster="campus")) == 3
    assert len(default_pose_service.resolve_pose_codes("sample10", db, roster="campus")) == 10

    health = HealthService()
    for st in (
        health.check_stage_1_pose_db(),
        health.check_stage_3_prompt_pipeline(),
        health.check_stage_4_precheck(),
        health.check_stage_5_workflows(),
        health.check_stage_9_gui_trinity_sync(),
    ):
        assert isinstance(st, DiagnosticResult)
        assert st.status == "PASS", f"Stage {st.stage_index} failed: {st.message}"
    table_str = format_diagnostics_table([health.check_stage_1_pose_db()])
    assert "Unified System Health Diagnostics" in table_str

    # AssetService 스캔 및 휴지통 복원 계약 검증
    svc = AssetService()
    assets = svc.list_character_assets("aya", roster="campus")
    assert isinstance(assets, list) and len(assets) >= 100
    trash_f = tmp_path / "assets" / "_trash" / "t_000.webp"
    orig_f = tmp_path / "assets" / "t" / "t_000.webp"
    trash_f.parent.mkdir(parents=True, exist_ok=True)
    trash_f.write_bytes(b"RIFFtest")
    assert restore_trash_bundle([{"trash": str(trash_f), "original": str(orig_f)}], tmp_path) is True
    assert orig_f.is_file()

    # novelchat_validator 검증
    bad_md = "# Test\n## 1. [탭 1: 프로필]\n### 1-1.\n```\n제목\n```\n{{url}} [@id=x]"
    res = validate_novelchat_markdown(bad_md)
    assert res.passed is False
    assert any("젠잇" in e for e in res.errors)
