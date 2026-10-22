"""포즈별 동적 배경 주입 통합 테스트."""
import pytest
from pathlib import Path
from plepa_engine.models import PoseEntry
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import GenerationParams, GenerationService
from plepa_engine.services.pose_background_service import default_pose_bg_service
from plepa_engine.services.background_service import default_background_service
from plepa_engine.prompt_builder import assemble_sdxl_prompt


def test_campus_pose_background_mappings():
    """캠퍼스 로스터의 V3 포즈별 배경 매핑 검증."""
    assert default_pose_bg_service.get_background_for_pose("campus", "000") == "default"
    assert default_pose_bg_service.get_background_for_pose("campus", "010") == "default"
    assert default_pose_bg_service.get_background_for_pose("campus", "048") == "aya_tea"
    assert default_pose_bg_service.get_background_for_pose("campus", "049") == "har_club"
    assert default_pose_bg_service.get_background_for_pose("campus", "050") == "campus_street"
    assert default_pose_bg_service.get_background_for_pose("campus", "051") == "mai_office"
    assert default_pose_bg_service.get_background_for_pose("campus", "052") == "campus_street"
    assert default_pose_bg_service.get_background_for_pose("campus", "053") == "campus_street"
    assert default_pose_bg_service.get_background_for_pose("campus", "054") == "campus_street"
    assert default_pose_bg_service.get_background_for_pose("campus", "055") == "campus_street"
    assert default_pose_bg_service.get_background_for_pose("campus", "060") == "bedroom"
    assert default_pose_bg_service.get_background_for_pose("campus", "080") == "bedroom"


def test_assembled_prompt_contains_dynamic_background():
    """assemble_sdxl_prompt 호출 시 포즈별로 매핑된 배경 태그가 프롬프트에 정상 주입되는지 검증."""
    res = default_character_service.find_character("aya", roster="campus")
    assert res is not None
    char = res[0]
    
    # 048 (캠퍼스 카페/테이블휴식) -> aya_tea
    bg_key_048 = default_pose_bg_service.get_background_for_pose("campus", "048")
    assert bg_key_048 == "aya_tea"
    bg_prompt_048 = default_background_service.get_preset("campus", bg_key_048)
    pose_048 = PoseEntry(
        code="048",
        label="테이블휴식",
        prompt="1girl, solo, sitting at table, holding mug, relaxed posture, looking at viewer",
        section="poses"
    )
    pos_048, _, _ = assemble_sdxl_prompt(char, pose_048, bg_prompt=bg_prompt_048)
    assert "modern minimalist campus cafe terrace" in pos_048

    # 050 (캠퍼스 벤치) -> campus_street
    bg_key_050 = default_pose_bg_service.get_background_for_pose("campus", "050")
    assert bg_key_050 == "campus_street"
    bg_prompt_050 = default_background_service.get_preset("campus", bg_key_050)
    pose_050 = PoseEntry(
        code="050",
        label="캠퍼스 벤치",
        prompt="1girl, solo, sitting on outdoor bench, relaxed pose, looking at viewer",
        section="poses"
    )
    pos_050, _, _ = assemble_sdxl_prompt(char, pose_050, bg_prompt=bg_prompt_050)
    assert "outdoor university campus walkway" in pos_050


def test_generation_service_dynamic_background_batch():
    """GenerationService에서 mock 배치 실행 시 포즈별 동적 배경이 적용되어 정상 완료되는지 검증."""
    svc = GenerationService()
    params = GenerationParams(
        character_expr="aya",
        pose_expr="000,048,050",
        roster="campus",
        mock=True,
        censor=False,
        no_ref=True,
    )
    results = svc.run_batch(params, quiet=True)
    assert len(results) == 3
    assert all(r.success for r in results)
