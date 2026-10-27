"""
tests/test_pose_background_integration.py
포즈별 동적 배경 매핑(pose_background_mapping.json) 및 배경 프리셋(background.json) 간의
무결성 계약과 프롬프트 동적 주입을 하드코딩 없이 검증하는 통합 테스트.
"""

import json
from pathlib import Path
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.models import PoseEntry
from plepa_engine.prompt_builder import assemble_sdxl_prompt
from plepa_engine.services.background_service import default_background_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import GenerationParams, GenerationService
from plepa_engine.services.pose_background_service import default_pose_bg_service


def test_campus_pose_background_mappings_contract():
    """
    캠퍼스 로스터의 pose_background_mapping.json에 정의된 모든 매핑이
    서비스 조회 결과와 1:1로 일치하고, 매핑된 모든 배경 키가 background.json에 실존하는지 동적 계약 검증.
    """
    mapping_file = PROJECTS_DIR / "campus" / "pose_background_mapping.json"
    assert mapping_file.is_file(), "projects/campus/pose_background_mapping.json 파일이 존재해야 합니다."

    with open(mapping_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    mappings = raw_data.get("pose_mappings") or raw_data.get("mappings") or raw_data
    valid_bg_presets = default_background_service.get_backgrounds("campus", engine="sdxl")

    checked = 0
    for code, expected_bg_key in mappings.items():
        if code.startswith("_") or not isinstance(expected_bg_key, str):
            continue
        actual_bg_key = default_pose_bg_service.get_background_for_pose("campus", code)
        assert actual_bg_key == expected_bg_key, (
            f"포즈 {code}의 배경 매핑 불일치: 기대={expected_bg_key}, 실제={actual_bg_key}"
        )
        assert actual_bg_key in valid_bg_presets, (
            f"포즈 {code}에 매핑된 배경 프리셋 '{actual_bg_key}'가 background.json에 존재하지 않습니다."
        )
        checked += 1

    assert checked > 0, "검증된 포즈 배경 매핑이 최소 1개 이상이어야 합니다."


def test_assembled_prompt_contains_dynamic_background():
    """assemble_sdxl_prompt 호출 시 포즈별로 매핑된 배경 프리셋의 프롬프트가 정상 주입되는지 동적 검증."""
    chars = default_character_service.list_characters(roster="campus")
    assert len(chars) > 0
    char = chars[0][1]

    # default가 아닌 커스텀 배경이 매핑된 포즈 코드들을 동적으로 수집하여 검증
    mapping_file = PROJECTS_DIR / "campus" / "pose_background_mapping.json"
    with open(mapping_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    mappings = raw_data.get("pose_mappings") or raw_data.get("mappings") or raw_data

    custom_mapped_codes = [
        c for c, bg in mappings.items()
        if not c.startswith("_") and isinstance(bg, str) and bg not in ("default", "none")
    ][:3]
    assert len(custom_mapped_codes) > 0

    for code in custom_mapped_codes:
        bg_key = default_pose_bg_service.get_background_for_pose("campus", code)
        bg_prompt = default_background_service.get_preset("campus", bg_key)
        assert bg_prompt, f"배경 프리셋 '{bg_key}'의 프롬프트가 비어있지 않아야 합니다."

        pose = PoseEntry(
            code=code,
            label="테스트포즈",
            prompt="1girl, solo, sitting, relaxed posture, looking at viewer",
            section="poses",
        )
        pos, _, _ = assemble_sdxl_prompt(char, pose, bg_prompt=bg_prompt)

        # bg_prompt의 첫 번째 핵심 태그가 조립된 프롬프트에 정상 포함되었는지 동적 확인
        first_tag = bg_prompt.split(",")[0].strip().strip("()")
        assert first_tag in pos, f"배경 프리셋 '{bg_key}'의 핵심 태그 '{first_tag}'가 조립 프롬프트에 포함되어야 합니다."


def test_generation_service_dynamic_background_batch():
    """GenerationService에서 mock 배치 실행 시 포즈별 동적 배경이 적용되어 정상 완료되는지 검증."""
    chars = default_character_service.list_characters(roster="campus")
    first_prefix = chars[0][1].prefix

    svc = GenerationService()
    params = GenerationParams(
        character_expr=first_prefix,
        pose_expr="000,048,050",
        roster="campus",
        mock=True,
        censor=False,
        no_ref=True,
    )
    results = svc.run_batch(params, quiet=True)
    assert len(results) == 3
    assert all(r.success for r in results)
