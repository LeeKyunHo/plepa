"""
tests/test_prompt_pipeline.py
H-씬 4-Tier 모브·성기 제어 파이프라인(Phase H1), 파일럿 8종 포즈 개편,
오토코노코 대칭성 격리 및 GenerationService Auto-QC/strict_censor_qc 연동 회귀 테스트.
"""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import assemble_sdxl_prompt
from plepa_engine.qa_validator import validate_generated_image
from plepa_engine.services.generation_service import (
    GenerationParams,
    GenerationService,
    get_optimal_resolution_for_pose,
)
from plepa_engine.services.pose_service import default_pose_service


def _make_female_char(sdxl_positive: str = "masterpiece BREAK 1girl, solo, long black hair, red eyes, white shirt, pleated skirt") -> CharacterConfig:
    return CharacterConfig(
        prefix="testf",
        name="TestFemale",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="long black hair, red eyes",
            physique="slender",
            outfit="school uniform",
        ),
        sdxl_positive=sdxl_positive,
        sdxl_negative="worst quality, lowres",
    )


def _make_otokonoko_char() -> CharacterConfig:
    return CharacterConfig(
        prefix="testo",
        name="TestOtoko",
        gender="otokonoko",
        appearance=CharacterAppearance(
            face_and_hair="silver hair, blue eyes",
            physique="feminine body, slender",
            outfit="girl uniform",
        ),
        sdxl_positive="masterpiece BREAK 1boy, solo, otokonoko, feminine boy, silver hair, pleated skirt",
        sdxl_negative="worst quality, lowres",
    )


def _assert_no_oversized_or_legacy_penis_tags(pos: str, neg: str) -> None:
    pos_low = pos.lower()
    neg_low = neg.lower()
    for banned_pos in ("large thick erect penis", "impressive manhood", "muscular build"):
        assert banned_pos not in pos_low, f"금지 과장 태그 잔류: {banned_pos} in {pos}"
    for banned_neg in ("small penis", "thin penis", "short penis", "micropenis"):
        assert banned_neg not in neg_low, f"금지 크기 네거티브 잔류: {banned_neg} in {neg}"


def test_legacy_oversized_penis_and_muscular_tags_removed_across_modes():
    """Step 1: TwoPersonMobMutator에서 과장 남성 체형·성기 하드코딩 및 small penis 네거티브가 전면 제거되었는지 검증."""
    char = _make_female_char()
    legacy_poses = [
        PoseEntry(code="084", section="h_scenes", label="기승위레거시", prompt="cowgirl, 1girl, 1boy, sex, bedroom"),
        PoseEntry(code="126", section="h_scenes", label="책상밑레거시", prompt="under desk, fellatio, 1girl, 1boy, clothed male partner", required_outfit="default"),
        PoseEntry(code="999", section="h_scenes", label="다인레거시", prompt="gangbang, 3boys, 1girl, completely nude"),
    ]
    for pose in legacy_poses:
        pos, neg, _ = assemble_sdxl_prompt(char=char, pose=pose, bg_prompt="bedroom")
        _assert_no_oversized_or_legacy_penis_tags(pos, neg)


def test_defect_defense_otokonoko_genital_branch_isolated_from_female():
    """Step 1: DefectDefenseMutator 오토코노코 성기 주입이 female 캐릭터에 절대 누출되지 않음을 검증."""
    # gender='female' 인데 본문 우연한 문자열이 있어도 여성 격리 보장
    female_char = _make_female_char(
        sdxl_positive="masterpiece BREAK 1girl, solo, long black hair, red eyes, otokonoko fan art"
    )
    pose_080 = default_pose_service.load_pose_db(engine="sdxl", roster="campus")["080"]
    pos_f, neg_f, _ = assemble_sdxl_prompt(char=female_char, pose=pose_080, bg_prompt="bedroom")
    assert "small erect penis" not in pos_f.lower()
    assert "testicles" not in pos_f.lower()
    assert "(pussy:1.35)" not in neg_f.lower()

    oto_char = _make_otokonoko_char()
    pose_150 = default_pose_service.load_pose_db(engine="sdxl", roster="campus")["150"]
    pos_o, neg_o, _ = assemble_sdxl_prompt(char=oto_char, pose=pose_150, bg_prompt="bedroom")
    assert "small erect penis" in pos_o.lower()
    assert "testicles" in pos_o.lower()
    assert "1girl" not in pos_o.lower()


