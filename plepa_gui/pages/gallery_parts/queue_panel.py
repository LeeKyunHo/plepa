"""
plepa_gui.pages.gallery_parts.queue_panel
갤러리 상단 리롤·대기열 상태 배지 및 최근 완성 이미지 드로어 패널.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from nicegui import ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.job_manager import global_job_manager
from plepa_gui.pages.gallery_parts.data_helpers import build_asset_web_url


def _update_queue_drawer_button(queue_drawer_btn: Any, is_running: bool, q_len: int, done_len: int) -> None:
    """진행·대기·완료 건수에 따라 리롤 대기열 토글 버튼의 텍스트와 색상을 갱신합니다."""
    if is_running:
        queue_drawer_btn.set_text(
            f"⏳ 진행 1 · 대기 {q_len} · 완료 {done_len}" if q_len > 0 else f"⚡ 진행 1 · 완료 {done_len}"
        )
        queue_drawer_btn.props(
            remove="outline",
            add="unelevated color=sky-400 text-color=slate-950 dense size=sm font-bold",
        )
    elif done_len > 0:
        queue_drawer_btn.set_text(f"✅ 새 완성 {done_len}건 확인")
        queue_drawer_btn.props(
            remove="outline",
            add="unelevated color=teal-500 text-color=white dense size=sm font-bold",
        )
    else:
        queue_drawer_btn.set_text("📋 리롤·대기열 (0)")
        queue_drawer_btn.props(
            remove="unelevated text-color",
            add="outline color=sky-400 dense size=sm font-bold",
        )


def _render_completed_cards(
    completed_items: List[Dict[str, Any]],
    retouched_versions: Dict[str, int],
    open_lightbox_cb: Callable[..., None],
) -> None:
    """새로 완성된 이미지 카드 스크롤 스트립을 렌더링합니다."""
    if not completed_items:
        ui.label("아직 리롤/생성으로 새로 완성된 이미지 기록이 없습니다. 이미지를 둘러보며 리롤을 걸면 여기에 차곡차곡 쌓입니다.").classes(
            "text-xs text-slate-400 py-2"
        )
        return

    completed_paths: List[Path] = []
    for c_item in completed_items:
        p_str = c_item.get("image_path") or ""
        if p_str and Path(p_str).is_file():
            completed_paths.append(Path(p_str))

    with ui.row().classes("w-full gap-3 overflow-x-auto pb-1"):
        for c_item in completed_items[:30]:
            p_str = c_item.get("image_path") or ""
            p_obj = Path(p_str) if p_str else None
            has_file = bool(p_obj and p_obj.is_file())
            web_u = ""
            if has_file and p_obj is not None:
                try:
                    rel_p = p_obj.relative_to(PROJECTS_DIR).as_posix()
                    web_u = build_asset_web_url(rel_p, retouched_versions, file_path=p_obj)
                except Exception:
                    has_file = False

            with ui.card().classes("w-36 shrink-0 bg-slate-800/80 border border-slate-700/70 p-2 rounded-lg hover:border-emerald-400 transition-all"):
                if has_file and web_u and p_obj is not None:
                    idx_in_list = completed_paths.index(p_obj) if p_obj in completed_paths else 0
                    ui.image(web_u).classes("w-full h-40 object-cover rounded cursor-pointer").on(
                        "click",
                        lambda u=web_u, fp=p_obj, paths=completed_paths, idx=idx_in_list: open_lightbox_cb(u, fp, paths, idx),
                    )
                ui.label(f"[{c_item.get('char', '')}] #{c_item.get('code', '')}").classes("text-[11px] font-mono font-bold text-amber-300 mt-1 truncate w-full")
                ui.label(str(c_item.get("label") or c_item.get("filename") or "")).classes("text-xs font-bold text-slate-100 truncate w-full")
                with ui.row().classes("w-full items-center justify-between text-[10px] text-slate-400 font-mono"):
                    ui.label(f"{c_item.get('duration_sec', 0)}s")
                    ui.label(str(c_item.get("timestamp") or ""))


def sync_queue_panel_state(
    queue_panel: Any,
    queue_drawer_btn: Any,
    queue_panel_state: Dict[str, Any],
    retouched_versions: Dict[str, int],
    refresh_thumb_cb: Callable[[str, int], None],
    toggle_cb: Callable[[], None],
    clear_history_cb: Callable[[], None],
    open_lightbox_cb: Callable[..., None],
    force: bool = False,
) -> None:
    """GlobalJobManager 작업 상태를 폴링하여 버튼 라벨·썸네일·드로어 UI를 동기화합니다."""
    status = global_job_manager.get_status()
    active_job = status.get("active_job")
    queued_jobs = status.get("queued_jobs") or []
    completed_items = status.get("completed_items") or []
    job_history = status.get("job_history") or []
    is_running = bool(status.get("is_running"))
    q_len, done_len = len(queued_jobs), len(completed_items)

    for item in completed_items:
        item_key = (item.get("job_id"), item.get("code"), item.get("filename"), item.get("timestamp"))
        if item_key in queue_panel_state["synced_done_keys"]:
            continue
        queue_panel_state["synced_done_keys"].add(item_key)
        img_str = item.get("image_path") or ""
        if img_str:
            try:
                rel_p = Path(img_str).relative_to(PROJECTS_DIR).as_posix()
                refresh_thumb_cb(rel_p, int(time.time()))
            except Exception:
                pass

    _update_queue_drawer_button(queue_drawer_btn, is_running, q_len, done_len)

    sig = (
        queue_panel_state["open"],
        is_running,
        q_len,
        status.get("current", 0),
        status.get("total", 0),
        done_len,
        len(job_history),
        active_job.get("job_id") if active_job else None,
        job_history[0].get("status") if job_history else None,
    )
    if not force and sig == queue_panel_state["last_sig"]:
        return
    queue_panel_state["last_sig"] = sig
    if not queue_panel_state["open"]:
        return

    queue_panel.clear()
    with queue_panel:
        with ui.row().classes("w-full items-center justify-between mb-3 pb-2 border-b border-slate-800 flex-wrap gap-2"):
            with ui.row().classes("items-center gap-2 flex-wrap"):
                ui.icon("history", size="22px").classes("text-sky-400")
                ui.label("📋 리롤 대기열 & 새로 완성된 이미지 기록").classes("text-base font-bold text-slate-100")
                if is_running:
                    ui.badge(f"진행 중 ({status.get('current', 0)}/{status.get('total', 0)})", color="amber-600").props("dense text-xs")
                if q_len > 0:
                    ui.badge(f"대기 {q_len}건", color="sky-700").props("dense text-xs")
                ui.badge(f"완료 {done_len}건", color="emerald-700").props("dense text-xs")

            with ui.row().classes("items-center gap-2"):
                if is_running or q_len > 0:
                    ui.button("🛑 대기열 중단", on_click=lambda: (global_job_manager.cancel_job(), sync_queue_panel_state(
                        queue_panel, queue_drawer_btn, queue_panel_state, retouched_versions,
                        refresh_thumb_cb, toggle_cb, clear_history_cb, open_lightbox_cb, force=True,
                    ))).props("outline color=rose-400 dense size=xs")
                if done_len > 0 or job_history:
                    ui.button("🧹 기록 비우기", on_click=clear_history_cb).props("flat color=slate-300 dense size=xs")
                ui.button(icon="close", on_click=toggle_cb).props("flat round dense size=xs color=slate-400")

        if active_job or queued_jobs:
            with ui.row().classes("w-full items-center gap-2 flex-wrap mb-3 p-2.5 bg-slate-950/70 rounded-lg border border-slate-800"):
                if active_job:
                    ui.chip(f"⚡ 실행 중: {active_job.get('label', '')} ({active_job.get('started_at', '')})", color="amber-700", text_color="white").props("dense text-xs font-bold")
                for idx, qj in enumerate(queued_jobs, start=1):
                    ui.chip(f"⏳ 대기 #{idx}: {qj.get('label', '')} ({qj.get('queued_at', '')})", color="slate-800", text_color="slate-200").props("dense text-xs")

        failed_jobs = [j for j in job_history if j.get("status") in ("failed", "cancelled")]
        if failed_jobs:
            with ui.row().classes("w-full items-center gap-2 flex-wrap mb-3"):
                for fj in failed_jobs[:8]:
                    tag_lbl = "✖ 실패" if fj.get("status") == "failed" else "⏹ 취소"
                    ui.badge(f"{tag_lbl}: {fj.get('label', '')} ({fj.get('finished_at', '')})", color="rose-800" if fj.get("status") == "failed" else "slate-700").props("dense text-[11px]").tooltip(fj.get("error") or "")

        _render_completed_cards(completed_items, retouched_versions, open_lightbox_cb)
