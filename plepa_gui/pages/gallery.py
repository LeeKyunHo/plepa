"""
plepa_gui.pages.gallery
캐릭터 에셋 갤러리:
1. 단일 캐릭터 전체 갤러리 뷰 (그리드 카드 뷰)
2. 다중 캐릭터 x 포즈 매트릭스 비교 뷰 (체형별/포즈별 비교 최적화)
"""

from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

from nicegui import run, ui
from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.reporter import open_in_explorer
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
    default_generation_service,
)
from plepa_engine.services.genit_exporter import default_genit_exporter
from plepa_engine.services.job_manager import global_job_manager
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.services.upscale_service import default_upscale_service
from plepa_gui.components.header import get_active_roster, render_header


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
from plepa_gui.components.retouch_editor import (
    RETOUCH_EDITOR_CSS,
    RETOUCH_EDITOR_HTML,
    build_retouch_editor_script,
)

mimetypes.add_type("image/webp", ".webp")
logger = logging.getLogger(__name__)


def _safe_notify(msg: str, type: str = "info") -> None:
    """UI 컨텍스트 유무와 무관하게 알림을 안전하게 호출합니다."""
    try:
        ui.notify(msg, type=type)
    except Exception as exc:
        logger.debug("ui.notify skipped (%s): %s", type, exc)


def detect_best_default_roster() -> str:
    """전역 활성 로스터를 기본값으로 사용하고 없을 시 자동 감지."""
    active_r = get_active_roster()
    if (PROJECTS_DIR / active_r).is_dir():
        return active_r
    best_roster = DEFAULT_ROSTER
    max_count = 0
    for p in PROJECTS_DIR.iterdir():
        if not p.is_dir() or p.name.startswith("."):
            continue
        assets_dir = p / "assets"
        if not assets_dir.is_dir():
            continue
        webp_count = len([f for f in assets_dir.rglob("*.webp") if "_origin" not in f.parts])
        if webp_count > max_count:
            max_count = webp_count
            best_roster = p.name
    return best_roster


def _pose_sort_key(code: str) -> tuple[int, int, str]:
    try:
        return (0, int(code), "")
    except ValueError:
        return (1, 0, code)


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

    existing_codes = sorted(existing_codes_set, key=_pose_sort_key)
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


