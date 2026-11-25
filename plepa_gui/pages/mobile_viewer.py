"""
plepa_gui.pages.mobile_viewer
스마트폰 모바일 터치 스와이프 & 3열 그리드 전용 초경량 에셋 검수 뷰어.
- 순수 HTML5/CSS3/Vanilla JS 기반 초경량 고속 렌더링 (Kiro 스타일 점진적 청크·순차 이미지 로딩)
- 상단 초슬림 1행 헤더(로스터 즉시 전환 / 그리드 토글 / 카운터 / 설정 시트) + 2행 필터 바(전체·최근·오늘·QC경고 + 캐릭터 칩)
- 하단 2단 수직 스택 바(메타데이터 줄바꿈/중복 제거 + 균등 5분할 원터치 액션)
- [🗑️ 즉시 삭제 (휴지통 & 실행취소 Undo)]
- [🔄 무검열 원본 복원] / [✏️ 직접검열 캔버스] / [⚡ 0.2초 재검열] / [🎲 단독 리롤] / [⚡ 누락 채우기]
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
from plepa_gui.components.header import get_active_roster
from plepa_gui.components.retouch_editor import (
    RETOUCH_EDITOR_CSS,
    RETOUCH_EDITOR_HTML,
    build_retouch_editor_script,
)


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


def get_mobile_gallery_data(roster: Optional[str] = None) -> Dict[str, Any]:
    """모바일 갤러리용 에셋 메타데이터 수집 (로스터 캐릭터 동적 로드)."""
    target_roster = (roster or get_active_roster() or DEFAULT_ROSTER).strip()
    available_rosters = _list_available_rosters(target_roster)
    assets_dir = PROJECTS_DIR / target_roster / "assets"
    if not assets_dir.is_dir():
        return {
            "items": [],
            "chars": [],
            "total_missing": 0,
            "roster": target_roster,
            "rosters": available_rosters,
        }

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

    char_name_map = {c["id"]: c["name"] for c in char_defs}
    now_ts = time.time()
    today_start = now_ts - (24 * 3600)
    recent_start = now_ts - (7 * 24 * 3600)

    items: List[Dict[str, Any]] = []
    for c_info in char_defs:
        char = c_info["id"]
        cdir = assets_dir / char
        if not cdir.is_dir():
            continue

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

        char_count = 0
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

            is_newly_generated = mtime >= today_start
            is_recent_mod = mtime >= recent_start
            qc_meta = manifest_qc_map.get(code, {})
            char_count += 1

            items.append({
                "char": char,
                "char_name": char_name_map.get(char, char),
                "char_short_name": c_info.get("short_name", char),
                "code": code,
                "label": label,
                "filename": f.name,
                "url": web_url,
                "origin_url": origin_web_url,
                "rel_path": rel_to_projects,
                "is_recent": is_recent_mod,
                "is_new": is_newly_generated,
                "mtime": mtime,
                "qc_passed": qc_meta.get("qc_passed", True),
                "qc_reason": qc_meta.get("qc_reason"),
            })
        c_info["count"] = char_count

    from plepa_engine.services.asset_service import default_asset_service
    missing_map = default_asset_service.get_missing_poses_by_character(target_roster)
    total_missing = sum(len(v) for v in missing_map.values())

    return {
        "items": items,
        "chars": char_defs,
        "total_missing": total_missing,
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

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>📱 PLEPA Mobile Studio</title>
    <style>
        * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
        html, body {{
            margin: 0; padding: 0; width: 100%; height: 100%; height: 100dvh;
            background: #020617; color: #f8fafc; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            user-select: none; -webkit-user-select: none;
        }}
        .viewer-container {{
            position: relative; width: 100%; height: 100dvh;
            display: flex; flex-direction: column; overflow: hidden;
            background: #020617;
        }}
        .viewer-container.immersive .top-bar,
        .viewer-container.immersive .bottom-bar {{
            display: none !important;
        }}

        /* 상단 초슬림 헤더 + 필터 스트립 */
        .top-bar {{
            position: relative; flex-shrink: 0; z-index: 30;
            background: rgba(15, 23, 42, 0.96);
            border-bottom: 1px solid rgba(51, 65, 85, 0.55);
            backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
            padding-top: max(6px, env(safe-area-inset-top));
        }}
        .header-row {{
            display: flex; align-items: center; justify-content: space-between;
            gap: 6px; padding: 4px 10px 6px; width: 100%;
        }}
        .header-left {{
            display: flex; align-items: center; gap: 6px; min-width: 0; flex: 1;
        }}
        .header-right {{
            display: flex; align-items: center; gap: 6px; flex-shrink: 0;
        }}
        .hdr-icon-btn {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 34px; height: 34px; border-radius: 9px; flex-shrink: 0;
            background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(71, 85, 105, 0.7);
            color: #cbd5e1; font-size: 14px; text-decoration: none; cursor: pointer;
        }}
        .hdr-icon-btn:active {{ transform: scale(0.94); }}
        .roster-select {{
            height: 34px; max-width: 148px; min-width: 84px;
            background: rgba(30, 41, 59, 0.95); border: 1px solid rgba(56, 189, 248, 0.5);
            color: #38bdf8; border-radius: 9px; padding: 0 8px;
            font-size: 13px; font-weight: 700; outline: none;
        }}
        .hdr-pill-btn {{
            height: 34px; padding: 0 10px; border-radius: 9px; white-space: nowrap;
            background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(71, 85, 105, 0.7);
            color: #e2e8f0; font-size: 12px; font-weight: 700; cursor: pointer;
            display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0;
        }}
        .hdr-pill-btn.active {{
            background: rgba(37, 99, 235, 0.35); border-color: #60a5fa; color: #ffffff;
        }}
        .counter-badge {{
            height: 34px; padding: 0 9px; border-radius: 9px; white-space: nowrap;
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 12px; font-weight: 700; color: #cbd5e1;
            background: rgba(30, 41, 59, 0.85); border: 1px solid rgba(51, 65, 85, 0.7);
            font-variant-numeric: tabular-nums;
        }}
        .job-queue-badge {{
            height: 28px; padding: 0 8px; border-radius: 9999px; white-space: nowrap;
            display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0;
            font-size: 11px; font-weight: 700; color: #fde68a;
            background: rgba(120, 53, 15, 0.75); border: 1px solid rgba(245, 158, 11, 0.65);
        }}

        .filter-strip {{
            display: flex; align-items: center; gap: 6px;
            overflow-x: auto; overflow-y: hidden;
            padding: 2px 10px 8px; scrollbar-width: none;
            -webkit-overflow-scrolling: touch;
        }}
        .filter-strip::-webkit-scrollbar {{ display: none; }}
        .chip-divider {{
            width: 1px; height: 18px; background: rgba(71, 85, 105, 0.55);
            flex: 0 0 auto; margin: 0 2px;
        }}
        .btn-chip {{
            background: rgba(30, 41, 59, 0.85); border: 1px solid rgba(71, 85, 105, 0.6);
            color: #cbd5e1; padding: 6px 11px; border-radius: 9999px; font-size: 12px;
            font-weight: 600; cursor: pointer; white-space: nowrap; flex: 0 0 auto;
            transition: all 0.15s ease; display: inline-flex; align-items: center; gap: 4px;
        }}
        .btn-chip.active {{
            background: #2563eb; border-color: #60a5fa; color: #ffffff;
            box-shadow: 0 0 10px rgba(37, 99, 235, 0.55);
        }}
        .btn-chip.chip-qc.has-warn {{
            border-color: rgba(245, 158, 11, 0.65); color: #fcd34d;
        }}
        .btn-chip.chip-qc.active {{
            background: #d97706; border-color: #fbbf24; color: #ffffff;
            box-shadow: 0 0 10px rgba(217, 119, 6, 0.55);
        }}

        /* 메인 뷰포트 */
        .main-viewport {{
            flex: 1; min-height: 0; position: relative; overflow: hidden;
            background: #020617;
        }}
        .stage {{
            width: 100%; height: 100%; position: relative;
            display: flex; align-items: center; justify-content: center;
            overflow: hidden; touch-action: pan-y pinch-zoom;
        }}
        .slide-img {{
            max-width: 100%; max-height: 100%; width: auto; height: auto;
            object-fit: contain;
            transition: opacity 0.18s ease;
            box-shadow: 0 16px 36px rgba(0, 0, 0, 0.75);
        }}
        .slide-spinner {{
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            background: rgba(15, 23, 42, 0.88); border: 1px solid rgba(56, 189, 248, 0.45);
            color: #e2e8f0; padding: 6px 12px; border-radius: 9999px;
            font-size: 12px; font-weight: 600; pointer-events: none;
            display: none; z-index: 15;
        }}
        .slide-spinner.visible {{ display: inline-flex; align-items: center; gap: 6px; }}
        .nav-tap-zone {{
            position: absolute; top: 0; bottom: 0; width: 24%; z-index: 10;
        }}
        .nav-tap-left {{ left: 0; }}
        .nav-tap-right {{ right: 0; }}
        .nav-indicator {{
            position: absolute; top: 50%; transform: translateY(-50%);
            background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(51, 65, 85, 0.6);
            color: #94a3b8; width: 34px; height: 34px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            opacity: 0; transition: opacity 0.2s ease; pointer-events: none; z-index: 11;
        }}
        .nav-indicator.left {{ left: 10px; }}
        .nav-indicator.right {{ right: 10px; }}
        @media (hover: hover) {{
            .stage:hover .nav-indicator {{ opacity: 0.75; }}
        }}

        /* 3열 썸네일 그리드 (Kiro 스타일 점진 순차 청크 로드) */
        .grid-view {{
            display: none; width: 100%; height: 100%; overflow-y: auto;
            -webkit-overflow-scrolling: touch; padding: 8px 8px 28px;
        }}
        .grid-container {{
            display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 6px; width: 100%;
        }}
        .grid-card {{
            position: relative; background: #0f172a; border: 1px solid #1e293b;
            border-radius: 10px; overflow: hidden; cursor: pointer;
            display: flex; flex-direction: column;
        }}
        .grid-card.active-card {{
            border-color: #38bdf8; box-shadow: 0 0 0 1px #38bdf8;
        }}
        .grid-thumb-wrap {{
            position: relative; width: 100%; aspect-ratio: 3 / 4;
            background: #0f172a; overflow: hidden;
        }}
        .grid-thumb-wrap.loading {{
            background: linear-gradient(110deg, #0f172a 20%, #1e293b 50%, #0f172a 80%);
            background-size: 200% 100%;
            animation: plepaSkeleton 1.2s linear infinite;
        }}
        @keyframes plepaSkeleton {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}
        .grid-thumb {{
            width: 100%; height: 100%; object-fit: cover; display: block;
            opacity: 0; transition: opacity 0.2s ease;
        }}
        .grid-thumb.loaded {{ opacity: 1; }}
        .grid-qc-badge {{
            position: absolute; top: 4px; right: 4px;
            background: rgba(217, 119, 6, 0.92); color: #ffffff;
            font-size: 10px; font-weight: 800; padding: 1px 5px; border-radius: 9999px;
        }}
        .grid-caption {{
            padding: 4px 6px; font-size: 10px; font-weight: 600; color: #cbd5e1;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            border-top: 1px solid rgba(30, 41, 59, 0.9);
        }}
        .grid-status {{
            text-align: center; font-size: 11px; color: #64748b; padding: 14px 8px 20px;
        }}

        /* 하단 2단 수직 스택 컨트롤 바 */
        .bottom-bar {{
            position: relative; flex-shrink: 0; z-index: 30;
            background: rgba(15, 23, 42, 0.96);
            border-top: 1px solid rgba(51, 65, 85, 0.55);
            backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
            padding: 8px 10px max(10px, env(safe-area-inset-bottom));
            display: flex; flex-direction: column; gap: 8px;
        }}
        .meta-row {{
            display: flex; align-items: center; justify-content: space-between;
            gap: 8px; width: 100%;
        }}
        .meta-text {{
            flex: 1; min-width: 0;
        }}
        .pose-title {{
            font-size: 14px; font-weight: 700; color: #f8fafc;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .pose-subtitle {{
            font-size: 11px; color: #94a3b8; margin-top: 2px;
            display: flex; align-items: center; gap: 6px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .qc-inline-badge {{
            display: inline-block; background: rgba(217, 119, 6, 0.25);
            border: 1px solid rgba(251, 191, 36, 0.6); color: #fcd34d;
            font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 9999px;
            max-width: 58%; overflow: hidden; text-overflow: ellipsis;
        }}
        .nav-pair {{
            display: flex; align-items: center; gap: 6px; flex-shrink: 0;
        }}
        .btn-nav-mini {{
            width: 36px; height: 34px; border-radius: 9px; border: 1px solid rgba(71, 85, 105, 0.7);
            background: rgba(30, 41, 59, 0.9); color: #e2e8f0; font-size: 14px; font-weight: 700;
            cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
        }}
        .btn-nav-mini.primary {{
            background: #2563eb; border-color: #60a5fa; color: #ffffff;
        }}
        .btn-nav-mini:active {{ transform: scale(0.93); }}

        .action-grid {{
            display: grid; grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 6px; width: 100%;
        }}
        .btn-action {{
            min-height: 46px; padding: 5px 2px; border-radius: 10px;
            cursor: pointer; border: 1px solid transparent;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            gap: 2px; transition: transform 0.12s ease; white-space: nowrap;
        }}
        .btn-action:active {{ transform: scale(0.95); }}
        .act-ico {{ font-size: 15px; line-height: 1.1; }}
        .act-lbl {{ font-size: 11px; font-weight: 700; line-height: 1.1; }}
        .btn-delete {{
            background: rgba(225, 29, 72, 0.22); border-color: rgba(244, 63, 94, 0.6); color: #fda4af;
        }}
        .btn-origin {{
            background: rgba(217, 119, 6, 0.22); border-color: rgba(251, 191, 36, 0.6); color: #fcd34d;
        }}
        .btn-retouch {{
            background: rgba(16, 185, 129, 0.22); border-color: rgba(52, 211, 153, 0.65); color: #6ee7b7;
        }}
        .btn-recensor {{
            background: rgba(37, 99, 235, 0.25); border-color: rgba(96, 165, 250, 0.65); color: #93c5fd;
        }}
        .btn-reroll {{
            background: rgba(139, 92, 246, 0.22); border-color: rgba(167, 139, 250, 0.6); color: #c4b5fd;
        }}

        /* ⚙️ 설정 바텀시트 */
        .sheet-backdrop {{
            position: fixed; inset: 0; z-index: 80;
            background: rgba(2, 6, 23, 0.65); backdrop-filter: blur(4px);
            display: none;
        }}
        .sheet-backdrop.open {{ display: block; }}
        .settings-sheet {{
            position: fixed; left: 0; right: 0; bottom: 0; z-index: 81;
            background: #0f172a; border-top: 1px solid #334155;
            border-radius: 18px 18px 0 0; padding: 14px 16px max(18px, env(safe-area-inset-bottom));
            box-shadow: 0 -14px 40px rgba(0, 0, 0, 0.75);
            transform: translateY(105%); transition: transform 0.22s ease-out;
        }}
        .settings-sheet.open {{ transform: translateY(0); }}
        .sheet-head {{
            display: flex; align-items: center; justify-content: space-between;
            margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #1e293b;
        }}
        .sheet-title {{ font-size: 15px; font-weight: 800; color: #f8fafc; }}
        .sheet-close {{
            width: 30px; height: 30px; border-radius: 8px; border: 1px solid #334155;
            background: #1e293b; color: #cbd5e1; font-size: 14px; cursor: pointer;
        }}
        .sheet-row {{
            display: flex; align-items: center; justify-content: space-between;
            gap: 10px; padding: 8px 0;
        }}
        .sheet-label {{ font-size: 13px; font-weight: 600; color: #cbd5e1; }}
        .censor-select-mini {{
            background: #020617; border: 1px solid #475569; color: #f8fafc;
            border-radius: 8px; padding: 7px 10px; font-size: 13px; outline: none;
            min-width: 165px;
        }}
        .sheet-actions {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px;
        }}
        .sheet-btn {{
            padding: 10px 10px; border-radius: 10px; font-size: 12px; font-weight: 700;
            background: #1e293b; border: 1px solid #334155; color: #e2e8f0;
            text-align: center; text-decoration: none; cursor: pointer;
        }}
        .sheet-btn.active {{
            background: #2563eb; border-color: #60a5fa; color: #ffffff;
        }}
        .btn-fill {{
            background: #059669; border-color: #34d399; color: #ffffff;
        }}
        .queue-section {{
            margin-top: 6px; padding-top: 8px; border-top: 1px solid #1e293b;
        }}
        .queue-section-title {{
            font-size: 12px; font-weight: 700; color: #cbd5e1;
            margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;
        }}
        .queue-panel {{
            max-height: 220px; overflow-y: auto; background: #020617;
            border: 1px solid #1e293b; border-radius: 10px; padding: 8px 10px;
            display: flex; flex-direction: column; gap: 6px;
        }}
        .q-item {{
            font-size: 11px; color: #cbd5e1; background: rgba(15, 23, 42, 0.92);
            border: 1px solid #1e293b; border-radius: 8px; padding: 6px 8px;
        }}
        .q-item.running {{ border-color: rgba(56, 189, 248, 0.65); }}
        .q-item.queued {{ border-color: rgba(245, 158, 11, 0.45); }}
        .q-item-top {{
            display: flex; justify-content: space-between; align-items: center;
            gap: 6px; font-weight: 700;
        }}
        .q-item-sub {{
            font-size: 10px; color: #94a3b8; margin-top: 2px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .q-bar-bg {{
            width: 100%; height: 5px; background: #1e293b;
            border-radius: 9999px; overflow: hidden; margin-top: 5px;
        }}
        .q-bar-fill {{
            height: 100%; background: #38bdf8; transition: width 0.25s ease;
        }}

        /* 토스트 알림 배너 */
        #toastBanner {{
            position: fixed; top: max(14px, env(safe-area-inset-top)); left: 50%;
            transform: translateX(-50%) translateY(-120px);
            background: rgba(15, 23, 42, 0.96); border: 1px solid #38bdf8; color: #f8fafc;
            padding: 9px 16px; border-radius: 9999px; font-size: 12px; font-weight: 600;
            z-index: 120; box-shadow: 0 10px 25px rgba(0,0,0,0.7);
            display: flex; align-items: center; gap: 8px;
            max-width: 92vw; transition: transform 0.25s cubic-bezier(0.18, 0.89, 0.32, 1.28);
            pointer-events: none;
        }}
        #toastBanner.show {{
            transform: translateX(-50%) translateY(0); pointer-events: auto;
        }}
        .btn-undo {{
            background: #38bdf8; color: #020617; border: none; padding: 4px 10px;
            border-radius: 9999px; font-size: 11px; font-weight: 800; cursor: pointer;
            white-space: nowrap;
        }}
    </style>
    {RETOUCH_EDITOR_CSS}
</head>
<body>
    <!-- 토스트 배너 -->
    <div id="toastBanner">
        <span id="toastMsg">알림</span>
        <button id="toastUndoBtn" type="button" class="btn-undo" style="display:none;" onclick="triggerUndo()">실행 취소</button>
    </div>

    <div id="mobileApp" class="viewer-container">
        <!-- 상단 초슬림 헤더 + 필터 바 -->
        <header id="topOverlay" class="top-bar">
            <div class="header-row">
                <div class="header-left">
                    <a href="/gallery" class="hdr-icon-btn" title="PC 스튜디오">❮</a>
                    <select id="rosterSelect" class="roster-select" onchange="switchRoster(this.value)" title="로스터 즉시 전환">
{roster_options_html}
                    </select>
                </div>
                <div class="header-right">
                    <span id="jobQueueBadge" class="job-queue-badge" style="display:none; cursor:pointer;" onclick="toggleSettingsSheet()" title="백그라운드 리롤 대기열 상세 보기"></span>
                    <button type="button" id="viewToggleBtn" class="hdr-pill-btn" onclick="toggleViewMode()" title="3열 그리드 모아보기 전환">⊞ 그리드</button>
                    <div id="counterBadge" class="counter-badge">0 / 0</div>
                    <button type="button" id="refreshBtn" class="hdr-icon-btn" onclick="manualRefreshGallery()" title="최신 에셋 새로고침">🔄</button>
                    <button type="button" id="settingsBtn" class="hdr-icon-btn" onclick="toggleSettingsSheet()" title="검열/정렬/일괄 설정">⚙️</button>
                </div>
            </div>
            <div class="filter-strip">
                <button type="button" class="btn-chip {'active' if initial_mode == 'all' else ''}" id="chipAll" onclick="setMode('all')">📂 전체</button>
                <button type="button" class="btn-chip {'active' if initial_mode == 'recent' else ''}" id="chipRecent" onclick="setMode('recent')">✨ 최근 (<span id="recentCountText">{recent_count}</span>)</button>
                <button type="button" class="btn-chip" id="chipNew" onclick="setMode('new')">🆕 오늘</button>
                <button type="button" class="btn-chip chip-qc {'has-warn' if qc_count > 0 else ''}" id="chipQc" onclick="setMode('qc')">⚠️ QC (<span id="qcCountText">{qc_count}</span>)</button>
                <div class="chip-divider"></div>
                <div id="charChipsWrap" style="display:flex; align-items:center; gap:6px; flex:0 0 auto;">
                    <button type="button" class="btn-chip" id="char_all" onclick="setCharFilter('all')">전체캐릭</button>
{char_buttons_html}
                </div>
            </div>
        </header>

        <!-- 메인 스테이지 (슬라이드 & 3열 그리드 전환) -->
        <main class="main-viewport">
            <div class="stage" id="stage" onclick="onStageClick(event)">
                <div class="nav-tap-zone nav-tap-left" onclick="prev(event)"></div>
                <div class="nav-tap-zone nav-tap-right" onclick="next(event)"></div>
                <div class="nav-indicator left">❮</div>
                <div class="nav-indicator right">❯</div>
                <div id="slideSpinner" class="slide-spinner">⏳ 불러오는 중...</div>
                <img id="mainImg" class="slide-img" src="" alt="에셋" />
            </div>

            <div class="grid-view" id="gridView">
                <div class="grid-container" id="gridContainer"></div>
                <div class="grid-status" id="gridLoadStatus"></div>
            </div>
        </main>

        <!-- 하단 2단 수직 스택 컨트롤 바 (슬라이드 모드 전용) -->
        <footer id="bottomOverlay" class="bottom-bar">
            <div class="meta-row">
                <div class="meta-text">
                    <div id="poseTitle" class="pose-title">포즈 정보</div>
                    <div id="poseSubtitle" class="pose-subtitle">캐릭터</div>
                </div>
                <div class="nav-pair">
                    <button type="button" class="btn-nav-mini" onclick="prev(event)" title="이전">❮</button>
                    <button type="button" class="btn-nav-mini primary" onclick="next(event)" title="다음">❯</button>
                </div>
            </div>
            <div class="action-grid">
                <button type="button" class="btn-action btn-delete" onclick="triggerDelete(event)" title="에셋 삭제 및 휴지통 이동">
                    <span class="act-ico">🗑️</span><span class="act-lbl">삭제</span>
                </button>
                <button type="button" class="btn-action btn-origin" onclick="triggerRestoreOrigin(event)" title="무검열 원본(_origin) 복원">
                    <span class="act-ico">🔄</span><span class="act-lbl">원본</span>
                </button>
                <button type="button" class="btn-action btn-retouch" onclick="triggerRetouch(event)" title="브러시 직접 검열/덧칠">
                    <span class="act-ico">✏️</span><span class="act-lbl">직접</span>
                </button>
                <button type="button" class="btn-action btn-recensor" onclick="triggerReapplyCensor(event)" title="0.2초 즉시 재검열">
                    <span class="act-ico">⚡</span><span class="act-lbl">재검열</span>
                </button>
                <button type="button" class="btn-action btn-reroll" onclick="triggerReroll(event)" title="새 시드 즉시 리롤">
                    <span class="act-ico">🎲</span><span class="act-lbl">리롤</span>
                </button>
            </div>
        </footer>
    </div>

    <!-- ⚙️ 설정 바텀시트 -->
    <div id="settingsBackdrop" class="sheet-backdrop" onclick="closeSettingsSheet()"></div>
    <div id="settingsSheet" class="settings-sheet" onclick="event.stopPropagation()">
        <div class="sheet-head">
            <span class="sheet-title">⚙️ 검열 · 정렬 · 일괄 작업</span>
            <button type="button" class="sheet-close" onclick="closeSettingsSheet()">✕</button>
        </div>
        <div class="sheet-row">
            <span class="sheet-label">검열 스타일</span>
            <select id="censorStyleSelect" class="censor-select-mini" title="즉시 재검열 및 리롤 스타일">
                <option value="white_silhouette" selected>white_silhouette</option>
                <option value="black_silhouette">black_silhouette</option>
                <option value="manga_bar">manga_bar</option>
                <option value="manga_glow">manga_glow</option>
                <option value="mosaic">mosaic</option>
                <option value="bar">bar</option>
                <option value="slim_bar">slim_bar</option>
                <option value="shadow">shadow</option>
                <option value="debug_bbox">debug_bbox</option>
            </select>
        </div>
        <div class="queue-section">
            <div class="queue-section-title">
                <span>🎲 대기열 · 진행 현황</span>
                <span id="queueSummaryText" style="font-size:11px;color:#94a3b8;">확인 중...</span>
            </div>
            <div id="queueStatusPanel" class="queue-panel">
                <div style="text-align:center;color:#64748b;font-size:11px;padding:12px 0;">대기열 상태를 불러오는 중...</div>
            </div>
        </div>
        <div class="sheet-actions">
            <button type="button" class="sheet-btn" id="chipSort" onclick="toggleSortOrder()">🕒 최신생성순</button>
            <button type="button" class="sheet-btn btn-fill" id="fillMissingBtn" onclick="triggerFillMissing()">⚡ 누락 채우기 (<span id="missingCountBadge">0</span>)</button>
            <a href="/gallery" class="sheet-btn" style="grid-column: span 2;">💻 PC 스튜디오 (/gallery) 열기</a>
        </div>
    </div>

    <script>
        const MOBILE_CHUNK_SIZE = 18;
        const MAX_CONCURRENT_IMG = 3;

        let rawData = {data_json};
        let currentMode = '{initial_mode}'; // 'all', 'recent', 'new', 'qc'
        let currentChar = 'all';
        let currentSort = 'code_asc'; // 'code_asc' or 'mtime_desc'
        let currentView = 'slide'; // 'slide' or 'grid'
        let filteredItems = [];
        let currentIndex = 0;
        let lastDeletedBundle = null;
        let toastTimeout = null;
        let immersiveMode = false;

        let renderSeq = 0;
        let slideLoadSeq = 0;
        let gridObserver = null;
        let imgLoadQueue = [];
        let activeImgLoads = 0;
        let isPollingJob = false;
        let isRefreshingGallery = false;
        let lastCompletedSig = '';
        let jobPollInitialized = false;

        function escapeHtml(str) {{
            return String(str ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }}

        function formatCharSubtitle(item) {{
            const cid = String(item.char || '');
            let shortNm = String(item.char_short_name || '').trim();
            if (!shortNm) {{
                const fullNm = String(item.char_name || cid).trim();
                const suffix = ' (' + cid + ')';
                shortNm = (cid && fullNm.endsWith(suffix))
                    ? fullNm.slice(0, -suffix.length).trim()
                    : fullNm;
            }}
            if (!cid || shortNm === cid) return shortNm || cid;
            return shortNm + ' (' + cid + ')';
        }}

        function showToast(msg, canUndo = false) {{
            const el = document.getElementById('toastBanner');
            document.getElementById('toastMsg').innerText = msg;
            const undoBtn = document.getElementById('toastUndoBtn');
            undoBtn.style.display = canUndo ? 'inline-block' : 'none';
            el.classList.add('show');
            if (toastTimeout) clearTimeout(toastTimeout);
            toastTimeout = setTimeout(() => {{
                el.classList.remove('show');
            }}, 5000);
        }}

        function toggleSettingsSheet() {{
            const open = !document.getElementById('settingsSheet').classList.contains('open');
            document.getElementById('settingsBackdrop').classList.toggle('open', open);
            document.getElementById('settingsSheet').classList.toggle('open', open);
            if (open) pollJobStatus();
        }}

        function closeSettingsSheet() {{
            document.getElementById('settingsBackdrop').classList.remove('open');
            document.getElementById('settingsSheet').classList.remove('open');
        }}

        function updateModeCounts() {{
            const items = rawData.items || [];
            const recentCnt = items.filter(i => i.is_recent).length;
            const qcCnt = items.filter(i => i.qc_passed === false).length;
            const recEl = document.getElementById('recentCountText');
            const qcEl = document.getElementById('qcCountText');
            const qcBtn = document.getElementById('chipQc');
            if (recEl) recEl.innerText = recentCnt;
            if (qcEl) qcEl.innerText = qcCnt;
            if (qcBtn) qcBtn.classList.toggle('has-warn', qcCnt > 0);
            const missEl = document.getElementById('missingCountBadge');
            if (missEl) missEl.innerText = rawData.total_missing || 0;
        }}

        function renderRosterSelect() {{
            const sel = document.getElementById('rosterSelect');
            if (!sel) return;
            const list = (rawData.rosters && rawData.rosters.length)
                ? rawData.rosters
                : [rawData.roster || 'campus'];
            sel.innerHTML = list.map(r => {{
                const esc = escapeHtml(r);
                const selected = r === rawData.roster ? ' selected' : '';
                return '<option value="' + esc + '"' + selected + '>' + esc + '</option>';
            }}).join('');
        }}

        function renderCharChips() {{
            const wrap = document.getElementById('charChipsWrap');
            if (!wrap) return;
            const items = rawData.items || [];
            const counts = {{}};
            items.forEach(it => {{
                counts[it.char] = (counts[it.char] || 0) + 1;
            }});
            const chars = (rawData.chars || []).slice().sort((a, b) => {{
                const ca = counts[a.id] ?? a.count ?? 0;
                const cb = counts[b.id] ?? b.count ?? 0;
                if ((ca === 0) !== (cb === 0)) return ca === 0 ? 1 : -1;
                return 0;
            }});

            let htmlStr = '<button type="button" class="btn-chip ' + (currentChar === 'all' ? 'active' : '') +
                '" id="char_all" onclick="setCharFilter(&quot;all&quot;)">전체캐릭 (' + items.length + ')</button>';

            chars.forEach(c => {{
                const cid = String(c.id || '');
                const cnt = counts[cid] ?? c.count ?? 0;
                const sName = c.short_name || (c.name ? String(c.name).replace(/\\s*\\([^)]*\\)$/, '') : cid);
                const dimStyle = cnt === 0 ? ' style="opacity:0.5;"' : '';
                const activeCls = currentChar === cid ? ' active' : '';
                htmlStr += '<button type="button" class="btn-chip' + activeCls + '" id="char_' + escapeHtml(cid) + '"' +
                    dimStyle + ' onclick="setCharFilter(' + JSON.stringify(cid).replace(/"/g, '&quot;') + ')">' +
                    escapeHtml(sName) + ' (' + cnt + ')</button>';
            }});
            wrap.innerHTML = htmlStr;
        }}

        function applyFilters(preserveRelPath = null) {{
            const items = rawData.items || [];
            filteredItems = items.filter(item => {{
                if (currentMode === 'recent' && !item.is_recent) return false;
                if (currentMode === 'new' && !item.is_new) return false;
                if (currentMode === 'qc' && item.qc_passed !== false) return false;
                if (currentChar !== 'all' && item.char !== currentChar) return false;
                return true;
            }});
            if (currentSort === 'mtime_desc') {{
                filteredItems.sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
            }}
            if (preserveRelPath) {{
                const keptIdx = filteredItems.findIndex(it => it.rel_path === preserveRelPath);
                if (keptIdx >= 0) currentIndex = keptIdx;
            }}
            if (currentIndex >= filteredItems.length) {{
                currentIndex = Math.max(0, filteredItems.length - 1);
            }}
            updateModeCounts();
            updateView();
            if (currentView === 'grid') {{
                renderGrid();
            }}
        }}

        function toggleSortOrder() {{
            currentSort = currentSort === 'mtime_desc' ? 'code_asc' : 'mtime_desc';
            const sortBtn = document.getElementById('chipSort');
            if (sortBtn) {{
                sortBtn.classList.toggle('active', currentSort === 'mtime_desc');
                sortBtn.textContent = currentSort === 'mtime_desc' ? '🕒 최신생성순 ✓' : '🕒 최신생성순';
            }}
            currentIndex = 0;
            applyFilters();
            if (currentSort === 'mtime_desc') {{
                refreshGalleryData(true);
            }}
        }}

        function setMode(mode) {{
            currentMode = mode;
            document.getElementById('chipAll').classList.toggle('active', mode === 'all');
            document.getElementById('chipRecent').classList.toggle('active', mode === 'recent');
            document.getElementById('chipNew').classList.toggle('active', mode === 'new');
            document.getElementById('chipQc').classList.toggle('active', mode === 'qc');
            currentIndex = 0;
            applyFilters();
        }}

        function setCharFilter(charId) {{
            currentChar = charId;
            const charIds = ['all'].concat((rawData.chars || []).map(c => c.id));
            charIds.forEach(c => {{
                const el = document.getElementById('char_' + c);
                if (el) el.classList.toggle('active', c === charId);
            }});
            currentIndex = 0;
            applyFilters();
        }}

        function toggleViewMode(forceMode = null) {{
            const nextView = forceMode || (currentView === 'slide' ? 'grid' : 'slide');
            currentView = nextView;
            const isGrid = currentView === 'grid';

            if (isGrid && immersiveMode) {{
                immersiveMode = false;
                document.getElementById('mobileApp').classList.remove('immersive');
            }}

            document.getElementById('stage').style.display = isGrid ? 'none' : 'flex';
            document.getElementById('gridView').style.display = isGrid ? 'block' : 'none';
            document.getElementById('bottomOverlay').style.display = isGrid ? 'none' : 'flex';

            const btn = document.getElementById('viewToggleBtn');
            if (btn) {{
                btn.classList.toggle('active', isGrid);
                btn.textContent = isGrid ? '🖼️ 슬라이드' : '⊞ 그리드';
            }}

            if (isGrid) {{
                renderGrid();
            }} else {{
                cancelGridQueue();
                updateView();
            }}
        }}

        function openSlideAt(idx) {{
            currentIndex = Math.max(0, Math.min(idx, Math.max(0, filteredItems.length - 1)));
            toggleViewMode('slide');
        }}

        function cancelGridQueue() {{
            ++renderSeq;
            imgLoadQueue = [];
            activeImgLoads = 0;
            if (gridObserver) {{
                gridObserver.disconnect();
                gridObserver = null;
            }}
        }}

        function pumpImageQueue(expectedSeq) {{
            while (activeImgLoads < MAX_CONCURRENT_IMG && imgLoadQueue.length > 0) {{
                const job = imgLoadQueue.shift();
                if (!job || job.seq !== renderSeq || !job.img || !job.img.isConnected) continue;
                const src = job.img.dataset.src;
                if (!src) continue;
                activeImgLoads++;
                job.img.onload = () => {{
                    activeImgLoads = Math.max(0, activeImgLoads - 1);
                    job.img.classList.add('loaded');
                    if (job.img.parentElement) job.img.parentElement.classList.remove('loading');
                    if (job.seq === renderSeq) pumpImageQueue(job.seq);
                }};
                job.img.onerror = () => {{
                    activeImgLoads = Math.max(0, activeImgLoads - 1);
                    job.img.classList.add('loaded');
                    if (job.img.parentElement) job.img.parentElement.classList.remove('loading');
                    if (job.seq === renderSeq) pumpImageQueue(job.seq);
                }};
                job.img.src = src;
            }}
        }}

        function renderGrid() {{
            const container = document.getElementById('gridContainer');
            const gridView = document.getElementById('gridView');
            const statusEl = document.getElementById('gridLoadStatus');
            if (!container || !gridView) return;

            cancelGridQueue();
            const mySeq = renderSeq;
            container.innerHTML = '';

            const total = filteredItems.length;
            if (total === 0) {{
                container.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:#64748b;padding:48px 12px;">표시할 에셋이 없습니다. 필터를 변경해보세요.</div>';
                if (statusEl) statusEl.textContent = '';
                return;
            }}

            if ('IntersectionObserver' in window) {{
                gridObserver = new IntersectionObserver((entries) => {{
                    if (mySeq !== renderSeq) return;
                    let added = false;
                    entries.forEach(entry => {{
                        if (!entry.isIntersecting) return;
                        const img = entry.target;
                        if (gridObserver) gridObserver.unobserve(img);
                        if (img.dataset.src && !img.dataset.queued) {{
                            img.dataset.queued = '1';
                            imgLoadQueue.push({{ img, seq: mySeq }});
                            added = true;
                        }}
                    }});
                    if (added) pumpImageQueue(mySeq);
                }}, {{ root: gridView, rootMargin: '240px 0px' }});
            }}

            let cursor = 0;
            function appendNextChunk() {{
                if (mySeq !== renderSeq) return;
                const frag = document.createDocumentFragment();
                const end = Math.min(cursor + MOBILE_CHUNK_SIZE, total);

                for (let idx = cursor; idx < end; idx++) {{
                    const item = filteredItems[idx];
                    const card = document.createElement('div');
                    card.className = 'grid-card' + (idx === currentIndex ? ' active-card' : '');
                    card.dataset.rel = item.rel_path;
                    card.onclick = () => openSlideAt(idx);

                    const thumbWrap = document.createElement('div');
                    thumbWrap.className = 'grid-thumb-wrap loading';

                    const img = document.createElement('img');
                    img.className = 'grid-thumb';
                    img.decoding = 'async';
                    img.dataset.src = item.url;
                    img.alt = item.filename || item.code || '';
                    thumbWrap.appendChild(img);

                    if (item.qc_passed === false) {{
                        const warn = document.createElement('span');
                        warn.className = 'grid-qc-badge';
                        warn.textContent = '⚠️ QC';
                        thumbWrap.appendChild(warn);
                    }}

                    const cap = document.createElement('div');
                    cap.className = 'grid-caption';
                    cap.textContent = '#' + item.code + ' ' + (item.label || item.char);

                    card.appendChild(thumbWrap);
                    card.appendChild(cap);
                    frag.appendChild(card);

                    if (gridObserver) {{
                        gridObserver.observe(img);
                    }} else {{
                        img.dataset.queued = '1';
                        imgLoadQueue.push({{ img, seq: mySeq }});
                    }}
                }}

                container.appendChild(frag);
                if (!gridObserver) pumpImageQueue(mySeq);

                cursor = end;
                if (statusEl) {{
                    statusEl.textContent = cursor < total
                        ? ('썸네일 순차 배치 중: ' + cursor + ' / ' + total + '장')
                        : ('총 ' + total + '장 (화면에 보이는 카드부터 3장씩 순차 로드)');
                }}
                if (cursor < total) {{
                    window.requestAnimationFrame(appendNextChunk);
                }}
            }}

            appendNextChunk();
        }}

        function preloadNextSequential(expectedSeq) {{
            if (expectedSeq !== slideLoadSeq) return;
            const total = filteredItems.length;
            if (currentIndex + 1 >= total) return;
            const p1 = new Image();
            p1.onload = p1.onerror = () => {{
                if (expectedSeq !== slideLoadSeq) return;
                if (currentIndex + 2 < filteredItems.length) {{
                    const p2 = new Image();
                    p2.src = filteredItems[currentIndex + 2].url;
                }}
            }};
            p1.src = filteredItems[currentIndex + 1].url;
        }}

        function updateView() {{
            const total = filteredItems.length;
            const counter = document.getElementById('counterBadge');
            const mainImg = document.getElementById('mainImg');
            const title = document.getElementById('poseTitle');
            const subtitle = document.getElementById('poseSubtitle');
            const spinner = document.getElementById('slideSpinner');

            if (total === 0) {{
                counter.innerText = '0 / 0';
                title.innerText = '표시할 에셋이 없습니다';
                subtitle.innerText = '상단 필터 또는 로스터를 변경해보세요';
                mainImg.removeAttribute('src');
                if (spinner) spinner.classList.remove('visible');
                return;
            }}

            const item = filteredItems[currentIndex];
            counter.innerText = (currentIndex + 1) + ' / ' + total;
            title.innerText = '#' + item.code + ' ' + (item.label || item.filename);

            subtitle.innerHTML = '';
            const subText = document.createElement('span');
            subText.textContent = formatCharSubtitle(item);
            subtitle.appendChild(subText);
            if (item.qc_passed === false) {{
                const qcTag = document.createElement('span');
                qcTag.className = 'qc-inline-badge';
                qcTag.textContent = '⚠️ ' + (item.qc_reason || 'QC 경고');
                subtitle.appendChild(qcTag);
            }}

            if (currentView !== 'slide') return;

            const mySlideSeq = ++slideLoadSeq;
            mainImg.style.opacity = '0.35';
            if (spinner) spinner.classList.add('visible');
            mainImg.onload = () => {{
                if (mySlideSeq !== slideLoadSeq) return;
                mainImg.style.opacity = '1';
                if (spinner) spinner.classList.remove('visible');
                preloadNextSequential(mySlideSeq);
            }};
            mainImg.onerror = () => {{
                if (mySlideSeq !== slideLoadSeq) return;
                mainImg.style.opacity = '1';
                if (spinner) spinner.classList.remove('visible');
            }};
            mainImg.src = item.url;
        }}

        function prev(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            currentIndex = (currentIndex - 1 + filteredItems.length) % filteredItems.length;
            updateView();
        }}

        function next(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            currentIndex = (currentIndex + 1) % filteredItems.length;
            updateView();
        }}

        function getPlepaAuthHeaders(extra = {{}}) {{
            const headers = Object.assign({{}}, extra || {{}});
            const tok = new URLSearchParams(window.location.search).get('token');
            if (tok) headers['X-Plepa-Token'] = tok;
            return headers;
        }}

        function getSelectedCensorOptions() {{
            const styleEl = document.getElementById('censorStyleSelect');
            return {{
                censor_style: styleEl ? styleEl.value : 'white_silhouette',
                censor_targets: 'penis',
                min_confidence: 0.16,
                enable_anchor_fallback: false
            }};
        }}

        // 로스터 즉시 전환 (페이지 리로드 없이 부드럽게 전환)
        async function switchRoster(newRoster) {{
            if (!newRoster || newRoster === rawData.roster) return;
            const sel = document.getElementById('rosterSelect');
            if (sel) sel.disabled = true;
            showToast('🔄 [' + newRoster + '] 로스터 불러오는 중...');
            try {{
                const res = await fetch('/api/mobile/gallery?roster=' + encodeURIComponent(newRoster), {{
                    headers: getPlepaAuthHeaders()
                }});
                const nextData = await res.json();
                if (!res.ok) throw new Error(nextData.detail || ('HTTP ' + res.status));

                rawData = nextData;
                currentChar = 'all';
                currentIndex = 0;

                const hasRecent = (rawData.items || []).some(i => i.is_recent);
                const nextMode = (currentMode === 'recent' && !hasRecent)
                    ? 'all'
                    : (currentMode === 'all' && hasRecent ? 'recent' : currentMode);

                renderRosterSelect();
                renderCharChips();
                updateModeCounts();
                setMode(nextMode);

                try {{
                    const u = new URL(window.location.href);
                    u.searchParams.set('roster', rawData.roster);
                    window.history.replaceState(null, '', u.toString());
                }} catch (err) {{}}

                showToast('✅ [' + rawData.roster + '] ' + (rawData.items || []).length + '장 로드 완료');
            }} catch (err) {{
                showToast('❌ 로스터 전환 실패: ' + err.message);
                renderRosterSelect();
            }} finally {{
                if (sel) sel.disabled = false;
            }}
        }}

        function onPlepaMobileRetouchSaved(savedPayload) {{
            if (!savedPayload) return;
            const targetItem = (rawData.items || []).find(it => it.rel_path === savedPayload.rel_path);
            if (targetItem) {{
                targetItem.url = targetItem.url.split('?')[0] + '?t=' + savedPayload.timestamp;
            }}
            updateView();
            if (currentView === 'grid') renderGrid();
        }}

        // 에셋 삭제 (휴지통 안전 이동)
        async function triggerDelete(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;

            const item = filteredItems[currentIndex];
            const targetName = '#' + item.code + ' ' + formatCharSubtitle(item);

            try {{
                const res = await fetch('/api/assets/delete', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{ rel_path: item.rel_path, roster: rawData.roster }})
                }});
                const data = await res.json();
                if (data.success) {{
                    lastDeletedBundle = {{ item: item, moved: data.data.moved }};
                    rawData.items = rawData.items.filter(x => x.rel_path !== item.rel_path);
                    rawData.total_missing = (rawData.total_missing || 0) + 1;
                    renderCharChips();
                    applyFilters();
                    showToast('🗑️ ' + targetName + ' 휴지통 이동됨', true);
                }} else {{
                    showToast('❌ 삭제 실패');
                }}
            }} catch (err) {{
                showToast('❌ 오류: ' + err.message);
            }}
        }}

        // 삭제 실행 취소 (Undo)
        async function triggerUndo() {{
            if (!lastDeletedBundle) return;
            try {{
                const res = await fetch('/api/assets/undo', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{ moved: lastDeletedBundle.moved }})
                }});
                const data = await res.json();
                if (data.success) {{
                    rawData.items.push(lastDeletedBundle.item);
                    rawData.total_missing = Math.max(0, (rawData.total_missing || 1) - 1);
                    renderCharChips();
                    applyFilters();
                    showToast('✅ 원상 복원 완료!');
                    lastDeletedBundle = null;
                }} else {{
                    showToast('❌ 복원 실패');
                }}
            }} catch (err) {{
                showToast('❌ 오류: ' + err.message);
            }}
        }}

        // 무검열 원본(_origin) 즉시 복원
        async function triggerRestoreOrigin(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            if (!confirm('#' + item.code + ' [' + item.char + '] 이미지를 무검열 원본(_origin)으로 복원하시겠습니까?')) return;

            try {{
                const res = await fetch('/api/assets/restore-origin', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{ rel_path: item.rel_path, roster: rawData.roster }})
                }});
                const data = await res.json();
                if (res.ok && data.success) {{
                    item.url = item.url.split('?')[0] + '?t=' + Date.now();
                    updateView();
                    showToast('✅ 원본 이미지로 복원 완료!');
                }} else {{
                    showToast('❌ 원본 복원 실패: ' + (data.detail || '알 수 없는 오류'));
                }}
            }} catch (err) {{
                showToast('❌ 요청 오류: ' + err.message);
            }}
        }}

        // 0.2초 즉시 재검열
        async function triggerReapplyCensor(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            const opts = getSelectedCensorOptions();

            showToast('⚡ #' + item.code + ' ' + opts.censor_style + ' 재검열 중...');
            try {{
                const res = await fetch('/api/assets/reapply-censor', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{
                        rel_path: item.rel_path,
                        roster: rawData.roster,
                        pose_code: item.code,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        min_confidence: opts.min_confidence,
                        enable_anchor_fallback: opts.enable_anchor_fallback
                    }})
                }});
                const data = await res.json();
                if (res.ok && data.success) {{
                    item.url = item.url.split('?')[0] + '?t=' + Date.now();
                    updateView();
                    showToast('⚡ 재검열 완료 (' + opts.censor_style + ', 탐지 ' + (data.detected_count ?? 0) + '건)');
                }} else {{
                    showToast('❌ 재검열 실패: ' + (data.detail || '알 수 없는 오류'));
                }}
            }} catch (err) {{
                showToast('❌ 요청 오류: ' + err.message);
            }}
        }}

        // 수동 캔버스 직접 검열/덧칠 에디터 열기
        function triggerRetouch(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            if (typeof openRetouchEditor === 'function') {{
                openRetouchEditor({{
                    relPath: item.rel_path,
                    roster: rawData.roster,
                    title: '✏️ #' + item.code + ' ' + (item.label || item.filename),
                    imageUrl: item.url,
                    originUrl: item.origin_url || ''
                }});
            }}
        }}

        // 현재 포즈 단독 리롤 (실수 클릭 방지 확인 팝업 포함)
        async function triggerReroll(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            if (!confirm('#' + item.code + ' [' + formatCharSubtitle(item) + '] 이미지를 새 시드로 리롤 대기열에 등록하시겠습니까?')) return;
            const opts = getSelectedCensorOptions();

            showToast('🎲 #' + item.code + ' [' + item.char + '] 리롤 대기열 등록 중...');
            try {{
                const res = await fetch('/api/assets/reroll', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{
                        char: item.char,
                        code: item.code,
                        roster: rawData.roster,
                        reuse_seed: false,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        auto_qc: true
                    }})
                }});
                const data = await res.json();
                if (res.ok && data.success) {{
                    showToast('🎲 ' + (data.message || ('#' + item.code + ' 리롤 대기열 등록 완료')));
                    pollJobStatus();
                }} else {{
                    showToast('❌ 리롤 실패: ' + (data.detail || '알 수 없는 오류'));
                }}
            }} catch (err) {{
                showToast('❌ 리롤 요청 오류: ' + err.message);
            }}
        }}

        // 누락 포즈 전체 일괄 생성
        async function triggerFillMissing() {{
            const count = document.getElementById('missingCountBadge').innerText;
            if (count === '0') {{
                showToast('✨ 누락된 포즈가 없습니다. 모든 포즈 완비!');
                return;
            }}
            if (!confirm('현재 로스터의 비어있는 포즈 ' + count + '개를 모두 백그라운드로 자동 생성하시겠습니까?')) return;

            closeSettingsSheet();
            const opts = getSelectedCensorOptions();
            showToast('⚡ 누락 포즈 ' + count + '개 백그라운드 생성 시작...');
            try {{
                const res = await fetch('/api/assets/fill-missing', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{
                        roster: rawData.roster,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        auto_qc: true
                    }})
                }});
                const data = await res.json();
                showToast('🚀 ' + data.message);
                pollJobStatus();
            }} catch (err) {{
                showToast('❌ 요청 오류: ' + err.message);
            }}
        }}

        // 백그라운드 생성 완료 시 최신 mtime·이미지 즉시 동기화
        async function refreshGalleryData(silent = true) {{
            if (isRefreshingGallery) return;
            isRefreshingGallery = true;
            const prevRelPath = (filteredItems[currentIndex] && filteredItems[currentIndex].rel_path)
                ? filteredItems[currentIndex].rel_path
                : null;
            try {{
                const res = await fetch('/api/mobile/gallery?roster=' + encodeURIComponent(rawData.roster), {{
                    headers: getPlepaAuthHeaders()
                }});
                if (!res.ok) return;
                const nextData = await res.json();
                rawData = nextData;
                renderRosterSelect();
                renderCharChips();
                updateModeCounts();
                if (currentSort === 'mtime_desc') {{
                    currentIndex = 0;
                    applyFilters(null);
                }} else {{
                    applyFilters(prevRelPath);
                }}
            }} catch (err) {{
                if (!silent) showToast('❌ 목록 갱신 실패: ' + err.message);
            }} finally {{
                isRefreshingGallery = false;
            }}
        }}

        // 원터치 최신 목록 + 대기열 강제 동기화 (외부 CLI 생성분 포함)
        async function manualRefreshGallery() {{
            await refreshGalleryData(false);
            await pollJobStatus();
            showToast('🔄 최신 에셋 목록 동기화 완료');
        }}

        // 대기열 · 진행 현황 패널 렌더링
        function renderQueuePanel(status) {{
            const panel = document.getElementById('queueStatusPanel');
            const summaryEl = document.getElementById('queueSummaryText');
            if (!panel || !status) return;

            const isRunning = !!status.is_running;
            const queued = Array.isArray(status.queued_jobs) ? status.queued_jobs : [];
            const completed = Array.isArray(status.completed_items) ? status.completed_items : [];
            const active = status.active_job || null;

            if (summaryEl) {{
                if (isRunning || queued.length > 0) {{
                    summaryEl.textContent = (isRunning ? '진행 1' : '진행 0') + ' · 대기 ' + queued.length;
                    summaryEl.style.color = '#fbbf24';
                }} else {{
                    summaryEl.textContent = '대기 없음';
                    summaryEl.style.color = '#94a3b8';
                }}
            }}

            const chunks = [];
            if (isRunning && active) {{
                const cur = Number(status.current || 0);
                const tot = Math.max(1, Number(status.total || 1));
                const pct = Math.min(100, Math.max(0, Number(status.percentage || Math.round((cur / tot) * 100))));
                const msg = status.current_msg ? escapeHtml(status.current_msg) : '이미지 생성 중...';
                chunks.push(
                    '<div class="q-item running">' +
                    '<div class="q-item-top"><span>⚡ 진행중: ' + escapeHtml(active.label || '') + '</span><span>' + cur + '/' + tot + ' (' + pct + '%)</span></div>' +
                    '<div class="q-bar-bg"><div class="q-bar-fill" style="width:' + pct + '%;"></div></div>' +
                    '<div class="q-item-sub">' + msg + '</div>' +
                    '</div>'
                );
            }}

            queued.forEach((job, idx) => {{
                chunks.push(
                    '<div class="q-item queued">' +
                    '<div class="q-item-top"><span>⏳ 대기 #' + (idx + 1) + ': ' + escapeHtml(job.label || '') + '</span><span style="color:#94a3b8;">' + escapeHtml(job.queued_at || '') + '</span></div>' +
                    '</div>'
                );
            }});

            completed.slice(0, 5).forEach(done => {{
                const icon = done.qc_passed === false ? '⚠️' : '✅';
                const dur = done.duration_sec !== undefined && done.duration_sec !== null ? (done.duration_sec + '초') : '';
                chunks.push(
                    '<div class="q-item">' +
                    '<div class="q-item-top"><span>' + icon + ' #' + escapeHtml(done.code || '?') + ' [' + escapeHtml(done.char || '') + ']</span><span style="color:#94a3b8;">' + escapeHtml(dur) + '</span></div>' +
                    '</div>'
                );
            }});

            if (chunks.length === 0) {{
                panel.innerHTML = '<div style="text-align:center;color:#64748b;font-size:11px;padding:12px 0;">진행 중이거나 대기 중인 생성 작업이 없습니다.</div>';
            }} else {{
                panel.innerHTML = chunks.join('');
            }}
        }}

        // 대기열 상태 폴링 + 1장 완료 즉시 이미지·정렬 자동 반영
        async function pollJobStatus() {{
            if (isPollingJob) return;
            isPollingJob = true;
            try {{
                const res = await fetch('/api/assets/job-status', {{
                    headers: getPlepaAuthHeaders()
                }});
                if (!res.ok) return;
                const status = await res.json();
                renderQueuePanel(status);
                const badge = document.getElementById('jobQueueBadge');
                const isRunning = !!status.is_running;
                const qLen = Number(status.queue_length || 0);

                if (badge) {{
                    if (isRunning || qLen > 0) {{
                        const totalActive = qLen + (isRunning ? 1 : 0);
                        badge.textContent = qLen > 0 ? ('🎲 진행+대기 ' + totalActive) : '🎲 생성중';
                        badge.style.display = 'inline-flex';
                    }} else {{
                        badge.style.display = 'none';
                    }}
                }}

                const completed = Array.isArray(status.completed_items) ? status.completed_items : [];
                const top = completed[0] || {{}};
                const latestTs = status.latest_result ? (status.latest_result.timestamp || '') : '';
                const curSig = completed.length + '|' + (top.job_id || '') + '|' + (top.timestamp || '') + '|' + (top.filename || '') + '|' + latestTs;

                if (!jobPollInitialized) {{
                    lastCompletedSig = curSig;
                    jobPollInitialized = true;
                }} else if (curSig !== lastCompletedSig) {{
                    lastCompletedSig = curSig;
                    await refreshGalleryData(true);
                    if (top && top.code) {{
                        showToast('✅ #' + top.code + ' [' + (top.char || '') + '] 재생성 반영됨');
                    }}
                }}
            }} catch (err) {{
                // 일시적 네트워크 단절 시 다음 주기에 자동 재시도
            }} finally {{
                isPollingJob = false;
            }}
        }}

        function onStageClick(e) {{
            if (currentView !== 'slide') return;
            const rect = e.currentTarget.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const w = rect.width;
            if (x < w * 0.24 || x > w * 0.76) return;

            immersiveMode = !immersiveMode;
            document.getElementById('mobileApp').classList.toggle('immersive', immersiveMode);
        }}

        // 터치 스와이프 제스처
        let touchStartX = 0;
        let touchStartY = 0;
        const stage = document.getElementById('stage');

        stage.addEventListener('touchstart', (e) => {{
            touchStartX = e.changedTouches[0].screenX;
            touchStartY = e.changedTouches[0].screenY;
        }}, {{ passive: true }});

        stage.addEventListener('touchend', (e) => {{
            if (currentView !== 'slide') return;
            const touchEndX = e.changedTouches[0].screenX;
            const touchEndY = e.changedTouches[0].screenY;
            const diffX = touchEndX - touchStartX;
            const diffY = touchEndY - touchStartY;

            if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 40) {{
                if (diffX > 0) prev();
                else next();
            }}
        }}, {{ passive: true }});

        // PC 키보드 화살표 & ESC
        window.addEventListener('keydown', (e) => {{
            if (window.__plepaRetouchOpen) return;
            if (e.key === 'Escape') closeSettingsSheet();
            if (currentView === 'slide') {{
                if (e.key === 'ArrowLeft') prev();
                if (e.key === 'ArrowRight' || e.key === ' ') next();
                if (e.key === 'Delete') triggerDelete();
                if (e.key === 'r' || e.key === 'R') triggerReroll();
            }}
        }});

        // 초기화
        renderRosterSelect();
        renderCharChips();
        updateModeCounts();
        setCharFilter('all');
        pollJobStatus();
        setInterval(() => {{
            if (!document.hidden) pollJobStatus();
        }}, 2500);
        document.addEventListener('visibilitychange', () => {{
            if (!document.hidden) pollJobStatus();
        }});
    </script>
    {RETOUCH_EDITOR_HTML}
    {retouch_script_html}
</body>
</html>"""


def render_mobile_viewer_page(roster: Optional[str] = None) -> None:
    """하위 호환용 NiceGUI 페이지 래퍼."""
    html_content = generate_mobile_viewer_html(roster or get_active_roster())
    ui.html(html_content)
