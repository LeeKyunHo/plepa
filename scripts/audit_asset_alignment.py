"""
scripts/audit_asset_alignment.py
기존 에셋 이미지들과 포즈 DB(및 로스터 events.json, pose_overrides.json) 간의 정합성을 전수 검사하는 도구:
1. 라벨 불일치(Label Mismatch) 검사
2. DB 메타데이터 기반 레거시/과도기 호환 에셋(Legacy Compatible) 자동 분류
3. 비어있는(누락된) 포즈 검사 (Missing Poses)
4. 포즈 DB에 없는데 생성되어 있는 미식별/고아 에셋 검사 (Orphan Assets)
5. 동일 코드 중복 파일 검사 (Duplicate Assets)
6. --fix 옵션: DB 공식 라벨에 맞춰 파일명을 자동 안전 동기화 (2-Pass Safe Rename)
7. 데이터 주도형 아키텍처: 포즈 DB 수정 시 검수 항목이 100% 실시간으로 자동 연동됨.
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

from plepa_engine.config import PROJECTS_DIR, SDXL_POSE_DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AssetAlignmentAuditor")

# 성별 전용 섹션 정의 (이 외의 모든 섹션은 성별 공통으로 동적 로드됨)
OTOKONOKO_SECTIONS = {"scenes_otokonoko", "special_otokonoko", "special_otokonoko_h"}
FEMALE_ONLY_SECTIONS = {"h_scenes", "special_h", "special_female_h"}


def normalize_label_for_comparison(label: str) -> str:
    """공백, 언더스코어, 괄호를 제거하고 소문자로 통일하여 순수 내용만 비교."""
    cleaned = re.sub(r"[\s_\(\)\[\]]", "", label).lower()
    return cleaned


def load_full_pose_catalog(
    roster: str,
    gender: str = "female",
    custom_db_data: Optional[Dict[str, Any]] = None,
    custom_roster_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    코어 포즈 DB(sdxl_pose_database.json)와 로스터별 오버라이드 및 이벤트를 동적으로 병합하여
    해당 성별과 로스터에 기대되는 전체 포즈 맵 {code: {...}} 을 실시간 생성합니다.
    
    포즈 DB에 신규 섹션이나 포즈가 추가/수정되면 즉시 100% 자동 연동됩니다.
    """
    catalog: Dict[str, Dict[str, Any]] = {}
    is_otokonoko = (gender or "").lower().strip() == "otokonoko"

    # 1. 코어 포즈 DB 로드 (동적 섹션 탐색)
    if custom_db_data is not None:
        core_db = custom_db_data
    else:
        core_db_path = SDXL_POSE_DB_PATH
        if core_db_path.exists():
            with open(core_db_path, "r", encoding="utf-8") as f:
                core_db = json.load(f)
        else:
            core_db = {}

    for sec_name, sec_dict in core_db.items():
        # 메타데이터 키 건너뛰기
        if sec_name.startswith("_") or not isinstance(sec_dict, dict):
            continue

        # 성별 필터링
        if is_otokonoko and sec_name in FEMALE_ONLY_SECTIONS:
            continue
        if not is_otokonoko and sec_name in OTOKONOKO_SECTIONS:
            continue

        for code, pdata in sec_dict.items():
            if not isinstance(pdata, dict) or "label" not in pdata:
                continue

            # target_gender 필터링
            target_g = pdata.get("target_gender")
            if target_g:
                t_lower = target_g.lower().strip()
                if is_otokonoko and t_lower not in ("otokonoko", "futa"):
                    continue
                if not is_otokonoko and t_lower in ("otokonoko", "male"):
                    continue

            # allowed_rosters 필터링
            allowed_r = pdata.get("allowed_rosters")
            if allowed_r and roster and roster not in allowed_r:
                continue

            # 별칭 및 레거시 라벨 통합 수집
            aliases = []
            if "aliases" in pdata and isinstance(pdata["aliases"], list):
                aliases.extend([str(a).strip() for a in pdata["aliases"]])
            if "legacy_labels" in pdata and isinstance(pdata["legacy_labels"], list):
                aliases.extend([str(l).strip() for l in pdata["legacy_labels"]])

            catalog[code] = {
                "label": pdata["label"].strip(),
                "aliases": aliases,
                "status": pdata.get("status", "active"),
                "section": sec_name,
                "source": "core_db",
                "required_outfit": pdata.get("required_outfit", ""),
            }

    # 2. 로스터 전용 오버라이드 및 이벤트 병합
    r_dir = custom_roster_dir or (PROJECTS_DIR / roster)
    if r_dir.is_dir():
        override_files = [
            r_dir / "pose_overrides.json",
            r_dir / "events.json",
            r_dir / "custom_poses.json",
        ]
        
        for ov_file in override_files:
            if not ov_file.exists():
                continue
            try:
                with open(ov_file, "r", encoding="utf-8") as f:
                    ov_data = json.load(f)
                
                for sec_name, sec_dict in ov_data.items():
                    if sec_name.startswith("_") or not isinstance(sec_dict, dict):
                        continue
                    if is_otokonoko and sec_name in FEMALE_ONLY_SECTIONS:
                        continue
                    if not is_otokonoko and sec_name in OTOKONOKO_SECTIONS:
                        continue

                    for code, pdata in sec_dict.items():
                        if not isinstance(pdata, dict) or "label" not in pdata:
                            continue

                        aliases = []
                        if "aliases" in pdata and isinstance(pdata["aliases"], list):
                            aliases.extend([str(a).strip() for a in pdata["aliases"]])
                        if "legacy_labels" in pdata and isinstance(pdata["legacy_labels"], list):
                            aliases.extend([str(l).strip() for l in pdata["legacy_labels"]])

                        # 기존 코어 항목이 있으면 별칭 유지하며 업데이트
                        if code in catalog:
                            merged_aliases = list(dict.fromkeys(catalog[code]["aliases"] + aliases))
                            catalog[code].update({
                                "label": pdata["label"].strip(),
                                "aliases": merged_aliases,
                                "section": sec_name,
                                "source": ov_file.name,
                            })
                        else:
                            catalog[code] = {
                                "label": pdata["label"].strip(),
                                "aliases": aliases,
                                "status": pdata.get("status", "active"),
                                "section": sec_name,
                                "source": ov_file.name,
                                "required_outfit": pdata.get("required_outfit", ""),
                            }
            except Exception as e:
                logger.warning(f"오버라이드 파일 로드 실패 ({ov_file}): {e}")

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
        "legacy_compatible": [], # DB에 명시된 레거시/과도기 허용 라벨
        "mismatches": [],        # 순수 라벨 불일치 오류
        "missing_poses": [],     # 카탈로그에는 있으나 파일 없음
        "orphan_files": [],      # DB에 없는 코드이거나 비규격 파일
        "duplicates": [],        # 동일 코드 중복 파일
        "fixed_files": [],       # 자동 교정된 파일 목록
    }

    if not char_dir.is_dir():
        logger.warning(f"캐릭터 에셋 폴더 없음: {char_dir}")
        return report

    # 1. 파일 수집
    pattern = re.compile(rf"^{re.escape(prefix)}_([A-Za-z0-9]+)(?:_(.*?))?(?:_censored)?\.(webp|png|jpg)$")
    files_by_code: Dict[str, List[Tuple[Path, str]]] = {}
    malformed_files: List[Path] = []

    all_files = sorted([
        f for f in char_dir.rglob("*")
        if f.is_file() and f.suffix in (".webp", ".png", ".jpg") and "_trash" not in f.parts
    ])
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
                "files": [f[0].name for f in flist],
            })

        # DB에 존재하는 코드인지 검사
        if code not in catalog:
            for fpath, raw_label in flist:
                report["orphan_files"].append({
                    "code": code,
                    "filename": fpath.name,
                    "path": str(fpath),
                    "reason": "포즈 DB 및 로스터 이벤트에 정의되지 않은 미식별 코드",
                })
        else:
            expected_info = catalog[code]
            expected_label = expected_info["label"]
            norm_exp = normalize_label_for_comparison(expected_label)
            aliases = expected_info.get("aliases", [])
            norm_aliases = [normalize_label_for_comparison(a) for a in aliases]

            for fpath, raw_label in flist:
                norm_raw = normalize_label_for_comparison(raw_label)

                # 1) 공식 라벨과 완벽 일치
                if norm_raw == norm_exp:
                    report["matched_count"] += 1
                # 2) DB에 등록된 레거시/과도기 허용 라벨(alias)과 일치
                elif norm_raw in norm_aliases:
                    report["legacy_compatible"].append({
                        "code": code,
                        "filename": fpath.name,
                        "path": str(fpath),
                        "actual_label": raw_label,
                        "expected_label": expected_label,
                        "section": expected_info["section"],
                        "note": f"DB 선언 레거시 호환 라벨 (공식 목표: '{expected_label}')",
                    })
                    # auto_fix 지정 시 공식 라벨로 안전 리네임 가능
                    if auto_fix:
                        _execute_safe_rename(fpath, char_dir, origin_dir, prefix, code, expected_label, report)
                # 3) DB 공식 및 별칭 어디에도 없는 순수 불일치
                else:
                    mismatch_item = {
                        "code": code,
                        "filename": fpath.name,
                        "path": str(fpath),
                        "actual_label": raw_label,
                        "expected_label": expected_label,
                        "section": expected_info["section"],
                    }
                    report["mismatches"].append(mismatch_item)

                    if auto_fix:
                        _execute_safe_rename(fpath, char_dir, origin_dir, prefix, code, expected_label, report)

    # 비규격 파일 처리
    for mf in malformed_files:
        report["orphan_files"].append({
            "code": "UNKNOWN",
            "filename": mf.name,
            "path": str(mf),
            "reason": f"파일명이 '{prefix}_{{code}}_{{label}}.ext' 규격을 따르지 않음",
        })

    # 3. 누락된 포즈 검사
    for code, expected_info in catalog.items():
        if code not in files_by_code:
            report["missing_poses"].append({
                "code": code,
                "label": expected_info["label"],
                "section": expected_info["section"],
            })

    return report


