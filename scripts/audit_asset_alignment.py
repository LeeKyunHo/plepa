"""
scripts/audit_asset_alignment.py
기존 에셋 이미지들과 포즈 DB(및 로스터 events.json) 간의 정합성을 전수 검사하는 도구:
1. 라벨 불일치(Label Mismatch) 검사
2. 비어있는(누락된) 포즈 검사 (Missing Poses)
3. 포즈 DB에 없는데 생성되어 있는 미식별/고아 에셋 검사 (Orphan Assets)
4. 동일 코드 중복 파일 검사 (Duplicate Assets)
5. --fix 옵션: DB 공식 라벨에 맞춰 파일명을 자동 안전 동기화
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from plepa_engine.config import PROJECTS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AssetAlignmentAuditor")


def load_full_pose_catalog(roster: str, gender: str = "female") -> Dict[str, Dict[str, str]]:
    """
    코어 포즈 DB(sdxl_pose_database.json)와 로스터별 이벤트(events.json)를 병합하여
    해당 성별에 기대되는 전체 포즈 맵 {code: {"label": ..., "section": ...}} 을 반환합니다.
    """
    catalog: Dict[str, Dict[str, str]] = {}
    
    # 1. 코어 포즈 DB 로드
    core_db_path = Path("data/sdxl_pose_database.json")
    if core_db_path.exists():
        with open(core_db_path, "r", encoding="utf-8") as f:
            core_db = json.load(f)
            
        allowed_sections = ["emotions", "poses", "romance"]
        if gender == "otokonoko":
            allowed_sections.extend(["scenes_otokonoko", "special_otokonoko"])
        else:
            allowed_sections.extend(["h_scenes", "special_h"])
            
        for sec in allowed_sections:
            sec_dict = core_db.get(sec, {})
            if isinstance(sec_dict, dict):
                for code, pdata in sec_dict.items():
                    if isinstance(pdata, dict) and "label" in pdata:
                        catalog[code] = {
                            "label": pdata["label"].strip(),
                            "section": sec,
                            "source": "core"
                        }

    # 2. 로스터 이벤트 로드 (events.json)
    events_path = PROJECTS_DIR / roster / "events.json"
    if events_path.exists():
        with open(events_path, "r", encoding="utf-8") as f:
            ev_data = json.load(f)
            
        ev_sections = ["daily_events"]
        if gender == "otokonoko":
            ev_sections.extend(["special_otokonoko"])
        else:
            ev_sections.extend(["special_female_h", "special_h"])
            
        for sec in ev_sections:
            sec_dict = ev_data.get(sec, {})
            if isinstance(sec_dict, dict):
                for code, pdata in sec_dict.items():
                    if isinstance(pdata, dict) and "label" in pdata:
                        catalog[code] = {
                            "label": pdata["label"].strip(),
                            "section": sec,
                            "source": "roster_events"
                        }

    return catalog


def normalize_label_for_comparison(label: str) -> str:
    """공백, 언더스코어, 괄호를 제거하고 소문자로 통일하여 순수 내용만 비교."""
    cleaned = re.sub(r"[\s_\(\)\[\]]", "", label).lower()
    return cleaned


def audit_character_alignment(
    roster: str,
    prefix: str,
    gender: str = "female",
    auto_fix: bool = False
) -> Dict[str, Any]:
    """한 캐릭터 폴더의 에셋과 포즈 DB의 일치성을 전수 점검."""
    char_dir = PROJECTS_DIR / roster / "assets" / prefix
    origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin"
    
    catalog = load_full_pose_catalog(roster, gender)
    
    report: Dict[str, Any] = {
        "roster": roster,
        "prefix": prefix,
        "gender": gender,
        "total_files": 0,
        "total_catalog_poses": len(catalog),
        "matched_count": 0,
        "mismatches": [],      # 라벨 불일치
        "missing_poses": [],   # 카탈로그에는 있으나 파일 없음
        "orphan_files": [],    # DB에 없는 코드이거나 비규격 파일
        "duplicates": [],      # 동일 코드 중복 파일
        "fixed_files": []      # 자동 교정된 파일 목록
    }
    
    if not char_dir.is_dir():
        logger.warning(f"캐릭터 에셋 폴더 없음: {char_dir}")
        return report

    # 1. 파일 수집
    pattern = re.compile(rf"^{re.escape(prefix)}_([A-Za-z0-9]+)(?:_(.*?))?(?:_censored)?\.(webp|png|jpg)$")
    files_by_code: Dict[str, List[Tuple[Path, str]]] = {}
    malformed_files: List[Path] = []
    
    all_files = sorted([f for f in char_dir.rglob("*") if f.is_file() and f.suffix in (".webp", ".png", ".jpg") and "_trash" not in f.parts])
    report["total_files"] = len(all_files)
    
    for fpath in all_files:
        m = pattern.match(fpath.name)
        if m:
            code = m.group(1)
            raw_label = m.group(2) or ""
            files_by_code.setdefault(code, []).append((fpath, raw_label))
        else:
            malformed_files.append(fpath)

    # 2. 코드별 정합성 판정
    for code, flist in files_by_code.items():
        # 중복 파일 검사
        if len(flist) > 1:
            report["duplicates"].append({
                "code": code,
                "files": [f[0].name for f in flist]
            })

        # DB에 존재하는 코드인지 검사
        if code not in catalog:
            for fpath, raw_label in flist:
                report["orphan_files"].append({
                    "code": code,
                    "filename": fpath.name,
                    "path": str(fpath),
                    "reason": "포즈 DB 및 로스터 이벤트에 정의되지 않은 코드"
                })
        else:
            expected_info = catalog[code]
            expected_label = expected_info["label"]
            norm_exp = normalize_label_for_comparison(expected_label)
            
            for fpath, raw_label in flist:
                norm_raw = normalize_label_for_comparison(raw_label)
                if norm_raw != norm_exp:
                    mismatch_item = {
                        "code": code,
                        "filename": fpath.name,
                        "path": str(fpath),
                        "actual_label": raw_label,
                        "expected_label": expected_label,
                        "section": expected_info["section"]
                    }
                    report["mismatches"].append(mismatch_item)
                    
                    # --fix 옵션 처리 (라벨 자동 교정)
                    if auto_fix:
                        ext = fpath.suffix
                        is_censored = "_censored" in fpath.name
                        censor_suffix = "_censored" if is_censored else ""
                        new_name = f"{prefix}_{code}_{expected_label}{censor_suffix}{ext}"
                        new_path = fpath.parent / new_name
                        if fpath != new_path:
                            # 2-pass rename
                            tmp_path = fpath.parent / f"__tmp_align_{fpath.name}"
                            os.rename(fpath, tmp_path)
                            os.rename(tmp_path, new_path)
                            report["fixed_files"].append(f"{fpath.name} -> {new_name}")
                            
                            # _origin 원본도 함께 리네임
                            if origin_dir.is_dir():
                                orig_target = origin_dir / fpath.relative_to(char_dir)
                                if orig_target.is_file():
                                    orig_new_path = orig_target.parent / new_name
                                    orig_tmp = orig_target.parent / f"__tmp_align_{orig_target.name}"
                                    os.rename(orig_target, orig_tmp)
                                    os.rename(orig_tmp, orig_new_path)
                else:
                    report["matched_count"] += 1

    # 비규격 파일 처리
    for mf in malformed_files:
        report["orphan_files"].append({
            "code": "UNKNOWN",
            "filename": mf.name,
            "path": str(mf),
            "reason": f"파일명이 '{prefix}_{{code}}_{{label}}.ext' 규격을 따르지 않음"
        })

    # 3. 누락된 포즈 검사
    for code, expected_info in catalog.items():
        if code not in files_by_code:
            report["missing_poses"].append({
                "code": code,
                "label": expected_info["label"],
                "section": expected_info["section"]
            })

    return report


def print_roster_alignment_report(roster: str, char_reports: List[Dict[str, Any]]):
    """결과 리포트 출력."""
    print("=" * 78)
    print(f"📊 [{roster.upper()}] 에셋 - 포즈 DB 명칭·누락·고아 전수 정합성 검사 결과")
    print("=" * 78)
    
    total_mismatches = sum(len(r["mismatches"]) for r in char_reports)
    total_orphans = sum(len(r["orphan_files"]) for r in char_reports)
    total_duplicates = sum(len(r["duplicates"]) for r in char_reports)
    total_missing = sum(len(r["missing_poses"]) for r in char_reports)
    total_fixed = sum(len(r["fixed_files"]) for r in char_reports)
    
    for r in char_reports:
        prefix = r["prefix"]
        print(f"\n👤 [{prefix.upper()}] (총 {r['total_files']}장 / 기대 포즈 {r['total_catalog_poses']}종)")
        print(f"  • 완벽 일치: {r['matched_count']}종")
        
        # 1. 라벨 불일치
        if r["mismatches"]:
            print(f"  🚨 [라벨 불일치] {len(r['mismatches'])}건:")
            for m in r["mismatches"]:
                print(f"    - 코드 {m['code']} [{m['section']}]: 현재='{m['actual_label']}' ➔ DB표준='{m['expected_label']}' ({m['filename']})")
        else:
            print(f"  ✅ [라벨 일치] 불일치 0건 (DB 표준과 100% 일치)")
            
        # 2. 중복 파일
        if r["duplicates"]:
            print(f"  ⚠️ [중복 파일] {len(r['duplicates'])}건:")
            for d in r["duplicates"]:
                print(f"    - 코드 {d['code']}: {', '.join(d['files'])}")
                
        # 3. 고아 / 미식별 파일
        if r["orphan_files"]:
            print(f"  ⚠️ [미식별/고아 파일] {len(r['orphan_files'])}건 (DB에 없는 코드):")
            for o in r["orphan_files"]:
                print(f"    - {o['filename']} ({o['reason']})")
        else:
            print(f"  ✅ [고아 파일] 미식별/규격외 파일 0건")

        # 4. 누락 포즈
        if r["missing_poses"]:
            print(f"  ℹ️ [미생성/누락 포즈] {len(r['missing_poses'])}종:")
            by_sec: Dict[str, List[str]] = {}
            for mp in r["missing_poses"]:
                by_sec.setdefault(mp["section"], []).append(f"{mp['code']}_{mp['label']}")
            for sec, plist in by_sec.items():
                print(f"    • [{sec}] ({len(plist)}): {', '.join(plist)}")
        else:
            print(f"  ✅ [누락 포즈] 전체 포즈 100% 완비!")
            
        if r["fixed_files"]:
            print(f"  🔧 [자동 교정 완료] {len(r['fixed_files'])}건 리네임됨")

    print("\n" + "=" * 78)
    print(f"🏁 종합 요약 ({roster.upper()} 로스터 {len(char_reports)}명):")
    print(f"  - 라벨 불일치: {total_mismatches}건")
    print(f"  - 미식별/고아 파일: {total_orphans}건")
    print(f"  - 동일 코드 중복: {total_duplicates}건")
    print(f"  - 누락된 포즈: {total_missing}건 (캐릭터 평균 {total_missing // max(1, len(char_reports))}종 미생성)")
    if total_fixed > 0:
        print(f"  - 자동 교정 성공: {total_fixed}건")
    print("=" * 78)


def main():
    parser = argparse.ArgumentParser(description="에셋 이미지와 포즈 DB 명칭·누락·고아 전수 정합성 검사")
    parser.add_argument("-r", "--roster", type=str, default="campus", help="검사할 로스터 (campus, ykn 등)")
    parser.add_argument("--fix", action="store_true", help="라벨 불일치 파일을 DB 표준 명칭으로 자동 교정 리네임")
    args = parser.parse_args()

    roster = args.roster
    char_list_file = PROJECTS_DIR / roster / "characters"
    if not char_list_file.is_dir():
        logger.error(f"로스터 캐릭터 폴더 없음: {char_list_file}")
        sys.exit(1)

    char_prefixes = [f.stem for f in char_list_file.glob("*.json")]
    reports = []
    
    for prefix in sorted(char_prefixes):
        # 캐릭터 성별 로드
        char_json_path = char_list_file / f"{prefix}.json"
        gender = "female"
        if char_json_path.exists():
            with open(char_json_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                gender = cdata.get("gender") or cdata.get("default_mode") or "female"
        
        rep = audit_character_alignment(roster, prefix, gender=gender, auto_fix=args.fix)
        reports.append(rep)

    print_roster_alignment_report(roster, reports)


if __name__ == "__main__":
    main()
