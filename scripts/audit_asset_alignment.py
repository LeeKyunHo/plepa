"""
scripts/audit_asset_alignment.py
기존 에셋 이미지들과 포즈 DB(및 로스터 events.json, pose_overrides.json) 간의 정합성을 전수 검사하는 도구:
1. 라벨 불일치(Label Mismatch) 검사
2. DB 메타데이터 기반 레거시/과도기 호환 에셋(Legacy Compatible) 자동 분류
3. 비어있는(누락된) 포즈 검사 (Missing Poses)
4. 포즈 DB에 없는데 생성되어 있는 미식별/고아 에셋 검사 (Orphan Assets)
5. 동일 코드 중복 파일 검사 (Duplicate Assets)
6. --fix 옵션: DB 공식 라벨에 맞춰 파일명을 자동 안전 동기화 (2-Pass Safe Rename)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from plepa_engine.config import PROJECTS_DIR, SDXL_POSE_DB_PATH
from scripts.audit_alignment_helpers import (
    FEMALE_ONLY_SECTIONS,
    OTOKONOKO_SECTIONS,
    collect_core_catalog,
    evaluate_code_alignment,
    execute_safe_rename as _execute_safe_rename,
    load_deprecated_poses,
    merge_override_catalog,
    normalize_label_for_comparison,
    print_char_alignment_summary,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AssetAlignmentAuditor")


def load_full_pose_catalog(
    roster: str,
    gender: str = "female",
    custom_db_data: Optional[Dict[str, Any]] = None,
    custom_roster_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """코어 포즈 DB와 로스터 오버라이드·이벤트를 병합하여 기대 포즈 카탈로그를 실시간 생성합니다."""
    is_otokonoko = (gender or "").lower().strip() == "otokonoko"

    if custom_db_data is not None:
        core_db = custom_db_data
    elif SDXL_POSE_DB_PATH.exists():
        core_db = json.loads(SDXL_POSE_DB_PATH.read_text(encoding="utf-8"))
    else:
        core_db = {}

    catalog = collect_core_catalog(core_db, roster, is_otokonoko)

    r_dir = custom_roster_dir or (PROJECTS_DIR / roster)
    if r_dir.is_dir():
        for ov_name in ("pose_overrides.json", "events.json", "custom_poses.json"):
            merge_override_catalog(catalog, r_dir / ov_name, is_otokonoko)
    return catalog


def audit_character_alignment(
    roster: str,
    prefix: str,
    gender: str = "female",
    auto_fix: bool = False,
    catalog: Optional[Dict[str, Dict[str, Any]]] = None,
    custom_roster_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """한 캐릭터 폴더의 에셋과 포즈 DB의 일치성을 전수 점검."""
    base_roster_dir = custom_roster_dir or (PROJECTS_DIR / roster)
    char_dir = base_roster_dir / "assets" / prefix
    origin_dir = base_roster_dir / "assets" / f"{prefix}_origin"

    if catalog is None:
        catalog = load_full_pose_catalog(roster, gender=gender, custom_roster_dir=custom_roster_dir)

    report: Dict[str, Any] = {
        "roster": roster,
        "prefix": prefix,
        "gender": gender,
        "total_files": 0,
        "total_catalog_poses": len(catalog),
        "matched_count": 0,
        "legacy_compatible": [],
        "mismatches": [],
        "missing_poses": [],
        "orphan_files": [],
        "duplicates": [],
        "fixed_files": [],
    }

    if not char_dir.is_dir():
        logger.warning(f"캐릭터 에셋 폴더 없음: {char_dir}")
        return report

    pattern = re.compile(rf"^{re.escape(prefix)}_([A-Za-z0-9]+)(?:_(.*?))?(?:_censored)?\.(webp|png|jpg)$")
    files_by_code: Dict[str, List[Tuple[Path, str]]] = {}
    malformed_files: List[Path] = []

    all_files = sorted([
        f for f in char_dir.rglob("*")
        if f.is_file()
        and f.suffix in (".webp", ".png", ".jpg")
        and not any(p.startswith("ckpt_") or p == "_trash" for p in f.parts)
    ])
    report["total_files"] = len(all_files)

    for fpath in all_files:
        m = pattern.match(fpath.name)
        if m:
            files_by_code.setdefault(m.group(1), []).append((fpath, m.group(2) or ""))
        else:
            malformed_files.append(fpath)

    deprecated_poses = load_deprecated_poses(SDXL_POSE_DB_PATH)
    for code, flist in files_by_code.items():
        if code not in catalog:
            if code in deprecated_poses:
                dep_info = deprecated_poses[code]
                for fpath, raw_label in flist:
                    report.setdefault("legacy_deprecated", []).append({
                        "code": code, "filename": fpath.name, "path": str(fpath),
                        "actual_label": raw_label, "canonical_code": dep_info.get("canonical_code"),
                        "section": dep_info.get("section"),
                        "note": f"DB 선언 레거시 보존 에셋 (대체 표준: {dep_info.get('canonical_code')})",
                    })
            else:
                for fpath, _ in flist:
                    report["orphan_files"].append({
                        "code": code, "filename": fpath.name, "path": str(fpath),
                        "reason": "포즈 DB 및 로스터 이벤트에 정의되지 않은 미식별 코드",
                    })
            continue
        evaluate_code_alignment(code, flist, catalog[code], auto_fix, char_dir, origin_dir, prefix, report)

    for mf in malformed_files:
        report["orphan_files"].append({
            "code": "UNKNOWN", "filename": mf.name, "path": str(mf),
            "reason": f"파일명이 '{prefix}_{{code}}_{{label}}.ext' 규격을 따르지 않음",
        })

    for code, expected_info in catalog.items():
        if code not in files_by_code:
            report["missing_poses"].append({"code": code, "label": expected_info["label"], "section": expected_info["section"]})

    return report


def print_roster_alignment_report(roster: str, char_reports: List[Dict[str, Any]]) -> None:
    """결과 리포트 출력."""
    print("=" * 80)
    print(f"📊 [{roster.upper()}] 에셋 - 포즈 DB 명칭·누락·고아 전수 정합성 검사 결과")
    print("=" * 80)

    for r in char_reports:
        print_char_alignment_summary(r)

    total_mismatches = sum(len(r["mismatches"]) for r in char_reports)
    total_legacy = sum(len(r["legacy_compatible"]) for r in char_reports)
    total_orphans = sum(len(r["orphan_files"]) for r in char_reports)
    total_duplicates = sum(len(r["duplicates"]) for r in char_reports)
    total_missing = sum(len(r["missing_poses"]) for r in char_reports)
    total_fixed = sum(len(r["fixed_files"]) for r in char_reports)

    print("\n" + "=" * 80)
    print(f"🏁 종합 요약 ({roster.upper()} 로스터 {len(char_reports)}명):")
    print(f"  - 순수 라벨 불일치 오류: {total_mismatches}건")
    print(f"  - 레거시/과도기 호환 에셋: {total_legacy}건 (DB 정의 별칭에 의해 정상 수용됨)")
    print(f"  - 미식별/고아 파일: {total_orphans}건")
    print(f"  - 동일 코드 중복: {total_duplicates}건")
    print(f"  - 누락된 포즈: {total_missing}건 (캐릭터 평균 {total_missing // max(1, len(char_reports))}종 미생성)")
    if total_fixed > 0:
        print(f"  - 자동 교정 성공: {total_fixed}건")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="에셋 이미지와 포즈 DB 명칭·누락·고아 전수 정합성 검사")
    parser.add_argument("-r", "--roster", type=str, default="campus", help="검사할 로스터 (campus, ykn 등)")
    parser.add_argument("--fix", action="store_true", help="라벨 불일치 파일을 DB 표준 명칭으로 자동 교정 리네임")
    args = parser.parse_args()

    roster = args.roster
    char_list_file = PROJECTS_DIR / roster / "characters"
    if not char_list_file.is_dir():
        logger.error(f"로스터 캐릭터 폴더 없음: {char_list_file}")
        sys.exit(1)

    reports = []
    for prefix in sorted(f.stem for f in char_list_file.glob("*.json")):
        char_json_path = char_list_file / f"{prefix}.json"
        gender = "female"
        if char_json_path.exists():
            cdata = json.loads(char_json_path.read_text(encoding="utf-8"))
            gender = cdata.get("gender") or cdata.get("default_mode") or "female"
        reports.append(audit_character_alignment(roster, prefix, gender=gender, auto_fix=args.fix))

    print_roster_alignment_report(roster, reports)


if __name__ == "__main__":
    main()
