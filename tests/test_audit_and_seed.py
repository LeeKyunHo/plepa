"""
tests/test_audit_and_seed.py
1. sample10 포즈 세트 동적 해석 계약 검증
2. _batch_manifest.json 시드 병합 및 보존 검증
3. AssetService.audit_roster_assets() 동적 캐릭터 수 및 에셋 검증
4. CharacterService.list_rosters() 동적 디렉토리 탐색 계약 검증
"""

import json
from pathlib import Path
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.models import CharacterConfig, GenerationResult, GenerationTarget
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import GenerationParams, default_generation_service
from plepa_engine.services.pose_service import default_pose_service


def test_sample10_pose_resolution():
    """sample10 포즈 세트가 pose_sets.json에 정의된 코드들과 1:1로 일치하게 해석되고 DB에 모두 존재하는지 동적 검증."""
    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    pose_sets = default_pose_service.load_pose_sets()
    sample10 = next((s for s in pose_sets if s.id == "sample10"), None)
    assert sample10 is not None, "pose_sets.json에 sample10 세트가 존재해야 합니다."

    resolved = default_pose_service.resolve_pose_codes("sample10", db)
    expected = [c for c in sample10.codes if c in db]
    assert resolved == expected, f"sample10 해석 불일치: {resolved} != {expected}"
    assert len(resolved) == len(sample10.codes), "sample10의 모든 코드가 DB에 유효하게 존재해야 합니다."


def test_audit_roster_assets():
    """campus 로스터의 audit_roster_assets가 등록된 캐릭터 수와 정확히 일치하는 리포트를 생성하는지 동적 검증."""
    campus_chars = default_character_service.list_characters("campus")
    reports = default_asset_service.audit_roster_assets("campus")
    assert len(reports) == len(campus_chars), (
        f"리포트 수({len(reports)})가 실제 등록된 캐릭터 수({len(campus_chars)})와 일치해야 합니다."
    )
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

    t0 = GenerationTarget(
        code="T00", section="emotions", label="평상",
        assembled_prompt="prompt 0", is_nude=False,
        output_filename="seed_test_T00_평상.webp", seed=12345
    )
    r0 = GenerationResult(target=t0, success=True, duration_sec=1.0)
    default_generation_service._save_batch_manifest(tmp_path, char, "default", params, [r0])

    manifest_file = tmp_path / "_batch_manifest.json"
    assert manifest_file.exists()
    with open(manifest_file, "r", encoding="utf-8") as f:
        data1 = json.load(f)
    assert len(data1["items"]) == 1
    assert data1["items"][0]["code"] == "T00"
    assert data1["items"][0]["seed"] == 12345

    t2 = GenerationTarget(
        code="T02", section="emotions", label="기쁨",
        assembled_prompt="prompt 2", is_nude=False,
        output_filename="seed_test_T02_기쁨.webp", seed=67890
    )
    r2 = GenerationResult(target=t2, success=True, duration_sec=1.2)
    default_generation_service._save_batch_manifest(tmp_path, char, "default", params, [r2])

    with open(manifest_file, "r", encoding="utf-8") as f:
        data2 = json.load(f)
    assert len(data2["items"]) == 2, f"기존 포즈가 보존되지 않음: {len(data2['items'])}"
    items_by_code = {it["code"]: it for it in data2["items"]}
    assert items_by_code["T00"]["seed"] == 12345
    assert items_by_code["T02"]["seed"] == 67890


def test_list_rosters_and_all_flag():
    """CharacterService.list_rosters()가 실제 디스크의 활성 로스터 디렉토리들을 누락 없이 동적 탐색하는지 검증."""
    rosters = default_character_service.list_rosters()
    assert isinstance(rosters, list)

    expected_dirs = [
        d.name for d in sorted(PROJECTS_DIR.iterdir())
        if d.is_dir() and (d / "characters").is_dir() and any((d / "characters").glob("*.json"))
    ]
    for exp in expected_dirs:
        assert exp in rosters, f"활성 로스터 '{exp}'가 list_rosters()에서 누락되었습니다."
