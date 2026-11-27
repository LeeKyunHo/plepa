"""
plepa_gui.pages.mobile_viewer
스마트폰 모바일 터치 스와이프 & 3열 그리드 전용 초경량 에셋 검수 뷰어.
정적 에셋(plepa_gui/static/mobile_viewer.{css,html,js})을 로드하여 독립형 HTML 문서를 조립합니다.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import urllib.parse

from nicegui import ui
from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service, pose_display_sort_key
from plepa_gui.components.header import get_active_roster
from plepa_gui.components.retouch_editor import (
    RETOUCH_EDITOR_CSS,
    RETOUCH_EDITOR_HTML,
    build_retouch_editor_script,
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _find_origin_for_asset_path(assets_dir: Path, char: str, asset_file: Path) -> Optional[Path]:
    """에셋 파일에 대응하는 {char}_origin 무검열 원본 경로를 탐색합니다."""
    subfolder = asset_file.parent.name if asset_file.parent != (assets_dir / char) else ""
    candidates: List[Path] = []
    if subfolder:
        candidates.append(assets_dir / f"{char}_origin" / subfolder / asset_file.name)
        candidates.append(assets_dir / char / "_origin" / subfolder / asset_file.name)
    candidates.append(assets_dir / f"{char}_origin" / asset_file.name)
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def _list_available_rosters(target_roster: str) -> List[str]:
    """사용 가능한 로스터 목록을 조회하고 target_roster 포함을 보장합니다."""
    try:
        rosters = [str(r).strip() for r in (default_character_service.list_rosters() or []) if str(r).strip()]
    except Exception:
        rosters = []
    if target_roster and target_roster not in rosters:
        rosters.append(target_roster)
    return rosters or ([target_roster] if target_roster else [DEFAULT_ROSTER])


def _load_manifest_qc_map(cdir: Path) -> Dict[str, Dict[str, Any]]:
    manifest_qc_map: Dict[str, Dict[str, Any]] = {}
    manifest_path = cdir / "_batch_manifest.json"
    if manifest_path.is_file():
        try:
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            for m_item in m_data.get("items", []):
                m_code = str(m_item.get("code", "")).strip()
                if m_code:
                    manifest_qc_map[m_code] = {
                        "qc_passed": m_item.get("qc_passed", True),
                        "qc_reason": m_item.get("qc_reason"),
                    }
        except Exception:
            pass
    return manifest_qc_map


def _collect_char_items(
    c_info: Dict[str, Any],
    assets_dir: Path,
    char_name_map: Dict[str, str],
    today_start: float,
    recent_start: float,
) -> List[Dict[str, Any]]:
    char = c_info["id"]
    cdir = assets_dir / char
    if not cdir.is_dir():
        return []

    manifest_qc_map = _load_manifest_qc_map(cdir)
    char_items: List[Dict[str, Any]] = []
    for f in sorted(cdir.rglob("*.webp")):
        if "_origin" in f.parts or "_censored" in f.name or "_trash" in f.parts:
            continue
        parts = f.stem.split("_", 2)
        code = parts[1] if len(parts) >= 2 else ""
        label = parts[2] if len(parts) >= 3 else ""

        mtime = f.stat().st_mtime
        rel_to_projects = f.relative_to(PROJECTS_DIR).as_posix()
        web_url = "/projects_static/" + urllib.parse.quote(rel_to_projects, safe="/") + f"?t={int(mtime * 1000)}"
        origin_file = _find_origin_for_asset_path(assets_dir, char, f)
        origin_web_url = (
            "/projects_static/"
            + urllib.parse.quote(origin_file.relative_to(PROJECTS_DIR).as_posix(), safe="/")
            + f"?t={int(origin_file.stat().st_mtime * 1000)}"
            if origin_file is not None
            else ""
        )
        qc_meta = manifest_qc_map.get(code, {})
        char_items.append({
            "char": char,
            "char_name": char_name_map.get(char, char),
            "char_short_name": c_info.get("short_name", char),
            "code": code,
            "label": label,
            "filename": f.name,
            "url": web_url,
            "origin_url": origin_web_url,
            "rel_path": rel_to_projects,
            "is_recent": mtime >= recent_start,
            "is_new": mtime >= today_start,
            "mtime": mtime,
            "qc_passed": qc_meta.get("qc_passed", True),
            "qc_reason": qc_meta.get("qc_reason"),
        })
    c_info["count"] = len(char_items)
    return char_items


def get_mobile_gallery_data(roster: Optional[str] = None) -> Dict[str, Any]:
    """모바일 갤러리용 에셋 메타데이터 수집 (로스터 캐릭터 동적 로드)."""
    target_roster = (roster or get_active_roster() or DEFAULT_ROSTER).strip()
    available_rosters = _list_available_rosters(target_roster)
    assets_dir = PROJECTS_DIR / target_roster / "assets"
    if not assets_dir.is_dir():
        return {"items": [], "chars": [], "total_missing": 0, "roster": target_roster, "rosters": available_rosters}

    char_entries = default_character_service.list_characters(target_roster)
    char_defs: List[Dict[str, Any]] = [
        {"id": c.prefix, "name": f"{c.name} ({c.prefix})", "short_name": c.name, "count": 0}
        for _, c, _ in char_entries
    ]
    if not char_defs:
        discovered_dirs = sorted(
            d.name for d in assets_dir.iterdir()
            if d.is_dir() and not d.name.endswith("_origin") and not d.name.startswith("_")
        )
        char_defs = [{"id": pfx, "name": pfx, "short_name": pfx, "count": 0} for pfx in discovered_dirs]

    pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=target_roster)
    char_name_map = {c["id"]: c["name"] for c in char_defs}
    now_ts = time.time()
    today_start, recent_start = now_ts - (24 * 3600), now_ts - (7 * 24 * 3600)

    items: List[Dict[str, Any]] = []
    for c_info in char_defs:
        c_items = _collect_char_items(c_info, assets_dir, char_name_map, today_start, recent_start)
        c_items.sort(key=lambda it: pose_display_sort_key(str(it.get("code") or ""), pose_db.get(str(it.get("code") or ""))))
        items.extend(c_items)

    from plepa_engine.services.asset_service import default_asset_service
    missing_map = default_asset_service.get_missing_poses_by_character(target_roster)
    return {
        "items": items,
        "chars": char_defs,
        "total_missing": sum(len(v) for v in missing_map.values()),
        "roster": target_roster,
        "rosters": available_rosters,
    }


def _short_char_label(char_info: Dict[str, Any]) -> str:
    """캐릭터 dict에서 중복 prefix 없는 짧은 표시명을 추출합니다."""
    short = str(char_info.get("short_name") or "").strip()
    if short:
        return short
    name = str(char_info.get("name") or char_info.get("id") or "").strip()
    cid = str(char_info.get("id") or "").strip()
    suffix = f" ({cid})"
    if cid and name.endswith(suffix):
        return name[: -len(suffix)].strip() or cid
    return name or cid


def generate_mobile_viewer_html(roster: Optional[str] = None) -> str:
    """순수 독립형 모바일 갤러리 HTML 문서 생성."""
    data = get_mobile_gallery_data(roster)
    active_roster = str(data.get("roster") or roster or get_active_roster() or DEFAULT_ROSTER).strip()
    roster_list = [str(r).strip() for r in (data.get("rosters") or []) if str(r).strip()]
    if active_roster and active_roster not in roster_list:
        roster_list.append(active_roster)
    data["rosters"] = roster_list

    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    items = data.get("items") or []
    recent_count = sum(1 for item in items if item.get("is_recent"))
    qc_count = sum(1 for item in items if item.get("qc_passed") is False)
    initial_mode = "recent" if recent_count > 0 else "all"

    roster_options_html = "\n".join(
        f'                    <option value="{html.escape(r, quote=True)}"'
        f'{" selected" if r == active_roster else ""}>{html.escape(r)}</option>'
        for r in roster_list
    )

    char_counts: Dict[str, int] = {}
    for it in items:
        cid = str(it.get("char") or "")
        char_counts[cid] = char_counts.get(cid, 0) + 1

    sorted_chars = sorted(
        enumerate(data.get("chars", [])),
        key=lambda pair: (char_counts.get(str(pair[1].get("id") or ""), pair[1].get("count", 0)) == 0, pair[0]),
    )
    char_buttons_html = "\n".join(
        f'                <button type="button" class="btn-chip" id="char_{html.escape(str(c["id"]), quote=True)}" '
        f'style="{"opacity:0.55;" if char_counts.get(str(c["id"]), c.get("count", 0)) == 0 else ""}" '
        f'onclick="setCharFilter({json.dumps(c["id"])})">'
        f'{html.escape(_short_char_label(c))} ({char_counts.get(str(c["id"]), c.get("count", 0))})</button>'
        for _, c in sorted_chars
    )

    retouch_script_html = build_retouch_editor_script(
        on_saved_js="""
            if (typeof onPlepaMobileRetouchSaved === 'function') {
                onPlepaMobileRetouchSaved(savedPayload);
            }
        """,
        on_notify_js="if (typeof showToast === 'function') { showToast(msg); }",
    )

    css_text = (_STATIC_DIR / "mobile_viewer.css").read_text(encoding="utf-8").rstrip("\n")
    js_text = (
        (_STATIC_DIR / "mobile_viewer.js")
        .read_text(encoding="utf-8")
        .rstrip("\n")
        .replace("__DATA_JSON__", data_json, 1)
        .replace("__INITIAL_MODE__", initial_mode, 1)
    )
    tpl = (_STATIC_DIR / "mobile_viewer.html").read_text(encoding="utf-8")
    return (
        tpl.replace("__MOBILE_VIEWER_CSS__", css_text, 1)
        .replace("__RETOUCH_EDITOR_CSS__", RETOUCH_EDITOR_CSS, 1)
        .replace("__ROSTER_OPTIONS_HTML__", roster_options_html, 1)
        .replace("__CHIP_ALL_ACTIVE__", "active" if initial_mode == "all" else "", 1)
        .replace("__CHIP_RECENT_ACTIVE__", "active" if initial_mode == "recent" else "", 1)
        .replace("__RECENT_COUNT__", str(recent_count), 1)
        .replace("__CHIP_QC_WARN__", "has-warn" if qc_count > 0 else "", 1)
        .replace("__QC_COUNT__", str(qc_count), 1)
        .replace("__CHAR_BUTTONS_HTML__", char_buttons_html, 1)
        .replace("__MOBILE_VIEWER_JS__", js_text, 1)
        .replace("__RETOUCH_EDITOR_HTML__", RETOUCH_EDITOR_HTML, 1)
        .replace("__RETOUCH_SCRIPT_HTML__", retouch_script_html, 1)
    )


def render_mobile_viewer_page(roster: Optional[str] = None) -> None:
    """하위 호환용 NiceGUI 페이지 래퍼."""
    html_content = generate_mobile_viewer_html(roster or get_active_roster())
    ui.html(html_content)
