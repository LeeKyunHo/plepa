"""
tests/test_wave4a_censor_package.py
Wave 4-A: plepa_engine/censor/ 서브패키지 분해 후 공개 API, Facade 패치 호환성,
AST 크기 제약(<=350L/<=120L) 및 오프라인 합성 이미지 기준 스타일·보호·정책 동등성 회귀 테스트.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image, ImageDraw

import plepa_engine.censor as censor
from plepa_engine.censor import models as censor_models
from plepa_engine.config import ROOT_DIR


def test_censor_subpackage_public_api_constants_and_ast_limits():
    """공개 API/상수 전량 재노출 및 censor/ 전 모듈 <=350L, 전 함수 <=120L 규격을 검증합니다."""
    expected_public = {
        "DAILY_EXPOSURE_CODES",
        "EXEMPT_DAILY_EVENT_CODES",
        "EXEMPT_EMOTION_CODES",
        "HAS_IMGUTILS",
        "NON_EXPOSURE_H_POSES",
        "POSE_EXACT_ANCHORS",
        "POSE_SAFE_ANCHORS",
        "ROMANCE_NON_EXPOSURE_CODES",
        "apply_black_silhouette",
        "apply_debug_bbox",
        "apply_manga_bar",
        "apply_manga_glow",
        "apply_mosaic",
        "apply_shadow_silhouette",
        "apply_silhouette",
        "apply_slim_black_bar",
        "apply_white_silhouette",
        "apply_wide_solid_bar",
        "censor_file",
        "censor_image",
        "detect_censors",
        "detect_genitals",
        "get_custom_censor_seg_model",
        "get_pose_anchor_box",
        "get_pose_category",
        "get_sam_model",
        "get_skin_mask",
        "is_pose_censor_required",
        "logger",
        "run_batch_censor",
        "unload_censor_models",
        "verify_and_heal_censor",
    }
    assert expected_public <= set(censor.__all__)
    for sym in expected_public:
        assert hasattr(censor, sym), f"plepa_engine.censor 누락 심볼: {sym}"

    # 기존 테스트·벤치마크가 직접 참조하는 내부 심볼 재노출 검증
    for internal_sym in (
        "_SAM_MODEL",
        "_SAM_MODEL_LOCK",
        "_CENSOR_SEG_MODEL",
        "_CENSOR_SEG_LOCK",
        "_POSE_DB_CACHE",
        "_POSE_DB_CACHE_LOCK",
        "_get_cached_pose_db",
        "_is_otokonoko_context",
        "_detect_target_candidates",
        "_filter_bottom_edge_false_positives",
        "_resolve_hybrid_targets_with_priors",
        "_resolve_hybrid_targets_and_mask",
        "_extract_semantic_sam_prompts",
        "_extract_hand_occlusion_mask",
        "_render_censored_style",
        "_estimate_penis_axis_and_base",
        "_classify_sam_mask_leak",
        "_snap_to_outer_lineart",
        "_compute_scale_factor",
    ):
        assert hasattr(censor, internal_sym), f"내부 호환 심볼 누락: {internal_sym}"

    assert not (ROOT_DIR / "plepa_engine" / "censor.py").exists()
    pkg_dir = ROOT_DIR / "plepa_engine" / "censor"
    py_files = sorted(pkg_dir.glob("*.py"))
    assert len(py_files) >= 7
    for p in py_files:
        src = p.read_text(encoding="utf-8")
        assert len(src.splitlines()) <= 350, f"{p.name} 350줄 초과"
        tree = ast.parse(src, filename=p.name)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno is not None:
                assert (node.end_lineno - node.lineno + 1) <= 120, f"{p.name}::{node.name} 120줄 초과"


def test_censor_facade_monkeypatch_and_singleton_sync(monkeypatch):
    """Facade(plepa_engine.censor)에 가한 monkeypatch와 싱글톤 상태 변경이 서브모듈 내부까지 전파되는지 검증."""
    skin = Image.new("RGB", (240, 240), color=(245, 200, 180))

    # 1. HAS_IMGUTILS / detect_censors 패치 전파 검증
    monkeypatch.setattr(censor, "HAS_IMGUTILS", False)
    assert censor.detect_genitals(skin, pose_code="088") == []

    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)
    monkeypatch.setattr(censor, "detect_censors", lambda *a, **kw: [((80, 90, 150, 190), "penis", 0.88)])
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: None)
    det = censor.detect_genitals(skin, pose_code="088", min_confidence=0.2)
    assert len(det) == 1 and det[0][1] == "penis"

    # 2. _detect_target_candidates 패치가 _resolve_hybrid_targets_with_priors까지 전파되는지 검증
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: [((60, 70, 130, 160), "penis", 0.77)])
    boxes, _, _, _, _ = censor._resolve_hybrid_targets_with_priors(skin, targets=("penis",))
    assert boxes == [((60, 70, 130, 160), "penis", 0.77)]

    # 3. _SAM_MODEL / unload_censor_models 양방향 동기화 검증
    sentinel = object()
    censor._SAM_MODEL = sentinel
    assert censor.get_sam_model() is sentinel
    censor.unload_censor_models()
    assert censor._SAM_MODEL is None
    assert censor_models._SAM_MODEL is None

    # 4. unittest.mock.patch 호환 검증
    with patch("plepa_engine.censor.censor_image", return_value=(skin, 1)) as m_ci:
        out_img, cnt = censor.censor_image(skin)
        assert cnt == 1 and out_img is skin
        m_ci.assert_called_once()


def test_censor_offline_styles_protection_and_policy_parity(monkeypatch):
    """오프라인 합성 이미지를 이용해 9종 스타일 렌더링, RGBA 보존, 보호 마스크 및 여성/오토코노코 정책을 검증합니다."""
    rgba = Image.new("RGBA", (320, 320), color=(245, 200, 180, 210))
    draw = ImageDraw.Draw(rgba)
    draw.rectangle([120, 100, 200, 250], fill=(235, 175, 155, 210), outline=(40, 25, 20, 255))

    monkeypatch.setattr(censor, "get_sam_model", lambda: None)
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: None)
    monkeypatch.setattr("imgutils.detect.detect_faces", lambda *a, **kw: [])
    monkeypatch.setattr("imgutils.detect.detect_hands", lambda *a, **kw: [])

    boxes = [((120, 100, 200, 250), "penis", 0.90)]
    censor_styles = (
        "white_silhouette",
        "black_silhouette",
        "bar",
        "slim_bar",
        "shadow",
        "mosaic",
        "manga_bar",
        "manga_glow",
    )
    for style in censor_styles:
        rendered = censor._render_censored_style(rgba, boxes, style=style)
        assert rendered.size == rgba.size
        assert rendered.mode == "RGBA"
        assert np.array_equal(np.array(rendered.getchannel("A")), np.array(rgba.getchannel("A")))

    dbg = censor._render_censored_style(rgba, boxes, style="debug_bbox")
    assert dbg.size == rgba.size and dbg.mode == "RGBA"
    assert not np.array_equal(np.array(dbg.convert("RGB")), np.array(rgba.convert("RGB")))

    # 손 가려짐 보호 마스크 & 배타 앵커 계산 검증
    skin_bool = np.ones((320, 320), dtype=bool)
    unocc_pts, hand_pts = censor._compute_mutually_exclusive_prompts(
        (120, 100, 200, 250), [(110, 155, 210, 195)], skin_bool
    )
    assert len(unocc_pts) >= 2 and len(hand_pts) >= 1
    hand_mask = censor._extract_hand_occlusion_mask(
        rgba.convert("RGB"), None, [(110, 155, 210, 195)], [(120, 100, 200, 250)], 1.0, skin_np=np.full((320, 320), 255, dtype=np.uint8)
    )
    assert np.count_nonzero(hand_mask[155:195, 110:210]) > 0
    assert np.count_nonzero(hand_mask[:140, :]) == 0

    # 여성 비노출 면제 vs 오토코노코 전수 검열 정책 동등성 검증
    for code in ("000", "010", "051", "060", "081", "109", "123"):
        assert censor.is_pose_censor_required(pose_code=code, roster="campus", is_otokonoko=False) is False
    for oto_code in ("151", "158", "179", "186"):
        assert censor.is_pose_censor_required(pose_code=oto_code, roster="oto") is True
    assert censor.is_pose_censor_required(pose_code="030", roster="oto") is True
    assert censor.is_pose_censor_required(pose_code="030", roster="campus") is False
    assert censor.is_pose_censor_required(
        pose_code="030",
        file_path=Path("output/oto/kei/01_normal/kei_030_test.webp"),
        roster="oto",
    ) is True
    assert censor.is_pose_censor_required(
        pose_code="030",
        file_path=Path("output/campus/aya/01_normal/aya_030_test.webp"),
        roster="campus",
    ) is False
