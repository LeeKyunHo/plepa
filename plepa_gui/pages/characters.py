"""
plepa_gui.pages.characters
캐릭터 목록 조회, 폼 편집, 원자적 저장, 복제 마법사 및 안전 삭제 페이지.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from nicegui import app, ui
from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.schemas import (
    CharacterAppearanceSchema,
    CharacterSchema,
    LoraSchema,
)
from plepa_gui.components.header import render_header


def render_characters_page() -> None:
    """캐릭터 관리 페이지 렌더링."""
    render_header("/characters")

    # 반응형 상태 저장소
    state = {
        "selected_roster": DEFAULT_ROSTER,
        "selected_prefix": None,
        "current_char": None,
        "current_file": None,
    }

    # 전체 로스터 목록 탐색
    available_rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    if not available_rosters:
        available_rosters = [DEFAULT_ROSTER]

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        # ==========================================
        # 좌측: 로스터 및 캐릭터 목록 사이드바
        # ==========================================
        with ui.card().classes("w-80 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            ui.label("👥 캐릭터 목록").classes("text-lg font-bold text-slate-100 mb-2")

            # 로스터 선택
            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("로스터:").classes("text-xs text-slate-400 font-semibold")
                roster_select = ui.select(
                    options=available_rosters,
                    value=state["selected_roster"],
                    on_change=lambda e: change_roster(e.value),
                ).props("dense outlined dark options-dense").classes("w-44 text-sm")

            # 캐릭터 목록 컨테이너
            char_list_container = ui.column().classes("w-full gap-2 max-h-[620px] overflow-y-auto pr-1")

            # 하단 버튼: 신규 추가
            with ui.row().classes("w-full mt-4 pt-4 border-t border-slate-800 justify-between"):
                ui.button("신규 캐릭터", icon="add", on_click=lambda: open_new_char_dialog()).props(
                    "outline color=amber-400 dense size=sm"
                )
                ui.button("새로고침", icon="refresh", on_click=lambda: refresh_char_list()).props(
                    "flat color=slate-400 dense size=sm"
                )

        # ==========================================
        # 우측: 캐릭터 상세 편집 폼
        # ==========================================
        form_card = ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[700px]")

    def change_roster(roster_name: str):
        state["selected_roster"] = roster_name
        state["selected_prefix"] = None
        state["current_char"] = None
        state["current_file"] = None
        refresh_char_list()
        render_form()

    def refresh_char_list():
        char_list_container.clear()
        chars = default_character_service.list_characters(roster=state["selected_roster"])

        if not chars:
            with char_list_container:
                ui.label("등록된 캐릭터가 없습니다.").classes("text-xs text-slate-500 py-4")
            return

        with char_list_container:
            for r_name, char, file_path in chars:
                is_selected = (char.prefix == state["selected_prefix"])
                btn_classes = "w-full justify-start text-left px-3 py-2 rounded-lg transition-all "
                if is_selected:
                    btn_classes += "bg-amber-500/20 text-amber-300 border border-amber-500/50 font-bold"
                else:
                    btn_classes += "bg-slate-800/60 text-slate-200 hover:bg-slate-800 border border-transparent"

                with ui.row().classes(btn_classes).on("click", lambda c=char, f=file_path: select_character(c, f)):
                    with ui.column().classes("gap-0"):
                        ui.label(f"{char.name}").classes("text-sm font-semibold")
                        ui.label(f"[{char.prefix}] {char.gender}").classes("text-[11px] text-slate-400")

        # 최초 진입 시 첫 번째 캐릭터 자동 선택
        if state["selected_prefix"] is None and chars:
            select_character(chars[0][1], chars[0][2])

    def select_character(char: CharacterSchema, file_path: Path):
        state["selected_prefix"] = char.prefix
        state["current_char"] = char
        state["current_file"] = file_path
        refresh_char_list()
        render_form()

    def render_form():
        form_card.clear()
        char: Optional[CharacterSchema] = state["current_char"]

        if not char:
            with form_card:
                with ui.column().classes("w-full h-96 items-center justify-center text-slate-500"):
                    ui.icon("person_search", size="48px").classes("text-slate-600 mb-2")
                    ui.label("좌측 목록에서 편집할 캐릭터를 선택해 주십시오.").classes("text-sm")
            return

        with form_card:
            # 상단 헤더 및 액션 버튼들
            with ui.row().classes("w-full justify-between items-center mb-6 pb-4 border-b border-slate-800"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("badge", size="28px").classes("text-amber-400")
                    with ui.column().classes("gap-0"):
                        ui.label(f"{char.name} ({char.prefix})").classes("text-xl font-bold text-slate-100")
                        ui.label(f"저장 위치: {state['current_file'].resolve() if state['current_file'] else '-'}").classes("text-xs text-slate-500 font-mono")
                
                with ui.row().classes("items-center gap-2"):
                    ui.button("복제 마법사", icon="content_copy", on_click=lambda: open_clone_dialog(char)).props(
                        "outline color=info dense size=sm"
                    ).tooltip("이 캐릭터를 복제하여 새 체형/의상 버전 만들기")
                    ui.button("삭제", icon="delete", on_click=lambda: confirm_delete(char)).props(
                        "outline color=negative dense size=sm"
                    ).tooltip("캐릭터를 휴지통으로 이동")
                    ui.button("저장", icon="save", on_click=lambda: save_current_form()).props(
                        "unelevated color=amber-500 text-color=slate-950 font-bold px-4"
                    )

            # 레퍼런스 이미지 배너 (있는 경우)
            ref_path = default_asset_service.find_reference_image(char.prefix, roster=state["selected_roster"])
            if ref_path:
                with ui.row().classes("w-full items-center gap-4 p-3 bg-slate-800/40 rounded-lg mb-6 border border-slate-700/50"):
                    app.add_static_files(f"/ref_imgs_{char.prefix}", str(ref_path.parent))
                    ui.image(f"/ref_imgs_{char.prefix}/{ref_path.name}").classes("w-16 h-16 object-cover rounded shadow border border-slate-600")
                    with ui.column().classes("gap-0"):
                        ui.label("IP-Adapter 레퍼런스 이미지").classes("text-xs font-semibold text-slate-300")
                        ui.label(f"{ref_path.name} (가중치: {char.ref_weight})").classes("text-xs text-slate-500 font-mono")

            # 폼 필드 입력 상태
            fields = {
                "prefix": char.prefix,
                "name": char.name,
                "gender": char.gender,
                "is_adult": char.is_adult,
                "face_and_hair": char.appearance.face_and_hair,
                "physique": char.appearance.physique,
                "outfit": char.appearance.outfit,
                "lora_name": char.lora.name or "",
                "lora_weight": char.lora.weight,
                "style_keywords": char.style_keywords,
                "sdxl_positive": char.sdxl_positive or "",
                "sdxl_negative": char.sdxl_negative or "",
                "ref_weight": char.ref_weight,
                "default_mode": char.default_mode or "",
            }

            # 1. 기본 식별 정보
            with ui.row().classes("w-full gap-4 mb-4"):
                ui.input("식별자 (Prefix, 영문/소문자/숫자)", value=fields["prefix"], on_change=lambda e: fields.update({"prefix": e.value})).props(
                    "outlined dark dense"
                ).classes("w-1/3")
                ui.input("캐릭터 이름 (한글/영문)", value=fields["name"], on_change=lambda e: fields.update({"name": e.value})).props(
                    "outlined dark dense"
                ).classes("w-1/3")
                ui.select(options=["female", "male", "otokonoko"], value=fields["gender"], on_change=lambda e: fields.update({"gender": e.value})).props(
                    "outlined dark dense"
                ).classes("w-1/4")
            
            # default_mode 설정 (키로 스타일)
            with ui.row().classes("w-full gap-4 mb-4 items-center"):
                ui.label("⚡ 기본 엔진 모드 (default_mode):").classes("text-xs font-semibold text-slate-400 w-48")
                ui.select(
                    options=["", "sdxl", "flux", "fast", "quality"],
                    value=fields["default_mode"],
                    on_change=lambda e: fields.update({"default_mode": e.value})
                ).props("outlined dark dense clearable").classes("flex-1").tooltip(
                    "빈칸: 시스템 기본값 | sdxl/fast: 고속 2D 체크포인트 | flux/quality/q: FLUX.1 [dev] 고품질"
                )

            # 2. 외형 묘사 (얼굴/헤어, 체형, 의상)
            ui.label("🎨 외형 묘사 (Appearance)").classes("text-sm font-bold text-amber-400 mt-4 mb-2")
            with ui.column().classes("w-full gap-3"):
                ui.textarea("얼굴 및 헤어스타일 (face_and_hair)", value=fields["face_and_hair"], on_change=lambda e: fields.update({"face_and_hair": e.value})).props(
                    "outlined dark autogrow rows=2"
                ).classes("w-full")
                ui.textarea("체형 및 신체 묘사 (physique: 슬랜더, 글래머, 키 등)", value=fields["physique"], on_change=lambda e: fields.update({"physique": e.value})).props(
                    "outlined dark autogrow rows=2"
                ).classes("w-full")
                ui.textarea("기본 착용 의상 (outfit)", value=fields["outfit"], on_change=lambda e: fields.update({"outfit": e.value})).props(
                    "outlined dark autogrow rows=2"
                ).classes("w-full")

            # 3. 모델 가중치 & SDXL 태그
            ui.label("⚙️ 엔진 및 프롬프트 세부 설정").classes("text-sm font-bold text-amber-400 mt-4 mb-2")
            with ui.row().classes("w-full gap-4"):
                ui.input("LoRA 파일명 (확장자 포함)", value=fields["lora_name"], on_change=lambda e: fields.update({"lora_name": e.value})).props(
                    "outlined dark dense"
                ).classes("flex-1")
                with ui.column().classes("w-48 gap-0"):
                    ui.label(f"LoRA 강도: {fields['lora_weight']}").classes("text-xs text-slate-400")
                    ui.slider(min=0.0, max=1.5, step=0.05, value=fields["lora_weight"], on_change=lambda e: fields.update({"lora_weight": e.value})).props("dark dense")
                with ui.column().classes("w-48 gap-0"):
                    ui.label(f"IP-Adapter 가중치: {fields['ref_weight']}").classes("text-xs text-slate-400")
                    ui.slider(min=0.0, max=1.0, step=0.05, value=fields["ref_weight"], on_change=lambda e: fields.update({"ref_weight": e.value})).props("dark dense")

            with ui.column().classes("w-full gap-3 mt-3"):
                ui.textarea("화풍 및 공통 스타일 (style_keywords)", value=fields["style_keywords"], on_change=lambda e: fields.update({"style_keywords": e.value})).props(
                    "outlined dark autogrow rows=2"
                ).classes("w-full")
                ui.textarea("SDXL 전용 긍정 태그 (sdxl_positive)", value=fields["sdxl_positive"], on_change=lambda e: fields.update({"sdxl_positive": e.value})).props(
                    "outlined dark autogrow rows=2"
                ).classes("w-full")
                ui.textarea("SDXL 전용 부정 태그 (sdxl_negative)", value=fields["sdxl_negative"], on_change=lambda e: fields.update({"sdxl_negative": e.value})).props(
                    "outlined dark autogrow rows=2"
                ).classes("w-full")

            # 저장 콜백 함수
            def save_current_form():
                try:
                    updated_data = CharacterSchema(
                        prefix=fields["prefix"],
                        name=fields["name"],
                        gender=fields["gender"],
                        is_adult=fields["is_adult"],
                        appearance=CharacterAppearanceSchema(
                            face_and_hair=fields["face_and_hair"],
                            physique=fields["physique"],
                            outfit=fields["outfit"],
                        ),
                        lora=LoraSchema(
                            name=fields["lora_name"] if fields["lora_name"].strip() else None,
                            weight=fields["lora_weight"],
                        ),
                        style_keywords=fields["style_keywords"],
                        sdxl_positive=fields["sdxl_positive"] if fields["sdxl_positive"].strip() else None,
                        sdxl_negative=fields["sdxl_negative"] if fields["sdxl_negative"].strip() else None,
                        ref_weight=fields["ref_weight"],
                        default_mode=fields["default_mode"] if fields["default_mode"].strip() else None,
                        profiles=char.profiles,
                    )
                    saved = default_character_service.save_character(
                        roster=state["selected_roster"],
                        char=updated_data,
                        original_file=state["current_file"]
                    )
                    ui.notify(f"캐릭터 '{updated_data.name}' 설정이 안전하게 저장되었습니다.", type="positive")
                    select_character(updated_data, saved)
                except Exception as ex:
                    ui.notify(f"저장 실패: {ex}", type="negative")

    # 복제 마법사 다이얼로그
    def open_clone_dialog(src_char: CharacterSchema):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg p-6 bg-slate-900 border border-slate-700"):
            ui.label("🧙 캐릭터 복제 마법사 (Clone Wizard)").classes("text-lg font-bold text-amber-400 mb-1")
            ui.label(f"'{src_char.name}'({src_char.prefix}) 설정을 기반으로 변형 캐릭터를 생성합니다.").classes("text-xs text-slate-400 mb-4")

            c_prefix = ui.input("새 식별자 (Prefix, 예: ykn_mat)", value=f"{src_char.prefix}_new").props("outlined dark dense").classes("w-full mb-3")
            c_name = ui.input("새 이름 (예: 유키노 성인)", value=f"{src_char.name} 변형").props("outlined dark dense").classes("w-full mb-3")
            c_physique = ui.textarea("신체/체형 묘사 변경 (physique)", value=src_char.appearance.physique).props("outlined dark autogrow rows=2").classes("w-full mb-4")

            def execute_clone():
                try:
                    new_p = c_prefix.value.strip()
                    new_n = c_name.value.strip()
                    if not new_p or not new_n:
                        ui.notify("식별자와 이름을 입력해주세요.", type="warning")
                        return
                    saved_path = default_character_service.clone_character(
                        src_prefix=src_char.prefix,
                        src_roster=state["selected_roster"],
                        new_prefix=new_p,
                        new_name=new_n,
                        overrides={"appearance": {"physique": c_physique.value.strip()}}
                    )
                    dialog.close()
                    ui.notify(f"새 캐릭터 '{new_n}' 복제 성공!", type="positive")
                    refresh_char_list()
                    # 신규 복제본 선택
                    new_char_obj = default_character_service.find_character(new_p, roster=state["selected_roster"])[0]
                    new_schema = CharacterSchema.model_validate(new_char_obj.__dict__)
                    select_character(new_schema, saved_path)
                except Exception as ce:
                    ui.notify(f"복제 실패: {ce}", type="negative")

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("취소", on_click=dialog.close).props("flat color=slate-400")
                ui.button("복제 생성", icon="auto_fix_high", on_click=execute_clone).props("unelevated color=amber-500 text-color=slate-950 font-bold")

        dialog.open()

    # 신규 캐릭터 생성 다이얼로그
    def open_new_char_dialog():
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg p-6 bg-slate-900 border border-slate-700"):
            ui.label("✨ 신규 캐릭터 등록").classes("text-lg font-bold text-amber-400 mb-4")
            n_prefix = ui.input("식별자 (Prefix, 예: new_char)").props("outlined dark dense").classes("w-full mb-3")
            n_name = ui.input("캐릭터 이름 (예: 신규 캐릭터)").props("outlined dark dense").classes("w-full mb-3")

            def execute_create():
                try:
                    p = n_prefix.value.strip()
                    n = n_name.value.strip()
                    if not p or not n:
                        ui.notify("식별자와 이름을 입력해주세요.", type="warning")
                        return
                    new_schema = CharacterSchema(
                        prefix=p,
                        name=n,
                        appearance=CharacterAppearanceSchema(face_and_hair="black hair", physique="slender", outfit="casual clothes")
                    )
                    saved = default_character_service.save_character(roster=state["selected_roster"], char=new_schema)
                    dialog.close()
                    ui.notify(f"캐릭터 '{n}' 생성 완료!", type="positive")
                    refresh_char_list()
                    select_character(new_schema, saved)
                except Exception as ce:
                    ui.notify(f"생성 실패: {ce}", type="negative")

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("취소", on_click=dialog.close).props("flat color=slate-400")
                ui.button("생성", on_click=execute_create).props("unelevated color=amber-500 text-color=slate-950 font-bold")

        dialog.open()

    # 삭제 확인 다이얼로그
    def confirm_delete(char: CharacterSchema):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md p-6 bg-slate-900 border border-slate-700"):
            ui.label("🗑️ 캐릭터 삭제").classes("text-lg font-bold text-rose-400 mb-2")
            ui.label(f"'{char.name}'({char.prefix}) 캐릭터를 삭제하시겠습니까?").classes("text-sm text-slate-200")
            ui.label("※ 파일은 영구 삭제되지 않고 _trash/ 폴더로 안전하게 이동됩니다.").classes("text-xs text-slate-400 mt-2 mb-4")

            def execute_delete():
                trash_path = default_character_service.delete_character(state["selected_roster"], char.prefix)
                dialog.close()
                ui.notify(f"캐릭터가 휴지통으로 이동되었습니다: {trash_path.name if trash_path else ''}", type="info")
                state["selected_prefix"] = None
                state["current_char"] = None
                state["current_file"] = None
                refresh_char_list()
                render_form()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("취소", on_click=dialog.close).props("flat color=slate-400")
                ui.button("휴지통 이동", color="negative", on_click=execute_delete).props("unelevated font-bold")

        dialog.open()

    # 최초 로딩
    refresh_char_list()
