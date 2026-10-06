"""
plepa_gui.pages.backgrounds
배경 프리셋(projects/{roster}/background.json) 관리 및 린터 검사 페이지.
"""

from __future__ import annotations

from nicegui import ui
from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.background_service import default_background_service
from plepa_gui.components.header import render_header


def render_backgrounds_page() -> None:
    """배경 프리셋 관리 페이지 렌더링."""
    render_header("/backgrounds")

    state = {
        "selected_roster": DEFAULT_ROSTER,
        "selected_key": "default",
        "current_prompt": "",
    }

    available_rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    if not available_rosters:
        available_rosters = [DEFAULT_ROSTER]

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        # 좌측: 로스터 및 프리셋 목록
        with ui.card().classes("w-80 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            ui.label("🖼️ 배경 프리셋").classes("text-lg font-bold text-slate-100 mb-2")

            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("로스터:").classes("text-xs text-slate-400 font-semibold")
                ui.select(
                    options=available_rosters,
                    value=state["selected_roster"],
                    on_change=lambda e: change_roster(e.value),
                ).props("dense outlined dark options-dense").classes("w-44 text-sm")

            presets_container = ui.column().classes("w-full gap-2 max-h-[500px] overflow-y-auto pr-1")

            with ui.row().classes("w-full mt-4 pt-4 border-t border-slate-800 justify-between"):
                ui.button("신규 프리셋", icon="add", on_click=lambda: open_new_preset_dialog()).props(
                    "outline color=amber-400 dense size=sm"
                )
                ui.button("새로고침", icon="refresh", on_click=lambda: refresh_presets()).props(
                    "flat color=slate-400 dense size=sm"
                )

        # 우측: 프리셋 상세 편집
        detail_card = ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[500px]")

    def change_roster(r_name: str):
        state["selected_roster"] = r_name
        state["selected_key"] = "default"
        refresh_presets()
        render_detail()

    common_presets = default_background_service.get_common_presets()

    def refresh_presets():
        presets_container.clear()
        bgs = default_background_service.get_backgrounds(state["selected_roster"])

        with presets_container:
            for k in bgs.keys():
                is_selected = (k == state["selected_key"])
                classes = "w-full p-2.5 rounded-lg cursor-pointer transition-all border justify-between items-center "
                if is_selected:
                    classes += "bg-amber-500/20 text-amber-300 border-amber-500/60 font-bold"
                else:
                    classes += "bg-slate-800/60 text-slate-200 border-transparent hover:bg-slate-800"

                with ui.row().classes(classes).on("click", lambda key=k: select_key(key)):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(k).classes("text-sm")
                    with ui.row().classes("items-center gap-1"):
                        if k in common_presets:
                            ui.badge("🌐 공용", color="emerald-700").props("dense text-xs")
                        if k == "none":
                            ui.badge("배경 없음", color="amber-600").props("dense text-xs")
                        elif k == "default":
                            ui.badge("기본값", color="blue-600").props("dense text-xs")

    def select_key(key: str):
        state["selected_key"] = key
        refresh_presets()
        render_detail()

    def render_detail():
        detail_card.clear()
        key = state["selected_key"]
        bgs = default_background_service.get_backgrounds(state["selected_roster"])
        prompt = bgs.get(key, "")
        state["current_prompt"] = prompt

        with detail_card:
            with ui.row().classes("w-full justify-between items-center mb-4 pb-4 border-b border-slate-800"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("wallpaper", size="28px").classes("text-amber-400")
                    with ui.column().classes("gap-0"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(f"배경 프리셋: '{key}'").classes("text-xl font-bold text-slate-100")
                            if key in common_presets:
                                ui.badge("🌐 전체 프로젝트 공용", color="emerald-700").props("dense text-xs")
                        ui.label(f"로스터: {state['selected_roster']}").classes("text-xs text-slate-400")

                with ui.row().classes("items-center gap-2"):
                    if key not in ("default", "none", "white_studio", "grey_studio"):
                        ui.button("삭제", icon="delete", on_click=lambda: delete_preset(key)).props(
                            "outline color=negative dense size=sm"
                        )
                    ui.button("저장", icon="save", on_click=lambda: save_preset(key, prompt_input.value)).props(
                        "unelevated color=amber-500 text-color=slate-950 font-bold px-4"
                    )

            if key in common_presets:
                with ui.row().classes("w-full p-2.5 bg-emerald-950/40 border border-emerald-600/40 rounded-lg items-center gap-2 mb-3"):
                    ui.icon("info", size="18px").classes("text-emerald-400")
                    ui.label(f"공용 프리셋 안내: {common_presets[key].get('description', '')} (모든 로스터 공용)").classes("text-xs text-emerald-200")

            prompt_input = ui.textarea("배경 프롬프트 내용", value=prompt).props("outlined dark autogrow rows=5").classes("w-full font-mono text-sm mb-4")

            # 실시간 린터 경고 컨테이너
            warning_box = ui.column().classes("w-full")

            def update_warnings(text: str):
                warning_box.clear()
                warnings = default_background_service.lint_prompt(text)
                if warnings:
                    with warning_box:
                        with ui.column().classes("w-full p-3 bg-amber-950/60 border border-amber-600/70 rounded-lg"):
                            ui.label("⚠️ 프롬프트 화질 저하 주의 경고").classes("text-xs font-bold text-amber-400")
                            for w in warnings:
                                ui.label(f"• {w}").classes("text-xs text-amber-200")

            prompt_input.on("input", lambda e: update_warnings(prompt_input.value))
            update_warnings(prompt)

    def save_preset(key: str, prompt: str):
        try:
            default_background_service.save_preset(state["selected_roster"], key, prompt)
            ui.notify(f"배경 프리셋 '{key}' 저장 완료!", type="positive")
            refresh_presets()
            render_detail()
        except Exception as ex:
            ui.notify(f"저장 실패: {ex}", type="negative")

    def delete_preset(key: str):
        try:
            default_background_service.delete_preset(state["selected_roster"], key)
            ui.notify(f"배경 프리셋 '{key}' 삭제 완료", type="info")
            state["selected_key"] = "default"
            refresh_presets()
            render_detail()
        except Exception as ex:
            ui.notify(f"삭제 실패: {ex}", type="negative")

    def open_new_preset_dialog():
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md p-6 bg-slate-900 border border-slate-700"):
            ui.label("✨ 신규 배경 프리셋").classes("text-lg font-bold text-amber-400 mb-3")
            k_input = ui.input("프리셋 키 (예: shower, bedroom)").props("outlined dark dense").classes("w-full mb-4")

            def execute_add():
                k = k_input.value.strip().lower()
                if not k:
                    ui.notify("키를 입력해주세요.", type="warning")
                    return
                default_background_service.save_preset(state["selected_roster"], k, "clean background, soft lighting")
                dialog.close()
                ui.notify(f"프리셋 '{k}' 생성 완료", type="positive")
                state["selected_key"] = k
                refresh_presets()
                render_detail()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("취소", on_click=dialog.close).props("flat color=slate-400")
                ui.button("추가", on_click=execute_add).props("unelevated color=amber-500 text-color=slate-950 font-bold")

        dialog.open()

    refresh_presets()
    render_detail()
