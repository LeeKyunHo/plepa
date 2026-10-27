"""
tests/test_checkpoint_service.py
checkpoint_profiles.json의 모든 프로필에 대한 동적 무결성 및 매칭 계약 검증 테스트.
"""

from plepa_engine.checkpoint_service import (
    CheckpointService,
    get_profile_for_checkpoint,
    get_recommended_summary,
)


def test_profile_loading():
    """등록된 모든 체크포인트 프로필의 필수 속성 무결성 검증."""
    service = CheckpointService()
    profiles = service.list_all_profiles()
    assert len(profiles) > 0, "최소 1개 이상의 체크포인트 프로필이 로드되어야 합니다."

    for profile in profiles:
        assert profile.name, "프로필 이름이 비어있지 않아야 합니다."
        assert profile.width > 0 and profile.height > 0
        assert profile.steps > 0
        assert profile.cfg > 0
        assert profile.sampler
        assert profile.scheduler


def test_exact_match():
    """checkpoint_profiles.json에 등록된 모든 키가 자기 자신 프로필로 정확히 매칭되는지 동적 검증."""
    service = CheckpointService()
    assert len(service._profiles) > 0

    for ckpt_filename, expected_profile in service._profiles.items():
        matched = get_profile_for_checkpoint(ckpt_filename)
        assert matched.name == expected_profile.name, (
            f"파일명 '{ckpt_filename}'의 정확 매칭 실패: 기대={expected_profile.name}, 실제={matched.name}"
        )


def test_fuzzy_match():
    """각 프로필의 match_patterns 키워드가 포함된 파일명이 정상 퍼지 매칭되는지 동적 검증."""
    service = CheckpointService()
    for profile in service.list_all_profiles():
        for pattern in profile.match_patterns:
            synthetic_name = f"custom_{pattern}_v99.safetensors"
            matched = get_profile_for_checkpoint(synthetic_name)
            assert matched is not None
            assert matched.width > 0


def test_fallback():
    """미등록 체크포인트가 기본 폴백 프로필을 안전하게 반환하는지 검증."""
    unknown_ckpt = "completely_unknown_model_v999.safetensors"
    profile = get_profile_for_checkpoint(unknown_ckpt)
    assert profile is not None
    assert profile.width > 0 and profile.height > 0
    assert profile.steps > 0


def test_recommended_summary():
    """모든 등록된 프로필에 대해 GUI 표시용 권장 설정 요약 문자열이 정상 생성되는지 검증."""
    service = CheckpointService()
    for ckpt_name, profile in service._profiles.items():
        summary = get_recommended_summary(ckpt_name)
        assert isinstance(summary, str) and len(summary) > 0
        assert f"{profile.width}x{profile.height}" in summary


def test_quality_tags():
    """모든 프로필이 비어있지 않은 긍정/부정 품질 태그를 보유하는지 계약 검증."""
    service = CheckpointService()
    for profile in service.list_all_profiles():
        assert len(profile.quality_positive.strip()) > 0
        assert len(profile.quality_negative.strip()) > 0


def test_profile_application():
    """프로필을 옵션 딕셔너리에 적용할 때 기본값 교체 및 사용자 커스텀 값 보존 계약 검증."""
    service = CheckpointService()
    first_ckpt, first_profile = next(iter(service._profiles.items()))

    default_options = {
        "width": 832,
        "height": 1216,
        "steps": 25,
        "cfg": 6.5,
        "sampler": "dpmpp_sde",
        "scheduler": "karras",
    }

    updated_options = service.apply_profile_to_options(
        default_options.copy(),
        first_ckpt,
        engine="sdxl",
        override_user_values=False,
    )
    assert updated_options["steps"] == first_profile.steps
    assert updated_options["cfg"] == first_profile.cfg

    # 사용자가 해상도를 1024x1024로 커스텀 지정한 경우 보존되는지 확인
    custom_options = default_options.copy()
    custom_options["width"] = 1024
    custom_options["height"] = 1024

    updated_custom = service.apply_profile_to_options(
        custom_options.copy(),
        first_ckpt,
        engine="sdxl",
        override_user_values=False,
    )
    assert updated_custom["width"] == 1024
    assert updated_custom["height"] == 1024