def _execute_safe_rename(
    fpath: Path,
    char_dir: Path,
    origin_dir: Path,
    prefix: str,
    code: str,
    expected_label: str,
    report: Dict[str, Any]
) -> None:
    """2-Pass 기법으로 에셋 및 _origin 파일을 공식 명칭으로 안전 동기화 리네임."""
    ext = fpath.suffix
    is_censored = "_censored" in fpath.name
    censor_suffix = "_censored" if is_censored else ""
    new_name = f"{prefix}_{code}_{expected_label}{censor_suffix}{ext}"
    new_path = fpath.parent / new_name

    if fpath != new_path:
        tmp_path = fpath.parent / f"__tmp_align_{fpath.name}"
        os.rename(fpath, tmp_path)
        os.rename(tmp_path, new_path)
        report["fixed_files"].append(f"{fpath.name} -> {new_name}")

        if origin_dir.is_dir():
            try:
                orig_target = origin_dir / fpath.relative_to(char_dir)
                if orig_target.is_file():
                    orig_new_path = orig_target.parent / new_name
                    orig_tmp = orig_target.parent / f"__tmp_align_{orig_target.name}"
                    os.rename(orig_target, orig_tmp)
                    os.rename(orig_tmp, orig_new_path)
            except Exception as e:
                logger.warning(f"_origin 리네임 중 오류: {e}")


