"""
plepa_gui.pages.generate
캐릭터 x 포즈 배치 생성 설정, 실시간 진행률 및 비동기 작업 제어 페이지.
"""

from __future__ import annotations

from typing import Any, Dict

from nicegui import ui
from plepa_engine.comfy_client import ComfyClient
from plepa_engine.config import COMFY_HOST, DEFAULT_SDXL_CKPT
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
)
from plepa_engine.services.job_manager import global_job_manager
from plepa_engine.services.pose_background_service import default_pose_bg_service
from plepa_engine.services.pose_service import default_pose_service
from plepa_gui.components.header import (
    get_active_roster,
    get_available_rosters,
    render_header,
)
from plepa_gui.components.option_controls import (
    normalize_option_values,
    render_option_controls,
)
from plepa_gui.pages.generate_sections import (
    build_initial_generate_state,
    build_status_preview_widgets,
    format_config_badge_text,
    get_bg_options,
    get_select_options,
    render_pose_quick_pack_bar,
    resolve_state_pose_codes,
    sync_generate_status_widgets,
)


def _create_selection_callbacks(
    state: Dict[str, Any],
    widgets: Dict[str, Any],
    discovered_models: Dict[str, Any],
    ckpt_options: list,
) -> Dict[str, Any]:
    """배치 생성 페이지의 캐릭터·포즈·배경·모델 선택 콜백을 생성합니다."""

    def _on_char_checkbox_change(prefix: str, checked: bool) -> None:
        if checked and prefix not in state["selected_chars"]:
            state["selected_chars"].append(prefix)
        elif not checked and prefix in state["selected_chars"]:
            state["selected_chars"].remove(prefix)

    def refresh_char_checkboxes(keep_selection: bool = False) -> None:
        widgets["chars_box"].clear()
        chars = default_character_service.list_characters(roster=state["roster"])
        if not keep_selection:
            state["selected_chars"] = []
        with widgets["chars_box"]:
            for _, c, _ in chars:
                ui.checkbox(
                    f"{c.name} ({c.prefix})",
                    value=(c.prefix in state["selected_chars"]),
                    on_change=lambda e, p=c.prefix: _on_char_checkbox_change(p, bool(e.value)),
                ).props("dark dense").classes("text-xs text-slate-200")

    def auto_match_background() -> None:
        try:
            codes = resolve_state_pose_codes(state)
            bg_options_list = get_bg_options(state["roster"], state["engine"])
            if len(codes) == 1:
                single_bg = default_pose_bg_service.get_background_for_pose(state["roster"], codes[0])
                if single_bg in bg_options_list:
                    state["bg_preset"] = single_bg
                    widgets["bg_sel"].value = single_bg
                    ui.notify(f"🎯 단일 포즈({codes[0]}) 맞춤 배경 적용: {bg_options_list[single_bg]}", type="positive")
                    return
            state["bg_preset"] = "auto"
            widgets["bg_sel"].value = "auto"
            ui.notify("🎯 포즈별 자동 매핑(Auto) 적용: 각 포즈(일상, 카페, 침실 등)에 맞는 배경이 동적으로 자동 주입됩니다.", type="positive")
        except Exception as exc:
            print(f"[WARNING] auto_match_background: {exc}")

    def on_pose_mode_changed(mode_str: str) -> None:
        widgets["pose_mode_container"].clear()
        sets = default_pose_service.load_pose_sets()
        set_options = {s.id: f"{s.name} ({len(s.codes)}종)" for s in sets}
        if state["selected_pose_set"] not in set_options and set_options:
            state["selected_pose_set"] = next(iter(set_options.keys()))

        with widgets["pose_mode_container"]:
            if "포즈 세트" in mode_str:
                state["pose_selection_mode"] = "set"
                ui.select(
                    options=set_options,
                    value=state["selected_pose_set"],
                    on_change=lambda e: (state.update({"selected_pose_set": e.value}), auto_match_background()),
                ).props("outlined dark dense options-dense").classes("w-full text-sm")
            else:
                state["pose_selection_mode"] = "custom"
                ui.input(
                    "포즈 표현식 (예: all, 000..019, 020,027,080, sample10)",
                    value=state["custom_pose_expr"],
                    on_change=lambda e: state.update({"custom_pose_expr": e.value}),
                ).props("outlined dark dense").classes("w-full text-sm")

    def select_all_chars(select: bool) -> None:
        chars = default_character_service.list_characters(roster=state["roster"])
        state["selected_chars"] = [c.prefix for _, c, _ in chars] if select else []
        msg = f"로스터 '{state['roster']}' 캐릭터 {len(chars)}명 전체 선택 완료" if select else "선택 해제 완료"
        ui.notify(msg, type="info")
        refresh_char_checkboxes(keep_selection=True)

    def select_genit_set(set_id: str, label_name: str) -> None:
        state["pose_selection_mode"] = "set"
        state["selected_pose_set"] = set_id
        widgets["mode_set_btn"].value = "포즈 세트 사용"
        on_pose_mode_changed("포즈 세트 사용")
        auto_match_background()
        ui.notify(f"👑 Genit {label_name} 선택 완료!", type="positive")

    def on_roster_changed(new_r: str) -> None:
        state["roster"] = new_r
        refresh_char_checkboxes()
        new_opts = get_bg_options(new_r, state["engine"])
        widgets["bg_sel"].options = new_opts
        if state["bg_preset"] not in new_opts:
            state["bg_preset"] = "none" if "none" in new_opts else list(new_opts.keys())[0]
            widgets["bg_sel"].value = state["bg_preset"]
        auto_match_background()

    def render_model_selector() -> None:
        widgets["model_select_container"].clear()
        with widgets["model_select_container"]:
            ckpts = discovered_models.get("checkpoints", [])
            lbl = f"SDXL 체크포인트 ({len(ckpts)}종 감지됨)" if ckpts else "SDXL 체크포인트 모델명"
            ui.select(
                options=ckpt_options,
                value=state["sdxl_ckpt"],
                label=lbl,
                on_change=lambda e: state.update({"sdxl_ckpt": e.value}),
            ).props("dense outlined dark options-dense use-input new-value-mode=add-unique").classes("w-full text-xs").tooltip(
                "ComfyUI models/checkpoints 폴더 내 모델을 선택하거나 직접 입력합니다."
            )
        widgets["config_badge"].set_text(format_config_badge_text())

    return {
        "refresh_char_checkboxes": refresh_char_checkboxes,
        "auto_match_background": auto_match_background,
        "on_pose_mode_changed": on_pose_mode_changed,
        "select_all_chars": select_all_chars,
        "select_genit_set": select_genit_set,
        "on_roster_changed": on_roster_changed,
        "render_model_selector": render_model_selector,
    }


