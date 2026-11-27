"""
scripts/audit_alignment_helpers.py
audit_asset_alignment.py의 카탈로그 병합, 파일 수집, 라벨 대조 및 리포트 출력 헬퍼.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AssetAlignmentAuditor")

OTOKONOKO_SECTIONS = {"scenes_otokonoko", "special_otokonoko", "special_otokonoko_h"}
FEMALE_ONLY_SECTIONS = {"h_scenes", "special_h", "special_female_h"}


def normalize_label_for_comparison(label: str) -> str:
    """공백, 언더스코어, 괄호를 제거하고 소문자로 통일하여 순수 내용만 비교."""
    return re.sub(r"[\s_\(\)\[\]]", "", label).lower()


def _extract_aliases(pdata: Dict[str, Any]) -> List[str]:
    aliases: List[str] = []
    if isinstance(pdata.get("aliases"), list):
        aliases.extend(str(a).strip() for a in pdata["aliases"])
    if isinstance(pdata.get("legacy_labels"), list):
        aliases.extend(str(lbl).strip() for lbl in pdata["legacy_labels"])
    return aliases


def _is_section_allowed(sec_name: str, is_otokonoko: bool) -> bool:
    if sec_name.startswith("_"):
        return False
    if is_otokonoko and sec_name in FEMALE_ONLY_SECTIONS:
        return False
    if not is_otokonoko and sec_name in OTOKONOKO_SECTIONS:
        return False
    return True


def collect_core_catalog(
    core_db: Dict[str, Any],
    roster: str,
    is_otokonoko: bool,
) -> Dict[str, Dict[str, Any]]:
    """코어 포즈 DB에서 성별·로스터 조건에 맞는 활성 기대 카탈로그를 구성합니다."""
    catalog: Dict[str, Dict[str, Any]] = {}
    for sec_name, sec_dict in core_db.items():
        if not isinstance(sec_dict, dict) or not _is_section_allowed(sec_name, is_otokonoko):
            continue
        for code, pdata in sec_dict.items():
            if not isinstance(pdata, dict) or "label" not in pdata:
                continue
            target_g = pdata.get("target_gender")
            if target_g:
                t_lower = target_g.lower().strip()
                if is_otokonoko and t_lower not in ("otokonoko", "futa"):
                    continue
                if not is_otokonoko and t_lower in ("otokonoko", "male"):
                    continue
            allowed_r = pdata.get("allowed_rosters")
            if allowed_r and roster and roster not in allowed_r:
                continue
            if pdata.get("status") == "deprecated":
                continue

            catalog[code] = {
                "label": pdata["label"].strip(),
                "aliases": _extract_aliases(pdata),
                "status": pdata.get("status", "active"),
                "section": sec_name,
                "source": "core_db",
                "required_outfit": pdata.get("required_outfit", ""),
            }
    return catalog


def merge_override_catalog(
    catalog: Dict[str, Dict[str, Any]],
    ov_file: Path,
    is_otokonoko: bool,
) -> None:
    """로스터 전용 pose_overrides/events/custom_poses JSON을 카탈로그에 병합합니다."""
    if not ov_file.exists():
        return
    try:
        ov_data = json.loads(ov_file.read_text(encoding="utf-8"))
        for sec_name, sec_dict in ov_data.items():
            if not isinstance(sec_dict, dict) or not _is_section_allowed(sec_name, is_otokonoko):
                continue
            for code, pdata in sec_dict.items():
                if not isinstance(pdata, dict) or "label" not in pdata:
                    continue
                aliases = _extract_aliases(pdata)
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
    except Exception as exc:
        logger.warning(f"오버라이드 파일 로드 실패 ({ov_file}): {exc}")


def load_deprecated_poses(pose_db_path: Path) -> Dict[str, Dict[str, Any]]:
    """코어 DB에서 status=deprecated 레거시 보존 포즈 메타데이터를 추출합니다."""
    deprecated_poses: Dict[str, Dict[str, Any]] = {}
    if not pose_db_path.exists():
        return deprecated_poses
    try:
        raw_db = json.loads(pose_db_path.read_text(encoding="utf-8"))
        for sec, items in raw_db.items():
            if isinstance(items, dict):
                for c, it in items.items():
                    if isinstance(it, dict) and it.get("status") == "deprecated":
                        deprecated_poses[c] = {
                            "label": it.get("label", ""),
                            "section": sec,
                            "canonical_code": it.get("canonical_code", ""),
                        }
    except Exception:
        pass
    return deprecated_poses


def execute_safe_rename(
    fpath: Path,
    char_dir: Path,
    origin_dir: Path,
    prefix: str,
    code: str,
    expected_label: str,
    report: Dict[str, Any],
) -> None:
    """2-Pass 기법으로 에셋 및 _origin 파일을 공식 명칭으로 안전 동기화 리네임."""
    ext = fpath.suffix
    censor_suffix = "_censored" if "_censored" in fpath.name else ""
    new_name = f"{prefix}_{code}_{expected_label}{censor_suffix}{ext}"
    new_path = fpath.parent / new_name

    if fpath == new_path:
        return
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
        except Exception as exc:
            logger.warning(f"_origin 리네임 중 오류: {exc}")


def evaluate_code_alignment(
    code: str,
    flist: List[Tuple[Path, str]],
    expected_info: Dict[str, Any],
    auto_fix: bool,
    char_dir: Path,
    origin_dir: Path,
    prefix: str,
    report: Dict[str, Any],
) -> None:
    """단일 포즈 코드의 파일 목록에 대해 중복·공식일치·별칭호환·불일치를 판정합니다."""
    expected_label = expected_info["label"]
    norm_exp = normalize_label_for_comparison(expected_label)
    norm_aliases = [normalize_label_for_comparison(a) for a in expected_info.get("aliases", [])]

    if len(flist) > 1:
        canonical_files = [f for f in flist if normalize_label_for_comparison(f[1]) == norm_exp]
        legacy_files = [f for f in flist if normalize_label_for_comparison(f[1]) in norm_aliases]
        if len(canonical_files) == 1 and (len(canonical_files) + len(legacy_files) == len(flist)):
            report["matched_count"] += 1
            for lf in legacy_files:
                report.setdefault("legacy_superseded", []).append({
                    "code": code,
                    "filename": lf[0].name,
                    "path": str(lf[0]),
                    "actual_label": lf[1],
                    "expected_label": expected_label,
                })
            return
        report["duplicates"].append({"code": code, "files": [f[0].name for f in flist]})

    for fpath, raw_label in flist:
        norm_raw = normalize_label_for_comparison(raw_label)
        if norm_raw == norm_exp:
            report["matched_count"] += 1
        elif norm_raw in norm_aliases:
            report["legacy_compatible"].append({
                "code": code, "filename": fpath.name, "path": str(fpath),
                "actual_label": raw_label, "expected_label": expected_label,
                "section": expected_info["section"],
                "note": f"DB 선언 레거시 호환 라벨 (공식 목표: '{expected_label}')",
            })
            if auto_fix:
                execute_safe_rename(fpath, char_dir, origin_dir, prefix, code, expected_label, report)
        else:
            report["mismatches"].append({
                "code": code, "filename": fpath.name, "path": str(fpath),
                "actual_label": raw_label, "expected_label": expected_label,
                "section": expected_info["section"],
            })
            if auto_fix:
                execute_safe_rename(fpath, char_dir, origin_dir, prefix, code, expected_label, report)


def print_char_alignment_summary(r: Dict[str, Any]) -> None:
    """단일 캐릭터 정합성 리포트를 콘솔에 출력합니다."""
    prefix = r["prefix"]
    print(f"\n👤 [{prefix.upper()}] (총 {r['total_files']}장 / 기대 포즈 {r['total_catalog_poses']}종)")
    print(f"  • 공식 표준 일치: {r['matched_count']}종")

    if r["legacy_compatible"]:
        print(f"  ⏳ [레거시/과도기 호환] {len(r['legacy_compatible'])}건 (DB 선언 별칭 일치):")
        for leg in r["legacy_compatible"]:
            print(f"    - 코드 {leg['code']} [{leg['section']}]: 현재='{leg['actual_label']}' ➔ 공식목표='{leg['expected_label']}' ({leg['filename']})")

    if r["mismatches"]:
        print(f"  🚨 [라벨 불일치 오류] {len(r['mismatches'])}건 (DB에 없는 임의 라벨):")
        for m in r["mismatches"]:
            print(f"    - 코드 {m['code']} [{m['section']}]: 현재='{m['actual_label']}' ➔ DB표준='{m['expected_label']}' ({m['filename']})")
    elif not r["legacy_compatible"]:
        print("  ✅ [라벨 일치] 불일치 0건 (DB 공식 표준과 100% 일치)")

    if r["duplicates"]:
        print(f"  ⚠️ [중복 파일] {len(r['duplicates'])}건:")
        for d in r["duplicates"]:
            print(f"    - 코드 {d['code']}: {', '.join(d['files'])}")

    if r["orphan_files"]:
        print(f"  ⚠️ [미식별/고아 파일] {len(r['orphan_files'])}건 (DB에 없는 코드):")
        for o in r["orphan_files"]:
            print(f"    - {o['filename']} ({o['reason']})")
    else:
        print("  ✅ [고아 파일] 미식별/규격외 파일 0건")

    if r["missing_poses"]:
        print(f"  ℹ️ [미생성/누락 포즈] {len(r['missing_poses'])}종:")
        by_sec: Dict[str, List[str]] = {}
        for mp in r["missing_poses"]:
            by_sec.setdefault(mp["section"], []).append(f"{mp['code']}_{mp['label']}")
        for sec, plist in by_sec.items():
            print(f"    • [{sec}] ({len(plist)}): {', '.join(plist)}")
    else:
        print("  ✅ [누락 포즈] 전체 포즈 100% 완비!")

    if r["fixed_files"]:
        print(f"  🔧 [자동 교정 완료] {len(r['fixed_files'])}건 리네임됨")