def print_roster_alignment_report(roster: str, char_reports: List[Dict[str, Any]]):
    """결과 리포트 출력."""
    print("=" * 80)
    print(f"📊 [{roster.upper()}] 에셋 - 포즈 DB 명칭·누락·고아 전수 정합성 검사 결과")
    print("=" * 80)

    total_mismatches = sum(len(r["mismatches"]) for r in char_reports)
    total_legacy = sum(len(r["legacy_compatible"]) for r in char_reports)
    total_orphans = sum(len(r["orphan_files"]) for r in char_reports)
    total_duplicates = sum(len(r["duplicates"]) for r in char_reports)
    total_missing = sum(len(r["missing_poses"]) for r in char_reports)
    total_fixed = sum(len(r["fixed_files"]) for r in char_reports)

    for r in char_reports:
        prefix = r["prefix"]
        print(f"\n👤 [{prefix.upper()}] (총 {r['total_files']}장 / 기대 포즈 {r['total_catalog_poses']}종)")
        print(f"  • 공식 표준 일치: {r['matched_count']}종")

        # 1. DB 선언 레거시/과도기 호환
        if r["legacy_compatible"]:
            print(f"  ⏳ [레거시/과도기 호환] {len(r['legacy_compatible'])}건 (DB 선언 별칭 일치):")
            for leg in r["legacy_compatible"]:
                print(f"    - 코드 {leg['code']} [{leg['section']}]: 현재='{leg['actual_label']}' ➔ 공식목표='{leg['expected_label']}' ({leg['filename']})")

        # 2. 라벨 불일치 오류
        if r["mismatches"]:
            print(f"  🚨 [라벨 불일치 오류] {len(r['mismatches'])}건 (DB에 없는 임의 라벨):")
            for m in r["mismatches"]:
                print(f"    - 코드 {m['code']} [{m['section']}]: 현재='{m['actual_label']}' ➔ DB표준='{m['expected_label']}' ({m['filename']})")
        elif not r["legacy_compatible"]:
            print(f"  ✅ [라벨 일치] 불일치 0건 (DB 공식 표준과 100% 일치)")

        # 3. 중복 파일
        if r["duplicates"]:
            print(f"  ⚠️ [중복 파일] {len(r['duplicates'])}건:")
            for d in r["duplicates"]:
                print(f"    - 코드 {d['code']}: {', '.join(d['files'])}")

        # 4. 고아 / 미식별 파일
        if r["orphan_files"]:
            print(f"  ⚠️ [미식별/고아 파일] {len(r['orphan_files'])}건 (DB에 없는 코드):")
            for o in r["orphan_files"]:
                print(f"    - {o['filename']} ({o['reason']})")
        else:
            print(f"  ✅ [고아 파일] 미식별/규격외 파일 0건")

        # 5. 누락 포즈
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
