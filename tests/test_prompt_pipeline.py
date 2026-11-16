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
        "088": 2,
        "091": 2,
        "086": 2,
        "092": 2,
        "104": 2,
        "035": 1,
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
            assert pos.count("BREAK") == 1
            assert "faceless" not in pos_low
            assert "partner head out of frame" in pos_low
            if code in ("086", "092", "104"):
                assert "crotch out of frame" in pos_low
            assert "penis" not in pos_low, f"Tier 2({code}) 프롬프트에 성기 태그 금지: {pos}"
            for expected_neg in ("detailed male face", "dark silhouette", "heavy shadow", "full body", "wide shot", "crotch focus"):
                assert expected_neg in neg_low
            assert "male hair" not in neg_low
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

    legacy_oral = PoseEntry(
        code="H98",
        section="h_scenes",
        label="테스트레거시오랄",
        prompt="1boy, solo focus, 1girl, completely nude, fellatio, kneeling, looking up at partner",
        mob_tier=None,
    )
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
        if "lying on back on bed, legs spread" in (kwargs.get("prompt") or "").lower():
            attempt_086 = sum(
                1 for c in recorded_qc_calls
                if "lying on back on bed, legs spread" in (c.get("prompt") or "").lower()
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

    for marker in ("on all fours", "lying on back on bed, legs spread", "fellatio"):
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


def test_adr101_style_guard_comic_expression_and_accessory_lock(monkeypatch):
    """ADR-101: Reference-5 화풍 가드(glossy 모드 하위 호환), 태닝/누드 예외, 코믹 표정 눈 보존, male hair 제거 및 초커 보호 검증."""
    from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry

    monkeypatch.setenv("PLEPA_STYLE_MODE", "glossy")

    char = CharacterConfig(
        prefix="gyaru",
        name="Gyaru",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="blonde twin tails, red eyes",
            physique="slender",
            outfit="choker, black shirt, red ribbon",
        ),
        sdxl_positive="masterpiece, best quality BREAK 1girl, blonde twin tails, red eyes, choker, black shirt",
        sdxl_negative="choker, necklace, worst quality, low quality",
    )
    shock_pose = PoseEntry(
        code="T01",
        section="emotions",
        label="놀람",
        prompt="cowboy shot, shocked expression, wide eyes, constricted pupils, surprised",
    )
    pos, neg, is_nude = assemble_sdxl_prompt(char=char, pose=shock_pose, bg_prompt="classroom")
    assert not is_nude
    pos_low = pos.lower()
    neg_low = neg.lower()
    assert "delicate colored lineart" in pos_low
    assert "2d cute anime face" in pos_low
    assert "detailed fabric texture" in pos_low
    assert "smooth pale skin" in pos_low
    assert "realistic nose" in neg_low
    assert "pupil-less" not in neg_low
    assert "blank stare" not in neg_low
    assert "choker" not in neg_low
    assert "male hair" not in neg_low


