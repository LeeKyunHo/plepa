"""
tests/test_quality_tags.py
checkpoint_profiles.json에 등록된 모든 체크포인트 프로필의 quality_tags가
assemble_sdxl_prompt 호출 시 동적으로 정확히 주입되는지 검증하는 계약 테스트.
"""

from plepa_engine.checkpoint_service import CheckpointService, get_profile_for_checkpoint
from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import assemble_sdxl_prompt


def test_quality_tag_injection():
    """등록된 모든 체크포인트 프로필 및 폴백 모델의 품질 태그가 프롬프트에 동적으로 주입되는지 검증."""
    char = CharacterConfig.from_dict({
        "prefix": "test",
        "name": "테스트 캐릭터",
        "appearance": {
            "outfit": "blue dress",
            "face_and_hair": "long black hair, brown eyes",
            "physique": "slim body",
        },
    })

    pose = PoseEntry(
        code="T00",
        label="평상",
        section="emotions",
        prompt="1girl, standing, smile",
    )

    service = CheckpointService()
    profiles = service.list_all_profiles()
    assert len(profiles) > 0, "최소 1개 이상의 체크포인트 프로필이 존재해야 합니다."

    # 1. 등록된 모든 프로필의 매칭 패턴을 사용하여 동적 검증
    for profile in profiles:
        if not profile.match_patterns:
            continue
        sample_ckpt = f"{profile.match_patterns[0]}_test_model.safetensors"
        resolved_profile = get_profile_for_checkpoint(sample_ckpt)
        expected_tags = resolved_profile.quality_positive

        pos_prompt, _, _ = assemble_sdxl_prompt(
            char,
            pose,
            bg_prompt="simple background",
            checkpoint_name=sample_ckpt,
        )
        for tag in [t.strip() for t in expected_tags.split(",") if t.strip()]:
            assert tag in pos_prompt, (
                f"체크포인트 '{sample_ckpt}' 조립 프롬프트에 프로필 품질 태그 '{tag}'가 포함되어야 합니다."
            )

    # 2. 미등록(Unknown) 모델 폴백 검증
    unknown_ckpt = "completely_unknown_custom_model.safetensors"
    fallback_profile = get_profile_for_checkpoint(unknown_ckpt)
    pos_fallback, _, _ = assemble_sdxl_prompt(
        char,
        pose,
        bg_prompt="simple background",
        checkpoint_name=unknown_ckpt,
    )
    for tag in [t.strip() for t in fallback_profile.quality_positive.split(",") if t.strip()]:
        assert tag in pos_fallback, f"폴백 품질 태그 '{tag}'가 프롬프트에 포함되어야 합니다."
