"""
tests/test_wave4b1_core_modules.py
Wave 4-B1: 코어 4대 모듈(prompt_pipeline·comfy_client·qa_validator·precheck) 분해 후
AST 크기 준수(<=350L/<=120L), 퍼사드 재노출, 패치 호환성 및 ADR-105/110 동등성 회귀 테스트.
"""

from __future__ import annotations

import ast
import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

import plepa_engine.comfy_client as comfy_client
import plepa_engine.prompt_pipeline as prompt_pipeline
import plepa_engine.qa_validator as qa_validator
from plepa_engine.config import ROOT_DIR
from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry
from plepa_engine.pipeline import SDXLPromptPipeline
from plepa_engine.precheck import PrecheckReport, check_pose_doc_sync, run_pregeneration_check
from plepa_engine.services.pose_service import default_pose_service
from tests.test_contract_guards import _FUNCTION_LINE_RATCHET_CAPS, _MODULE_LINE_RATCHET_CAPS


def _make_char(gender: str = "female", name: str = "테스트") -> CharacterConfig:
    is_oto = gender == "otokonoko"
    subj = "1boy, otokonoko, crossdressing" if is_oto else "1girl"
    return CharacterConfig(
        name=name,
        prefix="tst",
        gender=gender,
        appearance=CharacterAppearance(
            face_and_hair="short hair, bright eyes",
            physique="slender build",
            outfit="white shirt, pleated skirt",
        ),
        sdxl_positive=f"masterpiece, best quality BREAK {subj}, solo, short hair, white shirt, pleated skirt",
        sdxl_nude_positive=f"masterpiece, best quality BREAK {subj}, solo, short hair",
        sdxl_negative="lowres, bad anatomy",
    )


def test_wave4b1_ast_limits_and_ratchet_removal():
    """Wave 4-B1 대상 4개 영역의 모든 모듈<=350L, 함수<=120L 및 래칫 Allowlist 제거 검증."""
    target_files = [
        ROOT_DIR / "plepa_engine" / "comfy_client.py",
        ROOT_DIR / "plepa_engine" / "comfy_transport.py",
        ROOT_DIR / "plepa_engine" / "qa_validator.py",
        ROOT_DIR / "plepa_engine" / "qa_checks.py",
        ROOT_DIR / "plepa_engine" / "precheck.py",
        ROOT_DIR / "plepa_engine" / "precheck_rules.py",
        ROOT_DIR / "plepa_engine" / "prompt_pipeline.py",
        *sorted((ROOT_DIR / "plepa_engine" / "pipeline").glob("*.py")),
    ]
    assert len(target_files) >= 16
    for path in target_files:
        src = path.read_text(encoding="utf-8")
        lines = src.splitlines()
        rel = path.relative_to(ROOT_DIR).as_posix()
        assert len(lines) <= 350, f"{rel} 350줄 초과 ({len(lines)}L)"
        assert rel not in _MODULE_LINE_RATCHET_CAPS, f"{rel}가 모듈 래칫에 잔류함"
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno is not None:
                fn_len = node.end_lineno - node.lineno + 1
                assert fn_len <= 120, f"{rel}::{node.name} 120줄 초과 ({fn_len}L)"

    for old_rel in (
        "plepa_engine/comfy_client.py",
        "plepa_engine/precheck.py",
        "plepa_engine/prompt_pipeline.py",
        "plepa_engine/qa_validator.py",
    ):
        assert old_rel not in _MODULE_LINE_RATCHET_CAPS
        assert not any(path_key == old_rel for path_key, _ in _FUNCTION_LINE_RATCHET_CAPS)


def test_prompt_pipeline_facade_exports_and_adr105_110_invariants():
    """prompt_pipeline 퍼사드 심볼 재노출 및 ADR-105(모브 그림자)·ADR-110(#109/#179) 불변식 검증."""
    for sym in (
        "PromptContext",
        "PromptMutator",
        "PoseTagPreparationMutator",
        "PositiveAssemblyMutator",
        "NegativeBaseMutator",
        "DefectDefenseMutator",
        "TwoPersonMobMutator",
        "CompositionAntiDriftMutator",
        "SanitizerMutator",
        "SDXLPromptPipeline",
        "default_sdxl_pipeline",
        "harmonize_character_expression",
        "normalize_tag",
        "split_tags",
        "find_tag_conflicts",
        "remove_conflicting_tags_from_negative",
        "_MOB_TIER_SPECS",
        "_PARTNER_POS_SPECS",
        "_MOB_SHADOW_EYES_POS",
        "_MOB_EYELESS_BANGS_NEG",
        "_strip_tags_preserving_parens",
    ):
        assert hasattr(prompt_pipeline, sym), f"퍼사드 누락 심볼: {sym}"

    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    female = _make_char("female", "아야")
    oto = _make_char("otokonoko", "케이")

    # ADR-105: Tier 2 + poses(#031) 모브 눈 음영 + 여캐 눈 보호 (#034 bury_chest는 인라인 백헤드 단독)
    pos_031, neg_031, _ = prompt_pipeline.default_sdxl_pipeline.execute(
        prompt_pipeline.PromptContext(char=female, pose=db["031"])
    )
    assert "(dark-haired male mob:1.15)" in pos_031
    assert "eyes obscured by shadow" in pos_031
    assert "(clear visible female eyes:1.15)" in pos_031
    assert "visible male eyes" in neg_031

    pos_034, _, _ = prompt_pipeline.default_sdxl_pipeline.execute(
        prompt_pipeline.PromptContext(char=female, pose=db["034"])
    )
    assert "back of dark-haired male head buried in her chest" in pos_034
    assert "(tall dark-haired male mob:1.15)" not in pos_034

    # ADR-110 (#109): between_thighs 인라인 백헤드 + 모브 BREAK 블록 미중복
    pose_109 = db["109"]
    pos_109, neg_109, is_nude_109 = prompt_pipeline.default_sdxl_pipeline.execute(
        prompt_pipeline.PromptContext(char=female, pose=pose_109)
    )
    assert is_nude_109
    assert "rear of male head centered at crotch level" in pos_109
    assert "(tall dark-haired male mob:1.15)" not in pos_109
    assert "detailed male face" in neg_109

    # ADR-110 (#179): 상반신 크롭(cropped at lower belly) 오토코노코 성기 태그 스킵
    pose_179 = db["179"]
    pos_179, _, _ = prompt_pipeline.default_sdxl_pipeline.execute(
        prompt_pipeline.PromptContext(char=oto, pose=pose_179)
    )
    assert "small erect penis" not in pos_179

    # 일반 나체 오토코노코(예: 120 등 비크롭)에는 성기 태그 주입 유지
    nude_oto_pose = PoseEntry(
        code="999", section="h_scenes", label="테스트나체", description="오토코노코 나체 테스트 포즈",
        prompt="lying on bed, spread legs", required_outfit="nude", mob_tier=1,
    )
    pos_oto_nude, _, _ = SDXLPromptPipeline().execute(prompt_pipeline.PromptContext(char=oto, pose=nude_oto_pose))
    assert "small erect penis" in pos_oto_nude