def test_mob_tier_pilot_8_poses_db_and_prompt_pipeline():
    """Step 1 & 2: 파일럿 8종 DB 프롬프트와 4-Tier 파이프라인 출력(Tier 0~3) 정합성 검증."""
    char = _make_female_char()
    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

    expected_tiers = {
        "080": 0,
        "088": 1,
        "091": 1,
        "086": 2,
        "092": 2,
        "104": 2,
        "072": 3,
        "100": 3,
    }

    for code, expected_tier in expected_tiers.items():
        pose = db[code]
        assert pose.mob_tier == expected_tier, f"#{code} mob_tier 불일치: {pose.mob_tier}"
        w, h = get_optimal_resolution_for_pose(pose, 832, 1216, engine="sdxl", user_specified=False)
        assert (w, h) == (832, 1216), f"#{code} 세로 해상도 유지 실패: {(w, h)}"

        pos, neg, _ = assemble_sdxl_prompt(char=char, pose=pose, bg_prompt="bedroom")
        pos_low = pos.lower()
        neg_low = neg.lower()

        _assert_no_oversized_or_legacy_penis_tags(pos, neg)
        assert "cowboy shot" not in pos_low, f"#{code} cowboy shot 잔류: {pos}"

        if expected_tier == 0:
            assert pose.is_solo_scene is True
            assert pose.is_two_person is False
            assert pos.count("BREAK") == 1, f"Tier 0({code}) 불필요한 2번째 BREAK 생성: {pos}"
            assert "solo" in pos_low
            assert "solo focus" in pos_low
            for expected_neg in ("1boy", "male body", "penis", "disembodied limb"):
                assert expected_neg in neg_low
        elif expected_tier == 1:
            assert pose.is_two_person is True
            assert pose.is_offscreen_partner is True
            assert pos.count("BREAK") == 1, f"Tier 1({code}) 별도 남성 BREAK 생성됨: {pos}"
            assert "disembodied male hands" in pos_low
            assert "cropped male arms" in pos_low
            assert "female focus" in pos_low
            for expected_neg in ("male face", "male torso", "muscular chest", "full male body", "lower body focus", "crotch focus"):
                assert expected_neg in neg_low
        elif expected_tier == 2:
            assert pose.is_two_person is True
            assert pose.is_offscreen_partner is True
            assert pos.count("BREAK") == 2
            mob_chunk = pos.split("BREAK")[-1].lower()
            assert "faceless shadowed male silhouette" in mob_chunk
            assert "cropped male shoulder" in mob_chunk
            assert "dark lighting on partner" in mob_chunk
            assert "female face and chest focus" in mob_chunk
            assert "crotch out of frame" in pos_low
            assert "penis" not in mob_chunk, f"Tier 2({code}) 모브 청크에 성기 태그 금지: {mob_chunk}"
            for expected_neg in ("male face", "detailed male eyes", "full body", "wide shot", "crotch focus"):
                assert expected_neg in neg_low
        elif expected_tier == 3:
            assert pose.is_two_person is True
            assert pose.is_offscreen_partner is True
            assert pos.count("BREAK") == 2
            mob_chunk = pos.split("BREAK")[-1].lower()
            assert "pov crotch" in mob_chunk
            assert "disembodied penis" in mob_chunk
            assert "partially visible glans" in mob_chunk
            assert "compact shaft" in mob_chunk
            assert "cropped male lower torso" in mob_chunk
            for expected_neg in ("giant penis", "hyper penis", "huge penis", "full male body", "male face", "muscular chest"):
                assert expected_neg in neg_low


def test_implicit_solo_focus_marker_triggers_tier_0_without_breaking_legacy():
    """mob_tier가 미지정이어도 순수 solo focus H-포즈는 Tier 0으로 승격되고, 1boy 포함 레거시 포즈는 2인 인터랙티브를 유지."""
    char = _make_female_char()
    solo_pov_pose = PoseEntry(
        code="H99",
        section="h_scenes",
        label="테스트솔로POV",
        prompt="solo focus, pov, tight bust portrait, 1girl, completely nude, lying on bed, parted lips",
    )
    pos, neg, _ = assemble_sdxl_prompt(char=char, pose=solo_pov_pose, bg_prompt="bedroom")
    assert pos.count("BREAK") == 1
    assert "solo" in pos.lower()
    assert "disembodied limb" in neg.lower()

    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    legacy_oral = db["096"]  # 1boy + solo focus + fellatio 레거시 포즈
    assert legacy_oral.mob_tier is None
    pos_leg, _, _ = assemble_sdxl_prompt(char=char, pose=legacy_oral, bg_prompt="bedroom")
    assert pos_leg.count("BREAK") == 2


def test_otokonoko_symmetry_preserved_on_150_to_209_and_romance_072():
    """Step 4: 오토코노코(150~209) +70 대칭 및 romance:072 공용 포즈가 1girl 누출/2boys 역오염 없이 동작하는지 검증."""
    oto_char = _make_otokonoko_char()
    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

    for oto_code in ("150", "156", "158", "161", "162", "170", "174"):
        pose = db[oto_code]
        assert pose.mob_tier is None
        pos, neg, _ = assemble_sdxl_prompt(char=oto_char, pose=pose, bg_prompt="bedroom")
        assert "1girl" not in pos.lower()
        assert "small erect penis" in pos.lower()
        _assert_no_oversized_or_legacy_penis_tags(pos, neg)

    # romance:072 (mob_tier=3)를 오토코노코로 생성 시 prompt_otokonoko(2boys)와 3boys 가드가 정상 유지되어야 함
    pose_072 = db["072"]
    pos_72, neg_72, _ = assemble_sdxl_prompt(char=oto_char, pose=pose_072, bg_prompt="bedroom")
    assert "2boys" in pos_72.lower()
    assert "1girl" not in pos_72.lower()
    assert "3boys" in neg_72.lower()
    assert "(2boys:" not in neg_72.lower()
    _assert_no_oversized_or_legacy_penis_tags(pos_72, neg_72)


