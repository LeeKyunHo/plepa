"""
plepa_engine.services.asset_helpers
캐릭터 에셋 스캔, 휴지통 번들 이동/복원, _origin 복원, 비규격 에셋 탐색 및 완비율 감사 헬퍼.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plepa_engine.services.repository import Repository

logger = logging.getLogger(__name__)


def _code_sort_key(k: str) -> Tuple[int, Any, Any]:
    """숫자 단독(000) -> 영문+숫자(A00, C01, N01) -> 일반 문자열 정렬 키."""
    if k.isdigit():
        return (0, "", int(k))
    if len(k) >= 2 and k[0].isalpha() and k[1:].isdigit():
        return (1, k[0].upper(), int(k[1:]))
    return (2, k, 0)


def scan_character_assets(asset_dir: Path, origin_dir: Path, prefix: str) -> List[Dict[str, Any]]:
    """캐릭터 에셋 디렉터리를 스캔해 코드별 정렬된 메타데이터 목록을 반환합니다."""
    if not asset_dir.is_dir():
        return []

    items_by_code: Dict[str, Dict[str, Any]] = {}
    pattern = re.compile(rf"^{re.escape(prefix)}_([A-Za-z0-9]+)(?:_(.*?))?(?:_censored)?\.(webp|png)$")

    for f in sorted(asset_dir.rglob(f"{prefix}_*")):
        if not f.is_file():
            continue
        m = pattern.match(f.name)
        if not m:
            continue

        code = m.group(1)
        raw_label = m.group(2) or ""
        is_censored = "_censored" in f.name
        if code not in items_by_code:
            items_by_code[code] = {
                "code": code,
                "label": raw_label,
                "path": None,
                "censored_path": None,
                "origin_path": None,
                "size_bytes": 0,
                "mtime": 0.0,
            }

        if is_censored:
            items_by_code[code]["censored_path"] = f
        else:
            items_by_code[code]["path"] = f
            items_by_code[code]["label"] = raw_label or items_by_code[code]["label"]
            items_by_code[code]["size_bytes"] = f.stat().st_size
            items_by_code[code]["mtime"] = f.stat().st_mtime

            if origin_dir.is_dir():
                origin_cand = origin_dir / f.name
                if not origin_cand.is_file():
                    code_matches = list(origin_dir.rglob(f"{prefix}_{code}*"))
                    if code_matches:
                        origin_cand = code_matches[0]
                if origin_cand.is_file():
                    items_by_code[code]["origin_path"] = origin_cand
                    if not items_by_code[code]["censored_path"]:
                        items_by_code[code]["censored_path"] = f

    return [v for _, v in sorted(items_by_code.items(), key=lambda x: _code_sort_key(x[0])) if v["path"] is not None]


def move_asset_bundle_to_trash(repo: Repository, file_path: Path) -> Dict[str, Any]:
    """에셋 및 쌍둥이 원본(_origin)을 휴지통으로 안전 이동하고 복원용 이력을 반환합니다."""
    p = Path(file_path).resolve()
    if not p.is_file():
        return {"success": False, "filename": p.name, "moved": [], "code": None, "prefix": None}

    moved: List[Dict[str, str]] = []
    main_trash = repo.move_to_trash(p)
    if main_trash:
        moved.append({"original": str(p), "trash": str(main_trash)})

    m = re.match(r"^([a-zA-Z0-9]+)_([a-zA-Z0-9]+)", p.name)
    prefix = m.group(1) if m else None
    code = m.group(2) if m else None

    if prefix:
        for parent in p.parents:
            if parent.name == prefix and parent.parent.name == "assets":
                origin_root = parent.parent / f"{prefix}_origin"
                if origin_root.is_dir():
                    sub_rel = p.parent.relative_to(parent)
                    for cand in (origin_root / sub_rel / p.name, origin_root / p.name):
                        if cand.is_file():
                            o_trash = repo.move_to_trash(cand)
                            if o_trash:
                                moved.append({"original": str(cand), "trash": str(o_trash)})
                break

    return {
        "success": len(moved) > 0,
        "filename": p.name,
        "moved": moved,
        "code": code,
        "prefix": prefix,
    }


def restore_trash_bundle(moved_list: List[Dict[str, str]], projects_dir: Path) -> bool:
    """휴지통으로 이동되었던 에셋 번들을 원래 위치로 원자적으로 복원(Undo)합니다."""
    projects_root = projects_dir.resolve()
    success = True
    for item in moved_list:
        tmp_restore: Optional[Path] = None
        try:
            trash_p = Path(item["trash"]).resolve()
            orig_p = Path(item["original"]).resolve()
            if not trash_p.is_relative_to(projects_root) or not orig_p.is_relative_to(projects_root):
                success = False
                continue
            if trash_p.is_file():
                orig_p.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.replace(trash_p, orig_p)
                except OSError:
                    tmp_restore = orig_p.parent / f".tmp_{uuid.uuid4().hex[:6]}_{orig_p.name}"
                    shutil.copy2(trash_p, tmp_restore)
                    os.replace(tmp_restore, orig_p)
                    trash_p.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("에셋 복원 실패 (%s): %s", item.get("original"), exc)
            if tmp_restore and tmp_restore.exists():
                tmp_restore.unlink(missing_ok=True)
            success = False
    return success


def scan_misc_assets_in_roster(roster_dir: Path) -> List[Dict[str, Any]]:
    """레퍼런스, 배경, 비정규 샘플 에셋을 수집하여 최신 수정 순으로 반환합니다."""
    if not roster_dir.is_dir():
        return []

    results: List[Dict[str, Any]] = []
    valid_exts = {".webp", ".png", ".jpg", ".jpeg"}

    ref_dir = roster_dir / "references"
    if ref_dir.is_dir():
        for f in sorted(ref_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in valid_exts:
                subfolder = f.parent.name
                cat_label = "레퍼런스 (창고)" if subfolder != "references" else "레퍼런스"
                results.append({
                    "name": f.name,
                    "category": cat_label,
                    "type": "reference",
                    "path": f,
                    "size_bytes": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                    "folder": f.parent.relative_to(roster_dir).as_posix(),
                })

    bg_dir = roster_dir / "backgrounds"
    if bg_dir.is_dir():
        for f in sorted(bg_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in valid_exts:
                results.append({
                    "name": f.name,
                    "category": "배경 (BG)",
                    "type": "background",
                    "path": f,
                    "size_bytes": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                    "folder": f.parent.relative_to(roster_dir).as_posix(),
                })

    assets_dir = roster_dir / "assets"
    pose_pattern = re.compile(r"^.+_[A-Za-z0-9]+(?:_.*)?\.(webp|png)$")
    if assets_dir.is_dir():
        for f in sorted(assets_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in valid_exts and not pose_pattern.match(f.name):
                results.append({
                    "name": f.name,
                    "category": "비규격/샘플",
                    "type": "sample",
                    "path": f,
                    "size_bytes": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                    "folder": f.parent.relative_to(roster_dir).as_posix(),
                })

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def restore_file_from_origin(
    origin_dir: Path,
    asset_dir: Path,
    prefix: str,
    code_str: str,
    subfolder: str,
) -> bool:
    """_origin 백업 원본을 임시파일 경유 os.replace로 원자적 복원합니다."""
    if not origin_dir.is_dir() or not asset_dir.is_dir():
        return False

    matches = list(origin_dir.rglob(f"{prefix}_{code_str}*"))
    if not matches:
        return False

    src_file = matches[0]
    sub_asset_dir = asset_dir / subfolder
    existing_targets = list(asset_dir.rglob(f"{prefix}_{code_str}*"))
    if existing_targets:
        dst_file = existing_targets[0]
    else:
        sub_asset_dir.mkdir(parents=True, exist_ok=True)
        dst_file = sub_asset_dir / src_file.name

    dst_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dst = dst_file.with_name(f".{dst_file.stem}_{uuid.uuid4().hex[:6]}.tmp{dst_file.suffix}")
    try:
        shutil.copy2(src_file, temp_dst)
        os.replace(temp_dst, dst_file)
    finally:
        if temp_dst.exists():
            temp_dst.unlink(missing_ok=True)
    return True


def build_character_audit_summary(
    char_obj: Any,
    char_expected_codes: List[str],
    assets: List[Dict[str, Any]],
    pose_db: Dict[str, Any],
) -> Dict[str, Any]:
    """단일 캐릭터 에셋 완비율 및 라벨 불일치·원본 백업 감사 요약을 산출합니다."""
    assets_by_code = {a["code"]: a for a in assets}
    present_codes = set(assets_by_code.keys())
    missing_codes = [c for c in char_expected_codes if c not in present_codes]

    outdated_labels = 0
    for code, a in assets_by_code.items():
        if code in pose_db:
            clean_file_label = (a["label"] or "").replace("_", "").replace(" ", "")
            clean_canon_label = (pose_db[code].label or "").replace("_", "").replace(" ", "")
            if clean_file_label and clean_canon_label and clean_file_label != clean_canon_label:
                outdated_labels += 1

    origin_count = sum(1 for a in assets if a.get("origin_path") is not None)
    expected_count = len(char_expected_codes)
    present_count = len(present_codes)
    rate = round((present_count / expected_count * 100), 1) if expected_count > 0 else 0.0

    return {
        "prefix": char_obj.prefix,
        "name": char_obj.name,
        "gender": char_obj.gender,
        "expected_count": expected_count,
        "present_count": present_count,
        "missing_codes": missing_codes,
        "missing_count": len(missing_codes),
        "completion_rate": rate,
        "outdated_labels": outdated_labels,
        "origin_count": origin_count,
    }
