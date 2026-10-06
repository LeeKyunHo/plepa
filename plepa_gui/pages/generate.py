"""
plepa_gui.pages.generate
캐릭터 x 포즈 배치 생성 설정, 실시간 진행률 및 비동기 작업 제어 페이지.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from nicegui import run, ui
from plepa_engine.config import DEFAULT_ENGINE, DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.models import GenerationResult
from plepa_engine.services.background_service import default_background_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import GenerationParams, default_generation_service
from plepa_engine.services.job_manager import global_job_manager
from plepa_engine.services.pose_service import default_pose_service
from plepa_gui.components.header import render_header


def render_generate_page() -> None:
    """배치 생성 페이지 렌더링."""
    render_header("/generate")

    # 반응형 폼 상태
    state = {
        "roster": DEFAULT_ROSTER,
        "selected_chars": [],
        "pose_selection_mode": "set",  # 'set' or 'custom'
        "selected_pose_set": "shower_trio",
        "custom_pose_expr": "000..019",
        "engine": DEFAULT_ENGINE,
        "bg_preset": "default",
        "face_detailer": False,
        "upscale": False,
        "censor": False,
        "overwrite": False,
        "mock": False,
        "is_running": False,
        "cancel_requested": False,
    }

    available_rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    if not available_rosters:
        available_rosters = [DEFAULT_ROSTER]

    all_chars = default_character_service.list_characters(roster=state["roster"])
    pose_sets = default_pose_service.load_pose_sets()
    bgs = default_background_service.get_backgrounds(state["roster"])

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        # 좌측: 생성 파라미터 제어판
        with ui.card().classes("w-[520px] bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg"):
            ui.label("⚡ 배치 생성 설정").classes("text-xl font-bold text-slate-100 mb-4")

            # 1. 로스터 및 캐릭터 선택
            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("1. 대상 캐릭터 선택").classes("text-xs font-bold text-amber-400")
                with ui.row().classes("gap-1"):
                    ui.button("전체 선택", icon="done_all", on_click=lambda: select_all_chars(True)).props("flat dense size=xs color=amber-400").tooltip("현재 로스터의 모든 캐릭터 선택")
                    ui.button("선택 해제", icon="remove_done", on_click=lambda: select_all_chars(False)).props("flat dense size=xs color=slate-400").tooltip("선택 해제")

            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("로스터:").classes("text-xs text-slate-400")
                roster_sel = ui.select(
                    options=available_rosters,
                    value=state["roster"],
                    on_change=lambda e: on_roster_changed(e.value),
                ).props("dense outlined dark options-dense").classes("w-48 text-sm")

            chars_box = ui.column().classes("w-full max-h-36 overflow-y-auto bg-slate-800/40 p-2 rounded border border-slate-700/50 mb-4")

            # 2. 포즈 선택 (세트 또는 표현식)
            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("2. 포즈 선택").classes("text-xs font-bold text-amber-400")
                ui.button("⭐ 전체 80종 포즈", icon="star", on_click=lambda: select_all_80_poses()).props(
                    "unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40"
                ).tooltip("000부터 159까지 전체 80종 포즈 일괄 선택")

            with ui.row().classes("w-full gap-4 mb-2"):
                mode_set_btn = ui.radio(
                    ["포즈 세트 사용", "코드 직접 입력"],
                    value="포즈 세트 사용",
                    on_change=lambda e: on_pose_mode_changed(e.value)
                ).props("dark inline dense")

            pose_mode_container = ui.column().classes("w-full mb-3")

            # 스마트 스킵 안내 배너
            with ui.row().classes("w-full p-2.5 bg-emerald-950/40 border border-emerald-600/40 rounded-lg items-center gap-2 mb-4"):
                ui.icon("check_circle", size="18px").classes("text-emerald-400")
                ui.label("기본 동작: 이미 있는 이미지는 자동 건너뛰고 누락된 포즈만 채웁니다.").classes("text-[11px] text-emerald-200")

            # 3. 엔진 및 옵션
            ui.label("3. 엔진 및 보정 옵션").classes("text-xs font-bold text-amber-400 mb-2")
            with ui.row().classes("w-full gap-4 mb-3"):
                ui.select(
                    options=["sdxl", "flux"],
                    value=state["engine"],
                    label="생성 엔진",
                    on_change=lambda e: state.update({"engine": e.value})
                ).props("dense outlined dark options-dense").classes("w-32")

                bg_sel = ui.select(
                    options=list(bgs.keys()) or ["default"],
                    value=state["bg_preset"],
                    label="배경 프리셋",
                    on_change=lambda e: state.update({"bg_preset": e.value})
                ).props("dense outlined dark options-dense").classes("flex-1")

            with ui.row().classes("w-full items-center gap-4 p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 mb-6"):
                ui.checkbox("Face Detailer", value=state["face_detailer"], on_change=lambda e: state.update({"face_detailer": e.value})).props("dark dense")
                ui.checkbox("4x Upscale", value=state["upscale"], on_change=lambda e: state.update({"upscale": e.value})).props("dark dense")
                ui.checkbox("자동 검열", value=state["censor"], on_change=lambda e: state.update({"censor": e.value})).props("dark dense")
                ui.checkbox("강제 덮어쓰기 (리롤)", value=state["overwrite"], on_change=lambda e: state.update({"overwrite": e.value})).props("dark dense").tooltip("기존 이미지를 무시하고 새로 생성하여 덮어씁니다.")
                ui.checkbox("Mock 시뮬레이션", value=state["mock"], on_change=lambda e: state.update({"mock": e.value})).props("dark dense").tooltip("ComfyUI 없이 0.001초 가상 생성")

            # 생성 시작 및 취소 버튼
            with ui.row().classes("w-full justify-between items-center"):
                start_btn = ui.button("배치 생성 시작", icon="play_arrow", on_click=lambda: start_generation()).props(
                    "unelevated color=amber-500 text-color=slate-950 font-bold px-6 py-2"
                )
                cancel_btn = ui.button("중단(취소)", icon="stop", on_click=lambda: request_cancel()).props(
                    "outline color=negative dense px-4"
                )
                cancel_btn.disable()

        # 우측: 실시간 진행 현황 및 콘솔 로그 카드
        with ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[600px]"):
            ui.label("📊 실시간 생성 현황").classes("text-xl font-bold text-slate-100 mb-4")

            with ui.row().classes("w-full items-center justify-between mb-2"):
                status_label = ui.label("대기 중").classes("text-sm font-semibold text-slate-400")
                progress_text = ui.label("0 / 0 (0%)").classes("text-sm font-mono text-amber-400")

            progress_bar = ui.linear_progress(value=0.0).props("color=amber-400 size=10px stripe").classes("rounded mb-6")

            ui.label("생성 로그:").classes("text-xs font-semibold text-slate-400 mb-1")
            log_box = ui.column().classes("w-full h-96 overflow-y-auto bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-slate-300 gap-1")

    def select_all_chars(select: bool):
        chars = default_character_service.list_characters(roster=state["roster"])
        if select:
            state["selected_chars"] = [c.prefix for _, c, _ in chars]
            ui.notify(f"로스터 '{state['roster']}' 캐릭터 {len(chars)}명 전체 선택 완료", type="info")
        else:
            state["selected_chars"] = []
            ui.notify("선택 해제 완료", type="info")
        refresh_char_checkboxes(keep_selection=True)

    def select_all_80_poses():
        state["pose_selection_mode"] = "set"
        state["selected_pose_set"] = "all_80"
        mode_set_btn.value = "포즈 세트 사용"
        on_pose_mode_changed("포즈 세트 사용")
        ui.notify("⭐ 전체 80종 포즈 (000~159) 선택 완료!", type="positive")

    def on_roster_changed(new_r: str):
        state["roster"] = new_r
        refresh_char_checkboxes()
        # 배경 목록 갱신
        new_bgs = default_background_service.get_backgrounds(new_r)
        bg_sel.options = list(new_bgs.keys()) or ["default"]
        bg_sel.value = "default"

    def refresh_char_checkboxes(keep_selection: bool = False):
        chars_box.clear()
        chars = default_character_service.list_characters(roster=state["roster"])
        if not keep_selection:
            state["selected_chars"] = [chars[0][1].prefix] if chars else []

        with chars_box:
            for _, c, _ in chars:
                is_chk = c.prefix in state["selected_chars"]

                def toggle_char(prefix=c.prefix):
                    if prefix in state["selected_chars"]:
                        state["selected_chars"].remove(prefix)
                    else:
                        state["selected_chars"].append(prefix)

                ui.checkbox(
                    f"{c.name} ({c.prefix})",
                    value=is_chk,
                    on_change=lambda e, p=c.prefix: (state["selected_chars"].append(p) if e.value else state["selected_chars"].remove(p))
                ).props("dark dense").classes("text-xs text-slate-200")

    def on_pose_mode_changed(mode_str: str):
        pose_mode_container.clear()
        sets = default_pose_service.load_pose_sets()
        set_options = {"all_80": "⭐ 전체 80종 포즈 (000~159)"}
        for s in sets:
            set_options[s.id] = f"{s.name} ({len(s.codes)}종)"

        with pose_mode_container:
            if "포즈 세트" in mode_str:
                state["pose_selection_mode"] = "set"
                ui.select(
                    options=set_options,
                    value=state["selected_pose_set"],
                    on_change=lambda e: state.update({"selected_pose_set": e.value})
                ).props("outlined dark dense options-dense").classes("w-full text-sm")
            else:
                state["pose_selection_mode"] = "custom"
                ui.input(
                    "포즈 표현식 (예: all, 000..019, 038,039,057)",
                    value=state["custom_pose_expr"],
                    on_change=lambda e: state.update({"custom_pose_expr": e.value})
                ).props("outlined dark dense").classes("w-full text-sm")

    def request_cancel():
        if global_job_manager.is_running:
            global_job_manager.cancel_job()
            status_label.set_text("취소 요청됨... (현재 항목 완료 후 중단)")
            ui.notify("생성 중단 요청이 전달되었습니다.", type="warning")

    def start_generation():
        if global_job_manager.is_running:
            ui.notify("이미 다른 배치 작업이 진행 중입니다.", type="warning")
            return

        if not state["selected_chars"]:
            ui.notify("최소 1명 이상의 캐릭터를 선택해 주십시오.", type="warning")
            return

        # 포즈 표현식 산출
        if state["pose_selection_mode"] == "set":
            if state["selected_pose_set"] == "all_80":
                pose_expr = "all"
            else:
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
            engine=state["engine"],
            bg_preset=state["bg_preset"],
            face_detailer=state["face_detailer"],
            upscale=state["upscale"],
            censor=state["censor"],
            overwrite=state["overwrite"],
            mock=state["mock"],
        )

        log_box.clear()
        nonlocal rendered_log_count
        rendered_log_count = 0

        started = global_job_manager.start_job(params)
        if started:
            ui.notify("백그라운드 배치 작업 시작! 다른 페이지로 이동해도 멈추지 않고 계속 생성됩니다.", type="positive")
            sync_job_status()
        else:
            ui.notify("작업 시작 실패 (이미 실행 중)", type="warning")

    # 전역 백그라운드 작업 상태 실시간 동기화
    rendered_log_count = 0

    def sync_job_status():
        nonlocal rendered_log_count
        status = global_job_manager.get_status()
        is_running = status["is_running"]

        if is_running:
            start_btn.disable()
            cancel_btn.enable()
            progress_bar.value = status["percentage"]
            progress_text.set_text(f"{status['current']} / {status['total']} ({int(status['percentage'] * 100)}%)")
            status_label.set_text(status["current_msg"])
        else:
            start_btn.enable()
            cancel_btn.disable()
            status_label.set_text(status["current_msg"])
            if status["total"] > 0:
                progress_bar.value = status["percentage"]
                progress_text.set_text(f"{status['current']} / {status['total']} ({int(status['percentage'] * 100)}%)")

        logs = status["logs"]
        if len(logs) > rendered_log_count:
            with log_box:
                for entry in logs[rendered_log_count:]:
                    ui.label(f"[{entry['timestamp']}] {entry['text']}").classes(
                        "text-emerald-400" if entry["success"] else "text-rose-400"
                    )
            rendered_log_count = len(logs)

    ui.timer(0.8, sync_job_status)

    # 초기화
    refresh_char_checkboxes()
    on_pose_mode_changed("포즈 세트 사용")
    sync_job_status()
