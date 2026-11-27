"""
plepa_gui.pages.gallery
캐릭터 에셋 갤러리 (매트릭스 비교 뷰 · 단일 캐릭터 뷰 · 비포즈 뷰 · 라이트박스).
상세 뷰/컨트롤/다이얼로그/라이트박스는 gallery_parts/ 모듈로 분리되어 있습니다.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from nicegui import ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.reporter import open_in_explorer
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
)
from plepa_engine.services.job_manager import global_job_manager
from plepa_engine.services.pose_service import default_pose_service
from plepa_gui.components.header import get_available_rosters, render_header
from plepa_gui.components.retouch_editor import (
    RETOUCH_EDITOR_CSS,
    RETOUCH_EDITOR_HTML,
    build_retouch_editor_script,
)
from plepa_gui.pages.gallery_parts.controls import (
    render_matrix_controls,
    render_misc_controls,
    render_single_controls,
)
from plepa_gui.pages.gallery_parts.data_helpers import (
    detect_best_default_roster,
    get_character_asset_counts,
    get_roster_gallery_pose_scope,
    parse_manifest_items_map,
    pose_sort_key as _pose_sort_key,
    safe_notify as _safe_notify,
)
from plepa_gui.pages.gallery_parts.dialogs import (
    open_audit_dialog,
    open_genit_export_dialog,
)
from plepa_gui.pages.gallery_parts.lightbox import open_gallery_lightbox
from plepa_gui.pages.gallery_parts.queue_panel import sync_queue_panel_state
from plepa_gui.pages.gallery_parts.views import (
    render_matrix_view,
    render_misc_view,
    render_single_char_view,
)

mimetypes.add_type("image/webp", ".webp")


def _mount_retouch_assets(
    active_lightbox_retouch_cb: Dict[str, Any],
) -> None:
    """갤러리 페이지용 수동 검열 에디터 정적 HTML/CSS/JS와 완료 이벤트를 바인딩합니다."""
    retouch_script = build_retouch_editor_script(
        on_saved_js="if (typeof emitEvent === 'function') { emitEvent('plepa_retouch_saved', savedPayload); }",
        on_notify_js=(
            "if (isError && typeof emitEvent === 'function') { emitEvent('plepa_retouch_error', {msg: msg}); }"
            " else { console.log(msg); }"
        ),
    )
    ui.add_head_html(RETOUCH_EDITOR_CSS)
    ui.add_body_html(RETOUCH_EDITOR_HTML + "\n" + retouch_script)

    def _on_saved(e) -> None:
        cb = active_lightbox_retouch_cb.get("fn")
        if callable(cb):
            cb(e.args if hasattr(e, "args") else {})
        ui.notify("✅ 수동 검열 저장 및 파일 교체가 완료되었습니다!", type="positive")

    def _on_err(e) -> None:
        msg = (e.args or {}).get("msg", "수동 검열 저장 실패") if hasattr(e, "args") else "수동 검열 저장 실패"
        ui.notify(str(msg), type="negative")

    ui.on("plepa_retouch_saved", _on_saved)
    ui.on("plepa_retouch_error", _on_err)


def _create_gallery_actions(
    state: Dict[str, Any],
    ctx: Dict[str, Any],
) -> Dict[str, Callable]:
    """갤러리 프리셋 선택·로스터 전환·뷰 갱신 콜백 묶음을 구성합니다."""

    def render_content() -> None:
        ctx["image_widgets_by_rel"].clear()
        ctx["content_container"].clear()
        if state["view_mode"] == "matrix":
            render_matrix_view(
                ctx["content_container"], state, ctx["all_poses"],
                ctx["image_widgets_by_rel"], ctx["retouched_versions"], ctx["open_lightbox"],
            )
        elif state["view_mode"] == "single":
            render_single_char_view(
                ctx["content_container"], state, ctx["all_poses"],
                ctx["image_widgets_by_rel"], ctx["retouched_versions"], ctx["open_lightbox"],
            )
        else:
            render_misc_view(ctx["content_container"], state, ctx["open_lightbox"])

    def update_control_bars() -> None:
        ctx["matrix_controls"].clear()
        ctx["single_controls"].clear()
        ctx["misc_controls"].clear()
        ctx["roster_scope"] = get_roster_gallery_pose_scope(state["roster"])
        roster_scope = ctx["roster_scope"]
        if state["pose_set"] not in roster_scope["set_options"]:
            state["pose_set"] = "all"
            state["selected_codes"] = list(roster_scope["existing_codes"])

        ctx["matrix_controls"].set_visibility(state["view_mode"] == "matrix")
        ctx["single_controls"].set_visibility(state["view_mode"] == "single")
        ctx["misc_controls"].set_visibility(state["view_mode"] not in ("matrix", "single"))

        if state["view_mode"] == "matrix":
            render_matrix_controls(ctx["matrix_controls"], state, roster_scope, actions)
        elif state["view_mode"] == "single":
            render_single_controls(ctx["single_controls"], state, roster_scope["char_counts"], render_content)
        else:
            render_misc_controls(ctx["misc_controls"], state, lambda: (update_control_bars(), render_content()))

    def _apply_preset(msg: str, prefixes: List[str], pose_set: Optional[str] = None, codes: Optional[List[str]] = None) -> None:
        _safe_notify(msg, type="positive")
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = [p for p in prefixes if p in counts]
        if pose_set is not None:
            state["pose_set"] = pose_set
        if codes is not None:
            state["selected_codes"] = codes
        update_control_bars()
        render_content()

    def select_quadruplets() -> None:
        counts = get_character_asset_counts(state["roster"])
        quad = ["yua", "serin", "sia", "hayul"] if any(k in counts for k in ("yua", "serin")) else ["ykn_1st", "ykn_2nd", "ykn_3rd", "ykn_4th"]
        _apply_preset("🌸 네쌍둥이 4인 (전체 포즈) 선택 완료!", quad, "all", list(ctx["roster_scope"]["existing_codes"]))

    actions: Dict[str, Callable] = {
        "render_content": render_content,
        "update_control_bars": update_control_bars,
        "switch_view_mode": lambda m: (state.update({"view_mode": m}), update_control_bars(), render_content()),
        "on_roster_changed": lambda r: (
            state.update({"roster": r, "selected_chars": [], "single_char": "", "pose_set": "all"}),
            ctx.update({"all_poses": default_pose_service.load_pose_db(engine="sdxl", roster=r), "roster_scope": get_roster_gallery_pose_scope(r)}),
            state.update({"selected_codes": list(ctx["roster_scope"]["existing_codes"])}),
            update_control_bars(),
            render_content(),
        ),
        "toggle_char": lambda p, sel: (
            state["selected_chars"].append(p) if sel and p not in state["selected_chars"] else (state["selected_chars"].remove(p) if not sel and p in state["selected_chars"] else None),
            render_content(),
        ),
        "on_set_changed": lambda sid: (
            state.update({"pose_set": sid, "selected_codes": list(ctx["roster_scope"].get("matched_codes_by_set", {}).get(sid, ctx["roster_scope"]["existing_codes"]))}),
            render_content(),
        ),
        "select_has_assets": lambda: (state.update({"selected_chars": [p for p, c in get_character_asset_counts(state["roster"]).items() if c > 0]}), update_control_bars(), render_content()),
        "select_all_chars": lambda sel: (state.update({"selected_chars": list(get_character_asset_counts(state["roster"]).keys()) if sel else []}), update_control_bars(), render_content()),
        "select_murim_all_preset": lambda: _apply_preset("🏮 무협 10인 전원 선택 완료!", ["aa", "bb", "cc", "dd", "ee", "ff", "gg", "hh", "ii", "jj"]),
        "select_murim_orthodox_preset": lambda: _apply_preset("🗡️ 정파 3인 (aa, bb, cc) 선택 완료!", ["aa", "bb", "cc"]),
        "select_quadruplets_preset": select_quadruplets,
        "select_ykn_braid_preset": lambda: _apply_preset("유키노 땋은머리 샘플 3종 (#000 평상) 선택 완료!", ["ykn_brd_a", "ykn_brd_b", "ykn_brd_c"], "all", ["000"]),
        "select_ykn_preset": lambda: _apply_preset("유키노 성인 5대 체형 및 업스케일 6종 선택 완료!", ["ykn_sle", "ykn_std", "ykn_mat", "ykn_crv", "ykn_gla", "ykn_gla_up"], "v3_daily_53", [f"{i:03d}" for i in range(0, 53)]),
        "select_ykn_outfit_preset": lambda: _apply_preset("유키노 신규 테마 의상 6종 선택 완료!", ["ykn_bun", "ykn_nur", "ykn_mai", "ykn_swm", "ykn_qip", "ykn_gya"], "v3_daily_53", [f"{i:03d}" for i in range(0, 53)]),
    }
    return actions


def _build_gallery_header_controls(
    state: Dict[str, Any],
    available_rosters: List[str],
    censor_spec_map: Dict[str, Any],
    actions: Dict[str, Callable],
    sync_queue_cb: Callable[[bool], None],
    toggle_queue_cb: Callable[[], None],
) -> Any:
    """상단 통합 컨트롤 바(뷰 탭, 로스터, 검열 옵션, 일괄 액션 버튼)를 렌더링합니다."""

    async def quick_fill_missing():
        missing_map = default_asset_service.get_missing_poses_by_character(state["roster"])
        tot = sum(len(v) for v in missing_map.values())
        if tot == 0:
            ui.notify("✨ 모든 포즈가 완비되었습니다!", type="positive")
            return
        enqueued_chars = 0
        for c_pfx, c_codes in missing_map.items():
            if not c_codes:
                continue
            g_params = GenerationParams(
                character_expr=c_pfx, pose_expr=",".join(c_codes), roster=state["roster"],
                overwrite=False, censor=True, censor_style=state["censor_style"], censor_targets=state["censor_targets"],
            )
            global_job_manager.enqueue_job(g_params, label=f"누락 채우기 {c_pfx} ({len(c_codes)}종)")
            enqueued_chars += 1
        sync_queue_cb(True)
        ui.notify(f"🚀 {enqueued_chars}명 / 총 {tot}개 누락 포즈를 작업 대기열에 등록했습니다.", type="positive")

    def open_current_folder():
        target = PROJECTS_DIR / state["roster"] if state["view_mode"] == "misc" else PROJECTS_DIR / state["roster"] / "assets"
        target.mkdir(parents=True, exist_ok=True)
        open_in_explorer(target)
        _safe_notify(f"📂 PC 파일 탐색기에서 폴더를 열었습니다: {target.name}", type="positive")

    with ui.row().classes("w-full justify-between items-center mb-3"):
        with ui.row().classes("items-center gap-4 flex-wrap"):
            ui.label("🎨 에셋 갤러리").classes("text-xl font-bold text-slate-100")
            ui.toggle(
                {"matrix": "체형 비교 매트릭스 뷰", "single": "단일 캐릭터 전체 갤러리", "misc": "✨ 비포즈 / 기타 에셋 (배경·레퍼런스·샘플)"},
                value=state["view_mode"],
                on_change=lambda e: actions["switch_view_mode"](e.value),
            ).props("dense dark").classes("text-xs")

            ui.label("로스터:").classes("text-xs text-slate-400 font-semibold ml-2")
            ui.select(options=available_rosters, value=state["roster"], on_change=lambda e: actions["on_roster_changed"](e.value)).props(
                "dense outlined dark options-dense"
            ).classes("w-36 text-sm")

            for c_field, w_cls in (("censor_style", "w-36"), ("censor_targets", "w-32")):
                c_spec = censor_spec_map.get(c_field)
                if c_spec:
                    ui.select(
                        options=c_spec["choices"], value=state[c_field], label=c_spec["label"],
                        on_change=lambda e, fld=c_field: (state.update({fld: e.value}), default_config_service.save_config({fld: e.value})),
                    ).props("dense outlined dark options-dense").classes(f"{w_cls} text-xs").tooltip(c_spec["tooltip"])

        with ui.row().classes("items-center gap-2"):
            ui.button("⚡ 누락 채우기", icon="bolt", on_click=quick_fill_missing).props("unelevated color=amber-500 text-color=slate-950 dense size=sm font-bold").tooltip("현재 로스터에서 비어있는 모든 포즈를 찾아 자동으로 일괄 생성합니다.")
            queue_drawer_btn = ui.button("📋 리롤·대기열 (0)", icon="history", on_click=toggle_queue_cb).props("outline color=sky-400 dense size=sm font-bold").tooltip("리롤 대기열 상태와 새로 완성된 이미지 목록을 확인합니다.")
            ui.button("📊 에셋 전수 감사", icon="assessment", on_click=lambda: open_audit_dialog(state, sync_queue_cb)).props("unelevated color=emerald-600 text-color=white dense size=sm font-bold").tooltip("로스터 캐릭터별 에셋 완비율과 누락 포즈를 1초 만에 전수 감사하고 누락분을 즉시 생성합니다.")
            ui.button("📦 Genit 내보내기", icon="cloud_download", on_click=lambda: open_genit_export_dialog(state)).props("unelevated color=indigo-500 text-color=white dense size=sm font-bold").tooltip("Genit 상용 규격({{url}}캐릭터코드/상황코드.webp)으로 에셋을 자동 변환 및 패키징합니다.")
            ui.button("에셋 폴더 열기", icon="folder_open", on_click=open_current_folder).props("outline color=slate-300 dense size=sm")
            ui.button("새로고침", icon="refresh", on_click=lambda: actions["render_content"]()).props("flat color=amber-400 dense size=sm")
    return queue_drawer_btn


def render_gallery_page() -> None:
    """통합 에셋 갤러리 페이지 렌더링."""
    render_header("/gallery")

    default_roster = detect_best_default_roster()
    roster_scope = get_roster_gallery_pose_scope(default_roster)
    conf = default_config_service.get_config()
    censor_spec_map = {s["field"]: s for s in GENERATION_OPTION_SPECS if s["field"] in ("censor_style", "censor_targets")}
    state: Dict[str, Any] = {
        "view_mode": "matrix", "roster": default_roster, "single_char": "", "selected_chars": [],
        "selected_codes": list(roster_scope["existing_codes"]), "pose_set": "all", "misc_filter": "all",
        "matrix_sort": "code_asc", "single_sort": "mtime_desc",
        "censor_style": conf.get("censor_style", "white_silhouette"),
        "censor_targets": conf.get("censor_targets", "penis"),
    }

    active_lightbox_retouch_cb: Dict[str, Any] = {"fn": None}
    image_widgets_by_rel: Dict[str, Any] = {}
    retouched_versions: Dict[str, int] = {}
    queue_panel_state: Dict[str, Any] = {"open": False, "last_sig": None, "synced_done_keys": set()}
    _mount_retouch_assets(active_lightbox_retouch_cb)

    def _refresh_single_thumbnail(rel_path: str, ts_val: int) -> None:
        retouched_versions[rel_path] = ts_val
        widget = image_widgets_by_rel.get(rel_path)
        if widget is not None:
            widget.set_source(f"/projects_static/{rel_path}?t={ts_val}")

    ctx: Dict[str, Any] = {
        "all_poses": default_pose_service.load_pose_db(engine="sdxl", roster=default_roster),
        "roster_scope": roster_scope,
        "image_widgets_by_rel": image_widgets_by_rel,
        "retouched_versions": retouched_versions,
    }
    actions = _create_gallery_actions(state, ctx)

    def sync_queue_panel(force: bool = False) -> None:
        sync_queue_panel_state(
            queue_panel, queue_drawer_btn, queue_panel_state, retouched_versions,
            _refresh_single_thumbnail, toggle_queue_panel,
            lambda: (global_job_manager.clear_history(), queue_panel_state["synced_done_keys"].clear(), sync_queue_panel(True), ui.notify("🧹 완료된 작업 기록을 비웠습니다.", type="info")),
            ctx["open_lightbox"], force=force,
        )

    def toggle_queue_panel() -> None:
        queue_panel_state["open"] = not queue_panel_state["open"]
        queue_panel.set_visibility(queue_panel_state["open"])
        sync_queue_panel(True)

    ctx["open_lightbox"] = lambda img_url, file_path, item_paths=None, current_idx=-1: open_gallery_lightbox(
        img_url, file_path, state, retouched_versions, image_widgets_by_rel,
        active_lightbox_retouch_cb, _refresh_single_thumbnail, sync_queue_panel, actions["render_content"],
        item_paths=item_paths, current_idx=current_idx,
    )

    with ui.column().classes("w-full max-w-[1550px] mx-auto p-6 gap-6"):
        with ui.card().classes("w-full bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            queue_drawer_btn = _build_gallery_header_controls(
                state, get_available_rosters(ensure_roster=default_roster), censor_spec_map, actions, sync_queue_panel, toggle_queue_panel
            )
            ctx["matrix_controls"] = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")
            ctx["single_controls"] = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")
            ctx["misc_controls"] = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")

        queue_panel = ui.card().classes("w-full bg-slate-900/95 border border-sky-700/50 p-4 rounded-xl shadow-lg")
        queue_panel.set_visibility(False)
        ctx["content_container"] = ui.card().classes("w-full bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg overflow-x-auto min-h-[500px]")

    ui.timer(1.5, sync_queue_panel)
    actions["update_control_bars"]()
    actions["render_content"]()


__all__ = [
    "detect_best_default_roster",
    "get_roster_gallery_pose_scope",
    "parse_manifest_items_map",
    "render_gallery_page",
]
