"""
tests/test_asset_pose_alignment.py
에셋 이미지와 포즈 DB(및 로스터 events.json, pose_overrides.json) 간의 엄격한 정합성 및 무결성 검증 테스트:
1. 포즈 DB에 존재하지 않는 미식별/고아 파일(Orphan Asset) 0건 검증
2. 동일 포즈 코드 중복 파일(Duplicate Asset) 0건 검증
3. DB 공식 표준 라벨 및 DB 선언 레거시 별칭과의 일치성 검증 (하드코딩 0개)
4. 포즈 DB 수정 시 검수 항목이 실시간으로 100% 동적 연동되는지 계약(Contract) 검증
5. 미생성/누락 포즈(Missing Poses) 동적 카탈로그 집계 검증
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, List
import pytest

from plepa_engine.config import PROJECTS_DIR, SDXL_POSE_DB_PATH
from scripts.audit_asset_alignment import (
    audit_character_alignment,
    load_full_pose_catalog,
    normalize_label_for_comparison,
)


def get_roster_character_prefixes(roster: str) -> List[str]:
    """로스터 캐릭터 폴더에서 실존하는 캐릭터 prefix 목록을 동적으로 스캔."""
    char_dir = PROJECTS_DIR / roster / "characters"
    if not char_dir.is_dir():
        return []
    return sorted([f.stem for f in char_dir.glob("*.json")])


def get_character_gender(roster: str, prefix: str) -> str:
    """캐릭터 JSON에서 성별 정보를 동적으로 조회."""
    char_file = PROJECTS_DIR / roster / "characters" / f"{prefix}.json"
    if char_file.is_file():
        try:
            with open(char_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gender") or data.get("default_mode") or "female"
        except Exception:
            pass
    return "female"


@pytest.fixture(scope="module")
def campus_characters():
    chars = get_roster_character_prefixes("campus")
    assert len(chars) > 0, "캠퍼스 캐릭터가 최소 1명 이상 감지되어야 합니다."
    return chars


@pytest.fixture(scope="module")
def ykn_characters():
    chars = get_roster_character_prefixes("ykn")
    assert len(chars) > 0, "YKN 캐릭터가 최소 1명 이상 감지되어야 합니다."
    return chars


class TestAssetPoseAlignment:
    """에셋 파일과 포즈 데이터베이스 간의 동적 무결성 및 정합성 테스트 스위트."""

    def test_no_orphan_files_in_rosters(self, campus_characters, ykn_characters):
        """DB 및 이벤트에 정의되지 않은 미식별/고아 코드가 모든 로스터에 0건인지 검증."""
        all_orphans = []
        for roster, chars in [("campus", campus_characters), ("ykn", ykn_characters)]:
            for prefix in chars:
                gender = get_character_gender(roster, prefix)
                rep = audit_character_alignment(roster, prefix, gender=gender)
                for o in rep["orphan_files"]:
                    all_orphans.append(f"[{roster}/{prefix}] {o['filename']} ({o['reason']})")
        assert len(all_orphans) == 0, "미식별/고아 에셋 파일 감지:\n" + "\n".join(all_orphans)

    def test_no_duplicate_files_in_rosters(self, campus_characters, ykn_characters):
        """동일 포즈 코드에 파일이 2개 이상 존재하는 중복 파일이 0건인지 검증."""
        duplicates = []
        for roster, chars in [("campus", campus_characters), ("ykn", ykn_characters)]:
            for prefix in chars:
                gender = get_character_gender(roster, prefix)
                rep = audit_character_alignment(roster, prefix, gender=gender)
                for d in rep["duplicates"]:
                    duplicates.append(f"[{roster}/{prefix}] 코드 {d['code']}: {', '.join(d['files'])}")
        assert len(duplicates) == 0, "동일 코드 중복 파일 감지:\n" + "\n".join(duplicates)

    def test_strict_label_alignment_integrity(self, campus_characters, ykn_characters):
        """
        DB 공식 라벨 및 DB 메타데이터(legacy_labels / aliases)에 정의되지 않은
        순수 라벨 불일치 오류(mismatches)가 0건인지 전수 검증 (하드코딩 없이 100% 동적 판정).
        """
        all_mismatches = []
        for roster, chars in [("campus", campus_characters), ("ykn", ykn_characters)]:
            for prefix in chars:
                gender = get_character_gender(roster, prefix)
                rep = audit_character_alignment(roster, prefix, gender=gender)
                for m in rep["mismatches"]:
                    all_mismatches.append(
                        f"[{roster}/{prefix}] 코드 {m['code']} [{m['section']}]: 현재='{m['actual_label']}' != DB표준='{m['expected_label']}' ({m['filename']})"
                    )
        assert len(all_mismatches) == 0, "순수 라벨 불일치 오류 파일 감지 (DB에 없는 임의 라벨):\n" + "\n".join(all_mismatches)

    def test_legacy_compatible_slots_are_declared_in_db(self, campus_characters):
        """
        과도기 호환 슬롯(예: 095 웨딩섹스 슬롯의 기존 파이즈리약 에셋)은
        테스트 코드의 하드코딩이 아니라 오직 DB 자체의 legacy_labels/aliases 선언에 의해서만
        정상적으로 과도기 수용되고 있는지 계약(Contract) 검증.
        """
        for prefix in campus_characters:
            gender = get_character_gender("campus", prefix)
            rep = audit_character_alignment("campus", prefix, gender=gender)
            for leg in rep["legacy_compatible"]:
                catalog = load_full_pose_catalog("campus", gender=gender)
                code = leg["code"]
                assert code in catalog, f"레거시 호환 코드가 DB 카탈로그에 존재해야 합니다: {code}"
                expected_aliases = catalog[code].get("aliases", [])
                norm_actual = normalize_label_for_comparison(leg["actual_label"])
                norm_aliases = [normalize_label_for_comparison(a) for a in expected_aliases]
                assert norm_actual in norm_aliases, (
                    f"에셋 라벨 '{leg['actual_label']}'이 DB 선언 별칭 {expected_aliases}에 명시적으로 등록되어 있어야 합니다."
                )

    def test_dynamic_pose_db_sync_contract(self):
        """
        포즈 데이터베이스 내용이 동적으로 변경(새 포즈 추가, 라벨 변경, 삭제 등)되었을 때
        검수기(audit_asset_alignment)가 코드 수정 없이 100% 실시간으로 연동되는지 계약 검증.
        """
        # 1. 원본 DB 카탈로그 기준
        original_catalog = load_full_pose_catalog("campus", gender="female")
        assert "000" in original_catalog
        original_label_000 = original_catalog["000"]["label"]

        # 2. 포즈 DB에 신규 포즈(999) 및 기존 라벨 변경이 발생했다고 가정한 가상 DB 생성
        with open(SDXL_POSE_DB_PATH, "r", encoding="utf-8") as f:
            mock_db = json.load(f)

        mock_db["emotions"]["999"] = {
            "label": "동적테스트표정",
            "prompt": "dynamic test expression",
            "description": "DB 변경 연동 실시간 검증용"
        }
        mock_db["emotions"]["000"]["label"] = "평상_수정된라벨"

        # 3. 변경된 DB를 주입하여 카탈로그 생성
        updated_catalog = load_full_pose_catalog("campus", gender="female", custom_db_data=mock_db)

        # 4. 검증: 코드 수정 없이 새 포즈 999가 즉시 포함되고, 000의 라벨이 즉시 반영되어야 함
        assert "999" in updated_catalog, "포즈 DB에 추가된 999번 포즈가 검수 카탈로그에 즉시 반영되어야 합니다."
        assert updated_catalog["999"]["label"] == "동적테스트표정"
        assert updated_catalog["000"]["label"] == "평상_수정된라벨"
        assert updated_catalog["000"]["label"] != original_label_000

        # 5. 캐릭터 검수 시 999번이 미생성 누락 포즈로 즉시 자동 적발되는지 검증
        rep = audit_character_alignment(
            roster="campus",
            prefix="aya",
            gender="female",
            catalog=updated_catalog
        )
        missing_codes = [mp["code"] for mp in rep["missing_poses"]]
        assert "999" in missing_codes, "DB에 신규 추가된 999번 포즈가 누락 포즈 검수 항목에 실시간 연동되어야 합니다."
        
        # 000번 라벨이 바뀌었으므로 파일명(aya_000_평상)과 불일치(mismatch)로 즉시 자동 감지되는지 검증
        mismatched_codes = [m["code"] for m in rep["mismatches"]]
        assert "000" in mismatched_codes, "DB 라벨 변경 시 검수기가 파일명 불일치를 실시간 자동 감지해야 합니다."

    def test_missing_poses_catalog_integrity(self, campus_characters, ykn_characters):
        """
        기대 포즈 카탈로그와 실제 파일 간의 누락 현황이
        전체 카탈로그 개수 = 완벽일치 + 레거시호환 + 불일치 + 누락합계 공식과 100% 부합하는지 수학적 무결성 검증.
        """
        for roster, chars in [("campus", campus_characters), ("ykn", ykn_characters)]:
            for prefix in chars:
                gender = get_character_gender(roster, prefix)
                catalog = load_full_pose_catalog(roster, gender=gender)
                rep = audit_character_alignment(roster, prefix, gender=gender, catalog=catalog)

                total_accounted = (
                    rep["matched_count"]
                    + len(rep["legacy_compatible"])
                    + len(rep["mismatches"])
                    + len(rep["missing_poses"])
                )
                assert total_accounted == len(catalog), (
                    f"[{roster}/{prefix}] 포즈 카탈로그 수({len(catalog)})와 에셋 분류 합계({total_accounted})가 완벽히 일치해야 합니다."
                )
