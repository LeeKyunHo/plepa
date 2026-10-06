"""
plepa_gui.pages.gallery
캐릭터 x 포즈 매트릭스 갤러리 및 상세 이미지 뷰어 페이지.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from nicegui import app, ui
from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.reporter import open_in_explorer
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service
from plepa_gui.components.header import render_header

# 정적 파일 서빙 등록
app.add_static_files("/projects_static", str(PROJECTS_DIR))


def render_gallery_page() -> None:
    """매트릭스 갤러리 페이지 렌더링."""
    render_header("/gallery")

    state = {
        "roster": DEFAULT_ROSTER,
        "selected_chars": [],
        "selected_codes": ["038", "039", "044", "057"],
        "pose_set": "shower_trio",
    }

    available_rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    if not available_rosters:
        available_rosters = [DEFAULT_ROSTER]

    all_poses = default_pose_service.load_pose_db(engine="flux")
    pose_sets = default_pose_service.load_pose_sets()

    with ui.column().classes("w-full max-w-[1500px] mx-auto p-6 gap-6"):
        # 상단 필터 및 옵션 바
        with ui.card().classes("w-full bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.row().classes("items-center gap-4 flex-wrap"):
                    ui.label("🎨 매트릭스 갤러리").classes("text-xl font-bold text-slate-100")

                    # 로스터 선택
                    ui.label("로스터:").classes("text-xs text-slate-400 font-semibold ml-2")
                    roster_sel = ui.select(
                        options=available_rosters,
                        value=state["roster"],
                        on_change=lambda e: on_roster_changed(e.value)
                    ).props("dense outlined dark options-dense").classes("w-36 text-sm")

                    # 포즈 세트 필터
                    ui.label("포즈 범위:").classes("text-xs text-slate-400 font-semibold ml-2")
                    set_opts = {s.id: s.name for s in pose_sets}
                    set_opts["all_80"] = "전체 80종 포즈"
                    ui.select(
                        options=set_opts,
                        value="shower_trio" if "shower_trio" in set_opts else list(set_opts.keys())[0],
                        on_change=lambda e: on_set_changed(e.value)
                    ).props("dense outlined dark options-dense").classes("w-48 text-sm")

                with ui.row().classes("items-center gap-2"):
                    ui.button("에셋 폴더 열기", icon="folder_open", on_click=lambda: open_current_folder()).props(
                        "outline color=slate-300 dense size=sm"
                    )
                    ui.button("새로고침", icon="refresh", on_click=lambda: render_matrix()).props(
                        "flat color=amber-400 dense size=sm"
                    )

            # 대상 캐릭터 체크박스 목록
            with ui.row().classes("w-full items-center gap-4 pt-3 mt-3 border-t border-slate-800 flex-wrap"):
                ui.label("비교 캐릭터:").classes("text-xs font-semibold text-slate-400")
                chars_chips_container = ui.row().classes("items-center gap-2 flex-wrap")

        # 메인 매트릭스 테이블 컨테이너
        matrix_container = ui.card().classes("w-full bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg overflow-x-auto")

    def on_roster_changed(new_r: str):
        state["roster"] = new_r
        refresh_char_chips()
        render_matrix()

    def on_set_changed(set_id: str):
        if set_id == "all_80":
            state["selected_codes"] = sorted(all_poses.keys())
        else:
            s = next((item for item in pose_sets if item.id == set_id), None)
            if s:
                state["selected_codes"] = s.codes
        render_matrix()

    def refresh_char_chips():
        chars_chips_container.clear()
        chars = default_character_service.list_characters(roster=state["roster"])
        # 기본값: 상위 최대 5개 선택
        state["selected_chars"] = [c.prefix for _, c, _ in chars[:5]]

        with chars_chips_container:
            for _, c, _ in chars:
                is_selected = c.prefix in state["selected_chars"]

                def toggle_c(prefix=c.prefix):
                    if prefix in state["selected_chars"]:
                        state["selected_chars"].remove(prefix)
                    else:
                        state["selected_chars"].append(prefix)
                    render_matrix()

                ui.chip(
                    f"{c.name} ({c.prefix})",
                    selectable=True,
                    selected=is_selected,
                    on_selection_change=lambda e, p=c.prefix: (state["selected_chars"].append(p) if e.value else state["selected_chars"].remove(p), render_matrix())
                ).props("dense text-xs")

    def open_current_folder():
        target = PROJECTS_DIR / state["roster"] / "assets"
        target.mkdir(parents=True, exist_ok=True)
        open_in_explorer(target)

    def render_matrix():
        matrix_container.clear()
        prefixes = state["selected_chars"]
        codes = state["selected_codes"]

        if not prefixes or not codes:
            with matrix_container:
                ui.label("비교할 캐릭터와 포즈를 선택해 주십시오.").classes("text-sm text-slate-500 py-6")
            return

        matrix = default_asset_service.get_matrix_map(prefixes, codes, roster=state["roster"])

        with matrix_container:
            # 테이블 구조 렌더링
            with ui.element("table").classes("w-full border-collapse text-left"):
                # Header: 포즈 라벨
                with ui.element("thead"):
                    with ui.element("tr").classes("border-b border-slate-700 bg-slate-800/80"):
                        ui.element("th").classes("p-3 text-xs font-bold text-amber-400 w-36").add_slot(
                            "default", "캐릭터 / 포즈"
                        )
                        for code in codes:
                            pose_obj = all_poses.get(code)
                            label_str = pose_obj.label if pose_obj else code
                            with ui.element("th").classes("p-3 text-xs font-semibold text-slate-300 text-center min-w-[130px]"):
                                with ui.column().classes("items-center gap-0"):
                                    ui.label(f"#{code}").classes("text-[10px] text-slate-400 font-mono")
                                    ui.label(label_str).classes("text-xs font-bold")

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
                                except Exception:
                                    ui.label(prefix).classes("text-sm text-slate-300")

                            # 각 포즈별 이미지 셀
                            for code in codes:
                                img_path: Optional[Path] = matrix.get(prefix, {}).get(code)
                                with ui.element("td").classes("p-2 text-center align-middle border-r border-slate-800/40"):
                                    if img_path and img_path.exists():
                                        rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                                        web_url = f"/projects_static/{rel_path}"

                                        with ui.column().classes("items-center justify-center gap-1 mx-auto"):
                                            ui.image(web_url).classes(
                                                "w-28 h-40 object-cover rounded shadow cursor-pointer border border-slate-700 hover:border-amber-400 transition-all hover:scale-105"
                                            ).on("click", lambda u=web_url, p=img_path: open_lightbox(u, p))
                                    else:
                                        with ui.column().classes("items-center justify-center w-28 h-40 bg-slate-800/30 rounded border border-dashed border-slate-700/60 text-slate-600"):
                                            ui.icon("image_not_supported", size="24px")
                                            ui.label("미생성").classes("text-[11px] mt-1")

    def open_lightbox(img_url: str, file_path: Path):
        with ui.dialog() as dialog, ui.card().classes("max-w-4xl p-4 bg-slate-950 border border-slate-700"):
            with ui.row().classes("w-full justify-between items-center mb-2"):
                ui.label(file_path.name).classes("text-sm font-bold text-slate-200 font-mono")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=slate-400")

            ui.image(img_url).classes("max-h-[75vh] object-contain rounded mx-auto")

            with ui.row().classes("w-full justify-between items-center mt-3 pt-2 border-t border-slate-800"):
                size_kb = file_path.stat().st_size / 1024
                ui.label(f"크기: {size_kb:.1f} KB").classes("text-xs text-slate-400")
                ui.button("원본 폴더 열기", icon="folder", on_click=lambda: open_in_explorer(file_path.parent)).props("flat dense size=sm color=amber-400")

        dialog.open()

    refresh_char_chips()
    on_set_changed("shower_trio")