def test_generation_service_auto_qc_and_strict_censor_qc_tier_routing(tmp_path: Path):
    """
    Step 3:
    1) mob_tier=0 -> is_solo_scene=True, is_two_person=False 로 validate_generated_image 전달.
    2) mob_tier in (1, 2, 3) -> is_two_person=True, is_offscreen_partner=True 전달 및 heads/faces>=2 시 리롤.
    3) strict_censor_qc=True 일 때 mob_tier in (0, 1, 2)는 성기 필수 검출/리롤에서 제외, mob_tier==3만 작동.
    """
    char = _make_female_char()
    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    pilot_poses = {c: db[c] for c in ("080", "086", "088", "100")}

    recorded_qc_calls = []

    class _FakeComfyClient:
        def __init__(self, host=None):
            self.host = host

        def check_connection(self):
            return True

        def session(self):
            return nullcontext()

        def generate_image(self, workflow, output_path: Path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (256, 384), color=(180, 170, 165)).save(output_path, "WEBP")

    def _spy_validate(image, **kwargs):
        recorded_qc_calls.append(kwargs)
        # Tier 2 (086) 1차 시도는 모브 얼굴 침범으로 리롤 유도, 2차 시도 통과
        if "shadowed male shoulder" in (kwargs.get("prompt") or "").lower():
            attempt_086 = sum(
                1 for c in recorded_qc_calls
                if "shadowed male shoulder" in (c.get("prompt") or "").lower()
            )
            if attempt_086 == 1:
                return False, "오프스크린 파트너 씬 모브 얼굴 노출 감지 (얼굴: 2개, 단독 1인 얼굴만 허용)", {"persons": 2, "heads": 1, "faces": 2, "hands": 2}
        return True, "", {"persons": 1, "heads": 1, "faces": 1, "hands": 2}

    svc = GenerationService()
    with patch("plepa_engine.services.generation_service.ComfyClient", _FakeComfyClient), \
         patch.object(svc.char_svc, "resolve_characters", return_value=[(char, "campus")]), \
         patch.object(svc.pose_svc, "load_pose_db", return_value=pilot_poses), \
         patch.object(svc.pose_svc, "resolve_pose_codes", return_value=["080", "088", "086", "100"]), \
         patch("plepa_engine.services.generation_service.validate_generated_image", side_effect=_spy_validate), \
         patch("plepa_engine.censor.detect_genitals", return_value=[((100, 150, 150, 220), "penis", 0.85)]) as m_detect:
        params = GenerationParams(
            character_expr=char.prefix,
            pose_expr="080,088,086,100",
            roster="campus",
            overwrite=True,
            auto_qc=True,
            strict_censor_qc=True,
            censor=False,
            max_retries=1,
            out_dir=str(tmp_path),
        )
        results = svc.run_batch(params, quiet=True)

    assert len(results) == 4
    assert all(r.success for r in results)

    # 1. Auto-QC 플래그 전달 검증 (086은 1회 리롤 포함 총 5회 호출)
    assert len(recorded_qc_calls) == 5
    qc_by_prompt = {c["prompt"]: c for c in recorded_qc_calls}

    c_080 = next(v for k, v in qc_by_prompt.items() if "solo focus" in k.lower())
    assert c_080["is_solo_scene"] is True
    assert c_080["is_two_person"] is False

    for marker in ("lying on stomach", "shadowed male shoulder", "fellatio"):
        c_t = next(v for k, v in qc_by_prompt.items() if marker in k.lower())
        assert c_t["is_solo_scene"] is False
        assert c_t["is_two_person"] is True
        assert c_t["is_offscreen_partner"] is True

    # 2. strict_censor_qc는 mob_tier==3(100) 1회만 detect_genitals를 호출해야 함 (080/088/086 제외)
    assert m_detect.call_count == 1
    assert m_detect.call_args.kwargs.get("pose_code") == "100"

    # 3. 실제 qa_validator가 Tier 2(086)의 남캐 얼굴 침입(faces=2 또는 heads=2)을 즉시 거부하는지 검증
    img = Image.new("RGB", (256, 384), color=(190, 190, 190))
    with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 150, 350), "person", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_heads", return_value=[((30, 30, 90, 90), "head", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_faces", return_value=[((35, 35, 85, 85), "face", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_hands", return_value=[]):
        passed_t2, reason_t2, _ = validate_generated_image(
            img,
            is_solo_scene=False,
            is_two_person=True,
            is_offscreen_partner=True,
            prompt=pilot_poses["086"].prompt,
        )
        assert passed_t2 is False
        assert "오프스크린 파트너" in reason_t2
