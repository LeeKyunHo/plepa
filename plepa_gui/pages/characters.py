"""
plepa_gui.pages.characters
캐릭터 목록 조회, 폼 편집, 원자적 저장, 복제 마법사 및 안전 삭제 페이지.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from nicegui import ui
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.schemas import CharacterSchema
from plepa_gui.components.header import (
    get_active_roster,
    get_available_rosters,
    render_header,
)
from plepa_gui.pages.characters_form import (
    build_updated_character_schema,
    confirm_delete_character_dialog,
    open_clone_character_dialog,
    open_new_character_dialog,
    render_character_detail_form,
)


def render_characters_page() -> None:
    """캐릭터 관리 페이지 렌더링."""
    render_header("/characters")

    available_rosters = get_available_rosters()
    state: Dict[str, Any] = {
        "selected_roster": get_active_roster(),
        "selected_prefix": None,
        "current_char": None,
        "current_file": None,
    }

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        with ui.card().classes("w-80 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            ui.label("👥 캐릭터 목록").classes("text-lg font-bold text-slate-100 mb-2")
            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("로스터:").classes("text-xs text-slate-400 font-semibold")
                ui.select(
                    options=available_rosters,
                    value=state["selected_roster"],
                    on_change=lambda e: change_roster(e.value),
                ).props("dense outlined dark options-dense").classes("w-44 text-sm")

            char_list_container = ui.column().classes("w-full gap-2 max-h-[620px] overflow-y-auto pr-1")
            with ui.row().classes("w-full mt-4 pt-4 border-t border-slate-800 justify-between"):
                ui.button("신규 캐릭터", icon="add", on_click=lambda: open_new_character_dialog(state, select_character)).props(
                    "outline color=amber-400 dense size=sm"
                )
                ui.button("새로고침", icon="refresh", on_click=lambda: refresh_char_list()).props(
                    "flat color=slate-400 dense size=sm"
                )

        form_card = ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[700px]")

    def change_roster(roster_name: str) -> None:
        state["selected_roster"] = roster_name
        state["selected_prefix"] = None
        state["current_char"] = None
        state["current_file"] = None
        refresh_char_list()
        render_form()

    def refresh_char_list() -> None:
        char_list_container.clear()
        chars = default_character_service.list_characters(roster=state["selected_roster"])
        if not chars:
            with char_list_container:
                ui.label("등록된 캐릭터가 없습니다.").classes("text-xs text-slate-500 py-4")
            return

        with char_list_container:
            for _, char, file_path in chars:
                is_selected = char.prefix == state["selected_prefix"]
                btn_classes = "w-full justify-start text-left px-3 py-2 rounded-lg transition-all "
                btn_classes += "bg-amber-500/20 text-amber-300 border border-amber-500/50 font-bold" if is_selected else "bg-slate-800/60 text-slate-200 hover:bg-slate-800 border border-transparent"
                with ui.row().classes(btn_classes).on("click", lambda c=char, f=file_path: select_character(c, f)):
                    with ui.column().classes("gap-0"):
                        ui.label(f"{char.name}").classes("text-sm font-semibold")
                        ui.label(f"[{char.prefix}] {char.gender}").classes("text-[11px] text-slate-400")

        if state["selected_prefix"] is None and chars:
            select_character(chars[0][1], chars[0][2])

    def select_character(char: CharacterSchema, file_path: Path) -> None:
        state["selected_prefix"] = char.prefix
        state["current_char"] = char
        state["current_file"] = file_path
        refresh_char_list()
        render_form()

    def _on_deleted() -> None:
        state["selected_prefix"] = None
        state["current_char"] = None
        state["current_file"] = None
        refresh_char_list()
        render_form()

    def render_form() -> None:
        render_character_detail_form(
            form_card,
            state,
            on_clone=lambda c: open_clone_character_dialog(state, c, select_character),
            on_delete=lambda c: confirm_delete_character_dialog(state, c, _on_deleted),
            on_saved=select_character,
        )

    refresh_char_list()


__all__ = ["build_updated_character_schema", "render_characters_page"]
