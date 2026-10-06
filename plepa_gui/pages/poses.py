"""
plepa_gui.pages.poses
포즈 DB 조회, 섹션별 탭, 라벨/설명/플래그 동시 편집, 에셋 리네임 트랜잭션 및 인스펙터 연동 페이지.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from nicegui import ui
from plepa_engine.config import DEFAULT_ROSTER
from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import SECTION_NAMES, default_pose_service
from plepa_gui.components.header import render_header
from plepa_gui.components.prompt_inspector import open_prompt_inspector_dialog

SECTION_LABELS = {
    "emotions": "😊 기본 표정 (000~019)",
    "poses": "🧍 전신·일상 포즈 (020~039)",
    "h_scenes": "🔞 H-씬 (040~059)",
    "scenes_otokonoko": "🎀 오토코노코 (140~159)",
}


def render_poses_page() -> None:
    """포즈 관리 페이지 렌더링."""
    render_header("/poses")

    state = {
        "current_section": "emotions",
        "selected_code": "000",
        "details": None,
    }

    # 샘플 캐릭터 로드 (인스펙터용)
    sample_char, _ = default_character_service.find_character("sample_character", roster="default")

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        # ==========================================
        # 좌측: 섹션 탭 및 포즈 목록 그리드
        # ==========================================
        with ui.card().classes("w-[420px] bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            ui.label("🧘 포즈 데이터베이스").classes("text-lg font-bold text-slate-100 mb-2")

            with ui.tabs().classes("w-full text-amber-400 text-xs") as section_tabs:
                tab_emo = ui.tab("emotions", label="표정")
                tab_pose = ui.tab("poses", label="포즈")
                tab_h = ui.tab("h_scenes", label="H-씬")
                tab_oto = ui.tab("scenes_otokonoko", label="오토코노코")

            # 포즈 항목 스크롤 리스트
            items_container = ui.column().classes("w-full gap-2 max-h-[620px] overflow-y-auto pr-1 mt-3")

        # ==========================================
        # 우측: 포즈 상세 편집 패널
        # ==========================================
        detail_card = ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[700px]")

    def switch_section(sec_name: str):
        state["current_section"] = sec_name
        # 해당 섹션의 첫 번째 코드 자동 선택
        db = default_pose_service.load_pose_db(engine="flux")
        sec_codes = [c for c, e in db.items() if e.section == sec_name]
        if sec_codes:
            state["selected_code"] = sec_codes[0]
        refresh_items_list()
        load_and_render_detail()

    section_tabs.on_value_change(lambda e: switch_section(e.value))

    def refresh_items_list():
        items_container.clear()
        flux_db = default_pose_service.load_pose_db(engine="flux")
        sec_codes = sorted([c for c, e in flux_db.items() if e.section == state["current_section"]])

        with items_container:
            for code in sec_codes:
                entry = flux_db[code]
                is_selected = (code == state["selected_code"])
                card_classes = "w-full p-2.5 rounded-lg cursor-pointer transition-all border "
                if is_selected:
                    card_classes += "bg-amber-500/20 text-amber-300 border-amber-500/60"
                else:
                    card_classes += "bg-slate-800/60 text-slate-200 border-transparent hover:bg-slate-800"

                with ui.row().classes(card_classes).on("click", lambda c=code: select_code(c)):
                    with ui.column().classes("gap-0.5 flex-1"):
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(f"#{code} {entry.label}").classes("text-sm font-bold")
                            # 플래그 요약 뱃지
                            details = default_pose_service.get_pose_details(code)
                            flags = details.get("flags") or {}
                            if flags.get("disabled"):
                                ui.badge("비활성", color="negative").props("dense text-xs")
                            elif flags.get("wet"):
                                ui.badge("수증기/젖음", color="info").props("dense text-xs")

                        ui.label(entry.description or entry.prompt[:40] + "..").classes("text-xs text-slate-400 truncate max-w-[340px]")

    def select_code(code: str):
        state["selected_code"] = code
        refresh_items_list()
        load_and_render_detail()

    def load_and_render_detail():
        detail_card.clear()
        code = state["selected_code"]
        details = default_pose_service.get_pose_details(code)
        state["details"] = details
        flags = dict(details.get("flags") or {})

        # 입력 필드 상태 바인딩
        fields = {
            "label": details["label"],
            "description": details["description"],
            "flux_prompt": details["flux_prompt"],
            "sdxl_prompt": details["sdxl_prompt"],
            "nude": flags.get("nude", False) or False,
            "scene_type": flags.get("scene_type") or "solo",
            "wet": flags.get("wet", False) or False,
            "disabled": flags.get("disabled", False) or False,
        }

        with detail_card:
            # 상단 헤더
            with ui.row().classes("w-full justify-between items-center mb-6 pb-4 border-b border-slate-800"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("tune", size="28px").classes("text-amber-400")
                    with ui.column().classes("gap-0"):
                        ui.label(f"#{code} {details['label']}").classes("text-xl font-bold text-slate-100")
                        ui.label(f"섹션: {SECTION_LABELS.get(details['section'], details['section'])}").classes("text-xs text-slate-400")

                with ui.row().classes("items-center gap-2"):
                    ui.button("프롬프트 검사기", icon="search", on_click=lambda: inspect_prompt(code, fields)).props(
                        "outline color=info dense size=sm"
                    )
                    ui.button("저장", icon="save", on_click=lambda: save_pose_changes(code, fields, details["label"])).props(
                        "unelevated color=amber-500 text-color=slate-950 font-bold px-4"
                    )

            # 1. 기본 메타데이터 (라벨, 설명)
            with ui.row().classes("w-full gap-4 mb-3"):
                ui.input("라벨 (권장 6글자 이하)", value=fields["label"], on_change=lambda e: fields.update({"label": e.value})).props(
                    "outlined dark dense"
                ).classes("w-1/3")
                ui.input("한글 상세 설명", value=fields["description"], on_change=lambda e: fields.update({"description": e.value})).props(
                    "outlined dark dense"
                ).classes("flex-1")

            # 2. 명시적 메타데이터 플래그 (057 버그 종식용)
            ui.label("🚩 포즈 특성 플래그 (명시적 메타데이터)").classes("text-xs font-bold text-amber-400 mt-2 mb-2")
            with ui.row().classes("w-full items-center gap-6 p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 mb-4"):
                ui.checkbox("탈의/나체 (nude)", value=fields["nude"], on_change=lambda e: fields.update({"nude": e.value})).props("dark dense")
                ui.select(
                    options=["solo", "interactive", "offscreen", "aftermath"],
                    value=fields["scene_type"],
                    on_change=lambda e: fields.update({"scene_type": e.value}),
                    label="씬 유형"
                ).props("outlined dark dense options-dense").classes("w-40 text-xs")
                ui.checkbox("수증기/젖은 질감 (wet)", value=fields["wet"], on_change=lambda e: fields.update({"wet": e.value})).props("dark dense")
                ui.checkbox("소프트 삭제 (disabled)", value=fields["disabled"], on_change=lambda e: fields.update({"disabled": e.value})).props("dark dense")

            # 3. SDXL 프롬프트 편집
            ui.label("🏷️ SDXL 프롬프트 (Unholy Mix, Danbooru 순수 태그)").classes("text-xs font-bold text-emerald-400 mt-3 mb-1")
            ui.textarea(value=fields["sdxl_prompt"], on_change=lambda e: fields.update({"sdxl_prompt": e.value})).props(
                "outlined dark autogrow rows=3"
            ).classes("w-full font-mono text-xs mb-3")

            # 4. FLUX 프롬프트 편집
            ui.label("📝 FLUX 프롬프트 (T5-XXL 서술형 영문 자연어)").classes("text-xs font-bold text-amber-400 mt-2 mb-1")
            ui.textarea(value=fields["flux_prompt"], on_change=lambda e: fields.update({"flux_prompt": e.value})).props(
                "outlined dark autogrow rows=4"
            ).classes("w-full font-mono text-xs mb-4")

    def inspect_prompt(code: str, fields: dict):
        p_entry = PoseEntry(
            code=code,
            section=state["current_section"],
            label=fields["label"],
            prompt=fields["flux_prompt"],
            description=fields["description"]
        )
        open_prompt_inspector_dialog(sample_char, p_entry)

    def save_pose_changes(code: str, fields: dict, old_label: str):
        new_label = fields["label"].strip()
        new_flags = {
            "nude": bool(fields["nude"]),
            "scene_type": str(fields["scene_type"]),
            "wet": bool(fields["wet"]),
            "disabled": bool(fields["disabled"]),
        }

        # 라벨 변경 시 에셋 리네임 계획 확인
        if old_label and new_label != old_label:
            plan = default_pose_service.plan_asset_rename(code, old_label, new_label)
            if plan:
                open_rename_confirm_dialog(code, fields, new_flags, old_label, new_label, plan)
                return

        # 일반 저장 실행
        try:
            default_pose_service.update_pose(
                code=code,
                label=new_label,
                description=fields["description"],
                flags=new_flags,
                flux_prompt=fields["flux_prompt"],
                sdxl_prompt=fields["sdxl_prompt"]
            )
            ui.notify(f"#{code} '{new_label}' 포즈가 SDXL & FLUX DB에 안전하게 동기화 저장되었습니다.", type="positive")
            refresh_items_list()
            load_and_render_detail()
        except Exception as ex:
            ui.notify(f"저장 실패: {ex}", type="negative")

    def open_rename_confirm_dialog(code: str, fields: dict, flags: dict, old_label: str, new_label: str, plan: list):
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
                        flux_prompt=fields["flux_prompt"],
                        sdxl_prompt=fields["sdxl_prompt"]
                    )
                    renamed_cnt = 0
                    if apply_rename:
                        renamed_cnt = default_pose_service.apply_asset_rename(plan)
                    dialog.close()
                    msg = f"포즈 DB 저장 완료"
                    if renamed_cnt > 0:
                        msg += f" 및 에셋 파일 {renamed_cnt}개 일괄 리네임 완료"
                    ui.notify(msg, type="positive")
                    refresh_items_list()
                    load_and_render_detail()
                except Exception as ex:
                    ui.notify(f"처리 실패: {ex}", type="negative")

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("포즈만 변경 (파일 유지)", on_click=lambda: execute_save_and_rename(False)).props("flat color=slate-400")
                ui.button("포즈 및 파일 동시 변경", icon="sync", on_click=lambda: execute_save_and_rename(True)).props("unelevated color=amber-500 text-color=slate-950 font-bold")

        dialog.open()

    # 최초 실행
    refresh_items_list()
    load_and_render_detail()