def _create_generate_callbacks(
    state: Dict[str, Any],
    widgets: Dict[str, Any],
    discovered_models: Dict[str, Any],
    ckpt_options: list,
    log_state: Dict[str, int],
) -> Dict[str, Any]:
    """배치 생성 페이지의 선택 콜백과 FIFO 대기열 실행 콜백을 결합합니다."""
    cbs = _create_selection_callbacks(state, widgets, discovered_models, ckpt_options)

    def sync_job_status() -> None:
        log_state["rendered"] = sync_generate_status_widgets(widgets, log_state["rendered"])

    def request_cancel() -> None:
        if global_job_manager.is_running:
            global_job_manager.cancel_job()
            widgets["status_label"].set_text("취소 요청됨... (현재 항목 완료 후 중단)")
            ui.notify("생성 중단 요청이 전달되었습니다.", type="warning")

    def start_generation() -> None:
        if not state["selected_chars"]:
            ui.notify("최소 1명 이상의 캐릭터를 선택해 주십시오.", type="warning")
            return
        if state["pose_selection_mode"] == "set":
            sets = default_pose_service.load_pose_sets()
            target_set = next((s for s in sets if s.id == state["selected_pose_set"]), None)
            if not target_set or not target_set.codes:
                ui.notify("선택된 포즈 세트에 포즈가 없습니다.", type="warning")
                return
            pose_expr = ",".join(target_set.codes)
        else:
            pose_expr = state["custom_pose_expr"].strip()
            if not pose_expr:
                ui.notify("포즈 표현식을 입력해 주십시오.", type="warning")
                return

        char_expr = ",".join(state["selected_chars"])
        params = GenerationParams(
            character_expr=char_expr,
            pose_expr=pose_expr,
            roster=state["roster"],
            engine="sdxl",
            ckpt=state["sdxl_ckpt"],
            bg_preset=state["bg_preset"],
            **normalize_option_values(GENERATION_OPTION_SPECS, state),
        )
        started, q_pos = global_job_manager.enqueue_job(params, label=f"배치 생성 {char_expr} ({pose_expr})")
        if started:
            widgets["log_box"].clear()
            log_state["rendered"] = 0
            ui.notify("백그라운드 배치 작업 시작! 다른 페이지로 이동해도 멈추지 않고 계속 생성됩니다.", type="positive")
        else:
            ui.notify(f"📋 대기열 #{q_pos} 등록: 진행 중인 작업 완료 후 순차 실행됩니다.", type="info")
        sync_job_status()

    cbs.update({
        "sync_job_status": sync_job_status,
        "request_cancel": request_cancel,
        "start_generation": start_generation,
    })
    return cbs


