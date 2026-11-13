"""
tests/test_censor_and_pipeline_fixes.py
H1(검열 targets 존중/로스터 캐시 격리/영숫자 정규식/폴백 기본값),
H2(custom_neg/pose.negative_add 격리 및 괄호 균형),
H6(GenitExporter & mobile_viewer 동적 로스터) 회귀 테스트.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from plepa_engine import censor
from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import assemble_sdxl_prompt
from plepa_engine.prompt_pipeline import remove_conflicting_tags_from_negative
from plepa_engine.services import genit_exporter
from plepa_engine.services.schemas import CharacterSchema
from plepa_gui.pages import mobile_viewer


def _make_skin_image(w: int = 500, h: int = 500) -> Image.Image:
    arr = np.full((h, w, 3), (245, 200, 180), dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def test_censor_image_and_verify_heal_honor_targets(monkeypatch):
    """H1: censor_image와 verify_and_heal_censor가 targets 인수를 엄격히 준수하는지 검증."""
    skin_img = _make_skin_image()
    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)

    # pussy만 탐지된 상황: targets=("penis",)는 무시하고 targets=("pussy",)/("all",)만 수용
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda *a, **kw: [((150, 300, 260, 420), "pussy", 0.90)],
    )
    _, cnt_penis_only = censor.censor_image(skin_img, targets=("penis",), pose_code="067")
    _, cnt_pussy = censor.censor_image(skin_img, targets=("pussy",), pose_code="067")
    _, cnt_all = censor.censor_image(skin_img, targets=("all",), pose_code="067")
    assert cnt_penis_only == 0
    assert cnt_pussy >= 1
    assert cnt_all >= 1

    # verify_and_heal_censor 역시 targets=("penis",)일 때 pussy 오탐을 무시해야 함
    _, healed_penis = censor.verify_and_heal_censor(skin_img, targets=("penis",))
    _, healed_pussy = censor.verify_and_heal_censor(skin_img, targets=("pussy",))
    assert healed_penis is False
    assert healed_pussy is True


def test_censor_pose_db_cache_isolation_and_defaults(monkeypatch):
    """H1: _get_cached_pose_db 로스터별 캐시 격리, 영숫자 코드 정규식, enable_anchor_fallback 기본 False 검증."""
    calls = []

    def _fake_load(engine="sdxl", roster="campus"):
        calls.append(roster)
        return {
            "088": PoseEntry(code="088", section="h_scenes", label="후배위", prompt="doggystyle")
        }

    with censor._POSE_DB_CACHE_LOCK:
        saved = dict(censor._POSE_DB_CACHE)
        censor._POSE_DB_CACHE.clear()
    try:
        monkeypatch.setattr(
            "plepa_engine.services.pose_service.default_pose_service.load_pose_db",
            _fake_load,
        )
        db1 = censor._get_cached_pose_db("campus")
        db2 = censor._get_cached_pose_db("campus")
        db3 = censor._get_cached_pose_db("ykn")
        assert db1 is db2
        assert db3 is not db1
        assert calls == ["campus", "ykn"]
    finally:
        with censor._POSE_DB_CACHE_LOCK:
            censor._POSE_DB_CACHE.clear()
            censor._POSE_DB_CACHE.update(saved)

    # 영숫자 성인 코드(N01) 및 일반 면제 코드(010) 판별 검증
    assert censor.is_pose_censor_required(file_path=Path("aya_N01_pose.webp")) is True
    assert censor.is_pose_censor_required(file_path=Path("aya_010_happy.webp")) is False

    # enable_anchor_fallback 기본값 False 계약 검증
    sig = inspect.signature(censor.censor_image)
    assert sig.parameters["enable_anchor_fallback"].default is False


def test_pipeline_isolates_custom_and_pose_negatives_from_mob_strip():
    """H2: pose.negative_add와 custom_neg의 남성 관련 부정 태그가 2인 씬 스트리핑에 훼손되지 않아야 함."""
    char = CharacterConfig(
        prefix="test",
        name="TestChar",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="long black hair, red eyes",
            physique="slender",
            outfit="school uniform",
        ),
        sdxl_positive="masterpiece BREAK 1girl, long black hair, red eyes, white shirt, pleated skirt",
        sdxl_negative="worst quality, lowres",
    )
    pose = PoseEntry(
        code="088",
        section="h_scenes",
        label="후배위",
        prompt="doggystyle, 1girl, partner, sex from behind",
        negative_add="multiple boys, 2boys, extra hands",
    )
    pos, neg, _ = assemble_sdxl_prompt(
        char=char,
        pose=pose,
        bg_prompt="bedroom",
        custom_neg="1boy focus, fat man",
    )
    assert "multiple boys" in neg
    assert "2boys" in neg
    assert "extra hands" in neg
    assert "1boy focus" in neg
    assert "fat man" in neg
    assert pos.count("(") == pos.count(")")
    assert neg.count("(") == neg.count(")")


def test_pipeline_clothed_oral_and_conflict_strip_balance_parentheses():
    """H2: 착의 구강 씬([패치 E]) 및 부정 충돌 제거 시 짝이 맞지 않는 괄호가 남지 않아야 함."""
    char = CharacterConfig(
        prefix="aya",
        name="아야",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="silver hair",
            physique="large breasts",
            outfit="open shirt, black sheer pantyhose",
        ),
        sdxl_positive="masterpiece BREAK (1girl:1.1), silver hair, (open shirt, black sheer pantyhose:1.15)",
        sdxl_negative="worst quality, lowres",
    )
    pose = PoseEntry(
        code="067",
        section="h_scenes",
        label="딥스로트",
        prompt="fellatio, deepthroat, 1boy, penis, kneeling",
        required_outfit="default",
    )
    pos, neg, is_nude = assemble_sdxl_prompt(char=char, pose=pose, bg_prompt="classroom")
    assert is_nude is False
    assert pos.count("(") == pos.count(")")
    assert neg.count("(") == neg.count(")")

    # 중첩 가중치 괄호 내 충돌 태그 제거 후에도 괄호 균형 유지
    cleaned_neg, removed = remove_conflicting_tags_from_negative(
        "smile, open mouth",
        "worst quality, (smile:1.2, bad hands), ((open mouth)), lowres",
    )
    assert "smile" in removed
    assert cleaned_neg.count("(") == cleaned_neg.count(")")
    assert "bad hands" in cleaned_neg


def test_dynamic_genit_exporter_and_mobile_viewer_non_campus(monkeypatch, tmp_path):
    """H6: GenitExporter genit_map.json 동적 매핑 및 mobile_viewer 임의 로스터 동적 탐색 검증."""
    custom_dir = tmp_path / "nebula"
    (custom_dir / "assets" / "zz" / "01_normal").mkdir(parents=True)
    (custom_dir / "assets" / "zz" / "01_normal" / "zz_020_wave.webp").write_bytes(b"WEBP")
    (custom_dir / "genit_map.json").write_text('{"zz": "NZ"}', encoding="utf-8")

    monkeypatch.setattr(genit_exporter, "PROJECTS_DIR", tmp_path)
    assert genit_exporter.GenitExporter.resolve_export_code("테스트", "zz", roster="nebula") == "NZ"

    monkeypatch.setattr(mobile_viewer, "PROJECTS_DIR", tmp_path)
    schema = CharacterSchema(prefix="zz", name="제트", gender="female")
    monkeypatch.setattr(
        mobile_viewer.default_character_service,
        "list_characters",
        lambda roster=None: [("nebula", schema, custom_dir / "characters" / "zz.json")],
    )
    monkeypatch.setattr(
        "plepa_engine.services.asset_service.default_asset_service.get_missing_poses_by_character",
        lambda roster=None: {"zz": []},
    )

    data = mobile_viewer.get_mobile_gallery_data(roster="nebula")
    assert data["roster"] == "nebula"
    assert [c["id"] for c in data["chars"]] == ["zz"]
    assert len(data["items"]) == 1
    assert data["items"][0]["code"] == "020"
    assert data["items"][0]["label"] == "wave"
    html_out = mobile_viewer.generate_mobile_viewer_html(roster="nebula")
    assert "제트" in html_out
    assert "아야" not in html_out
