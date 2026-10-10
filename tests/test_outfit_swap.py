"""
tests.test_outfit_swap
다이내믹 의상 모듈화 & 테마 스왑 엔진 단위 테스트
"""

from plepa_engine.models import CharacterAppearance, CharacterConfig, LoraConfig, PoseEntry
from plepa_engine.prompt_builder import (
    DEFAULT_THEME_OUTFITS,
    assemble_flux_prompt,
    assemble_sdxl_prompt,
    get_character_outfit_prompt,
    resolve_pose_outfit_slot,
)


def create_sample_character(custom_outfits=None) -> CharacterConfig:
    appearance = CharacterAppearance(
        face_and_hair="platinum blonde long hair, blue eyes",
        physique="slender body, huge breasts",
        outfit="white collared academy shirt, navy blue blazer, pleated skirt"
    )
    return CharacterConfig(
        prefix="test_char",
        name="테스트캐릭",
        gender="female",
        appearance=appearance,
        lora=LoraConfig(),
        sdxl_positive="1girl, solo, platinum blonde long hair, blue eyes, huge breasts, white collared academy shirt, navy blue blazer, pleated skirt",
        sdxl_negative="bad hands",
        outfits=custom_outfits or {}
    )


def test_resolve_pose_outfit_slot():
    """포즈 코드 및 명시된 슬롯에 따른 의상 슬롯 판별 정확도 검증."""
    # 1. 일반 기본 포즈
    p_default = PoseEntry(code="000", section="emotions", label="평상", prompt="smile")
    assert resolve_pose_outfit_slot(p_default) == "default"

    # 2. H씬 포즈 (자동 nude)
    p_nude = PoseEntry(code="040", section="h_scenes", label="정상위", prompt="missionary")
    assert resolve_pose_outfit_slot(p_nude) == "nude"

    # 3. D 계열 (수영복)
    p_swim = PoseEntry(code="D01", section="swimsuit", label="수영복전신", prompt="full body")
    assert resolve_pose_outfit_slot(p_swim) == "swimsuit"

    # 4. F 계열 (바니걸)
    p_bunny = PoseEntry(code="F01", section="bunny", label="바니전신", prompt="standing")
    assert resolve_pose_outfit_slot(p_bunny) == "bunny"

    # 5. 명시적 required_outfit 지정 포즈
    p_custom = PoseEntry(code="200", section="combat", label="전투준비", prompt="battle pose", required_outfit="combat")
    assert resolve_pose_outfit_slot(p_custom) == "combat"


def test_sdxl_outfit_swapping_default():
    """기본 포즈 생성 시 캐릭터의 원래 교복/사복 착용 유지 검증."""
    char = create_sample_character()
    pose = PoseEntry(code="000", section="emotions", label="평상", prompt="standing, smile")

    pos, neg, is_nude = assemble_sdxl_prompt(char, pose)
    assert not is_nude
    assert "navy blue blazer" in pos
    assert "pleated skirt" in pos
    assert "micro bikini" not in pos


def test_sdxl_outfit_swapping_nude():
    """H씬 포즈 생성 시 모든 의상 태그 박멸 및 nude 주입 검증."""
    char = create_sample_character()
    pose = PoseEntry(code="040", section="h_scenes", label="정상위", prompt="missionary sex")

    pos, neg, is_nude = assemble_sdxl_prompt(char, pose)
    assert is_nude
    assert "nude, completely nude" in pos
    assert "navy blue blazer" not in pos
    assert "pleated skirt" not in pos
    assert "white collared academy shirt" not in pos


def test_sdxl_outfit_swapping_theme_fallback():
    """테마(수영복) 포즈 생성 시 기본 교복 완전 제거 및 공용 비키니 자동 스왑 검증."""
    char = create_sample_character()
    pose = PoseEntry(code="D01", section="swimsuit", label="물놀이", prompt="full body, beach")

    pos, neg, is_nude = assemble_sdxl_prompt(char, pose)
    assert not is_nude
    # 기본 교복은 증발해야 함
    assert "navy blue blazer" not in pos
    assert "pleated skirt" not in pos
    # 공용 테마 수영복이 주입되어야 함
    assert "micro bikini" in pos
    assert "halterneck bikini top" in pos
    # 캐릭터 외모는 온전히 보존되어야 함
    assert "platinum blonde long hair" in pos
    assert "huge breasts" in pos


def test_sdxl_outfit_swapping_custom_character_outfit():
    """캐릭터 JSON에 정의된 고유 맞춤 테마 의상이 최우선 스왑되는지 검증."""
    char = create_sample_character(custom_outfits={
        "swimsuit": "white ruffled bikini, side-tie bottoms"
    })
    pose = PoseEntry(code="D01", section="swimsuit", label="물놀이", prompt="full body, beach")

    pos, neg, is_nude = assemble_sdxl_prompt(char, pose)
    assert not is_nude
    # 기본 교복 및 공용 비키니 대신 캐릭터 맞춤 비키니가 장착되어야 함
    assert "navy blue blazer" not in pos
    assert "white ruffled bikini" in pos
    assert "side-tie bottoms" in pos


def test_flux_outfit_swapping():
    """FLUX 서술형 자연어 프롬프트 조립 시 다이내믹 의상 스왑 검증."""
    char = create_sample_character(custom_outfits={
        "swimsuit": "a stunning luxury gold bikini"
    })

    # 1. 기본 포즈 ➔ 기본 교복
    p_def = PoseEntry(code="000", section="emotions", label="평상", prompt="A girl standing gracefully.")
    flux_pos_def, nude_def = assemble_flux_prompt(char, p_def)
    assert not nude_def
    assert "navy blue blazer" in flux_pos_def

    # 2. 수영복 포즈 ➔ 맞춤 골드 비키니
    p_swim = PoseEntry(code="D01", section="swimsuit", label="비치", prompt="A girl enjoying the sunny beach.")
    flux_pos_swim, nude_swim = assemble_flux_prompt(char, p_swim)
    assert not nude_swim
    assert "navy blue blazer" not in flux_pos_swim
    assert "a stunning luxury gold bikini" in flux_pos_swim