def test_adr101_qa_headpat_3hands_and_night_color_burn():
    """ADR-101: #047 쓰다듬기(3손 허용) 및 #050 야경 Color Burn(0.35 완화) 검증."""
    from plepa_engine.qa_validator import validate_generated_image

    img = Image.new("RGB", (256, 384), color=(180, 180, 180))
    with patch("plepa_engine.qa_validator.detect_person", return_value=[((10, 10, 200, 370), "person", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_heads", return_value=[((50, 20, 150, 120), "head", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_faces", return_value=[((60, 40, 140, 120), "face", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_hands", return_value=[((10, 10, 30, 30), "hand", 0.9)] * 3), \
         patch("plepa_engine.qa_validator._compute_color_burn_ratio", return_value=0.05):
        ok, reason, metrics = validate_generated_image(
            img,
            prompt="cowboy shot, ((pov hand patting head:1.25)), blissful smiling face",
            is_solo_scene=True,
            is_two_person=False,
        )
        assert ok is True, reason
        assert metrics["hands"] == 3

    with patch("plepa_engine.qa_validator.detect_person", return_value=[((10, 10, 200, 370), "person", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_heads", return_value=[((50, 20, 150, 120), "head", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_faces", return_value=[((60, 40, 140, 120), "face", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_hands", return_value=[((10, 10, 30, 30), "hand", 0.9)] * 2), \
         patch("plepa_engine.qa_validator._compute_color_burn_ratio", return_value=0.28):
        ok, reason, _ = validate_generated_image(
            img,
            prompt="cowboy shot, city night view, glowing city lights, dark night sky",
            is_solo_scene=True,
            is_two_person=False,
        )
        assert ok is True, reason


def test_adr101_pose_db_and_events_zero_conflicts():
    """ADR-101/H2-C: sdxl_pose_database.json 및 events.json 내 prompt/prompt_female/prompt_otokonoko/negative_add 전수 계약 검증."""
    import json
    from pathlib import Path

    banned_tokens = (
        "bald",
        "faceless",
        "large thick erect penis",
        "impressive manhood",
        "impressive large manhood",
        "small penis",
        "micropenis",
    )
    clothed_romance_codes = {"060", "064", "067", "068", "069", "070", "071", "073", "074", "075", "076", "077"}

    for path in (Path("data/sdxl_pose_database.json"), Path("projects/campus/events.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for sec, items in data.items():
            if not isinstance(items, dict):
                continue
            for code, entry in items.items():
                if not isinstance(entry, dict):
                    continue
                for field in ("prompt", "prompt_female", "prompt_otokonoko", "negative_add"):
                    t = (entry.get(field) or "").lower()
                    if not t:
                        continue
                    for tok in banned_tokens:
                        assert tok not in t, f"{tok!r} in {path}:{sec}:{code}:{field}"
                    if field != "negative_add":
                        has_tight = any(k in t for k in ("tight bust portrait", "intimate close-up", "close-up bust shot"))
                        has_wide = any(k in t for k in ("cowboy shot", "full body"))
                        assert not (has_tight and has_wide), f"DUAL_SHOT in {path}:{sec}:{code}:{field}"
                        assert not ("solo" in t and "1boy" in t), f"SOLO+1BOY in {path}:{sec}:{code}:{field}"
                if code in clothed_romance_codes and entry.get("required_outfit") == "default":
                    for field in ("prompt", "prompt_female"):
                        t = (entry.get(field) or "").lower()
                        assert "completely nude" not in t, f"completely nude in default-outfit {sec}:{code}:{field}"


def test_adr101_campus_70_female_h_poses_complete_tier_and_partner_pos():
    """ADR-101 Phase H2-B: 캠퍼스 여성 H-씬 70종(060~132, 121 제외) 전수 mob_tier 및 Tier 2 partner_pos 계약 검증."""
    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    checked = 0
    for code, pose in sorted(db.items()):
        if not (code.isdigit() and 60 <= int(code) <= 132 and code != "121"):
            continue
        checked += 1
        assert pose.mob_tier in (0, 1, 2, 3), f"#{code} mob_tier 누락: {pose.mob_tier}"
        if pose.mob_tier == 2:
            assert pose.partner_pos in ("above", "below", "behind", "side_kiss", "offscreen"), (
                f"#{code} Tier 2 partner_pos 누락/무효: {pose.partner_pos}"
            )
    assert checked == 70, f"기대 여성 H-씬 70종 불일치: {checked}"


def test_h2d_patch_e_preserves_intentional_half_clothed_and_exposed_poses():
    """H2-D: #131 및 #067/#064 등 의도적 반착의/노출 포즈에서 [패치 E]가 단추 잠금/가슴 차단을 강제하지 않는지 검증."""
    char = _make_female_char()
    db_campus = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

    for code in ("067", "131"):
        pose = db_campus[code]
        pos, neg, _ = assemble_sdxl_prompt(char=char, pose=pose, bg_prompt="")
        pos_low = pos.lower()
        neg_low = neg.lower()
        assert "fully buttoned shirt" not in pos_low, f"#{code} 강제 단추 잠금 오주입: {pos}"
        assert "covered breasts" not in pos_low, f"#{code} covered breasts 오주입: {pos}"
        assert "bare breasts" not in neg_low, f"#{code} bare breasts 네거티브 오주입: {neg}"
        assert "unbuttoned shirt" not in neg_low, f"#{code} unbuttoned shirt 네거티브 오주입: {neg}"


def test_h2d_068_to_070_tier3_and_kiss_vs_side_partner_pos():
    """H2-D: #068~#070 mob_tier==3 성기 콤팩트 노출 및 #060/#061 키스 vs #108 측위 partner_pos 분리 검증."""
    char = _make_female_char()
    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

    for code in ("068", "069", "070"):
        pose = db[code]
        assert pose.mob_tier == 3
        pos, _, _ = assemble_sdxl_prompt(char=char, pose=pose, bg_prompt="bedroom")
        assert "partially visible glans, compact shaft" in pos.lower()

    for kiss_code in ("060", "061"):
        pos_kiss, _, _ = assemble_sdxl_prompt(char=char, pose=db[kiss_code], bg_prompt="bedroom")
        assert "cropped dark-haired male jaw and lips at extreme frame edge" in pos_kiss.lower()
        assert "back of dark-haired male head" not in pos_kiss.lower()

    pos_side, _, _ = assemble_sdxl_prompt(char=char, pose=db["108"], bg_prompt="bedroom")
    assert "cropped male torso and shoulder at edge" in pos_side.lower()


def test_h2d_qa_allows_head_contact_back_of_head_with_1_face():
    """H2-D: #109 커닐링구스 등 뒤통수 허용 오프스크린 씬에서 heads=2, faces=1일 때 Auto-QC 합격 검증."""
    from plepa_engine.qa_validator import validate_generated_image

    img = Image.new("RGB", (256, 384), color=(180, 180, 180))
    with patch("plepa_engine.qa_validator.detect_person", return_value=[((10, 10, 200, 370), "person", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_heads", return_value=[((50, 20, 150, 120), "head", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_faces", return_value=[((60, 40, 140, 120), "face", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_hands", return_value=[((10, 10, 30, 30), "hand", 0.9)] * 2), \
         patch("plepa_engine.qa_validator._compute_color_burn_ratio", return_value=0.05):
        ok, reason, metrics = validate_generated_image(
            img,
            prompt="cunnilingus, back of dark-haired male head between thighs, male face obscured",
            is_solo_scene=False,
            is_two_person=True,
            is_offscreen_partner=True,
        )
        assert ok is True, reason
        assert metrics["heads"] == 2
        assert metrics["faces"] == 1


def test_style_mode_legacy_balanced_and_belt_guard(monkeypatch):
    """Style A/B Test: legacy/balanced 모드 분기 및 tucked into + belt 착의 방어 검증."""
    from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry

    char = CharacterConfig(
        prefix="aya",
        name="Ayame",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="silver bob hair, deep violet eyes",
            physique="slender",
            outfit="white blouse tucked into high-waisted skirt, leather belt",
        ),
        sdxl_positive="masterpiece, best quality BREAK 1girl, silver bob hair, deep violet eyes, white blouse tucked into high-waisted skirt, leather belt",
        sdxl_nude_positive="masterpiece, best quality BREAK 1girl, silver bob hair, deep violet eyes, nude",
        sdxl_negative="worst quality, low quality",
    )
    clothed_pose = PoseEntry(
        code="000",
        section="emotions",
        label="평상",
        prompt="upper body, standing, gentle smile",
    )
    nude_pose = PoseEntry(
        code="086",
        section="h_scenes",
        label="정상위강",
        prompt="missionary, nude, looking at viewer",
        required_outfit="nude",
    )

    # Mode A: legacy (기본값)
    monkeypatch.delenv("PLEPA_STYLE_MODE", raising=False)
    pos_leg, neg_leg, _ = assemble_sdxl_prompt(char=char, pose=clothed_pose, bg_prompt="classroom")
    assert "delicate colored lineart" not in pos_leg.lower()
    assert "2d cute anime face" not in pos_leg.lower()
    assert "iridescent hair highlights" not in pos_leg.lower()
    assert "heavy dark shadows" not in neg_leg.lower()
    assert "untucked shirt, shirt over belt" in neg_leg.lower()

    # Mode B: balanced
    monkeypatch.setenv("PLEPA_STYLE_MODE", "balanced")
    pos_bal, neg_bal, _ = assemble_sdxl_prompt(char=char, pose=clothed_pose, bg_prompt="classroom")
    pos_bal_low = pos_bal.lower()
    neg_bal_low = neg_bal.lower()
    assert "delicate colored lineart" in pos_bal_low
    assert "ultra-fine linework" in pos_bal_low
    assert "soft peach blush" in pos_bal_low
    assert "2d cute anime face" not in pos_bal_low
    assert "iridescent hair highlights" not in pos_bal_low
    assert "cinematic rim lighting" not in pos_bal_low
    assert "detailed fabric texture" not in pos_bal_low
    assert "heavy dark shadows" not in neg_bal_low
    assert "realistic nose" in neg_bal_low
    assert "untucked shirt, shirt over belt" in neg_bal_low

    # 누드 포즈에서는 belt 방어 미주입
    _, neg_nude, is_nude = assemble_sdxl_prompt(char=char, pose=nude_pose, bg_prompt="bedroom")
    assert is_nude is True
    assert "untucked shirt, shirt over belt" not in neg_nude.lower()


def test_adr102_wet_h_scene_vs_daily_sweat_isolation(monkeypatch):
    """ADR-102: 일상 씬(000~055) 땀/물광 차단 vs H-씬(060+) 3중 족쇄 해제 및 수분광 부스터 검증."""
    from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry

    monkeypatch.delenv("PLEPA_STYLE_MODE", raising=False)
    char = CharacterConfig(
        prefix="aya",
        name="Ayame",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="silver bob hair, deep violet eyes",
            physique="slender",
            outfit="white blouse",
        ),
        sdxl_positive="masterpiece, best quality, glossy skin, wet skin, sweat BREAK 1girl, silver bob hair, deep violet eyes",
        sdxl_nude_positive="masterpiece, best quality, wet skin, sweat BREAK 1girl, silver bob hair, deep violet eyes",
        sdxl_negative="worst quality, low quality, oily skin, white dots, spots on skin",
    )

    daily_pose = PoseEntry(
        code="000",
        section="emotions",
        label="평상",
        prompt="upper body, standing, gentle smile",
    )
    h_pose = PoseEntry(
        code="086",
        section="h_scenes",
        label="정상위강",
        prompt="missionary, nude, looking at viewer",
        required_outfit="nude",
    )

    # 일상 씬: 땀/물광 제거 + soft shaded skin 유지 + 수분광 부스터 미주입
    pos_daily, neg_daily, _ = assemble_sdxl_prompt(char=char, pose=daily_pose, bg_prompt="none")
    pos_daily_low = pos_daily.lower()
    neg_daily_low = neg_daily.lower()
    assert "wet skin" not in pos_daily_low
    assert "glossy skin" not in pos_daily_low
    assert "moist glistening skin" not in pos_daily_low
    assert "soft shaded skin" in pos_daily_low
    assert "oily skin" in neg_daily_low

    # H-씬: 3중 족쇄 해제 (wet skin/sweat 보존, soft shaded skin 미주입, 수분광 부스터 주입, 네거티브 oily/white dots 제거)
    pos_h, neg_h, _ = assemble_sdxl_prompt(char=char, pose=h_pose, bg_prompt="none")
    pos_h_low = pos_h.lower()
    neg_h_low = neg_h.lower()
    assert "wet skin" in pos_h_low
    assert "soft shaded skin" not in pos_h_low
    assert "moist glistening skin, sweaty skin" in pos_h_low
    assert "beads of sweat rolling down face and body" in pos_h_low
    assert "specular skin highlights, dewy skin texture" in pos_h_low
    assert "hot breath, subtle steam" in pos_h_low
    assert "oily skin" not in neg_h_low
    assert "greasy skin" not in neg_h_low
    assert "shiny skin" not in neg_h_low
    assert "white dots" not in neg_h_low
    assert "spots on skin" not in neg_h_low


def test_phase_s3_h_scene_mood_lighting_and_negative_unlock(monkeypatch):
    """Phase S3: H-씬 심야 무드 라이팅 주입, 주간 조명 제거 및 캐릭터 무드 조명 차단 네거티브 해제 검증."""
    from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry

    monkeypatch.delenv("PLEPA_STYLE_MODE", raising=False)
    char = CharacterConfig(
        prefix="aya",
        name="Ayame",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="silver bob hair, deep violet eyes",
            physique="slender",
            outfit="white blouse",
        ),
        sdxl_positive="masterpiece, best quality, soft lighting BREAK 1girl, silver bob hair, deep violet eyes",
        sdxl_nude_positive="masterpiece, best quality, soft lighting BREAK 1girl, silver bob hair, deep violet eyes",
        sdxl_negative="worst quality, low quality, (warm lighting, amber lighting, purple tint, blue lighting, colored ambient lighting:1.3)",
    )
    daily_pose = PoseEntry(
        code="000",
        section="emotions",
        label="평상",
        prompt="upper body, standing, gentle smile",
    )
    h_pose = PoseEntry(
        code="086",
        section="h_scenes",
        label="정상위강",
        prompt="missionary, soft bedroom lighting, nude, looking at viewer",
        required_outfit="nude",
    )

    # 일상 씬: soft lighting 유지, 캐릭터 네거티브 warm lighting 유지, mood lighting 미주입
    pos_d, neg_d, _ = assemble_sdxl_prompt(char=char, pose=daily_pose, bg_prompt="classroom")
    assert "soft lighting" in pos_d.lower()
    assert "dimly lit, moody intimate lighting" not in pos_d.lower()
    assert "warm lighting" in neg_d.lower()
    assert "bright daylight" not in neg_d.lower()

    # H-씬: soft lighting/soft bedroom lighting 제거, 심야 무드 라이팅 주입, warm lighting 등 해제, 대낮/형광등 억제 추가
    pos_h, neg_h, _ = assemble_sdxl_prompt(char=char, pose=h_pose, bg_prompt="bedroom")
    pos_h_low = pos_h.lower()
    neg_h_low = neg_h.lower()
    assert "soft lighting" not in pos_h_low
    assert "soft bedroom lighting" not in pos_h_low
    assert "dimly lit, moody intimate lighting, low-key atmospheric lighting" in pos_h_low
    assert "deep soft shadows, dramatic chiaroscuro, warm rim light on skin" in pos_h_low
    assert "warm lighting" not in neg_h_low
    assert "amber lighting" not in neg_h_low
    assert "purple tint" not in neg_h_low
    assert "colored ambient lighting" not in neg_h_low
    assert "bright daylight, harsh studio lighting, fluorescent light" in neg_h_low


def test_phase_s4_pose_reclassification_and_qc_fixes():
    """Phase S4: 2인 스킨십 포즈(027~036, 045, 088, 091) 재분류, 182 is_solo 해제 및 키스/수유/bury_chest QA 예외 검증."""
    from plepa_engine.qa_validator import validate_generated_image

    char = _make_female_char()
    db_campus = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    db_oto = default_pose_service.load_pose_db(engine="sdxl", roster="oto")

    for c in ("027", "028", "031", "088"):
        assert db_campus[c].mob_tier == 2
        assert db_campus[c].partner_pos == "behind"
    assert db_campus["036"].mob_tier == 2
    assert db_campus["036"].partner_pos == "carry"
    pos_036, neg_036, _ = assemble_sdxl_prompt(char=char, pose=db_campus["036"], bg_prompt="classroom")
    assert "carried in male partner's arms" in pos_036.lower()
    assert "disembodied male hands" not in pos_036.lower()
    assert "male torso" not in neg_036.lower()

    assert db_campus["034"].mob_tier == 2
    assert db_campus["034"].partner_pos == "bury_chest"
    pos_034, _, _ = assemble_sdxl_prompt(char=char, pose=db_campus["034"], bg_prompt="bedroom")
    assert "back of dark-haired male head buried in her chest" in pos_034.lower()

    assert db_campus["045"].mob_tier == 0
    assert db_campus["045"].is_solo_scene is True

    assert db_campus["091"].mob_tier == 2
    assert db_campus["091"].partner_pos == "below"

    # #081, #107, #112 1boy 잔여 제거 및 #182 2인 씬 판정 검증
    for c in ("081", "107", "112"):
        assert "1boy" not in db_campus[c].prompt.lower()
    assert db_oto["182"].is_two_person is True
    assert db_oto["182"].is_solo_scene is False

    # QA Validator: 오프스크린 키스/수유 faces=2 허용 및 bury_chest heads=2 허용
    img = Image.new("RGB", (256, 384), color=(180, 180, 180))
    with patch("plepa_engine.qa_validator.detect_person", return_value=[((10, 10, 200, 370), "person", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_heads", return_value=[((50, 20, 150, 120), "head", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_faces", return_value=[((60, 40, 140, 120), "face", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_hands", return_value=[((10, 10, 30, 30), "hand", 0.9)] * 2), \
         patch("plepa_engine.qa_validator._compute_color_burn_ratio", return_value=0.05):
        ok_kiss, reason_kiss, _ = validate_generated_image(
            img,
            prompt="french kiss, cropped dark-haired male jaw and lips at extreme frame edge",
            is_solo_scene=False,
            is_two_person=True,
            is_offscreen_partner=True,
        )
        assert ok_kiss is True, reason_kiss

    with patch("plepa_engine.qa_validator.detect_person", return_value=[((10, 10, 200, 370), "person", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_heads", return_value=[((50, 20, 150, 120), "head", 0.9)] * 2), \
         patch("plepa_engine.qa_validator.detect_faces", return_value=[((60, 40, 140, 120), "face", 0.9)]), \
         patch("plepa_engine.qa_validator.detect_hands", return_value=[((10, 10, 30, 30), "hand", 0.9)] * 2), \
         patch("plepa_engine.qa_validator._compute_color_burn_ratio", return_value=0.05):
        ok_bury, reason_bury, _ = validate_generated_image(
            img,
            prompt=pos_034,
            is_solo_scene=False,
            is_two_person=True,
            is_offscreen_partner=True,
        )
        assert ok_bury is True, reason_bury
