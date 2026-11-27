"""
plepa_gui.pages.gallery_parts.data_helpers
갤러리 로스터/포즈/매니페스트 파싱 및 URL 빌더 유틸리티.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from nicegui import ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service
from plepa_gui.components.header import get_active_roster, get_available_rosters

logger = logging.getLogger(__name__)


def parse_manifest_items_map(raw_doc: Any) -> Dict[str, Dict[str, Any]]:
    """_batch_manifest.json 문서(items 리스트 또는 레거시 딕셔너리)를 포즈 코드 기준 맵으로 안전하게 정규화합니다."""
    if not isinstance(raw_doc, dict):
        return {}
    top_ts = raw_doc.get("timestamp", "-")
    raw_items = raw_doc.get("items", [])
    loaded_m: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw_items, list):
        for it in raw_items:
            if isinstance(it, dict) and "code" in it:
                entry = dict(it)
                entry.setdefault("timestamp", top_ts)
                loaded_m[str(it["code"]).strip()] = entry
    elif isinstance(raw_items, dict):
        for k, v in raw_items.items():
            if isinstance(v, dict):
                entry = dict(v)
                entry.setdefault("timestamp", top_ts)
                loaded_m[str(k).strip()] = entry
    return loaded_m


def safe_notify(msg: str, type: str = "info") -> None:
    """UI 컨텍스트 유무와 무관하게 알림을 안전하게 호출합니다."""
    try:
        ui.notify(msg, type=type)
    except Exception as exc:
        logger.debug("ui.notify skipped (%s): %s", type, exc)


def detect_best_default_roster() -> str:
    """전역 활성 로스터를 기본값으로 사용하고 없을 시 활성 로스터 중 최다 에셋 로스터를 선택."""
    active_r = get_active_roster()
    if (PROJECTS_DIR / active_r).is_dir():
        return active_r
    best_roster = get_available_rosters()[0]
    max_count = 0
    for r_name in get_available_rosters():
        assets_dir = PROJECTS_DIR / r_name / "assets"
        if not assets_dir.is_dir():
            continue
        webp_count = len([f for f in assets_dir.rglob("*.webp") if "_origin" not in f.parts])
        if webp_count > max_count:
            max_count = webp_count
            best_roster = r_name
    return best_roster


def pose_sort_key(code: str) -> tuple[int, int, str]:
    """숫자 포즈 코드를 선행 정렬하고 영숫자 포즈 코드를 후행 사전순 정렬합니다."""
    try:
        return (0, int(code), "")
    except ValueError:
        return (1, 0, code)


def get_character_asset_counts(roster: str) -> Dict[str, int]:
    """로스터 내 캐릭터별 생성된 에셋 개수 맵 반환."""
    chars = default_character_service.list_characters(roster=roster)
    counts: Dict[str, int] = {}
    for _, c, _ in chars:
        assets = default_asset_service.list_character_assets(c.prefix, roster)
        counts[c.prefix] = len(assets)
    return counts


def get_roster_gallery_pose_scope(roster: str) -> Dict[str, Any]:
    """
    현재 로스터에서 실제 이미지가 1장 이상 생성된 포즈 코드와
    해당 로스터의 성별·보유 에셋에 부합하는 '포즈 범위' 드롭다운 옵션을 반환합니다.
    """
    chars = default_character_service.list_characters(roster=roster)
    char_counts: Dict[str, int] = {}
    existing_codes_set: set[str] = set()
    char_genders: set[str] = set()

    for _, c, _ in chars:
        assets = default_asset_service.list_character_assets(c.prefix, roster)
        char_counts[c.prefix] = len(assets)
        char_genders.add((getattr(c, "gender", "") or "female").strip().lower())
        for a in assets:
            code = str(a.get("code") or "").strip()
            if code:
                existing_codes_set.add(code)

    existing_codes = sorted(existing_codes_set, key=pose_sort_key)
    pose_sets = default_pose_service.load_pose_sets()
    has_otokonoko = "otokonoko" in char_genders
    otokonoko_only = char_genders == {"otokonoko"}
    roster_l = (roster or "").strip().lower()

    set_options: Dict[str, str] = {"all": f"전체 보유 포즈 ({len(existing_codes)}종)"}
    matched_codes_by_set: Dict[str, List[str]] = {"all": list(existing_codes)}

    for s in pose_sets:
        sid = (s.id or "").lower()
        if not has_otokonoko and (sid.startswith("oto_") or "otokonoko" in sid or sid == "unified_152"):
            continue
        if otokonoko_only and sid in ("h_scenes_52", "unified_100", "campus_108", "unified_152"):
            continue
        if sid.startswith("wuxia_") and roster_l not in ("murim", "wuxia"):
            continue
        if sid.startswith("spy_") and roster_l != "spy":
            continue
        matched = [c for c in s.codes if c in existing_codes_set]
        if not matched:
            continue
        set_options[s.id] = f"{s.name} ({len(matched)}종)"
        matched_codes_by_set[s.id] = matched

    return {
        "char_counts": char_counts,
        "existing_codes": existing_codes,
        "set_options": set_options,
        "matched_codes_by_set": matched_codes_by_set,
    }


def build_asset_web_url(
    rel_path: str,
    retouched_versions: Dict[str, int],
    file_path: Optional[Path] = None,
    mtime: Optional[float] = None,
) -> str:
    """브라우저 캐시 무효화 타임스탬프 쿼리를 포함한 정적 서빙 URL을 생성합니다."""
    ver = retouched_versions.get(rel_path)
    if ver is None:
        if mtime is not None:
            ver = int(mtime * 1000)
        elif file_path is not None:
            try:
                ver = int(file_path.stat().st_mtime * 1000)
            except OSError:
                ver = None
    return f"/projects_static/{rel_path}?t={ver}" if ver else f"/projects_static/{rel_path}"
