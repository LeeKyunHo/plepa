"""
plepa_gui.pages.pose_sets
이름 붙인 포즈 묶음(포즈 세트 / Pose Sets) 관리 페이지.
"""

from __future__ import annotations

from nicegui import ui
from plepa_engine.services.pose_service import SECTION_NAMES, default_pose_service
from plepa_engine.services.schemas import PoseSetSchema
from plepa_gui.components.header import render_header


def render_pose_sets_page() -> None:
    """포즈 세트 관리 페이지 렌더링."""
    render_header("/pose-sets")

    state = {
        "selected_set_id": None,
        "current_set": None,
    }

    all_poses = default_pose_service.load_pose_db(engine="flux")

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        # 좌측: 포즈 세트 목록
        with ui.card().classes("w-80 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            ui.label("📦 포즈 세트 목록").classes("text-lg font-bold text-slate-100 mb-4")

            sets_container = ui.column().classes("w-full gap-2 max-h-[500px] overflow-y-auto pr-1")

            with ui.row().classes("w-full mt-4 pt-4 border-t border-slate-800 justify-between"):
                ui.button("신규 세트", icon="add", on_click=lambda: open_new_set_dialog()).props(
                    "outline color=amber-400 dense size=sm"
                )
                ui.button("새로고침", icon="refresh", on_click=lambda: refresh_sets()).props(
                    "flat color=slate-400 dense size=sm"
                )

        # 우측: 세트 상세 편집 및 포즈 체크리스트
        detail_card = ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[600px]")

    def refresh_sets():
        sets_container.clear()
        sets = default_pose_service.load_pose_sets()

        if not sets:
            with sets_container:
                ui.label("등록된 세트가 없습니다.").classes("text-xs text-slate-500 py-4")
            return

        with sets_container:
            for s in sets:
                is_selected = (s.id == state["selected_set_id"])
                classes = "w-full p-2.5 rounded-lg cursor-pointer transition-all border "
                if is_selected:
                    classes += "bg-amber-500/20 text-amber-300 border-amber-500/60 font-bold"
                else:
                    classes += "bg-slate-800/60 text-slate-200 border-transparent hover:bg-slate-800"

                with ui.row().classes(classes).on("click", lambda current_s=s: select_set(current_s)):
                    with ui.column().classes("gap-0"):
                        ui.label(s.name).classes("text-sm font-semibold")
                        ui.label(f"{len(s.codes)}개 포즈 ({s.id})").classes("text-xs text-slate-400")

        if state["selected_set_id"] is None and sets:
            select_set(sets[0])

    def select_set(s: PoseSetSchema):
        state["selected_set_id"] = s.id
        state["current_set"] = s
        refresh_sets()
        render_detail()

    def render_detail():
        detail_card.clear()
        s: PoseSetSchema = state["current_set"]
        if not s:
            with detail_card:
                ui.label("포즈 세트를 선택해 주십시오.").classes("text-slate-500 text-sm")
            return

        selected_codes = set(s.codes)

        with detail_card:
            with ui.row().classes("w-full justify-between items-center mb-6 pb-4 border-b border-slate-800"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("collections_bookmark", size="28px").classes("text-amber-400")
                    with ui.column().classes("gap-0"):
                        ui.label(f"{s.name} ({s.id})").classes("text-xl font-bold text-slate-100")
                        ui.label(f"선택된 포즈: 총 {len(selected_codes)}개").classes("text-xs text-amber-400 font-semibold")

                with ui.row().classes("items-center gap-2"):
                    ui.button("삭제", icon="delete", on_click=lambda: delete_set(s.id)).props(
                        "outline color=negative dense size=sm"
                    )
                    ui.button("저장", icon="save", on_click=lambda: save_set(s, name_in.value, desc_in.value, list(selected_codes))).props(
                        "unelevated color=amber-500 text-color=slate-950 font-bold px-4"
                    )

            with ui.row().classes("w-full gap-4 mb-4"):
                name_in = ui.input("세트 표시 이름", value=s.name).props("outlined dark dense").classes("w-1/2")
                desc_in = ui.input("설명", value=s.description).props("outlined dark dense").classes("flex-1")

            # 빠른 선택 액션 버튼들
            with ui.row().classes("w-full items-center gap-2 mb-3"):
                ui.label("포즈 선택:").classes("text-xs font-semibold text-slate-400 mr-2")
                ui.button("전체 선택", on_click=lambda: select_all(True)).props("flat dense size=sm color=slate-300")
                ui.button("전체 해제", on_click=lambda: select_all(False)).props("flat dense size=sm color=slate-300")
                ui.button("H-씬만 (40~59)", on_click=lambda: select_range(40, 59)).props("flat dense size=sm color=amber-400")

            # 4대 섹션별 포즈 체크박스 그리드
            with ui.column().classes("w-full gap-4 max-h-[480px] overflow-y-auto pr-2"):
                for sec in SECTION_NAMES:
                    sec_items = [p for c, p in all_poses.items() if p.section == sec]
                    if not sec_items:
                        continue
                    with ui.card().classes("w-full bg-slate-800/40 border border-slate-700/50 p-3 rounded-lg"):
                        ui.label(f"📌 {sec.upper()} ({len(sec_items)}개)").classes("text-xs font-bold text-amber-400 mb-2")
                        with ui.grid(columns=4).classes("w-full gap-2"):
                            for p in sec_items:
                                is_checked = p.code in selected_codes

                                def toggle_code(code_val=p.code, chk=is_checked):
                                    if code_val in selected_codes:
                                        selected_codes.remove(code_val)
                                    else:
                                        selected_codes.add(code_val)

                                ui.checkbox(
                                    f"#{p.code} {p.label}",
                                    value=is_checked,
                                    on_change=lambda e, code_val=p.code: (selected_codes.add(code_val) if e.value else selected_codes.discard(code_val))
                                ).props("dark dense").classes("text-xs text-slate-200")

    def select_all(val: bool):
        s = state["current_set"]
        if val:
            s.codes = sorted(all_poses.keys())
        else:
            s.codes = []
        render_detail()

    def select_range(start: int, end: int):
        s = state["current_set"]
        s.codes = [f"{i:03d}" for i in range(start, end + 1) if f"{i:03d}" in all_poses]
        render_detail()

    def save_set(old_s: PoseSetSchema, name: str, desc: str, codes: list):
        try:
            new_s = PoseSetSchema(
                id=old_s.id,
                name=name.strip(),
                description=desc.strip(),
                codes=sorted(codes, key=lambda x: int(x))
            )
            default_pose_service.save_pose_set(new_s)
            ui.notify(f"포즈 세트 '{name}' 저장 완료!", type="positive")
            state["current_set"] = new_s
            refresh_sets()
            render_detail()
        except Exception as ex:
            ui.notify(f"저장 실패: {ex}", type="negative")

    def delete_set(set_id: str):
        try:
            default_pose_service.delete_pose_set(set_id)
            ui.notify("포즈 세트가 삭제되었습니다.", type="info")
            state["selected_set_id"] = None
            state["current_set"] = None
            refresh_sets()
            render_detail()
        except Exception as ex:
            ui.notify(f"삭제 실패: {ex}", type="negative")

    def open_new_set_dialog():
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md p-6 bg-slate-900 border border-slate-700"):
            ui.label("✨ 신규 포즈 세트").classes("text-lg font-bold text-amber-400 mb-3")
            id_in = ui.input("세트 ID (영문/숫자, 예: summer_pack)").props("outlined dark dense").classes("w-full mb-3")
            name_in = ui.input("세트 표시 이름 (예: 여름 수영복 세트)").props("outlined dark dense").classes("w-full mb-4")

            def execute_add():
                s_id = id_in.value.strip().lower()
                s_name = name_in.value.strip()
                if not s_id or not s_name:
                    ui.notify("ID와 이름을 모두 입력해주세요.", type="warning")
                    return
                new_set = PoseSetSchema(id=s_id, name=s_name, description="", codes=[])
                default_pose_service.save_pose_set(new_set)
                dialog.close()
                ui.notify(f"포즈 세트 '{s_name}' 생성 완료", type="positive")
                select_set(new_set)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("취소", on_click=dialog.close).props("flat color=slate-400")
                ui.button("추가", on_click=execute_add).props("unelevated color=amber-500 text-color=slate-950 font-bold")

        dialog.open()

    refresh_sets()
