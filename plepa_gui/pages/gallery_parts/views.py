"""
plepa_gui.pages.gallery_parts.views
갤러리 콘텐츠 영역의 3대 뷰(매트릭스, 단일 캐릭터, 비포즈/기타 에셋) 렌더러.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from nicegui import ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_gui.pages.gallery_parts.data_helpers import (
    build_asset_web_url,
    get_character_asset_counts,
    pose_sort_key,
)

logger = logging.getLogger(__name__)


def render_single_char_view(
    content_container: Any,
    state: Dict[str, Any],
    all_poses: Dict[str, Any],
    image_widgets_by_rel: Dict[str, Any],
    retouched_versions: Dict[str, int],
    open_lightbox_cb: Callable[..., None],
) -> None:
    """단일 캐릭터 전체 갤러리 카드 뷰를 렌더링합니다."""
    prefix = state["single_char"]
    if not prefix:
        with content_container:
            with ui.column().classes("w-full py-16 items-center justify-center text-slate-500"):
                ui.icon("person_search", size="48px").classes("text-slate-600 mb-2")
                ui.label("상단에서 열람할 캐릭터를 선택해 주십시오.").classes("text-sm font-semibold")
        return

    assets = default_asset_service.list_character_assets(prefix, state["roster"])
    sort_mode = state.get("single_sort", "mtime_desc")
    if sort_mode == "mtime_desc":
        assets = sorted(assets, key=lambda x: x.get("mtime", 0.0), reverse=True)

    with content_container:
        if not assets:
            with ui.column().classes("w-full py-16 items-center justify-center text-slate-500"):
                ui.icon("photo_library", size="48px").classes("text-slate-600 mb-2")
                ui.label(f"'{prefix}' 캐릭터에 생성된 이미지가 없습니다.").classes("text-sm")
            return

        with ui.row().classes("w-full items-center justify-between mb-4 pb-2 border-b border-slate-800"):
            sort_text = "🕒 최신 생성순 (NEW 먼저)" if sort_mode == "mtime_desc" else "🔢 포즈 번호순"
            ui.label(f"🖼️ {prefix} 생성 에셋 목록 (총 {len(assets)}장 · {sort_text})").classes("text-base font-bold text-amber-300")

        all_single_paths = [x["path"] for x in assets]
        with ui.grid(columns=4).classes("w-full gap-4"):
            for idx, a in enumerate(assets):
                img_path: Path = a["path"]
                rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                item_mtime = a.get("mtime")
                web_url = build_asset_web_url(rel_path, retouched_versions, file_path=img_path, mtime=item_mtime)
                code = a["code"]
                pose_obj = all_poses.get(code)
                label_str = pose_obj.label if pose_obj else a["label"]

                with ui.card().classes("bg-slate-800/80 border border-slate-700/60 p-2 rounded-lg hover:border-amber-400 transition-all"):
                    img_w = ui.image(web_url).classes("w-full h-72 object-cover rounded shadow cursor-pointer hover:scale-[1.02] transition-transform").on(
                        "click",
                        lambda p=img_path, rp=rel_path, mt=item_mtime, i=idx: open_lightbox_cb(
                            build_asset_web_url(rp, retouched_versions, file_path=p, mtime=mt), p, all_single_paths, i
                        ),
                    )
                    image_widgets_by_rel[rel_path] = img_w

                    with ui.row().classes("w-full items-center justify-between mt-2 px-1"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"#{code} {label_str}").classes("text-xs font-bold text-slate-100 truncate max-w-[170px]").tooltip(label_str)
                            mtime_val = a.get("mtime", 0.0)
                            mtime_str = datetime.fromtimestamp(mtime_val).strftime("%m-%d %H:%M") if mtime_val else ""
                            ui.label(f"{(a['size_bytes']/1024):.0f} KB · {mtime_str}").classes("text-[10px] text-slate-400 font-mono")

                        if (time.time() - a.get("mtime", 0.0)) < 3600:
                            ui.badge("NEW ✨", color="amber-500").props("dense text-[10px] text-slate-950 font-bold")
                        elif a.get("censored_path"):
                            ui.badge("검열본", color="info").props("dense text-[10px]")


def _render_matrix_table(
    content_container: Any,
    state: Dict[str, Any],
    all_poses: Dict[str, Any],
    prefixes: List[str],
    codes: List[str],
    matrix: Dict[str, Dict[str, Optional[Path]]],
    code_mtime_map: Dict[str, float],
    sort_mode: str,
    image_widgets_by_rel: Dict[str, Any],
    retouched_versions: Dict[str, int],
    open_lightbox_cb: Callable[..., None],
) -> None:
    """정렬된 매트릭스 테이블 DOM을 렌더링합니다."""
    with content_container:
        with ui.element("table").classes("w-full border-collapse text-left"):
            with ui.element("thead"):
                with ui.element("tr").classes("border-b border-slate-700 bg-slate-800/80 sticky top-0 z-10"):
                    ui.element("th").classes("p-3 text-xs font-bold text-amber-400 w-36").add_slot("default", "캐릭터 / 포즈")
                    now_ts = time.time()
                    for code in codes:
                        pose_obj = all_poses.get(code)
                        label_str = pose_obj.label if pose_obj else code
                        c_mtime = code_mtime_map.get(code, 0.0)
                        with ui.element("th").classes("p-3 text-xs font-semibold text-slate-300 text-center min-w-[130px]"):
                            with ui.column().classes("items-center gap-0"):
                                ui.label(f"#{code}").classes("text-[10px] text-slate-400 font-mono")
                                ui.label(label_str).classes("text-xs font-bold")
                                if sort_mode == "mtime_desc" and c_mtime > 0:
                                    m_lbl = datetime.fromtimestamp(c_mtime).strftime("%m-%d %H:%M")
                                    lbl_cls = "text-[10px] font-mono text-amber-300 font-bold" if (now_ts - c_mtime) < 3600 else "text-[10px] font-mono text-slate-500"
                                    ui.label(m_lbl).classes(lbl_cls)

            with ui.element("tbody"):
                for prefix in prefixes:
                    with ui.element("tr").classes("border-b border-slate-800/70 hover:bg-slate-800/30 transition-colors"):
                        with ui.element("td").classes("p-3 text-sm font-bold text-slate-200 border-r border-slate-800"):
                            try:
                                char_obj, _ = default_character_service.find_character(prefix, roster=state["roster"])
                                ui.label(char_obj.name).classes("text-sm font-bold text-amber-300")
                                ui.label(f"[{prefix}]").classes("text-xs text-slate-500 font-mono")
                            except Exception as exc:
                                logger.debug("캐릭터 조회 폴백 (%s): %s", prefix, exc)
                                ui.label(prefix).classes("text-sm text-slate-300")

                        row_paths = [matrix.get(prefix, {}).get(c) for c in codes if matrix.get(prefix, {}).get(c) and matrix[prefix][c].exists()]
                        for code in codes:
                            img_path: Optional[Path] = matrix.get(prefix, {}).get(code)
                            with ui.element("td").classes("p-2 text-center align-middle border-r border-slate-800/40"):
                                if img_path and img_path.exists():
                                    rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                                    web_url = build_asset_web_url(rel_path, retouched_versions, file_path=img_path)
                                    c_idx = row_paths.index(img_path) if img_path in row_paths else 0
                                    with ui.column().classes("items-center justify-center gap-1 mx-auto"):
                                        img_w = ui.image(web_url).classes(
                                            "w-28 h-40 object-cover rounded shadow cursor-pointer border border-slate-700 hover:border-amber-400 transition-all hover:scale-105"
                                        ).on("click", lambda p=img_path, rp=rel_path, paths=row_paths, idx=c_idx: open_lightbox_cb(
                                            build_asset_web_url(rp, retouched_versions, file_path=p), p, paths, idx
                                        ))
                                        image_widgets_by_rel[rel_path] = img_w
                                else:
                                    with ui.column().classes("items-center justify-center w-28 h-40 bg-slate-800/30 rounded border border-dashed border-slate-700/60 text-slate-600"):
                                        ui.icon("image_not_supported", size="24px")
                                        ui.label("미생성").classes("text-[11px] mt-1")


def render_matrix_view(
    content_container: Any,
    state: Dict[str, Any],
    all_poses: Dict[str, Any],
    image_widgets_by_rel: Dict[str, Any],
    retouched_versions: Dict[str, int],
    open_lightbox_cb: Callable[..., None],
) -> None:
    """캐릭터 x 포즈 2차원 매트릭스 비교 테이블을 렌더링합니다."""
    char_counts = get_character_asset_counts(state["roster"])
    prefixes = [p for p in state["selected_chars"] if p in char_counts]
    codes = state["selected_codes"]

    if not prefixes:
        with content_container:
            with ui.column().classes("w-full py-12 items-center justify-center text-slate-400"):
                ui.icon("tune", size="40px").classes("text-amber-400 mb-2")
                ui.label("상단에서 비교할 캐릭터를 1명 이상 선택해 주십시오.").classes("text-sm font-semibold")
                ui.label("💡 상단의 '👑 유키노 체형 6종 세트' 또는 '📷 이미지 있는 캐릭터만 선택' 버튼을 누르면 즉시 조회됩니다.").classes("text-xs text-slate-500 mt-1")
        return

    matrix = default_asset_service.get_matrix_map(prefixes, codes, roster=state["roster"])
    codes = [c for c in codes if any(matrix.get(p, {}).get(c) and matrix[p][c].exists() for p in prefixes)]
    if not codes:
        with content_container:
            with ui.column().classes("w-full py-12 items-center justify-center text-slate-400"):
                ui.icon("photo_library", size="40px").classes("text-slate-500 mb-2")
                ui.label("선택한 캐릭터와 포즈 범위에 표시할 생성된 이미지가 없습니다.").classes("text-sm font-semibold")
        return

    code_mtime_map: Dict[str, float] = {}
    for c in codes:
        best_m = 0.0
        for p in prefixes:
            mp = matrix.get(p, {}).get(c)
            if mp and mp.exists():
                try:
                    best_m = max(best_m, mp.stat().st_mtime)
                except OSError:
                    pass
        code_mtime_map[c] = best_m

    sort_mode = state.get("matrix_sort", "code_asc")
    sorted_codes = sorted(codes, key=lambda c: (-code_mtime_map.get(c, 0.0), pose_sort_key(c))) if sort_mode == "mtime_desc" else sorted(codes, key=pose_sort_key)
    _render_matrix_table(
        content_container, state, all_poses, prefixes, sorted_codes, matrix,
        code_mtime_map, sort_mode, image_widgets_by_rel, retouched_versions, open_lightbox_cb,
    )


def render_misc_view(
    content_container: Any,
    state: Dict[str, Any],
    open_lightbox_cb: Callable[..., None],
) -> None:
    """비포즈 / 기타 에셋 (배경, 레퍼런스, 샘플) 그리드 뷰를 렌더링합니다."""
    all_misc = default_asset_service.list_misc_assets(state["roster"])
    m_filter = state.get("misc_filter", "all")
    assets = [a for a in all_misc if a.get("type") == m_filter] if m_filter != "all" else all_misc

    with content_container:
        if not assets:
            with ui.column().classes("w-full py-16 items-center justify-center text-slate-500"):
                ui.icon("collections", size="48px").classes("text-slate-600 mb-2")
                ui.label(f"'{state['roster']}' 로스터에 등록된 비포즈 / 기타 에셋이 없습니다.").classes("text-sm font-semibold")
                ui.label("💡 레퍼런스 이미지(references/)나 배경 이미지(backgrounds/)가 이곳에 자동 표시됩니다.").classes("text-xs text-slate-600 mt-1")
            return

        with ui.row().classes("w-full items-center justify-between mb-4 pb-2 border-b border-slate-800"):
            ui.label(f"✨ 비포즈 / 기타 에셋 목록 (총 {len(assets)}장)").classes("text-base font-bold text-purple-300")
            ui.label(f"현재 로스터: {state['roster']}").classes("text-xs text-slate-400 font-mono")

        misc_paths = [x["path"] for x in assets]
        with ui.grid(columns=4).classes("w-full gap-4"):
            for idx, a in enumerate(assets):
                img_path: Path = a["path"]
                rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                web_url = f"/projects_static/{rel_path}"
                type_str = a.get("type", "misc")
                badge_color = "purple-500" if type_str == "reference" else ("blue-500" if type_str == "background" else "emerald-500")

                with ui.card().classes("bg-slate-800/80 border border-slate-700/60 p-2 rounded-lg hover:border-purple-400 transition-all"):
                    ui.image(web_url).classes("w-full h-72 object-cover rounded shadow cursor-pointer hover:scale-[1.02] transition-transform").on(
                        "click", lambda u=web_url, p=img_path, i=idx: open_lightbox_cb(u, p, misc_paths, i)
                    )
                    with ui.column().classes("w-full mt-2 px-1 gap-1"):
                        with ui.row().classes("w-full justify-between items-center"):
                            ui.badge(a["category"], color=badge_color).props("dense text-[10px]")
                            ui.label(f"{(a['size_bytes']/1024):.0f} KB").classes("text-[10px] text-slate-400")
                        ui.label(a["name"]).classes("text-xs font-bold text-slate-100 truncate w-full").tooltip(a["name"])
                        ui.label(f"📁 {a.get('folder', '')}").classes("text-[10px] text-slate-500 font-mono truncate w-full")
