"""
plepa_gui.pages.poses
포즈 DB 조회, 섹션별 탭, 라벨/설명/플래그 동시 편집, 에셋 리네임 트랜잭션 및 인스펙터 연동 페이지.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from nicegui import ui
from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import SECTION_METADATA, default_pose_service, pose_display_sort_key
from plepa_gui.components.header import get_active_roster, render_header
from plepa_gui.components.prompt_inspector import open_prompt_inspector_dialog

# SSOT 메타데이터 레지스트리 기반 동적 레이블 프록시
SECTION_LABELS = {sec_id: meta["name"] for sec_id, meta in SECTION_METADATA.items()}


def _open_rename_confirm_dialog(
    code: str,
    fields: dict,
    flags: dict,
    old_label: str,
    new_label: str,
    plan: list,
    on_saved: Callable[[], None],
) -> None:
    """라벨 변경에 따른 연관 에셋 파일명 리네임 확인 다이얼로그를 엽니다."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg p-6 bg-slate-900 border border-slate-700"):
        ui.label("⚠️ 에셋 파일명 동기화 알림").classes("text-lg font-bold text-amber-400 mb-2")
        ui.label(f"라벨이 '{old_label}' -> '{new_label}'(으)로 변경됩니다.").classes("text-sm text-slate-200")
        ui.label(f"연관된 기존 생성 파일 {len(plan)}개의 파일명을 함께 변경하시겠습니까?").classes("text-xs text-slate-400 mt-2 mb-4")

        with ui.column().classes("w-full max-h-48 overflow-y-auto bg-slate-950 p-2 rounded text-xs font-mono text-slate-400 mb-4"):
            for src, dst in plan:
                ui.label(f"• {src.name} -> {dst.name}")

        def execute_save_and_rename(apply_rename: bool):
            try:
                default_pose_service.update_pose(
                    code=code,
                    label=new_label,
                    description=fields["description"],
                    flags=flags,
                    sdxl_prompt=fields["sdxl_prompt"],
                )
                renamed_cnt = default_pose_service.apply_asset_rename(plan) if apply_rename else 0
                dialog.close()
                msg = "포즈 DB 저장 완료"
                if renamed_cnt > 0:
                    msg += f" 및 에셋 파일 {renamed_cnt}개 일괄 리네임 완료"
                ui.notify(msg, type="positive")
                on_saved()
            except Exception as ex:
                ui.notify(f"처리 실패: {ex}", type="negative")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("포즈만 변경 (파일 유지)", on_click=lambda: execute_save_and_rename(False)).props("flat color=slate-400")
            ui.button("포즈 및 파일 동시 변경", icon="sync", on_click=lambda: execute_save_and_rename(True)).props(
                "unelevated color=amber-500 text-color=slate-950 font-bold"
            )

    dialog.open()