def test_qa_validator_facade_monkeypatch_compatibility():
    """qa_validator.py 분할 후 기존 detect_*/burn/laplacian/aesthetic 패치 호환성 검증."""
    img = Image.new("RGB", (256, 256), color=(190, 190, 190))

    with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 100, 200), "person", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_heads", return_value=[((20, 20, 80, 80), "head", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_faces", return_value=[((25, 25, 75, 75), "face", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_hands", return_value=[((10, 10, 30, 30), "hand", 0.9)] * 2), \
         patch("plepa_engine.qa_validator._compute_color_burn_ratio", return_value=0.04):
        ok, reason, metrics = qa_validator.validate_generated_image(
            img, is_solo_scene=True, is_two_person=False, prompt="1girl, solo, portrait"
        )
        assert ok is True
        assert reason == ""
        assert metrics["faces"] == 1
        assert metrics["color_burn_ratio"] == 0.04

    with patch("plepa_engine.qa_validator.detect_person", return_value=[]):
        ok_burn, reason_burn, _ = qa_validator.validate_generated_image(
            img, check_color_burn=True, max_color_burn_ratio=0.10,
            prompt="1girl, solo",
        )
        # gray image has 0 burn, now force burn ratio via patch
        with patch("plepa_engine.qa_validator._compute_color_burn_ratio", return_value=0.25):
            ok_burn, reason_burn, _ = qa_validator.validate_generated_image(
                img, check_color_burn=True, max_color_burn_ratio=0.22, prompt="1girl, solo",
            )
            assert ok_burn is False
            assert "Color Burn" in reason_burn


def test_comfy_client_transport_delegation_and_patch_hooks(monkeypatch, tmp_path):
    """comfy_transport 분리 후에도 comfy_client.websocket/os/time 패치와 WebP 저장이 정상 동작하는지 검증."""
    fake_ws = MagicMock()
    fake_ws.recv.side_effect = [
        json.dumps({"type": "progress", "data": {"value": 1, "max": 2, "node": "KSampler"}}),
        json.dumps({
            "type": "executed",
            "data": {"prompt_id": "pid-99", "output": {"images": [{"filename": "ok.png", "subfolder": "", "type": "output"}]}},
        }),
    ]
    monkeypatch.setattr(comfy_client, "websocket", SimpleNamespace(WebSocket=lambda: fake_ws))

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (30, 60, 90)).save(buf, "PNG")
    png_bytes = buf.getvalue()

    class _Resp:
        def __init__(self, body: bytes, status: int = 200):
            self._body = body
            self.status = status
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return self._body

    def _fake_urlopen(req, timeout=5.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/system_stats"):
            return _Resp(b"{}")
        if url.endswith("/prompt"):
            return _Resp(json.dumps({"prompt_id": "pid-99"}).encode("utf-8"))
        if "/view?" in url:
            return _Resp(png_bytes)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(comfy_client.urllib.request, "urlopen", _fake_urlopen)

    progress_events = []
    client = comfy_client.ComfyClient("127.0.0.1:8188")
    out_file = tmp_path / "out.webp"
    saved = client.generate_image(
        {"1": {}},
        out_file,
        progress_cb=lambda v, m, n: progress_events.append((v, m, n)),
    )
    assert saved == out_file
    assert out_file.is_file()
    assert progress_events == [(1, 2, "KSampler")]


def test_precheck_rules_and_comfy_node_patch_compatibility():
    """precheck_rules 분리 후 PrecheckReport, 문서 동기화 및 Comfy 노드 패치 통합 검증."""
    ok_sync, missing = check_pose_doc_sync()
    assert ok_sync is True
    assert missing == []

    with patch(
        "plepa_engine.comfy_client.verify_required_nodes",
        return_value=(True, {}),
    ):
        report = run_pregeneration_check("campus", check_comfy=True)
        assert isinstance(report, PrecheckReport)
        assert report.passed is True
        assert report.total_characters >= 6
        assert report.total_poses >= 170
