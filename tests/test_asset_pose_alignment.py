"""
tests/test_asset_pose_alignment.py
에셋 이미지와 포즈 DB(및 로스터 events.json) 간의 엄격한 정합성 및 무결성 검증 테스트:
1. 포즈 DB에 존재하지 않는 미식별/고아 파일(Orphan Asset) 0건 검증
2. 동일 포즈 코드 중복 파일(Duplicate Asset) 0건 검증
3. 파일명 규격 준수 (Non-standard filename) 검증
4. 포즈 DB 공식 라벨 일치율(Label Alignment) 검증 및 불일치 감지
5. 미생성/누락 포즈(Missing Poses) 카탈로그 리포팅
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
import pytest

from plepa_engine.config import PROJECTS_DIR
from scripts.audit_asset_alignment import load_full_pose_catalog, normalize_label_for_comparison, audit_character_alignment


@pytest.fixture(scope="module")
def campus_characters():
    return ["aya", "har", "mai", "yur", "shz", "kao"]


@pytest.fixture(scope="module")
def ykn_characters():
    return ["hay", "ser", "sia", "yua"]


class TestAssetPoseAlignment:
    """에셋 파일과 포즈 데이터베이스 간의 무결성 및 정합성 테스트 스위트."""

    def test_no_orphan_files_in_campus(self, campus_characters):
        """캠퍼스 로스터에 DB 및 이벤트에 정의되지 않은 미식별/고아 코드가 없는지 검증."""
        all_orphans = []
        for prefix in campus_characters:
            rep = audit_character_alignment("campus", prefix, gender="female")
            for o in rep["orphan_files"]:
                all_orphans.append(f"[{prefix}] {o['filename']} ({o['reason']})")
        assert len(all_orphans) == 0, f"미식별/고아 에셋 파일 감지:\n" + "\n".join(all_orphans)

    def test_no_orphan_files_in_ykn(self, ykn_characters):
        """YKN 로스터에 DB 및 이벤트에 정의되지 않은 미식별/고아 코드가 없는지 검증."""
        all_orphans = []
        for prefix in ykn_characters:
            rep = audit_character_alignment("ykn", prefix, gender="female")
            for o in rep["orphan_files"]:
                all_orphans.append(f"[{prefix}] {o['filename']} ({o['reason']})")
        assert len(all_orphans) == 0, f"미식별/고아 에셋 파일 감지:\n" + "\n".join(all_orphans)

    def test_no_duplicate_files_in_rosters(self, campus_characters, ykn_characters):
        """동일 포즈 코드에 파일이 2개 이상 존재하는 중복 파일이 없는지 검증."""
        duplicates = []
        for roster, chars in [("campus", campus_characters), ("ykn", ykn_characters)]:
            for prefix in chars:
                rep = audit_character_alignment(roster, prefix, gender="female")
                for d in rep["duplicates"]:
                    duplicates.append(f"[{roster}/{prefix}] 코드 {d['code']}: {', '.join(d['files'])}")
        assert len(duplicates) == 0, f"동일 코드 중복 파일 감지:\n" + "\n".join(duplicates)

    def test_label_alignment_integrity_ykn(self, ykn_characters):
        """YKN 로스터 에셋의 라벨이 포즈 DB의 공식 라벨과 일치하는지 검증."""
        mismatches = []
        for prefix in ykn_characters:
            rep = audit_character_alignment("ykn", prefix, gender="female")
            for m in rep["mismatches"]:
                mismatches.append(f"[{prefix}] 코드 {m['code']} [{m['section']}]: 현재 '{m['actual_label']}' != DB표준 '{m['expected_label']}' ({m['filename']})")
        assert len(mismatches) == 0, f"YKN 포즈 라벨 불일치 감지:\n" + "\n".join(mismatches)

    def test_label_alignment_integrity_campus(self, campus_characters):
        """캠퍼스 로스터 에셋의 라벨 일치성 검증 (신규 슬롯 교체 대기 항목 분리 추적)."""
        # 095번은 구버전(파이즈리약) -> 신규(웨딩섹스) 개편 슬롯으로, 재양산 전까지 과도기 항목으로 식별
        PENDING_UPGRADE_CODES = {"095"}
        
        strict_mismatches = []
        pending_upgrades = []
        
        for prefix in campus_characters:
            rep = audit_character_alignment("campus", prefix, gender="female")
            for m in rep["mismatches"]:
                if m["code"] in PENDING_UPGRADE_CODES:
                    pending_upgrades.append(f"[{prefix}] 코드 {m['code']}: 현재 '{m['actual_label']}' ➔ 향후 재양산 목표 '{m['expected_label']}'")
                else:
                    strict_mismatches.append(f"[{prefix}] 코드 {m['code']} [{m['section']}]: 현재 '{m['actual_label']}' != DB표준 '{m['expected_label']}' ({m['filename']})")
                    
        assert len(strict_mismatches) == 0, f"캠퍼스 불일치 라벨 감지 (즉시 교정 필요):\n" + "\n".join(strict_mismatches)
        # 095번 교체 대기 현황은 정상 추적됨
        assert len(pending_upgrades) == len(campus_characters), "095번 웨딩섹스 교체 대기 항목이 6명 전원 정상 추적되어야 합니다."

    def test_missing_poses_catalog_summary(self, campus_characters, ykn_characters):
        """로스터별 기대 포즈 카탈로그 대비 누락 현황을 안전하게 집계 및 단언."""
        for roster, chars, expected_min_poses in [("campus", campus_characters, 100), ("ykn", ykn_characters, 110)]:
            for prefix in chars:
                rep = audit_character_alignment(roster, prefix, gender="female")
                assert rep["total_files"] >= expected_min_poses, (
                    f"[{roster}/{prefix}] 생성된 에셋 수({rep['total_files']}장)가 최소 기대치({expected_min_poses}장)에 미달합니다."
                )