def render_gallery_page() -> None:
    """통합 에셋 갤러리 페이지 렌더링."""
    render_header("/gallery")

    default_roster = detect_best_default_roster()
    
    def get_roster_poses(r: str) -> Dict[str, Any]:
        return default_pose_service.load_pose_db(engine="sdxl", roster=r)

    all_poses = get_roster_poses(default_roster)
    roster_scope = get_roster_gallery_pose_scope(default_roster)

    available_rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    if not available_rosters:
        available_rosters = [default_roster]

    conf = default_config_service.get_config()
    censor_spec_map = {s["field"]: s for s in GENERATION_OPTION_SPECS if s["field"] in ("censor_style", "censor_targets")}

    state = {
        "view_mode": "matrix",  # 'matrix', 'single', 'misc'
        "roster": default_roster,
        "single_char": "",
        "selected_chars": [],
        "selected_codes": list(roster_scope["existing_codes"]),
        "pose_set": "all",
        "misc_filter": "all",
        "matrix_sort": "code_asc",    # 'code_asc' (포즈 번호순), 'mtime_desc' (최근 생성/수정순)
        "single_sort": "mtime_desc",  # 'mtime_desc' (최신 생성순), 'code_asc' (포즈 번호순)
        "censor_style": conf.get("censor_style", "white_silhouette"),
        "censor_targets": conf.get("censor_targets", "penis"),
    }

    active_lightbox_retouch_cb = {"fn": None}
    image_widgets_by_rel: Dict[str, Any] = {}
    retouched_versions: Dict[str, int] = {}

    def _asset_web_url(rel_path: str, file_path: Optional[Path] = None, mtime: Optional[float] = None) -> str:
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

    def _refresh_single_thumbnail(rel_path: str, ts_val: int) -> None:
        retouched_versions[rel_path] = ts_val
        widget = image_widgets_by_rel.get(rel_path)
        if widget is not None:
            widget.set_source(f"/projects_static/{rel_path}?t={ts_val}")

    def _update_censor_setting(field: str, value: str) -> None:
        state[field] = value
        default_config_service.save_config({field: value})

    retouch_script = build_retouch_editor_script(
        on_saved_js="if (typeof emitEvent === 'function') { emitEvent('plepa_retouch_saved', savedPayload); }",
        on_notify_js=(
            "if (isError && typeof emitEvent === 'function') { emitEvent('plepa_retouch_error', {msg: msg}); }"
            " else { console.log(msg); }"
        ),
    )
    ui.add_head_html(RETOUCH_EDITOR_CSS)
    ui.add_body_html(RETOUCH_EDITOR_HTML + "\n" + retouch_script)

    def _handle_gallery_retouch_saved(e) -> None:
        cb = active_lightbox_retouch_cb.get("fn")
        if callable(cb):
            cb(e.args if hasattr(e, "args") else {})
        ui.notify("✅ 수동 검열 저장 및 파일 교체가 완료되었습니다!", type="positive")

    def _handle_gallery_retouch_error(e) -> None:
        msg = (e.args or {}).get("msg", "수동 검열 저장 실패") if hasattr(e, "args") else "수동 검열 저장 실패"
        ui.notify(str(msg), type="negative")

    ui.on("plepa_retouch_saved", _handle_gallery_retouch_saved)
    ui.on("plepa_retouch_error", _handle_gallery_retouch_error)

    with ui.column().classes("w-full max-w-[1550px] mx-auto p-6 gap-6"):
        # 상단 통합 컨트롤 바
        with ui.card().classes("w-full bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            with ui.row().classes("w-full justify-between items-center mb-3"):
                with ui.row().classes("items-center gap-4 flex-wrap"):
                    ui.label("🎨 에셋 갤러리").classes("text-xl font-bold text-slate-100")

                    # 뷰 모드 전환 탭
                    view_toggle = ui.toggle(
                        {
                            "matrix": "체형 비교 매트릭스 뷰",
                            "single": "단일 캐릭터 전체 갤러리",
                            "misc": "✨ 비포즈 / 기타 에셋 (배경·레퍼런스·샘플)",
                        },
                        value=state["view_mode"],
                        on_change=lambda e: switch_view_mode(e.value)
                    ).props("dense dark").classes("text-xs")

                    # 로스터 선택
                    ui.label("로스터:").classes("text-xs text-slate-400 font-semibold ml-2")
                    roster_sel = ui.select(
                        options=available_rosters,
                        value=state["roster"],
                        on_change=lambda e: on_roster_changed(e.value)
                    ).props("dense outlined dark options-dense").classes("w-36 text-sm")

                    for c_field, w_cls in (("censor_style", "w-36"), ("censor_targets", "w-32")):
                        c_spec = censor_spec_map.get(c_field)
                        if c_spec:
                            ui.select(
                                options=c_spec["choices"],
                                value=state[c_field],
                                label=c_spec["label"],
                                on_change=lambda e, fld=c_field: _update_censor_setting(fld, e.value),
                            ).props("dense outlined dark options-dense").classes(f"{w_cls} text-xs").tooltip(c_spec["tooltip"])

                with ui.row().classes("items-center gap-2"):
                    async def quick_fill_missing():
                        missing_map = default_asset_service.get_missing_poses_by_character(state["roster"])
                        tot = sum(len(v) for v in missing_map.values())
                        if tot == 0:
                            ui.notify("✨ 모든 포즈가 완비되었습니다!", type="positive")
                            return
                        ui.notify(f"⚡ 누락 포즈 {tot}개 백그라운드 생성 가동...", type="info")
                        for c_pfx, c_codes in missing_map.items():
                            if not c_codes:
                                continue
                            g_params = GenerationParams(
                                character_expr=c_pfx,
                                pose_expr=",".join(c_codes),
                                roster=state["roster"],
                                overwrite=False,
                                censor=True,
                                censor_style=state["censor_style"],
                                censor_targets=state["censor_targets"],
                            )
                            run.io_bound(default_generation_service.run_batch, g_params)
                        ui.notify(f"🚀 총 {tot}개 누락 포즈 생성이 시작되었습니다.", type="positive")

                    ui.button("⚡ 누락 채우기", icon="bolt", on_click=quick_fill_missing).props(
                        "unelevated color=amber-500 text-color=slate-950 dense size=sm font-bold"
                    ).tooltip("현재 로스터에서 비어있는 모든 포즈를 찾아 자동으로 일괄 생성합니다.")
                    queue_drawer_btn = ui.button("📋 리롤·대기열 (0)", icon="history", on_click=lambda: toggle_queue_panel()).props(
                        "outline color=sky-400 dense size=sm font-bold"
                    ).tooltip("리롤 대기열 상태와 새로 완성된 이미지 목록을 확인합니다.")
                    ui.button("📊 에셋 전수 감사", icon="assessment", on_click=lambda: open_audit_dialog()).props(
                        "unelevated color=emerald-600 text-color=white dense size=sm font-bold"
                    ).tooltip("로스터 캐릭터별 에셋 완비율과 누락 포즈를 1초 만에 전수 감사하고 누락분을 즉시 생성합니다.")
                    ui.button("📦 Genit 내보내기", icon="cloud_download", on_click=lambda: open_genit_export_dialog()).props(
                        "unelevated color=indigo-500 text-color=white dense size=sm font-bold"
                    ).tooltip("Genit 상용 규격({{url}}캐릭터코드/상황코드.webp)으로 에셋을 자동 변환 및 패키징합니다.")
                    ui.button("에셋 폴더 열기", icon="folder_open", on_click=lambda: open_current_folder()).props(
                        "outline color=slate-300 dense size=sm"
                    )
                    ui.button("새로고침", icon="refresh", on_click=lambda: render_content()).props(
                        "flat color=amber-400 dense size=sm"
                    )

            # 매트릭스 뷰 전용 필터 컨트롤
            matrix_controls = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")

            # 단일 캐릭터 뷰 전용 필터 컨트롤
            single_controls = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")

            # 기타/비포즈 에셋 전용 필터 컨트롤
            misc_controls = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")

        # 실시간 리롤 대기열 & 새로 완성된 이미지 기록 패널 (토글식)
        queue_panel_state = {
            "open": False,
            "last_sig": None,
            "synced_done_keys": set(),
        }
        queue_panel = ui.card().classes("w-full bg-slate-900/95 border border-sky-700/50 p-4 rounded-xl shadow-lg")
        queue_panel.set_visibility(False)

        # 메인 콘텐츠 뷰어 컨테이너
        content_container = ui.card().classes("w-full bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg overflow-x-auto min-h-[500px]")

    def toggle_queue_panel() -> None:
        queue_panel_state["open"] = not queue_panel_state["open"]
        queue_panel.set_visibility(queue_panel_state["open"])
        sync_queue_panel(force=True)

    def _clear_reroll_history() -> None:
        global_job_manager.clear_history()
        queue_panel_state["synced_done_keys"].clear()
        sync_queue_panel(force=True)
        ui.notify("🧹 완료된 작업 기록을 비웠습니다.", type="info")

    def sync_queue_panel(force: bool = False) -> None:
        status = global_job_manager.get_status()
        active_job = status.get("active_job")
        queued_jobs = status.get("queued_jobs") or []
        completed_items = status.get("completed_items") or []
        job_history = status.get("job_history") or []
        is_running = bool(status.get("is_running"))
        q_len = len(queued_jobs)
        done_len = len(completed_items)

        # 새로 완성된 이미지가 생기면 배경 썸네일만 1회 갱신
        for item in completed_items:
            item_key = (item.get("job_id"), item.get("code"), item.get("filename"), item.get("timestamp"))
            if item_key in queue_panel_state["synced_done_keys"]:
                continue
            queue_panel_state["synced_done_keys"].add(item_key)
            img_str = item.get("image_path") or ""
            if img_str:
                try:
                    rel_p = Path(img_str).relative_to(PROJECTS_DIR).as_posix()
                    _refresh_single_thumbnail(rel_p, int(time.time()))
                except Exception:
                    pass

        # 상단 버튼 라벨·색상 최신화 (이전 상태의 outline/unelevated/text-color 충돌 제거)
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
                        ui.button("🛑 대기열 중단", on_click=lambda: (global_job_manager.cancel_job(), sync_queue_panel(force=True))).props(
                            "outline color=rose-400 dense size=xs"
                        )
                    if done_len > 0 or job_history:
                        ui.button("🧹 기록 비우기", on_click=_clear_reroll_history).props(
                            "flat color=slate-300 dense size=xs"
                        )
                    ui.button(icon="close", on_click=toggle_queue_panel).props("flat round dense size=xs color=slate-400")

            # 1. 진행 중 + 대기열 표시
            if active_job or queued_jobs:
                with ui.row().classes("w-full items-center gap-2 flex-wrap mb-3 p-2.5 bg-slate-950/70 rounded-lg border border-slate-800"):
                    if active_job:
                        ui.chip(
                            f"⚡ 실행 중: {active_job.get('label', '')} ({active_job.get('started_at', '')})",
                            color="amber-700",
                            text_color="white",
                        ).props("dense text-xs font-bold")
                    for idx, qj in enumerate(queued_jobs, start=1):
                        ui.chip(
                            f"⏳ 대기 #{idx}: {qj.get('label', '')} ({qj.get('queued_at', '')})",
                            color="slate-800",
                            text_color="slate-200",
                        ).props("dense text-xs")

            # 2. 실패/취소 작업 이력 요약 (있을 때만)
            failed_jobs = [j for j in job_history if j.get("status") in ("failed", "cancelled")]
            if failed_jobs:
                with ui.row().classes("w-full items-center gap-2 flex-wrap mb-3"):
                    for fj in failed_jobs[:8]:
                        tag_lbl = "✖ 실패" if fj.get("status") == "failed" else "⏹ 취소"
                        ui.badge(
                            f"{tag_lbl}: {fj.get('label', '')} ({fj.get('finished_at', '')})",
                            color="rose-800" if fj.get("status") == "failed" else "slate-700",
                        ).props("dense text-[11px]").tooltip(fj.get("error") or "")

            # 3. 새로 완성된 이미지 목록 (클릭 시 바로 라이트박스 검수)
            if not completed_items:
                ui.label("아직 리롤/생성으로 새로 완성된 이미지 기록이 없습니다. 이미지를 둘러보며 리롤을 걸면 여기에 차곡차곡 쌓입니다.").classes(
                    "text-xs text-slate-400 py-2"
                )
            else:
                completed_paths: List[Path] = []
                for c_item in completed_items:
                    p_str = c_item.get("image_path") or ""
                    if p_str:
                        p_obj = Path(p_str)
                        if p_obj.is_file():
                            completed_paths.append(p_obj)

                with ui.row().classes("w-full gap-3 overflow-x-auto pb-1"):
                    for c_item in completed_items[:30]:
                        p_str = c_item.get("image_path") or ""
                        p_obj = Path(p_str) if p_str else None
                        has_file = bool(p_obj and p_obj.is_file())
                        rel_p = ""
                        web_u = ""
                        if has_file and p_obj is not None:
                            try:
                                rel_p = p_obj.relative_to(PROJECTS_DIR).as_posix()
                                web_u = _asset_web_url(rel_p, file_path=p_obj)
                            except Exception:
                                has_file = False

                        with ui.card().classes(
                            "w-36 shrink-0 bg-slate-800/80 border border-slate-700/70 p-2 rounded-lg hover:border-emerald-400 transition-all"
                        ):
                            if has_file and web_u and p_obj is not None:
                                idx_in_list = completed_paths.index(p_obj) if p_obj in completed_paths else 0
                                ui.image(web_u).classes(
                                    "w-full h-40 object-cover rounded cursor-pointer"
                                ).on(
                                    "click",
                                    lambda u=web_u, fp=p_obj, paths=completed_paths, idx=idx_in_list: open_lightbox(u, fp, paths, idx),
                                )
                            ui.label(f"[{c_item.get('char', '')}] #{c_item.get('code', '')}").classes(
                                "text-[11px] font-mono font-bold text-amber-300 mt-1 truncate w-full"
                            )
                            ui.label(str(c_item.get("label") or c_item.get("filename") or "")).classes(
                                "text-xs font-bold text-slate-100 truncate w-full"
                            )
                            with ui.row().classes("w-full items-center justify-between text-[10px] text-slate-400 font-mono"):
                                ui.label(f"{c_item.get('duration_sec', 0)}s")
                                ui.label(str(c_item.get("timestamp") or ""))

    ui.timer(1.5, sync_queue_panel)

    def switch_view_mode(mode: str):
        state["view_mode"] = mode
        update_control_bars()
        render_content()

    def on_roster_changed(new_r: str):
        state["roster"] = new_r
        nonlocal all_poses, roster_scope
        all_poses = get_roster_poses(new_r)
        roster_scope = get_roster_gallery_pose_scope(new_r)
        state["selected_chars"] = []
        state["single_char"] = ""
        state["pose_set"] = "all"
        state["selected_codes"] = list(roster_scope["existing_codes"])
        update_control_bars()
        render_content()

    def open_current_folder():
        if state["view_mode"] == "misc":
            target = PROJECTS_DIR / state["roster"]
        else:
            target = PROJECTS_DIR / state["roster"] / "assets"
        target.mkdir(parents=True, exist_ok=True)
        open_in_explorer(target)
        _safe_notify(f"📂 PC 파일 탐색기에서 폴더를 열었습니다: {target.name}", type="positive")

    def open_genit_export_dialog():
        """Genit 규격 내보내기 모달 다이얼로그 (해상도 통일 + 전체 일괄 내보내기 지원)."""
        chars = default_character_service.list_characters(roster=state["roster"])
        if not chars:
            ui.notify(f"로스터 '{state['roster']}'에 캐릭터가 없습니다.", type="warning")
            return

        with ui.dialog() as dlg, ui.card().classes("w-[540px] max-w-[95vw] p-6 bg-slate-900 border border-indigo-700/60 rounded-xl shadow-2xl"):
            ui.label("📦 Genit 상용 규격 에셋 내보내기").classes("text-lg font-bold text-indigo-300 mb-1")
            ui.label("로컬 원본 에셋은 100% 무손실 보존하고, dist/genit/ 폴더로 규격 변환·해상도 통일하여 내보냅니다.").classes("text-xs text-slate-400 mb-4")

            char_opts = {"__ALL__": f"🌟 로스터 전체 일괄 내보내기 ({len(chars)}명)"}
            for _, c, _ in chars:
                char_opts[c.prefix] = f"{c.name} ({c.prefix})"
            selected_char_prefix = {"val": "__ALL__"}

            init_char_obj = chars[0][1]
            init_export_code = default_genit_exporter.resolve_export_code(
                init_char_obj.name, init_char_obj.prefix, roster=state["roster"]
            )
            code_input_state = {"val": init_export_code}
            naming_state = {"val": "original_name"}
            size_state = {"val": "1024x1536"}

            ui.label("1. 대상 캐릭터 선택").classes("text-xs font-bold text-amber-400 mb-1")

            def _sync_code_visibility():
                show_legacy_code = (
                    selected_char_prefix["val"] != "__ALL__"
                    and naming_state["val"] == "legacy_code"
                )
                code_box.set_visibility(show_legacy_code)

            def on_dialog_char_change(prefix_val):
                selected_char_prefix["val"] = prefix_val
                if prefix_val != "__ALL__":
                    c_obj = next(c for _, c, _ in chars if c.prefix == prefix_val)
                    new_code = default_genit_exporter.resolve_export_code(
                        c_obj.name, c_obj.prefix, roster=state["roster"]
                    )
                    code_input.value = new_code
                    code_input_state["val"] = new_code
                _sync_code_visibility()

            ui.select(
                options=char_opts,
                value="__ALL__",
                on_change=lambda e: on_dialog_char_change(e.value),
            ).props("dense outlined dark options-dense").classes("w-full mb-3")

            ui.label("2. 경로·파일명 규격").classes("text-xs font-bold text-amber-400 mb-1")
            ui.select(
                options={
                    "original_name": "✨ 폴더/원본파일명 유지 (예: aya/aya_000_평상.webp — v2.2 권장)",
                    "legacy_code": "레거시 2글자 코드 (예: AA/A0.webp)",
                },
                value="original_name",
                on_change=lambda e: (naming_state.update({"val": e.value}), _sync_code_visibility()),
            ).props("dense outlined dark options-dense").classes("w-full mb-3")

            code_box = ui.column().classes("w-full mb-3 gap-1")
            with code_box:
                ui.label("2-1. 캐릭터 코드 (2글자 대문자)").classes("text-xs font-bold text-amber-400")
                code_input = ui.input(
                    value=init_export_code,
                    on_change=lambda e: code_input_state.update({"val": e.value.upper()}),
                ).props("dense outlined dark").classes("w-full font-mono font-bold")
            code_box.set_visibility(False)

            ui.label("3. 출력 해상도 통일").classes("text-xs font-bold text-amber-400 mb-1")
            ui.select(
                options={
                    "1024x1536": "✨ 1024×1536 / 가로 1536×1024 통일 (권장 · 방향 자동 감지 고해상도)",
                    "832x1216": "832×1216 / 가로 1216×832 통일 (SDXL 표준 · 방향 자동 감지)",
                    "original": "원본 해상도 그대로 (무손실 복사)",
                },
                value="1024x1536",
                on_change=lambda e: size_state.update({"val": e.value}),
            ).props("dense outlined dark options-dense").classes("w-full mb-6")

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("취소", on_click=dlg.close).props("flat color=slate-400")

                async def do_export():
                    c_prefix = selected_char_prefix["val"]
                    keep_orig = naming_state["val"] == "original_name"
                    size_map = {
                        "1024x1536": (1024, 1536),
                        "832x1216": (832, 1216),
                        "original": None,
                    }
                    target_sz = size_map.get(size_state["val"])
                    size_label = size_state["val"] if target_sz else "원본"
                    dlg.close()

                    ui.notify(f"📦 Genit 내보내기 진행 중 ({size_label})...", type="info")
                    if c_prefix == "__ALL__":
                        total_cnt, out_root, char_cnt = await run.io_bound(
                            default_genit_exporter.export_roster,
                            roster=state["roster"],
                            target_size=target_sz,
                            keep_original_filename=keep_orig,
                        )
                        if total_cnt > 0:
                            ui.notify(
                                f"🎉 '{state['roster']}' {char_cnt}명 총 {total_cnt}장 Genit 내보내기 완료! ({size_label})",
                                type="positive",
                            )
                            open_in_explorer(out_root)
                        else:
                            ui.notify(f"⚠️ 내보낼 수 있는 에셋이 없습니다: {state['roster']}", type="warning")
                    else:
                        c_obj = next(c for _, c, _ in chars if c.prefix == c_prefix)
                        c_code = code_input_state["val"].strip().upper() or "AA"
                        count, out_path, final_code = await run.io_bound(
                            default_genit_exporter.export_character,
                            roster=state["roster"],
                            char_prefix=c_prefix,
                            char_name=c_obj.name,
                            custom_export_code=c_code,
                            target_size=target_sz,
                            keep_original_filename=keep_orig,
                        )
                        if count > 0:
                            ui.notify(
                                f"🎉 {c_obj.name} ({final_code}) 에셋 {count}장 Genit 내보내기 완료! ({size_label})",
                                type="positive",
                            )
                            open_in_explorer(out_path)
                        else:
                            ui.notify(f"⚠️ 내보낼 수 있는 에셋이 없습니다: {c_prefix}", type="warning")

                ui.button("내보내기 실행", icon="check", on_click=do_export).props("unelevated color=indigo-500 font-bold")
        dlg.open()

    def open_audit_dialog():
        """로스터 내 에셋 완비율 및 누락 포즈 1초 전수 감사 모달 다이얼로그."""
        reports = default_asset_service.audit_roster_assets(roster=state["roster"])
        if not reports:
            ui.notify(f"로스터 '{state['roster']}'에 감사할 캐릭터가 없습니다.", type="warning")
            return

        with ui.dialog() as dlg, ui.card().classes("w-[900px] max-w-[95vw] max-h-[85vh] p-6 bg-slate-900 border border-emerald-700/60 rounded-xl shadow-2xl overflow-y-auto"):
            with ui.row().classes("w-full justify-between items-center mb-4 pb-2 border-b border-slate-800"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("assessment", size="26px").classes("text-emerald-400")
                    ui.label(f"📊 '{state['roster']}' 에셋 전수 감사 리포트 (총 {len(reports)}명)").classes("text-lg font-bold text-slate-100")
                ui.button(icon="close", on_click=dlg.close).props("flat dense round color=slate-400")

            # 감사 테이블
            with ui.element("table").classes("w-full border-collapse text-left text-xs mb-2"):
                with ui.element("thead"):
                    with ui.element("tr").classes("border-b border-slate-700 bg-slate-800/80"):
                        ui.element("th").classes("p-2.5 text-slate-300 font-bold")._text = "식별자"
                        ui.element("th").classes("p-2.5 text-slate-300 font-bold")._text = "이름"
                        ui.element("th").classes("p-2.5 text-slate-300 font-bold")._text = "보유 / 기대"
                        ui.element("th").classes("p-2.5 text-slate-300 font-bold")._text = "완비율"
                        ui.element("th").classes("p-2.5 text-slate-300 font-bold")._text = "무검열 백업(_origin)"
                        ui.element("th").classes("p-2.5 text-slate-300 font-bold")._text = "누락 포즈 코드"
                        ui.element("th").classes("p-2.5 text-slate-300 font-bold text-right")._text = "원클릭 액션"

                with ui.element("tbody"):
                    for r in reports:
                        with ui.element("tr").classes("border-b border-slate-800/70 hover:bg-slate-800/40"):
                            ui.element("td").classes("p-2.5 font-mono font-bold text-amber-300")._text = r["prefix"]
                            ui.element("td").classes("p-2.5 text-slate-200 font-semibold")._text = r["name"]
                            ui.element("td").classes("p-2.5 font-mono text-slate-300")._text = f"{r['present_count']} / {r['expected_count']}"
                            
                            with ui.element("td").classes("p-2.5"):
                                rate = r["completion_rate"]
                                color = "emerald" if rate >= 100 else ("amber" if rate >= 50 else "rose")
                                ui.badge(f"{rate}%", color=color).props("dense text-[10px]")

                            with ui.element("td").classes("p-2.5"):
                                orig_cnt = r["origin_count"]
                                if orig_cnt > 0:
                                    ui.badge(f"{orig_cnt}장 백업", color="cyan-800").props("dense text-[10px]")
                                else:
                                    ui.label("-").classes("text-slate-500")

                            with ui.element("td").classes("p-2.5"):
                                missing = r["missing_codes"]
                                if not missing:
                                    ui.label("✔ 완벽").classes("text-emerald-400 font-bold")
                                else:
                                    m_text = ",".join(missing[:4]) + (f".. (+{len(missing)-4})" if len(missing) > 4 else "")
                                    ui.label(m_text).classes("font-mono text-rose-300 text-[11px]").tooltip(",".join(missing))

                            with ui.element("td").classes("p-2.5 text-right"):
                                missing = r["missing_codes"]
                                if missing:
                                    async def trigger_missing(char_p=r["prefix"], miss_codes=missing):
                                        dlg.close()
                                        ui.notify(f"⚡ {char_p} 누락 포즈 {len(miss_codes)}개 생성 시작...", type="info")
                                        from plepa_engine.services.generation_service import GenerationParams, default_generation_service
                                        m_params = GenerationParams(
                                            character_expr=char_p,
                                            pose_expr=",".join(miss_codes),
                                            roster=state["roster"],
                                            censor=True,
                                            censor_style=state["censor_style"],
                                            censor_targets=state["censor_targets"],
                                        )
                                        await run.io_bound(default_generation_service.run_batch, m_params)
                                        ui.notify(f"🎉 {char_p} 결손 에셋 생성 완료!", type="positive")
                                        render_content()

                                    ui.button("⚡ 누락분 즉시 생성", on_click=trigger_missing).props(
                                        "unelevated dense size=xs color=amber-500 text-color=slate-950 font-bold"
                                    ).tooltip("누락된 포즈들만 묶어서 즉시 생성합니다")
                                else:
                                    ui.label("완비").classes("text-slate-500 text-[11px]")

        dlg.open()

    def update_control_bars():
        matrix_controls.clear()
        single_controls.clear()
        misc_controls.clear()

        # 현재 로스터의 캐릭터 및 보유 포즈 범위 동적 조회
        nonlocal roster_scope
        roster_scope = get_roster_gallery_pose_scope(state["roster"])
        char_asset_counts = roster_scope["char_counts"]
        set_opts = roster_scope["set_options"]
        if state["pose_set"] not in set_opts:
            state["pose_set"] = "all"
            state["selected_codes"] = list(roster_scope["existing_codes"])

        if state["view_mode"] == "matrix":
            matrix_controls.set_visibility(True)
            single_controls.set_visibility(False)
            misc_controls.set_visibility(False)

            with matrix_controls:
                # 1. 빠른 프리셋 버튼들
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    ui.label("빠른 캐릭터 프리셋:").classes("text-xs font-semibold text-slate-400 mr-1")

                    # 무협 10인 세트 퀵 버튼
                    if any(k in char_asset_counts for k in ["aa", "bb", "cc", "dd", "ee", "ff", "gg", "hh", "ii", "jj"]):
                        ui.button("🏮 무협 10인 전원", icon="auto_awesome", on_click=lambda: select_murim_all_preset()).props(
                            "unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40"
                        ).tooltip("무협 아포칼립스 10인(aa~jj) 전원 선택")
                        ui.button("🗡️ 정파 3인 (aa, bb, cc)", icon="shield", on_click=lambda: select_murim_orthodox_preset()).props(
                            "unelevated dense size=xs color=cyan-500/20 text-color=cyan-300 border border-cyan-500/40"
                        ).tooltip("정파 3인 (백설아, 제갈혜진, 남궁소율) 선택")

                    # 네쌍둥이 4인 세트 퀵 버튼
                    if any(k in char_asset_counts for k in ["yua", "serin", "sia", "hayul", "ykn_1st", "ykn_2nd", "ykn_3rd", "ykn_4th"]):
                        ui.button("🌸 네쌍둥이 4인 (전체 포즈)", icon="auto_awesome", on_click=lambda: select_quadruplets_preset()).props(
                            "unelevated dense size=xs color=rose-500/20 text-color=rose-300 border border-rose-500/40"
                        ).tooltip("설유아, 설세린, 설시아, 설하율 4인의 전체 포즈 비교")

                    # 땋은머리 3종 세트 퀵 버튼
                    if any(k in char_asset_counts for k in ["ykn_brd_a", "ykn_brd_b", "ykn_brd_c"]):
                        ui.button("🎀 땋은머리 샘플 3종", icon="face", on_click=lambda: select_ykn_braid_preset()).props(
                            "unelevated dense size=xs color=purple-500/20 text-color=purple-300 border border-purple-500/40"
                        ).tooltip("ykn_brd_a, ykn_brd_b, ykn_brd_c (000 평상) 선택")

                    # 유키노 체형 및 의상 묶음 퀵 버튼
                    if any(k in char_asset_counts for k in ["ykn_sle", "ykn_std", "ykn_mat"]):
                        ui.button("👑 유키노 체형 6종 세트", icon="group", on_click=lambda: select_ykn_preset()).props(
                            "unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40"
                        ).tooltip("ykn_sle, ykn_std, ykn_mat, ykn_crv, ykn_gla, ykn_gla_up 일괄 선택")

                    if any(k in char_asset_counts for k in ["ykn_bun", "ykn_nur", "ykn_mai"]):
                        ui.button("👗 유키노 의상 6종 세트", icon="checkroom", on_click=lambda: select_ykn_outfit_preset()).props(
                            "unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40"
                        ).tooltip("ykn_bun, ykn_nur, ykn_mai, ykn_swm, ykn_qip, ykn_gya 일괄 선택")

                    ui.button("📷 이미지 있는 캐릭터만 선택", icon="filter_alt", on_click=lambda: select_has_assets()).props(
                        "flat dense size=xs color=emerald-400"
                    )
                    ui.button("전체 선택", icon="done_all", on_click=lambda: select_all_chars(True)).props(
                        "flat dense size=xs color=slate-400"
                    )
                    ui.button("선택 해제", icon="remove_done", on_click=lambda: select_all_chars(False)).props(
                        "flat dense size=xs color=slate-500"
                    )

                    # 포즈 범위 선택 셀렉터 (현재 로스터 보유 에셋 기준 동적 필터링)
                    ui.label("포즈 범위:").classes("text-xs text-slate-400 font-semibold ml-4")
                    ui.select(
                        options=set_opts,
                        value=state["pose_set"],
                        on_change=lambda e: on_set_changed(e.value)
                    ).props("dense outlined dark options-dense").classes("w-56 text-xs")

                    ui.label("정렬:").classes("text-xs text-slate-400 font-semibold ml-2")
                    ui.toggle(
                        {
                            "code_asc": "🔢 포즈 번호순",
                            "mtime_desc": "🕒 최근 생성순 (NEW 먼저)",
                        },
                        value=state.get("matrix_sort", "code_asc"),
                        on_change=lambda e: (state.update({"matrix_sort": e.value}), render_content()),
                    ).props("dense dark").classes("text-xs")

                # 2. 개별 캐릭터 칩 목록 (보유 장수 뱃지 포함)
                with ui.row().classes("items-center gap-2 flex-wrap mt-1"):
                    ui.label("대상 캐릭터:").classes("text-xs font-semibold text-slate-400 mr-1")
                    for prefix, cnt in char_asset_counts.items():
                        is_selected = prefix in state["selected_chars"]
                        chip_label = f"{prefix} ({cnt}장)" if cnt > 0 else f"{prefix} (0)"
                        color_props = "color=amber-600 text-color=white" if is_selected else "color=slate-800 text-color=slate-300"
                        ui.chip(
                            chip_label,
                            selectable=True,
                            selected=is_selected,
                            on_selection_change=lambda e, p=prefix: (toggle_char(p, e.value))
                        ).props(f"dense text-xs {color_props}")

        elif state["view_mode"] == "single":
            # 단일 캐릭터 뷰
            matrix_controls.set_visibility(False)
            single_controls.set_visibility(True)
            misc_controls.set_visibility(False)

            with single_controls:
                with ui.row().classes("items-center gap-4 flex-wrap"):
                    ui.label("캐릭터 선택:").classes("text-xs text-slate-400 font-semibold")
                    char_opts = {p: f"{p} ({cnt}장)" for p, cnt in char_asset_counts.items() if cnt > 0}
                    if not char_opts:
                        char_opts = {p: f"{p} (0장)" for p in char_asset_counts.keys()}

                    ui.select(
                        options=char_opts,
                        value=state["single_char"] if state["single_char"] in char_opts else None,
                        on_change=lambda e: (state.update({"single_char": e.value}), render_content())
                    ).props("dense outlined dark options-dense").classes("w-60 text-sm")

                    ui.label("정렬:").classes("text-xs text-slate-400 font-semibold ml-2")
                    ui.toggle(
                        {
                            "mtime_desc": "🕒 최신 생성순 (NEW 먼저)",
                            "code_asc": "🔢 포즈 번호순",
                        },
                        value=state.get("single_sort", "mtime_desc"),
                        on_change=lambda e: (state.update({"single_sort": e.value}), render_content())
                    ).props("dense dark").classes("text-xs")

        else:
            # 기타 / 비포즈 에셋 뷰 (배경, 레퍼런스, 샘플)
            matrix_controls.set_visibility(False)
            single_controls.set_visibility(False)
            misc_controls.set_visibility(True)

            with misc_controls:
                with ui.row().classes("items-center justify-between w-full flex-wrap gap-3"):
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.label("카테고리 필터:").classes("text-xs font-semibold text-slate-400 mr-1")
                        filter_opts = {
                            "all": "전체 보기",
                            "reference": "레퍼런스 이미지",
                            "background": "배경 (BG)",
                            "sample": "비규격/샘플",
                        }
                        for f_key, f_label in filter_opts.items():
                            is_active = state.get("misc_filter", "all") == f_key
                            color = "color=purple-600 text-color=white" if is_active else "color=slate-800 text-color=slate-300"
                            ui.chip(
                                f_label,
                                selectable=True,
                                selected=is_active,
                                on_selection_change=lambda e, k=f_key: (
                                    state.update({"misc_filter": k}),
                                    update_control_bars(),
                                    render_content()
                                ) if e.value else None
                            ).props(f"dense text-xs {color}")

                    with ui.row().classes("items-center gap-2"):
                        ref_dir = PROJECTS_DIR / state["roster"] / "references"
                        ui.button("레퍼런스 폴더 열기", icon="folder", on_click=lambda: open_in_explorer(ref_dir)).props(
                            "flat dense size=xs color=purple-300"
                        )

    def get_character_asset_counts(roster: str) -> Dict[str, int]:
        """로스터 내 캐릭터별 생성된 에셋 개수 맵 반환."""
        chars = default_character_service.list_characters(roster=roster)
        counts = {}
        for _, c, _ in chars:
            assets = default_asset_service.list_character_assets(c.prefix, roster)
            counts[c.prefix] = len(assets)
        return counts

    def toggle_char(prefix: str, selected: bool):
        if selected and prefix not in state["selected_chars"]:
            state["selected_chars"].append(prefix)
        elif not selected and prefix in state["selected_chars"]:
            state["selected_chars"].remove(prefix)
        render_content()

    def _apply_char_preset(
        notify_msg: str,
        prefixes: List[str],
        pose_set: Optional[str] = None,
        selected_codes: Optional[List[str]] = None,
    ) -> None:
        _safe_notify(notify_msg, type="positive")
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = [p for p in prefixes if p in counts]
        if pose_set is not None:
            state["pose_set"] = pose_set
        if selected_codes is not None:
            state["selected_codes"] = selected_codes
        update_control_bars()
        render_content()

    def select_murim_all_preset():
        _apply_char_preset(
            "🏮 무협 10인 전원 선택 완료!",
            ["aa", "bb", "cc", "dd", "ee", "ff", "gg", "hh", "ii", "jj"],
        )

    def select_murim_orthodox_preset():
        _apply_char_preset("🗡️ 정파 3인 (aa, bb, cc) 선택 완료!", ["aa", "bb", "cc"])

    def select_quadruplets_preset():
        counts = get_character_asset_counts(state["roster"])
        quad_prefixes = (
            ["yua", "serin", "sia", "hayul"]
            if any(k in counts for k in ["yua", "serin"])
            else ["ykn_1st", "ykn_2nd", "ykn_3rd", "ykn_4th"]
        )
        _apply_char_preset(
            "🌸 네쌍둥이 4인 (전체 포즈) 선택 완료!",
            quad_prefixes,
            pose_set="all",
            selected_codes=list(roster_scope["existing_codes"]),
        )

    def select_ykn_braid_preset():
        _apply_char_preset(
            "유키노 땋은머리 샘플 3종 (#000 평상) 선택 완료!",
            ["ykn_brd_a", "ykn_brd_b", "ykn_brd_c"],
            pose_set="all",
            selected_codes=["000"],
        )

    def select_ykn_preset():
        _apply_char_preset(
            "유키노 성인 5대 체형 및 업스케일 6종 선택 완료!",
            ["ykn_sle", "ykn_std", "ykn_mat", "ykn_crv", "ykn_gla", "ykn_gla_up"],
            pose_set="v3_daily_53",
            selected_codes=[f"{i:03d}" for i in range(0, 53)],
        )

    def select_ykn_outfit_preset():
        _apply_char_preset(
            "유키노 신규 테마 의상 6종 선택 완료!",
            ["ykn_bun", "ykn_nur", "ykn_mai", "ykn_swm", "ykn_qip", "ykn_gya"],
            pose_set="v3_daily_53",
            selected_codes=[f"{i:03d}" for i in range(0, 53)],
        )

    def select_has_assets():
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = [p for p, c in counts.items() if c > 0]
        update_control_bars()
        render_content()

    def select_all_chars(select: bool):
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = list(counts.keys()) if select else []
        update_control_bars()
        render_content()

    def on_set_changed(set_id: str):
        state["pose_set"] = set_id
        matched_map = roster_scope.get("matched_codes_by_set", {})
        if set_id in matched_map:
            state["selected_codes"] = list(matched_map[set_id])
        else:
            state["selected_codes"] = list(roster_scope["existing_codes"])
        render_content()

    def render_content():
        image_widgets_by_rel.clear()
        content_container.clear()
        if state["view_mode"] == "matrix":
            render_matrix_view()
        elif state["view_mode"] == "single":
            render_single_char_view()
        else:
            render_misc_view()

    def render_single_char_view():
        """단일 캐릭터 전체 갤러리 카드 뷰."""
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
            # 4열 반응형 카드 그리드
            with ui.grid(columns=4).classes("w-full gap-4"):
                for idx, a in enumerate(assets):
                    img_path: Path = a["path"]
                    rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                    item_mtime = a.get("mtime")
                    web_url = _asset_web_url(rel_path, file_path=img_path, mtime=item_mtime)
                    code = a["code"]
                    pose_obj = all_poses.get(code)
                    label_str = pose_obj.label if pose_obj else a["label"]

                    with ui.card().classes("bg-slate-800/80 border border-slate-700/60 p-2 rounded-lg hover:border-amber-400 transition-all"):
                        img_w = ui.image(web_url).classes(
                            "w-full h-72 object-cover rounded shadow cursor-pointer hover:scale-[1.02] transition-transform"
                        ).on("click", lambda p=img_path, rp=rel_path, mt=item_mtime, i=idx: open_lightbox(_asset_web_url(rp, file_path=p, mtime=mt), p, all_single_paths, i))
                        image_widgets_by_rel[rel_path] = img_w

                        with ui.row().classes("w-full items-center justify-between mt-2 px-1"):
                            with ui.column().classes("gap-0"):
                                ui.label(f"#{code} {label_str}").classes("text-xs font-bold text-slate-100 truncate max-w-[170px]").tooltip(label_str)
                                mtime_val = a.get("mtime", 0.0)
                                mtime_str = datetime.fromtimestamp(mtime_val).strftime("%m-%d %H:%M") if mtime_val else ""
                                ui.label(f"{(a['size_bytes']/1024):.0f} KB · {mtime_str}").classes("text-[10px] text-slate-400 font-mono")

                            # 최근 1시간 이내 생성된 파일에 NEW 황금 뱃지 부여
                            is_new = (time.time() - a.get("mtime", 0.0)) < 3600
                            if is_new:
                                ui.badge("NEW ✨", color="amber-500").props("dense text-[10px] text-slate-950 font-bold")
                            elif a.get("censored_path"):
                                ui.badge("검열본", color="info").props("dense text-[10px]")

    def render_matrix_view():
        """캐릭터 x 포즈 2차원 매트릭스 비교 테이블."""
        char_counts = get_character_asset_counts(state["roster"])
        # 현재 로스터에 실제로 존재하는 캐릭터만 엄격하게 필터링 (타 프로젝트 캐릭터 침범 방지)
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
        codes = [
            c for c in codes
            if any(matrix.get(p, {}).get(c) and matrix[p][c].exists() for p in prefixes)
        ]
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
                        m = mp.stat().st_mtime
                        if m > best_m:
                            best_m = m
                    except OSError:
                        pass
            code_mtime_map[c] = best_m

        sort_mode = state.get("matrix_sort", "code_asc")
        if sort_mode == "mtime_desc":
            codes = sorted(codes, key=lambda c: (-code_mtime_map.get(c, 0.0), _pose_sort_key(c)))
        else:
            codes = sorted(codes, key=_pose_sort_key)

        with content_container:
            with ui.element("table").classes("w-full border-collapse text-left"):
                # Header: 포즈 라벨
                with ui.element("thead"):
                    with ui.element("tr").classes("border-b border-slate-700 bg-slate-800/80 sticky top-0 z-10"):
                        ui.element("th").classes("p-3 text-xs font-bold text-amber-400 w-36").add_slot(
                            "default", "캐릭터 / 포즈"
                        )
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

                # Body: 행=캐릭터, 열=포즈
                with ui.element("tbody"):
                    for prefix in prefixes:
                        with ui.element("tr").classes("border-b border-slate-800/70 hover:bg-slate-800/30 transition-colors"):
                            # 캐릭터 식별 칼럼
                            with ui.element("td").classes("p-3 text-sm font-bold text-slate-200 border-r border-slate-800"):
                                try:
                                    char_obj, _ = default_character_service.find_character(prefix, roster=state["roster"])
                                    ui.label(char_obj.name).classes("text-sm font-bold text-amber-300")
                                    ui.label(f"[{prefix}]").classes("text-xs text-slate-500 font-mono")
                                except Exception as exc:
                                    logger.debug("캐릭터 조회 폴백 (%s): %s", prefix, exc)
                                    ui.label(prefix).classes("text-sm text-slate-300")

                            # 행(캐릭터)별 존재하는 이미지 목록
                            row_paths = [matrix.get(prefix, {}).get(c) for c in codes if matrix.get(prefix, {}).get(c) and matrix.get(prefix, {}).get(c).exists()]

                            # 각 포즈별 이미지 셀
                            for code in codes:
                                img_path: Optional[Path] = matrix.get(prefix, {}).get(code)
                                with ui.element("td").classes("p-2 text-center align-middle border-r border-slate-800/40"):
                                    if img_path and img_path.exists():
                                        rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                                        web_url = _asset_web_url(rel_path, file_path=img_path)
                                        c_idx = row_paths.index(img_path) if img_path in row_paths else 0

                                        with ui.column().classes("items-center justify-center gap-1 mx-auto"):
                                            img_w = ui.image(web_url).classes(
                                                "w-28 h-40 object-cover rounded shadow cursor-pointer border border-slate-700 hover:border-amber-400 transition-all hover:scale-105"
                                            ).on("click", lambda p=img_path, rp=rel_path, paths=row_paths, idx=c_idx: open_lightbox(_asset_web_url(rp, file_path=p), p, paths, idx))
                                            image_widgets_by_rel[rel_path] = img_w
                                    else:
                                        with ui.column().classes("items-center justify-center w-28 h-40 bg-slate-800/30 rounded border border-dashed border-slate-700/60 text-slate-600"):
                                            ui.icon("image_not_supported", size="24px")
                                            ui.label("미생성").classes("text-[11px] mt-1")

    def render_misc_view():
        """비포즈 / 기타 에셋 (배경, 레퍼런스, 샘플) 그리드 뷰."""
        all_misc = default_asset_service.list_misc_assets(state["roster"])
        m_filter = state.get("misc_filter", "all")
        if m_filter != "all":
            assets = [a for a in all_misc if a.get("type") == m_filter]
        else:
            assets = all_misc

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
            # 4열 반응형 카드 그리드
            with ui.grid(columns=4).classes("w-full gap-4"):
                for idx, a in enumerate(assets):
                    img_path: Path = a["path"]
                    rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                    web_url = f"/projects_static/{rel_path}"
                    cat_name = a["category"]
                    folder_name = a.get("folder", "")
                    type_str = a.get("type", "misc")

                    badge_color = "purple-500" if type_str == "reference" else ("blue-500" if type_str == "background" else "emerald-500")

                    with ui.card().classes("bg-slate-800/80 border border-slate-700/60 p-2 rounded-lg hover:border-purple-400 transition-all"):
                        ui.image(web_url).classes(
                            "w-full h-72 object-cover rounded shadow cursor-pointer hover:scale-[1.02] transition-transform"
                        ).on("click", lambda u=web_url, p=img_path, i=idx: open_lightbox(u, p, misc_paths, i))

                        with ui.column().classes("w-full mt-2 px-1 gap-1"):
                            with ui.row().classes("w-full justify-between items-center"):
                                ui.badge(cat_name, color=badge_color).props("dense text-[10px]")
                                ui.label(f"{(a['size_bytes']/1024):.0f} KB").classes("text-[10px] text-slate-400")

                            ui.label(a["name"]).classes("text-xs font-bold text-slate-100 truncate w-full").tooltip(a["name"])
                            ui.label(f"📁 {folder_name}").classes("text-[10px] text-slate-500 font-mono truncate w-full")

    def open_lightbox(img_url: str, file_path: Path, item_paths: Optional[List[Path]] = None, current_idx: int = -1):
        items = [p for p in item_paths if p and p.exists()] if item_paths else [file_path]
        if file_path not in items:
            items.insert(0, file_path)
        cur_idx = current_idx if (0 <= current_idx < len(items)) else items.index(file_path)
        nav_state = {"idx": cur_idx}
        manifest_cache: Dict[Path, Dict[str, Any]] = {}
        dim_cache: Dict[Path, Tuple[Optional[Tuple[int, int]], bool]] = {}
        url_cache: Dict[Path, str] = {}

        def _get_cached_url(p: Path) -> str:
            cached = url_cache.get(p)
            if cached is not None:
                return cached
            try:
                rel = p.relative_to(PROJECTS_DIR).as_posix()
            except ValueError:
                rel = str(p)
            u = _asset_web_url(rel, file_path=p)
            url_cache[p] = u
            return u

        def _get_cached_dims(p: Path) -> Tuple[Optional[Tuple[int, int]], bool]:
            if p not in dim_cache:
                dims = default_upscale_service.get_image_dimensions(p)
                is_4k = default_upscale_service.is_already_4k(p) if dims else False
                dim_cache[p] = (dims, is_4k)
            return dim_cache[p]

        if img_url:
            url_cache[file_path] = img_url
        curr = {"url": img_url or _get_cached_url(file_path), "path": file_path}
        showing_origin = {"val": False}
        toggle_origin_holder = {"fn": None}

        with ui.dialog() as dialog, ui.card().classes(
            "max-w-6xl w-full md:w-[92vw] min-h-[480px] p-4 bg-slate-950 border border-slate-700 rounded-2xl shadow-2xl overflow-y-auto"
        ):
            header_box = ui.row().classes("w-full justify-between items-center mb-3 px-2 pb-2 border-b border-slate-800 flex-wrap gap-2")
            img_box = ui.column().classes("w-full flex-1 items-center justify-center py-2")
            with img_box:
                ui.html(
                    f'<div style="display: flex; justify-content: center; align-items: center; width: 100%; min-height: 400px;">'
                    f'<img id="plepaLightboxImg" src="{curr["url"]}" alt="{curr["path"].name}" style="max-height: 75vh; max-width: 100%; width: auto; height: auto; object-fit: contain; border-radius: 12px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); display: block;" />'
                    f'</div>'
                )
            meta_box = ui.row().classes("w-full justify-between items-center mt-2 px-2 pt-2 border-t border-slate-800/80 text-xs text-slate-400 font-mono flex-wrap gap-2")

            def go_to_index(idx: int):
                if not items:
                    return
                nav_state["idx"] = idx % len(items)
                new_path = items[nav_state["idx"]]
                curr["path"] = new_path
                curr["url"] = _get_cached_url(new_path)
                showing_origin["val"] = False
                refresh_img()
                refresh_header()
                refresh_meta()

            def refresh_meta():
                meta_box.clear()
                p = curr["path"]
                import re
                m_code = re.match(r"^([a-zA-Z0-9]+)_([a-zA-Z0-9]+)", p.name)
                prefix_val = m_code.group(1) if m_code else None
                code_val = m_code.group(2) if m_code else None

                # 매니페스트 경로: 서브폴더(p.parent.parent) 및 플랫(p.parent) 동시 지원 (메모리 캐시)
                manifest_p = (p.parent.parent / "_batch_manifest.json") if (p.parent.parent / "_batch_manifest.json").is_file() else (p.parent / "_batch_manifest.json")
                if manifest_p not in manifest_cache:
                    loaded_m: Dict[str, Any] = {}
                    if manifest_p.is_file():
                        try:
                            with open(manifest_p, "r", encoding="utf-8") as f:
                                loaded_m = parse_manifest_items_map(json.load(f))
                        except Exception as exc:
                            logger.debug("매니페스트 로드 스킵 (%s): %s", manifest_p, exc)
                    manifest_cache[manifest_p] = loaded_m
                manifest_map = manifest_cache[manifest_p]
                manifest_item = manifest_map.get(str(code_val or ""), {}) or manifest_map.get(f"{prefix_val}_{code_val}", {})

                seed_val = manifest_item.get("seed") or "미기록"
                ts_val = manifest_item.get("timestamp", "-")
                with meta_box:
                    with ui.row().classes("items-center gap-3"):
                        ui.label(f"🔒 골든 시드: {seed_val}").classes("text-amber-300 font-bold")
                        ui.label(f"🕒 생성시각: {ts_val}").classes("text-slate-400")
                        ui.label(f"📁 {p.name}").classes("text-slate-500 truncate max-w-sm")
                    with ui.row().classes("items-center gap-2"):
                        ui.label("단축키: ← 이전 | → 다음 | Space 원본/검열 토글").classes("text-[11px] text-slate-500")

            def refresh_header():
                header_box.clear()
                p = curr["path"]
                with header_box:
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        # 이전/다음 네비게이션 버튼
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

                        dims, is_4k = _get_cached_dims(p)
                        if dims:
                            dim_text = f"{dims[0]}x{dims[1]}"
                            if is_4k:
                                ui.badge("4K UHD", color="emerald-600").props("dense text-xs")
                            ui.badge(dim_text, color="slate-800").props("dense text-xs border border-slate-700 text-slate-300 font-mono")

                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        size_kb = p.stat().st_size / 1024 if p.exists() else 0
                        ui.label(f"{size_kb:.1f} KB").classes("text-xs text-slate-400 mr-2")

                        import re
                        m_code = re.match(r"^([a-zA-Z0-9]+)_([a-zA-Z0-9]+)", p.name)
                        prefix_val = m_code.group(1) if m_code else None
                        code_val = m_code.group(2) if m_code else None

                        if prefix_val and code_val:
                            async def run_reroll(reuse_seed: bool):
                                try:
                                    from plepa_engine.services.generation_service import GenerationParams
                                    from plepa_engine.services.job_manager import global_job_manager

                                    r_params = GenerationParams(
                                        character_expr=prefix_val,
                                        pose_expr=code_val,
                                        roster=state["roster"],
                                        overwrite=True,
                                        censor=True,
                                        censor_style=state["censor_style"],
                                        censor_targets=state["censor_targets"],
                                        reuse_seed=reuse_seed,
                                    )
                                    done_event = threading.Event()
                                    callback_holder: Dict[str, Any] = {"results": [], "error": None}

                                    def _on_reroll_done(res_list, err):
                                        callback_holder["results"] = res_list
                                        callback_holder["error"] = err
                                        done_event.set()

                                    target_item_path = items[nav_state["idx"]] if items else p
                                    started, queue_pos = global_job_manager.enqueue_job(
                                        r_params,
                                        label=f"갤러리 리롤 {prefix_val}:{code_val}",
                                        on_complete=_on_reroll_done,
                                    )
                                    sync_queue_panel(force=True)
                                    if started:
                                        ui.notify(f"🔄 #{code_val} {'골든 시드 고정' if reuse_seed else '새 시드'} 리롤 시작...", type="info")
                                    else:
                                        ui.notify(f"⏳ #{code_val} 리롤이 대기열 #{queue_pos}에 등록되었습니다.", type="info")

                                    await run.io_bound(done_event.wait)
                                    sync_queue_panel(force=True)
                                    if callback_holder["error"] is not None:
                                        ui.notify(f"⚠️ 리롤 중단/오류: {callback_holder['error']}", type="warning")
                                        return

                                    results = callback_holder["results"]
                                    if results and results[0].success:
                                        res_img = results[0].image_path
                                        rel = res_img.relative_to(PROJECTS_DIR).as_posix()
                                        ts_val = int(time.time())
                                        if rel in image_widgets_by_rel:
                                            _refresh_single_thumbnail(rel, ts_val)
                                        else:
                                            retouched_versions[rel] = ts_val
                                        ui.notify(f"🎉 [{prefix_val}] #{code_val} 리롤 완료!", type="positive")

                                        # 사용자가 여전히 같은 이미지를 보고 있는 경우에만 라이트박스 즉시 갱신
                                        still_same = bool(dialog.value and items and items[nav_state["idx"]] == target_item_path)
                                        if still_same:
                                            curr["path"] = res_img
                                            curr["url"] = f"/projects_static/{rel}?t={ts_val}"
                                            url_cache[res_img] = curr["url"]
                                            dim_cache.pop(res_img, None)
                                            manifest_cache.clear()
                                            refresh_header()
                                            refresh_img()
                                            refresh_meta()
                                    else:
                                        ui.notify(f"❌ [{prefix_val}] #{code_val} 리롤 생성 실패", type="negative")
                                except Exception as ex:
                                    ui.notify(f"❌ 리롤 오류: {ex}", type="negative")

                            ui.button("🎲 새 시드 리롤", icon="casino", on_click=lambda: run_reroll(False)).props(
                                "unelevated dense size=sm color=blue-600 text-white font-bold"
                            ).tooltip("새로운 무작위 시드로 다시 생성합니다")

                            ui.button("🔒 시드 고정 리롤", icon="lock_reset", on_click=lambda: run_reroll(True)).props(
                                "unelevated dense size=sm color=amber-600 text-slate-950 font-bold"
                            ).tooltip("기존 골든 시드를 고정하여 구도는 유지하고 의상/태그만 다시 생성합니다")

                            async def run_delete_asset():
                                res = default_asset_service.delete_asset_bundle(curr["path"])
                                if res["success"]:
                                    ui.notify(f"🗑️ {res['filename']} 휴지통으로 이동되었습니다.", type="warning")
                                    dialog.close()
                                    render_content()
                                else:
                                    ui.notify("❌ 삭제 실패", type="negative")

                            ui.button("🗑️ 삭제", icon="delete", on_click=run_delete_asset).props(
                                "unelevated dense size=sm color=rose-700 text-white font-bold"
                            ).tooltip("해당 에셋(원본 포함)을 휴지통으로 안전하게 이동합니다 (단축키: Del)")

                        # _origin 무검열 원본 비교 및 복원 버튼 (2-Track 서브폴더/플랫 동시 지원)
                        main_asset_p = items[nav_state["idx"]] if items else p
                        char_pfx = prefix_val or main_asset_p.name.split("_")[0]
                        cand_sub = PROJECTS_DIR / state["roster"] / "assets" / f"{char_pfx}_origin" / main_asset_p.parent.name / main_asset_p.name
                        cand_flat = PROJECTS_DIR / state["roster"] / "assets" / f"{char_pfx}_origin" / main_asset_p.name
                        origin_cand = cand_sub if cand_sub.is_file() else cand_flat

                        rel_main_asset = main_asset_p.relative_to(PROJECTS_DIR).as_posix()
                        retouch_payload = {
                            "relPath": rel_main_asset,
                            "roster": state["roster"],
                            "title": f"✏️ {main_asset_p.name} 수동 검열/덧칠",
                            "imageUrl": f"/projects_static/{urllib.parse.quote(rel_main_asset, safe='/')}",
                            "originUrl": (
                                f"/projects_static/{urllib.parse.quote(origin_cand.relative_to(PROJECTS_DIR).as_posix(), safe='/')}"
                                if origin_cand.is_file()
                                else ""
                            ),
                        }

                        def _on_retouch_saved_refresh(payload: dict) -> None:
                            if not isinstance(payload, dict) or payload.get("rel_path") != rel_main_asset:
                                return
                            ts_val = payload.get("timestamp") or int(time.time())
                            showing_origin["val"] = False
                            curr["path"] = main_asset_p
                            curr["url"] = f"/projects_static/{urllib.parse.quote(rel_main_asset, safe='/')}?t={ts_val}"
                            url_cache[main_asset_p] = curr["url"]
                            _refresh_single_thumbnail(rel_main_asset, ts_val)
                            refresh_header()
                            refresh_img()
                            refresh_meta()

                        active_lightbox_retouch_cb["fn"] = _on_retouch_saved_refresh

                        async def open_manual_retouch():
                            await ui.run_javascript(f"openRetouchEditor({json.dumps(retouch_payload, ensure_ascii=False)});")

                        ui.button("✏️ 직접 검열", icon="brush", on_click=open_manual_retouch).props(
                            "unelevated dense size=sm color=emerald-700 text-white font-bold"
                        ).tooltip("기존 검열 제거(원본 로드) 후 직접 화이트 브러시/지우개로 편집하고 파일을 즉시 교체합니다")

                        if origin_cand.is_file():
                            def on_toggle_origin():
                                showing_origin["val"] = not showing_origin["val"]
                                target_f = origin_cand if showing_origin["val"] else main_asset_p
                                curr["path"] = target_f
                                curr["url"] = _get_cached_url(target_f)
                                toggle_btn.text = "🛡️ 검열본" if showing_origin["val"] else "👁️ 원본"
                                refresh_img()

                            toggle_origin_holder["fn"] = on_toggle_origin

                            toggle_btn = ui.button(
                                "🛡️ 검열본" if showing_origin["val"] else "👁️ 원본",
                                icon="visibility",
                                on_click=on_toggle_origin
                            ).props("unelevated dense size=sm color=slate-700 text-amber-300 border border-amber-500/40").tooltip("무검열 원본과 검열본을 번갈아 비교합니다 (단축키: Space)")

                            async def on_restore_origin():
                                ok = await run.io_bound(default_asset_service.restore_from_origin, prefix_val, code_val, state["roster"])
                                if ok:
                                    ui.notify("⏪ 무검열 원본으로 복원되었습니다!", type="positive")
                                    showing_origin["val"] = False
                                    curr["path"] = main_asset_p
                                    rel = main_asset_p.relative_to(PROJECTS_DIR).as_posix()
                                    ts_val = int(time.time())
                                    curr["url"] = f"/projects_static/{rel}?t={ts_val}"
                                    url_cache[main_asset_p] = curr["url"]
                                    _refresh_single_thumbnail(rel, ts_val)
                                    refresh_header()
                                    refresh_img()
                                    refresh_meta()
                                else:
                                    ui.notify("복원 실패", type="negative")

                            ui.button("⏪ 원본 복원", icon="undo", on_click=on_restore_origin).props(
                                "flat dense size=sm color=rose-400"
                            ).tooltip("assets/{char}_origin/의 무검열 원본을 본 폴더로 복사해 검열을 해제합니다")
                        else:
                            toggle_origin_holder["fn"] = None

                        # 4K AI 업스케일 버튼
                        _, is_already = _get_cached_dims(p)

                        async def on_upscale_click():
                            upscale_btn.props("loading")
                            ui.notify("🚀 AI 초해상화(4x-UltraSharp) 연산 중입니다... (약 15~20초 소요)", type="info")
                            try:
                                res_path = await run.io_bound(default_upscale_service.upscale_file, curr["path"], overwrite=False)
                                if res_path and res_path.exists():
                                    curr["path"] = res_path
                                    rel = res_path.relative_to(PROJECTS_DIR).as_posix()
                                    ts_val = int(time.time())
                                    curr["url"] = f"/projects_static/{rel}?t={ts_val}"
                                    url_cache[res_path] = curr["url"]
                                    dim_cache.pop(res_path, None)
                                    ui.notify(f"🎉 4K 업스케일 완료: {res_path.name}", type="positive")
                                    refresh_header()
                                    refresh_img()
                                    refresh_meta()
                                    if rel in image_widgets_by_rel:
                                        _refresh_single_thumbnail(rel, ts_val)
                                    else:
                                        render_content()
                                else:
                                    ui.notify("❌ 4K 업스케일 생성에 실패했습니다.", type="negative")
                            except Exception as ex:
                                ui.notify(f"❌ 업스케일 오류: {ex}", type="negative")
                            finally:
                                upscale_btn.props(remove="loading")

                        upscale_btn = ui.button(
                            "4K 완료 (재연산)" if is_already else "✨ 4K AI 업스케일",
                            icon="auto_fix_high",
                            on_click=on_upscale_click
                        ).props(
                            f"unelevated dense size=sm color={'emerald-700' if is_already else 'purple-600'} text-white"
                        ).tooltip(
                            "이미 4K 초고화질입니다 (클릭 시 재연산)" if is_already else "4x-UltraSharp 초해상화 모델로 4K(4096x6144) 무손실 업스케일"
                        )

                        # 새 탭에서 원본 전용 뷰어로 열기
                        view_url = f"/view_image?src={curr['url']}&name={p.name}"
                        ui.button(
                            "새 탭",
                            icon="open_in_new",
                            on_click=lambda u=view_url: ui.navigate.to(u, new_tab=True)
                        ).props(f'flat dense size=sm color=amber-400 href="{view_url}" target="_blank"').tooltip(
                            "새 탭에서 고화질 뷰어로 보기"
                        )

                        def handle_open_folder():
                            open_in_explorer(curr["path"])
                            _safe_notify(f"🖥️ PC 파일 탐색기를 열었습니다: {curr['path'].name}", type="positive")

                        ui.button(icon="folder", on_click=handle_open_folder).props(
                            "flat dense size=sm color=slate-300"
                        ).tooltip("호스트 PC 파일 탐색기에서 해당 파일 위치 열기")
                        ui.button(icon="close", on_click=dialog.close).props("flat round dense color=slate-300")

            def refresh_img(preload: bool = True):
                preload_urls: List[str] = []
                if preload and len(items) > 1:
                    n = len(items)
                    idx = nav_state["idx"]
                    for offset in (1, -1):
                        adj_p = items[(idx + offset) % n]
                        u = _get_cached_url(adj_p)
                        if u != curr["url"]:
                            preload_urls.append(u)
                js_code = (
                    "const im = document.getElementById('plepaLightboxImg');"
                    f"if (im) {{ im.alt = {json.dumps(curr['path'].name)}; im.src = {json.dumps(curr['url'])}; }}"
                    + "".join(f"new Image().src = {json.dumps(pu)};" for pu in preload_urls)
                )
                ui.run_javascript(js_code)

            def handle_keyboard(e):
                if not dialog.value or not getattr(getattr(e, "action", None), "keydown", False):
                    return
                if e.key == "ArrowLeft":
                    go_to_index(nav_state["idx"] - 1)
                elif e.key == "ArrowRight":
                    go_to_index(nav_state["idx"] + 1)
                elif e.key == " ":
                    if toggle_origin_holder.get("fn"):
                        toggle_origin_holder["fn"]()

            kb = ui.keyboard(on_key=handle_keyboard)

            def _cleanup_lightbox():
                kb.active = False
                active_lightbox_retouch_cb["fn"] = None
                dialog.delete()

            dialog.on("hide", _cleanup_lightbox)

            refresh_header()
            refresh_img()
            refresh_meta()

        dialog.open()

    # 초기화: 진입 시 아무 캐릭터도 미리 올라가지 않은 깨끗한 빈 상태로 시작
    state["selected_chars"] = []
    state["single_char"] = ""

    update_control_bars()
    render_content()