def _render_pose_detail_panel(
    detail_card: Any,
    state: Dict[str, Any],
    sample_char: CharacterConfig,
    on_save_pose: Callable[[str, dict, str], None],
) -> None:
    """우측 포즈 상세 편집 패널(메타데이터·플래그·SDXL 프롬프트)을 렌더링합니다."""
    detail_card.clear()
    code = state["selected_code"]
    details = default_pose_service.get_pose_details(code)
    state["details"] = details
    flags = dict(details.get("flags") or {})

    fields = {
        "label": details["label"],
        "description": details["description"],
        "sdxl_prompt": details["sdxl_prompt"],
        "nude": flags.get("nude", False) or False,
        "scene_type": flags.get("scene_type") or "solo",
        "wet": flags.get("wet", False) or False,
        "disabled": flags.get("disabled", False) or False,
    }

    def inspect_prompt():
        p_entry = PoseEntry(
            code=code,
            section=state["current_section"],
            label=fields["label"],
            prompt=fields["sdxl_prompt"],
            description=fields["description"],
        )
        open_prompt_inspector_dialog(sample_char, p_entry)

    with detail_card:
        with ui.row().classes("w-full justify-between items-center mb-6 pb-4 border-b border-slate-800"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("tune", size="28px").classes("text-amber-400")
                with ui.column().classes("gap-0"):
                    ui.label(f"#{code} {details['label']}").classes("text-xl font-bold text-slate-100")
                    ui.label(f"섹션: {SECTION_LABELS.get(details['section'], details['section'])}").classes("text-xs text-slate-400")

            with ui.row().classes("items-center gap-2"):
                ui.button("프롬프트 검사기", icon="search", on_click=inspect_prompt).props("outline color=info dense size=sm")
                ui.button("저장", icon="save", on_click=lambda: on_save_pose(code, fields, details["label"])).props(
                    "unelevated color=amber-500 text-color=slate-950 font-bold px-4"
                )

        with ui.row().classes("w-full gap-4 mb-3"):
            ui.input("라벨 (권장 6글자 이하)", value=fields["label"], on_change=lambda e: fields.update({"label": e.value})).props("outlined dark dense").classes("w-1/3")
            ui.input("한글 상세 설명", value=fields["description"], on_change=lambda e: fields.update({"description": e.value})).props("outlined dark dense").classes("flex-1")

        ui.label("🚩 포즈 특성 플래그 (명시적 메타데이터)").classes("text-xs font-bold text-amber-400 mt-2 mb-2")
        with ui.row().classes("w-full items-center gap-6 p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 mb-4"):
            ui.checkbox("탈의/나체 (nude)", value=fields["nude"], on_change=lambda e: fields.update({"nude": e.value})).props("dark dense")
            ui.select(
                options=["solo", "interactive", "offscreen", "aftermath"],
                value=fields["scene_type"],
                on_change=lambda e: fields.update({"scene_type": e.value}),
                label="씬 유형",
            ).props("outlined dark dense options-dense").classes("w-40 text-xs")
            ui.checkbox("수증기/젖은 질감 (wet)", value=fields["wet"], on_change=lambda e: fields.update({"wet": e.value})).props("dark dense")
            ui.checkbox("소프트 삭제 (disabled)", value=fields["disabled"], on_change=lambda e: fields.update({"disabled": e.value})).props("dark dense")

        ui.label("🏷️ SDXL 프롬프트 (Danbooru 순수 쉼표 태그)").classes("text-xs font-bold text-emerald-400 mt-3 mb-1")
        ui.textarea(value=fields["sdxl_prompt"], on_change=lambda e: fields.update({"sdxl_prompt": e.value})).props("outlined dark autogrow rows=4").classes("w-full font-mono text-xs mb-4")


def _render_pose_items_column(
    items_container: Any,
    state: Dict[str, Any],
    on_select: Callable[[str], None],
) -> None:
    """현재 선택된 섹션의 포즈 항목 스크롤 리스트를 렌더링합니다."""
    items_container.clear()
    sdxl_db = default_pose_service.load_pose_db(engine="sdxl", roster=get_active_roster())
    sec_codes = sorted(
        [c for c, e in sdxl_db.items() if e.section == state["current_section"]],
        key=lambda c: pose_display_sort_key(c, sdxl_db.get(c)),
    )

    with items_container:
        for code in sec_codes:
            entry = sdxl_db[code]
            is_selected = code == state["selected_code"]
            card_classes = "w-full p-2.5 rounded-lg cursor-pointer transition-all border "
            card_classes += "bg-amber-500/20 text-amber-300 border-amber-500/60" if is_selected else "bg-slate-800/60 text-slate-200 border-transparent hover:bg-slate-800"

            with ui.row().classes(card_classes).on("click", lambda c=code: on_select(c)):
                with ui.column().classes("gap-0.5 flex-1"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(f"#{code} {entry.label}").classes("text-sm font-bold")
                        flags = default_pose_service.get_pose_details(code).get("flags") or {}
                        if flags.get("disabled"):
                            ui.badge("비활성", color="negative").props("dense text-xs")
                        elif flags.get("wet"):
                            ui.badge("수증기/젖음", color="info").props("dense text-xs")
                    ui.label(entry.description or entry.prompt[:40] + "..").classes("text-xs text-slate-400 truncate max-w-[340px]")


def render_poses_page() -> None:
    """포즈 관리 페이지 렌더링."""
    render_header("/poses")

    active_roster = get_active_roster()
    active_sections = default_pose_service.get_active_sections(engine="sdxl", roster=active_roster)
    default_sec = active_sections[0]["id"] if active_sections else "emotions"
    state: Dict[str, Any] = {"current_section": default_sec, "selected_code": "000", "details": None}
    sample_char, _ = default_character_service.find_character("sample_character", roster="default")

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        with ui.card().classes("w-[420px] bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            ui.label("🧘 포즈 데이터베이스").classes("text-lg font-bold text-slate-100 mb-2")
            with ui.tabs(value=state["current_section"]).classes("w-full text-amber-400 text-xs flex-wrap") as section_tabs:
                for sec in active_sections:
                    ui.tab(sec["id"], label=f"{sec['short_label']} ({sec['count']})")
            items_container = ui.column().classes("w-full gap-2 max-h-[620px] overflow-y-auto pr-1 mt-3")

        detail_card = ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[700px]")

    def refresh_items_list() -> None:
        _render_pose_items_column(items_container, state, select_code)

    def load_and_render_detail() -> None:
        _render_pose_detail_panel(detail_card, state, sample_char, save_pose_changes)

    def switch_section(sec_name: str) -> None:
        state["current_section"] = sec_name
        db = default_pose_service.load_pose_db(engine="sdxl", roster=get_active_roster())
        sec_codes = sorted(
            [c for c, e in db.items() if e.section == sec_name],
            key=lambda c: pose_display_sort_key(c, db.get(c)),
        )
        if sec_codes:
            state["selected_code"] = sec_codes[0]
        refresh_items_list()
        load_and_render_detail()

    def select_code(code: str) -> None:
        state["selected_code"] = code
        refresh_items_list()
        load_and_render_detail()

    def save_pose_changes(code: str, fields: dict, old_label: str) -> None:
        new_label = fields["label"].strip()
        new_flags = {
            "nude": bool(fields["nude"]),
            "scene_type": str(fields["scene_type"]),
            "wet": bool(fields["wet"]),
            "disabled": bool(fields["disabled"]),
        }
        if old_label and new_label != old_label:
            plan = default_pose_service.plan_asset_rename(code, old_label, new_label)
            if plan:
                _open_rename_confirm_dialog(
                    code, fields, new_flags, old_label, new_label, plan,
                    lambda: (refresh_items_list(), load_and_render_detail()),
                )
                return
        try:
            default_pose_service.update_pose(
                code=code, label=new_label, description=fields["description"],
                flags=new_flags, sdxl_prompt=fields["sdxl_prompt"],
            )
            ui.notify(f"#{code} '{new_label}' 포즈가 SDXL DB에 안전하게 저장되었습니다.", type="positive")
            refresh_items_list()
            load_and_render_detail()
        except Exception as ex:
            ui.notify(f"저장 실패: {ex}", type="negative")

    section_tabs.on_value_change(lambda e: switch_section(e.value))

    init_db = default_pose_service.load_pose_db(engine="sdxl")
    init_codes = [c for c, e in init_db.items() if e.section == state["current_section"]]
    if init_codes:
        state["selected_code"] = sorted(init_codes, key=lambda c: pose_display_sort_key(c, init_db.get(c)))[0]

    refresh_items_list()
    load_and_render_detail()