def render_generate_page() -> None:
    """배치 생성 페이지 렌더링."""
    render_header("/generate")

    conf = default_config_service.get_config()
    discovered_models = ComfyClient(host=conf.get("comfy_host", COMFY_HOST)).get_available_models()
    ckpt_options = get_select_options(discovered_models.get("checkpoints", []), conf.get("sdxl_ckpt", DEFAULT_SDXL_CKPT))

    state = build_initial_generate_state(get_active_roster(), conf)
    available_rosters = get_available_rosters(ensure_roster=state["roster"])
    bg_options = get_bg_options(state["roster"], state["engine"])
    widgets: Dict[str, Any] = {}
    log_state = {"rendered": 0}
    cbs = _create_generate_callbacks(state, widgets, discovered_models, ckpt_options, log_state)

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        with ui.card().classes("w-[520px] bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg"):
            ui.label("⚡ 배치 생성 설정").classes("text-xl font-bold text-slate-100 mb-4")
            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("1. 대상 캐릭터 선택").classes("text-xs font-bold text-amber-400")
                with ui.row().classes("gap-1"):
                    ui.button("전체 선택", icon="done_all", on_click=lambda: cbs["select_all_chars"](True)).props("flat dense size=xs color=amber-400").tooltip("현재 로스터의 모든 캐릭터 선택")
                    ui.button("선택 해제", icon="remove_done", on_click=lambda: cbs["select_all_chars"](False)).props("flat dense size=xs color=slate-400").tooltip("선택 해제")

            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("로스터:").classes("text-xs text-slate-400")
                ui.select(options=available_rosters, value=state["roster"], on_change=lambda e: cbs["on_roster_changed"](e.value)).props("dense outlined dark options-dense").classes("w-48 text-sm")

            widgets["chars_box"] = ui.column().classes("w-full max-h-36 overflow-y-auto bg-slate-800/40 p-2 rounded border border-slate-700/50 mb-4")

            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("2. 포즈 선택").classes("text-xs font-bold text-amber-400")
                with ui.row().classes("gap-1"):
                    ui.button("🌟 10대 골든 (sample10)", icon="star", on_click=lambda: cbs["select_genit_set"]("sample10", "10대 대표 골든 샘플러")).props("unelevated dense size=xs color=amber-500 text-color=slate-950 font-bold").tooltip("000, 020, 034, 044, 048, 060, 067, 088, 130, 131 (10대 대표 골든 샘플러)")
                    ui.button("🏫 캠퍼스 108종", icon="school", on_click=lambda: cbs["select_genit_set"]("campus_108", "캠퍼스 108종 풀패키지")).props("unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40").tooltip("000~052, 060~079(활성), 080~124, 130~132 (108종 풀패키지, 오토코노코 자동 +70 대칭)")

            render_pose_quick_pack_bar(cbs["select_genit_set"])

            with ui.row().classes("w-full gap-4 mb-2"):
                widgets["mode_set_btn"] = ui.radio(["포즈 세트 사용", "코드 직접 입력"], value="포즈 세트 사용", on_change=lambda e: cbs["on_pose_mode_changed"](e.value)).props("dark inline dense")
            widgets["pose_mode_container"] = ui.column().classes("w-full mb-3")

            with ui.row().classes("w-full p-2.5 bg-emerald-950/40 border border-emerald-600/40 rounded-lg items-center gap-2 mb-4"):
                ui.icon("check_circle", size="18px").classes("text-emerald-400")
                ui.label("기본 동작: 이미 있는 이미지는 자동 건너뛰고 누락된 포즈만 채웁니다.").classes("text-[11px] text-emerald-200")

            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("3. 모델 및 보정 옵션").classes("text-xs font-bold text-amber-400")
                widgets["config_badge"] = ui.label("").classes("text-xs font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30")

            with ui.row().classes("w-full gap-4 mb-2 items-center"):
                ui.badge("SDXL 공식 엔진", color="emerald-700").props("dense text-xs")
                widgets["bg_sel"] = ui.select(options=bg_options, value=state["bg_preset"], label="배경 프리셋", on_change=lambda e: state.update({"bg_preset": e.value})).props("dense outlined dark options-dense").classes("flex-1")
                ui.button("🎯", on_click=lambda: cbs["auto_match_background"]()).props("flat dense color=amber-400").tooltip("선택된 포즈에 맞는 배경 자동 매칭 (로스터별 최적화)")

            widgets["model_select_container"] = ui.column().classes("w-full mb-3")

            def _on_option_changed(field_name: str, value: object, persist: bool = False) -> None:
                state.update({field_name: value})
                if persist:
                    default_config_service.save_config({field_name: value})

            render_option_controls(GENERATION_OPTION_SPECS, state, _on_option_changed)

            with ui.row().classes("w-full justify-between items-center"):
                widgets["start_btn"] = ui.button("배치 생성 시작", icon="play_arrow", on_click=lambda: cbs["start_generation"]()).props("unelevated color=amber-500 text-color=slate-950 font-bold px-6 py-2")
                widgets["cancel_btn"] = ui.button("중단(취소)", icon="stop", on_click=lambda: cbs["request_cancel"]()).props("outline color=negative dense px-4")
                widgets["cancel_btn"].disable()

        with ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[600px]"):
            widgets.update(build_status_preview_widgets())

    ui.timer(0.8, cbs["sync_job_status"])
    cbs["refresh_char_checkboxes"]()
    cbs["on_pose_mode_changed"]("포즈 세트 사용")
    cbs["render_model_selector"]()
    widgets["config_badge"].set_text(format_config_badge_text())
    cbs["sync_job_status"]()
