"""
tests/test_audit_and_seed.py
새로 추가된 기능 단위 테스트:
1. sample10 포즈 세트 resolve_pose_codes 검증
2. _batch_manifest.json 시드 병합 및 보존 검증
3. AssetService.audit_roster_assets() 검증
4. AssetService.restore_from_origin() 검증
"""

import json
from pathlib import Path
from plepa_engine.models import CharacterConfig, GenerationResult, GenerationTarget
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.generation_service import GenerationParams, default_generation_service
from plepa_engine.services.pose_service import default_pose_service


def test_sample10_pose_resolution():
    """sample10 포즈 세트가 10대 대표 골든샘플 포즈 코드로 정상 해석되는지 검증."""
    db = default_pose_service.load_pose_db(engine="sdxl")
    resolved = default_pose_service.resolve_pose_codes("sample10", db)
    expected = ["000", "020", "034", "044", "048", "060", "088", "102", "130", "131"]
    assert resolved == expected, f"sample10 해석 실패: {resolved} != {expected}"


def test_audit_roster_assets():
    """campus 로스터의 audit_roster_assets가 올바른 구조로 리포트를 생성하는지 검증."""
    reports = default_asset_service.audit_roster_assets("campus")
    assert len(reports) == 6, f"campus 캐릭터 수가 6명이 아님: {len(reports)}"
    for r in reports:
        assert "prefix" in r
        assert "name" in r
        assert "present_count" in r
        assert "origin_count" in r
        assert r["present_count"] >= 100, f"{r['prefix']} 에셋 수가 100개 미만: {r['present_count']}"
        assert r["origin_count"] > 0, f"{r['prefix']}의 _origin 백업 수가 0개임"


def test_manifest_seed_merge(tmp_path: Path):
    """_batch_manifest.json 저장 시 이전 포즈 기록 및 시드가 보존되고 병합되는지 검증."""
    char = CharacterConfig.from_dict({
        "prefix": "seed_test",
        "name": "시드 테스트",
        "appearance": {"face_and_hair": "a", "physique": "b", "outfit": "c"}
    })
    params = GenerationParams(character_expr="seed_test")

    # 1차 저장: 000번 포즈 생성 (시드 12345)
    t0 = GenerationTarget(
        code="000", section="emotions", label="평상",
        assembled_prompt="prompt 0", is_nude=False,
        output_filename="seed_test_000_평상.webp", seed=12345
    )
    r0 = GenerationResult(target=t0, success=True, duration_sec=1.0)
    default_generation_service._save_batch_manifest(tmp_path, char, "default", params, [r0])

    manifest_file = tmp_path / "_batch_manifest.json"
    assert manifest_file.exists()
    with open(manifest_file, "r", encoding="utf-8") as f:
        data1 = json.load(f)
    assert len(data1["items"]) == 1
    assert data1["items"][0]["code"] == "000"
    assert data1["items"][0]["seed"] == 12345

    # 2차 저장: 002번 포즈 부분 재생성 (시드 67890) -> 000번이 유지되어야 함!
    t2 = GenerationTarget(
        code="002", section="emotions", label="기쁨",
        assembled_prompt="prompt 2", is_nude=False,
        output_filename="seed_test_002_기쁨.webp", seed=67890
    )
    r2 = GenerationResult(target=t2, success=True, duration_sec=1.2)
    default_generation_service._save_batch_manifest(tmp_path, char, "default", params, [r2])

    with open(manifest_file, "r", encoding="utf-8") as f:
        data2 = json.load(f)
    assert len(data2["items"]) == 2, f"기존 포즈가 보존되지 않음: {len(data2['items'])}"
    items_by_code = {it["code"]: it for it in data2["items"]}
    assert items_by_code["000"]["seed"] == 12345
    assert items_by_code["002"]["seed"] == 67890


def test_list_rosters_and_all_flag():
    """CharacterService.list_rosters()가 등록된 활성 로스터 목록을 정상 탐색하는지 검증."""
    from plepa_engine.services.character_service import default_character_service
    rosters = default_character_service.list_rosters()
    assert isinstance(rosters, list)
    assert len(rosters) >= 10
    for expected in ["campus", "default", "don", "hey", "maid", "man", "murim", "sns", "spy", "ykn"]:
        assert expected in rosters, f"로스터 '{expected}'가 탐색되지 않음: {rosters}"
