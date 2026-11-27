"""
plepa_gui.pages.gallery_parts.lightbox
에셋 확대 검수용 라이트박스 모달 다이얼로그 및 키보드·사전 로딩 컨트롤러.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from nicegui import ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.upscale_service import default_upscale_service
from plepa_gui.pages.gallery_parts.data_helpers import build_asset_web_url
from plepa_gui.pages.gallery_parts.lightbox_actions import (
    add_origin_and_retouch_buttons,
    add_upscale_and_utility_buttons,
    enqueue_lightbox_reroll,
    parse_char_and_pose_code,
    render_lightbox_meta,
)


def _refresh_lightbox_img(
    items: List[Path],
    nav_state: Dict[str, int],
    curr: Dict[str, Any],
    get_cached_url: Callable[[Path], str],
    preload: bool = True,
) -> None:
    """라이트박스 이미지 소스를 즉시 교체하고 인접 ±1 이미지를 사전 로딩합니다."""
    preload_urls: List[str] = []
    if preload and len(items) > 1:
        n, idx = len(items), nav_state["idx"]
        for offset in (1, -1):
            u = get_cached_url(items[(idx + offset) % n])
            if u != curr["url"]:
                preload_urls.append(u)
    js_code = (
        "const im = document.getElementById('plepaLightboxImg');"
        f"if (im) {{ im.alt = {json.dumps(curr['path'].name)}; im.src = {json.dumps(curr['url'])}; }}"
        + "".join(f"new Image().src = {json.dumps(pu)};" for pu in preload_urls)
    )
    ui.run_javascript(js_code)


def _render_lightbox_header(
    header_box: Any,
    ctx: Dict[str, Any],
    go_to_index: Callable[[int], None],
    get_cached_dims: Callable[[Path], Tuple[Optional[Tuple[int, int]], bool]],
) -> None:
    """라이트박스 상단 네비게이션 바 및 액션 버튼 툴바를 렌더링합니다."""
    header_box.clear()
    items, nav_state = ctx["items"], ctx["nav_state"]
    p: Path = ctx["curr"]["path"]

    with header_box:
        with ui.row().classes("items-center gap-2 flex-wrap"):
            if len(items) > 1:
                ui.button(icon="arrow_back", on_click=lambda: go_to_index(nav_state["idx"] - 1)).props(
                    "flat round dense size=sm color=amber-400"
                ).tooltip("이전 포즈 (단축키: ←)")
                ui.label(f"{nav_state['idx'] + 1}/{len(items)}").classes("text-xs font-mono text-amber-300 px-1 font-bold")
                ui.button(icon="arrow_forward", on_click=lambda: go_to_index(nav_state["idx"] + 1)).props(
                    "flat round dense size=sm color=amber-400"
                ).tooltip("다음 포즈 (단축키: →)")

            ui.icon("zoom_in", size="20px").classes("text-amber-400")
            ui.label(p.name).classes("text-sm md:text-base font-bold text-slate-100 font-mono")
            dims, is_already = get_cached_dims(p)
            if dims:
                if is_already:
                    ui.badge("4K UHD", color="emerald-600").props("dense text-xs")
                ui.badge(f"{dims[0]}x{dims[1]}", color="slate-800").props("dense text-xs border border-slate-700 text-slate-300 font-mono")

        with ui.row().classes("items-center gap-2 flex-wrap"):
            size_kb = p.stat().st_size / 1024 if p.exists() else 0
            ui.label(f"{size_kb:.1f} KB").classes("text-xs text-slate-400 mr-2")
            prefix_val, code_val = parse_char_and_pose_code(p.name)

            if prefix_val and code_val:
                target_item_path = items[nav_state["idx"]] if items else p
                ui.button("🎲 새 시드 리롤", icon="casino", on_click=lambda: enqueue_lightbox_reroll(prefix_val, code_val, False, target_item_path, ctx)).props(
                    "unelevated dense size=sm color=blue-600 text-white font-bold"
                ).tooltip("새로운 무작위 시드로 다시 생성합니다")
                ui.button("🔒 시드 고정 리롤", icon="lock_reset", on_click=lambda: enqueue_lightbox_reroll(prefix_val, code_val, True, target_item_path, ctx)).props(
                    "unelevated dense size=sm color=amber-600 text-slate-950 font-bold"
                ).tooltip("기존 골든 시드를 고정하여 구도는 유지하고 의상/태그만 다시 생성합니다")

                async def run_delete_asset():
                    res = default_asset_service.delete_asset_bundle(ctx["curr"]["path"])
                    if res["success"]:
                        ui.notify(f"🗑️ {res['filename']} 휴지통으로 이동되었습니다.", type="warning")
                        ctx["dialog"].close()
                        ctx["render_content"]()
                    else:
                        ui.notify("❌ 삭제 실패", type="negative")

                ui.button("🗑️ 삭제", icon="delete", on_click=run_delete_asset).props(
                    "unelevated dense size=sm color=rose-700 text-white font-bold"
                ).tooltip("해당 에셋(원본 포함)을 휴지통으로 안전하게 이동합니다 (단축키: Del)")

            add_origin_and_retouch_buttons(p, prefix_val, code_val, ctx)
            _, is_4k = get_cached_dims(p)
            add_upscale_and_utility_buttons(p, is_4k, ctx)


def open_gallery_lightbox(
    img_url: str,
    file_path: Path,
    state: Dict[str, Any],
    retouched_versions: Dict[str, int],
    image_widgets_by_rel: Dict[str, Any],
    active_lightbox_retouch_cb: Dict[str, Any],
    refresh_single_thumbnail: Callable[[str, int], None],
    sync_queue_panel: Callable[[bool], None],
    render_content: Callable[[], None],
    item_paths: Optional[List[Path]] = None,
    current_idx: int = -1,
) -> None:
    """갤러리 에셋 확대 검수용 라이트박스 다이얼로그를 엽니다."""
    items = [p for p in item_paths if p and p.exists()] if item_paths else [file_path]
    if file_path not in items:
        items.insert(0, file_path)
    cur_idx = current_idx if (0 <= current_idx < len(items)) else items.index(file_path)

    nav_state = {"idx": cur_idx}
    manifest_cache: Dict[Path, Dict[str, Any]] = {}
    dim_cache: Dict[Path, Tuple[Optional[Tuple[int, int]], bool]] = {}
    url_cache: Dict[Path, str] = {}

    def get_cached_url(p: Path) -> str:
        if p in url_cache:
            return url_cache[p]
        try:
            rel = p.relative_to(PROJECTS_DIR).as_posix()
        except ValueError:
            rel = str(p)
        u = build_asset_web_url(rel, retouched_versions, file_path=p)
        url_cache[p] = u
        return u

    def get_cached_dims(p: Path) -> Tuple[Optional[Tuple[int, int]], bool]:
        if p not in dim_cache:
            dims = default_upscale_service.get_image_dimensions(p)
            dim_cache[p] = (dims, default_upscale_service.is_already_4k(p) if dims else False)
        return dim_cache[p]

    if img_url:
        url_cache[file_path] = img_url
    curr = {"url": img_url or get_cached_url(file_path), "path": file_path}
    showing_origin = {"val": False}
    toggle_origin_holder: Dict[str, Any] = {"fn": None}

    with ui.dialog() as dialog, ui.card().classes(
        "max-w-6xl w-full md:w-[92vw] min-h-[480px] p-4 bg-slate-950 border border-slate-700 rounded-2xl shadow-2xl overflow-y-auto"
    ):
        header_box = ui.row().classes("w-full justify-between items-center mb-3 px-2 pb-2 border-b border-slate-800 flex-wrap gap-2")
        with ui.column().classes("w-full flex-1 items-center justify-center py-2"):
            ui.html(
                f'<div style="display: flex; justify-content: center; align-items: center; width: 100%; min-height: 400px;">'
                f'<img id="plepaLightboxImg" src="{curr["url"]}" alt="{curr["path"].name}" style="max-height: 75vh; max-width: 100%; width: auto; height: auto; object-fit: contain; border-radius: 12px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); display: block;" />'
                f"</div>"
            )
        meta_box = ui.row().classes("w-full justify-between items-center mt-2 px-2 pt-2 border-t border-slate-800/80 text-xs text-slate-400 font-mono flex-wrap gap-2")

        ctx: Dict[str, Any] = {
            "state": state,
            "items": items,
            "nav_state": nav_state,
            "curr": curr,
            "showing_origin": showing_origin,
            "toggle_origin_holder": toggle_origin_holder,
            "dialog": dialog,
            "url_cache": url_cache,
            "dim_cache": dim_cache,
            "manifest_cache": manifest_cache,
            "image_widgets_by_rel": image_widgets_by_rel,
            "retouched_versions": retouched_versions,
            "active_lightbox_retouch_cb": active_lightbox_retouch_cb,
            "refresh_single_thumbnail": refresh_single_thumbnail,
            "sync_queue_panel": sync_queue_panel,
            "render_content": render_content,
            "get_cached_url": get_cached_url,
        }

        def refresh_img(preload: bool = True) -> None:
            _refresh_lightbox_img(items, nav_state, curr, get_cached_url, preload=preload)

        def refresh_all() -> None:
            _render_lightbox_header(header_box, ctx, go_to_index, get_cached_dims)
            refresh_img()
            render_lightbox_meta(meta_box, curr["path"], manifest_cache)

        def go_to_index(idx: int) -> None:
            if not items:
                return
            nav_state["idx"] = idx % len(items)
            new_path = items[nav_state["idx"]]
            curr["path"] = new_path
            curr["url"] = get_cached_url(new_path)
            showing_origin["val"] = False
            refresh_all()

        ctx["refresh_img"] = refresh_img
        ctx["refresh_all"] = refresh_all

        def handle_keyboard(e):
            if not dialog.value or not getattr(getattr(e, "action", None), "keydown", False):
                return
            if e.key == "ArrowLeft":
                go_to_index(nav_state["idx"] - 1)
            elif e.key == "ArrowRight":
                go_to_index(nav_state["idx"] + 1)
            elif e.key == " " and toggle_origin_holder.get("fn"):
                toggle_origin_holder["fn"]()

        kb = ui.keyboard(on_key=handle_keyboard)
        dialog.on("hide", lambda: (setattr(kb, "active", False), active_lightbox_retouch_cb.update({"fn": None}), dialog.delete()))
        refresh_all()

    dialog.open()
