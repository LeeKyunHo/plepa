"""
plepa_gui.pages.gallery
캐릭터 에셋 갤러리:
1. 단일 캐릭터 전체 갤러리 뷰 (그리드 카드 뷰)
2. 다중 캐릭터 x 포즈 매트릭스 비교 뷰 (체형별/포즈별 비교 최적화)
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Dict, List, Optional

from nicegui import app, run, ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.reporter import open_in_explorer
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.services.upscale_service import default_upscale_service
from plepa_gui.components.header import render_header

import mimetypes
mimetypes.add_type("image/webp", ".webp")

# 정적 파일 서빙 등록
app.add_static_files("/projects_static", str(PROJECTS_DIR))


def detect_best_default_roster() -> str:
    """에셋이 가장 많이 존재하는 로스터를 기본값으로 자동 감지 (예: don)."""
    best_roster = "don"
    max_count = 0
    for p in PROJECTS_DIR.iterdir():
        if not p.is_dir() or p.name.startswith("."):
            continue
        assets_dir = p / "assets"
        if not assets_dir.is_dir():
            continue
        webp_count = len(list(assets_dir.glob("*/*.webp")))
        if webp_count > max_count:
            max_count = webp_count
            best_roster = p.name
    return best_roster


def render_gallery_page() -> None:
    """통합 에셋 갤러리 페이지 렌더링."""
    render_header("/gallery")

    default_roster = detect_best_default_roster()
    all_poses = default_pose_service.load_pose_db(engine="flux")
    pose_sets = default_pose_service.load_pose_sets()

    available_rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    if not available_rosters:
        available_rosters = [default_roster]

    state = {
        "view_mode": "matrix",  # 'matrix', 'single', 'misc'
        "roster": default_roster,
        "single_char": "",
        "selected_chars": [],
        "selected_codes": sorted(all_poses.keys()),  # 전체 포즈 (000~159) 기본
        "pose_set": "all",  # "전체 포즈"
        "misc_filter": "all",
    }

    with ui.column().classes("w-full max-w-[1550px] mx-auto p-6 gap-6"):
        # 상단 통합 컨트롤 바
        with ui.card().classes("w-full bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg"):
            with ui.row().classes("w-full justify-between items-center mb-3"):
                with ui.row().classes("items-center gap-4 flex-wrap"):
                    ui.label("🎨 에셋 갤러리").classes("text-xl font-bold text-slate-100")

                    # 뷰 모드 전환 탭
                    view_toggle = ui.toggle(
                        {
                            "matrix": "체형 비교 매트릭스 뷰",
                            "single": "단일 캐릭터 전체 갤러리",
                            "misc": "✨ 비포즈 / 기타 에셋 (배경·레퍼런스·샘플)",
                        },
                        value=state["view_mode"],
                        on_change=lambda e: switch_view_mode(e.value)
                    ).props("dense dark").classes("text-xs")

                    # 로스터 선택
                    ui.label("로스터:").classes("text-xs text-slate-400 font-semibold ml-2")
                    roster_sel = ui.select(
                        options=available_rosters,
                        value=state["roster"],
                        on_change=lambda e: on_roster_changed(e.value)
                    ).props("dense outlined dark options-dense").classes("w-36 text-sm")

                with ui.row().classes("items-center gap-2"):
                    ui.button("에셋 폴더 열기", icon="folder_open", on_click=lambda: open_current_folder()).props(
                        "outline color=slate-300 dense size=sm"
                    )
                    ui.button("새로고침", icon="refresh", on_click=lambda: render_content()).props(
                        "flat color=amber-400 dense size=sm"
                    )

            # 매트릭스 뷰 전용 필터 컨트롤
            matrix_controls = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")

            # 단일 캐릭터 뷰 전용 필터 컨트롤
            single_controls = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")

            # 기타/비포즈 에셋 전용 필터 컨트롤
            misc_controls = ui.column().classes("w-full gap-3 pt-3 border-t border-slate-800")

        # 메인 콘텐츠 뷰어 컨테이너
        content_container = ui.card().classes("w-full bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg overflow-x-auto min-h-[500px]")

    def switch_view_mode(mode: str):
        state["view_mode"] = mode
        update_control_bars()
        render_content()

    def on_roster_changed(new_r: str):
        state["roster"] = new_r
        state["selected_chars"] = []
        state["single_char"] = ""
        update_control_bars()
        render_content()

    def open_current_folder():
        if state["view_mode"] == "misc":
            target = PROJECTS_DIR / state["roster"]
        else:
            target = PROJECTS_DIR / state["roster"] / "assets"
        target.mkdir(parents=True, exist_ok=True)
        open_in_explorer(target)
        try:
            ui.notify(f"📂 PC 파일 탐색기에서 폴더를 열었습니다: {target.name}", type="positive")
        except Exception:
            pass

    def update_control_bars():
        matrix_controls.clear()
        single_controls.clear()
        misc_controls.clear()

        # 현재 로스터의 캐릭터 및 에셋 통계 조회
        char_asset_counts = get_character_asset_counts(state["roster"])

        if state["view_mode"] == "matrix":
            matrix_controls.set_visibility(True)
            single_controls.set_visibility(False)
            misc_controls.set_visibility(False)

            with matrix_controls:
                # 1. 빠른 프리셋 버튼들
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    ui.label("빠른 캐릭터 프리셋:").classes("text-xs font-semibold text-slate-400 mr-1")

                    # 네쌍둥이 4인 세트 퀵 버튼
                    if any(k in char_asset_counts for k in ["yua", "serin", "sia", "hayul", "ykn_1st", "ykn_2nd", "ykn_3rd", "ykn_4th"]):
                        ui.button("🌸 네쌍둥이 4인 (전체 포즈)", icon="auto_awesome", on_click=lambda: select_quadruplets_preset()).props(
                            "unelevated dense size=xs color=rose-500/20 text-color=rose-300 border border-rose-500/40"
                        ).tooltip("설유아, 설세린, 설시아, 설하율 4인의 전체 포즈 비교")

                    # 땋은머리 3종 세트 퀵 버튼
                    if any(k in char_asset_counts for k in ["ykn_brd_a", "ykn_brd_b", "ykn_brd_c"]):
                        ui.button("🎀 땋은머리 샘플 3종", icon="face", on_click=lambda: select_ykn_braid_preset()).props(
                            "unelevated dense size=xs color=purple-500/20 text-color=purple-300 border border-purple-500/40"
                        ).tooltip("ykn_brd_a, ykn_brd_b, ykn_brd_c (000 평상) 선택")

                    # 유키노 체형 및 의상 묶음 퀵 버튼
                    if any(k in char_asset_counts for k in ["ykn_sle", "ykn_std", "ykn_mat"]):
                        ui.button("👑 유키노 체형 6종 세트", icon="group", on_click=lambda: select_ykn_preset()).props(
                            "unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40"
                        ).tooltip("ykn_sle, ykn_std, ykn_mat, ykn_crv, ykn_gla, ykn_gla_up 일괄 선택")

                    if any(k in char_asset_counts for k in ["ykn_bun", "ykn_nur", "ykn_mai"]):
                        ui.button("👗 유키노 의상 6종 세트", icon="checkroom", on_click=lambda: select_ykn_outfit_preset()).props(
                            "unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40"
                        ).tooltip("ykn_bun, ykn_nur, ykn_mai, ykn_swm, ykn_qip, ykn_gya 일괄 선택")

                    ui.button("📷 이미지 있는 캐릭터만 선택", icon="filter_alt", on_click=lambda: select_has_assets()).props(
                        "flat dense size=xs color=emerald-400"
                    )
                    ui.button("전체 선택", icon="done_all", on_click=lambda: select_all_chars(True)).props(
                        "flat dense size=xs color=slate-400"
                    )
                    ui.button("선택 해제", icon="remove_done", on_click=lambda: select_all_chars(False)).props(
                        "flat dense size=xs color=slate-500"
                    )

                    # 포즈 범위 선택 셀렉터
                    ui.label("포즈 범위:").classes("text-xs text-slate-400 font-semibold ml-4")
                    set_opts = {"all": f"전체 포즈 ({len(all_poses)}종)"}
                    for s in pose_sets:
                        set_opts[s.id] = f"{s.name} ({len(s.codes)}종)"
                    ui.select(
                        options=set_opts,
                        value=state["pose_set"],
                        on_change=lambda e: on_set_changed(e.value)
                    ).props("dense outlined dark options-dense").classes("w-56 text-xs")

                # 2. 개별 캐릭터 칩 목록 (보유 장수 뱃지 포함)
                with ui.row().classes("items-center gap-2 flex-wrap mt-1"):
                    ui.label("대상 캐릭터:").classes("text-xs font-semibold text-slate-400 mr-1")
                    for prefix, cnt in char_asset_counts.items():
                        is_selected = prefix in state["selected_chars"]
                        chip_label = f"{prefix} ({cnt}장)" if cnt > 0 else f"{prefix} (0)"
                        color_props = "color=amber-600 text-color=white" if is_selected else "color=slate-800 text-color=slate-300"
                        ui.chip(
                            chip_label,
                            selectable=True,
                            selected=is_selected,
                            on_selection_change=lambda e, p=prefix: (toggle_char(p, e.value))
                        ).props(f"dense text-xs {color_props}")

        elif state["view_mode"] == "single":
            # 단일 캐릭터 뷰
            matrix_controls.set_visibility(False)
            single_controls.set_visibility(True)
            misc_controls.set_visibility(False)

            with single_controls:
                with ui.row().classes("items-center gap-4 flex-wrap"):
                    ui.label("캐릭터 선택:").classes("text-xs text-slate-400 font-semibold")
                    char_opts = {p: f"{p} ({cnt}장)" for p, cnt in char_asset_counts.items() if cnt > 0}
                    if not char_opts:
                        char_opts = {p: f"{p} (0장)" for p in char_asset_counts.keys()}

                    ui.select(
                        options=char_opts,
                        value=state["single_char"] if state["single_char"] in char_opts else None,
                        on_change=lambda e: (state.update({"single_char": e.value}), render_content())
                    ).props("dense outlined dark options-dense").classes("w-60 text-sm")

        else:
            # 기타 / 비포즈 에셋 뷰 (배경, 레퍼런스, 샘플)
            matrix_controls.set_visibility(False)
            single_controls.set_visibility(False)
            misc_controls.set_visibility(True)

            with misc_controls:
                with ui.row().classes("items-center justify-between w-full flex-wrap gap-3"):
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.label("카테고리 필터:").classes("text-xs font-semibold text-slate-400 mr-1")
                        filter_opts = {
                            "all": "전체 보기",
                            "reference": "레퍼런스 이미지",
                            "background": "배경 (BG)",
                            "sample": "비규격/샘플",
                        }
                        for f_key, f_label in filter_opts.items():
                            is_active = state.get("misc_filter", "all") == f_key
                            color = "color=purple-600 text-color=white" if is_active else "color=slate-800 text-color=slate-300"
                            ui.chip(
                                f_label,
                                selectable=True,
                                selected=is_active,
                                on_selection_change=lambda e, k=f_key: (
                                    state.update({"misc_filter": k}),
                                    update_control_bars(),
                                    render_content()
                                ) if e.value else None
                            ).props(f"dense text-xs {color}")

                    with ui.row().classes("items-center gap-2"):
                        ref_dir = PROJECTS_DIR / state["roster"] / "references"
                        ui.button("레퍼런스 폴더 열기", icon="folder", on_click=lambda: open_in_explorer(ref_dir)).props(
                            "flat dense size=xs color=purple-300"
                        )

    def get_character_asset_counts(roster: str) -> Dict[str, int]:
        """로스터 내 캐릭터별 생성된 에셋 개수 맵 반환."""
        chars = default_character_service.list_characters(roster=roster)
        counts = {}
        for _, c, _ in chars:
            assets = default_asset_service.list_character_assets(c.prefix, roster)
            counts[c.prefix] = len(assets)
        return counts

    def toggle_char(prefix: str, selected: bool):
        if selected and prefix not in state["selected_chars"]:
            state["selected_chars"].append(prefix)
        elif not selected and prefix in state["selected_chars"]:
            state["selected_chars"].remove(prefix)
        render_content()

    def select_quadruplets_preset():
        try:
            ui.notify("🌸 네쌍둥이 4인 (전체 포즈) 선택 완료!", type="positive")
        except Exception:
            pass
        counts = get_character_asset_counts(state["roster"])
        quad_prefixes = ["yua", "serin", "sia", "hayul"] if any(k in counts for k in ["yua", "serin"]) else ["ykn_1st", "ykn_2nd", "ykn_3rd", "ykn_4th"]
        state["selected_chars"] = [p for p in quad_prefixes if p in counts]
        state["pose_set"] = "all"
        state["selected_codes"] = sorted(all_poses.keys())
        update_control_bars()
        render_content()

    def select_ykn_braid_preset():
        try:
            ui.notify("유키노 땋은머리 샘플 3종 (#000 평상) 선택 완료!", type="positive")
        except Exception:
            pass
        braid_prefixes = ["ykn_brd_a", "ykn_brd_b", "ykn_brd_c"]
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = [p for p in braid_prefixes if p in counts]
        state["pose_set"] = "all"
        state["selected_codes"] = ["000"]
        update_control_bars()
        render_content()

    def select_ykn_preset():
        try:
            ui.notify("유키노 성인 5대 체형 및 업스케일 6종 선택 완료!", type="positive")
        except Exception:
            pass
        ykn_prefixes = ["ykn_sle", "ykn_std", "ykn_mat", "ykn_crv", "ykn_gla", "ykn_gla_up"]
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = [p for p in ykn_prefixes if p in counts]
        state["pose_set"] = "adult_testing"
        state["selected_codes"] = [f"{i:03d}" for i in range(24, 60)]
        update_control_bars()
        render_content()

    def select_ykn_outfit_preset():
        try:
            ui.notify("유키노 신규 테마 의상 6종 선택 완료!", type="positive")
        except Exception:
            pass
        ykn_outfits = ["ykn_bun", "ykn_nur", "ykn_mai", "ykn_swm", "ykn_qip", "ykn_gya"]
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = [p for p in ykn_outfits if p in counts]
        state["pose_set"] = "adult_testing"
        state["selected_codes"] = [f"{i:03d}" for i in range(24, 60)]
        update_control_bars()
        render_content()

    def select_has_assets():
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = [p for p, c in counts.items() if c > 0]
        update_control_bars()
        render_content()

    def select_all_chars(select: bool):
        counts = get_character_asset_counts(state["roster"])
        state["selected_chars"] = list(counts.keys()) if select else []
        update_control_bars()
        render_content()

    def on_set_changed(set_id: str):
        state["pose_set"] = set_id
        if set_id in ("all", "all_80"):
            state["selected_codes"] = sorted(all_poses.keys())
        else:
            s = next((item for item in pose_sets if item.id == set_id), None)
            if s:
                state["selected_codes"] = s.codes
        render_content()

    def render_content():
        content_container.clear()
        if state["view_mode"] == "matrix":
            render_matrix_view()
        elif state["view_mode"] == "single":
            render_single_char_view()
        else:
            render_misc_view()

    def render_single_char_view():
        """단일 캐릭터 전체 갤러리 카드 뷰."""
        prefix = state["single_char"]
        if not prefix:
            with content_container:
                with ui.column().classes("w-full py-16 items-center justify-center text-slate-500"):
                    ui.icon("person_search", size="48px").classes("text-slate-600 mb-2")
                    ui.label("상단에서 열람할 캐릭터를 선택해 주십시오.").classes("text-sm font-semibold")
            return

        assets = default_asset_service.list_character_assets(prefix, state["roster"])

        with content_container:
            if not assets:
                with ui.column().classes("w-full py-16 items-center justify-center text-slate-500"):
                    ui.icon("photo_library", size="48px").classes("text-slate-600 mb-2")
                    ui.label(f"'{prefix}' 캐릭터에 생성된 이미지가 없습니다.").classes("text-sm")
                return

            with ui.row().classes("w-full items-center justify-between mb-4 pb-2 border-b border-slate-800"):
                ui.label(f"🖼️ {prefix} 생성 에셋 목록 (총 {len(assets)}장)").classes("text-base font-bold text-amber-300")

            # 4열 반응형 카드 그리드
            with ui.grid(columns=4).classes("w-full gap-4"):
                for a in assets:
                    img_path: Path = a["path"]
                    rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                    web_url = f"/projects_static/{rel_path}"
                    code = a["code"]
                    pose_obj = all_poses.get(code)
                    label_str = pose_obj.label if pose_obj else a["label"]

                    with ui.card().classes("bg-slate-800/80 border border-slate-700/60 p-2 rounded-lg hover:border-amber-400 transition-all"):
                        ui.image(web_url).classes(
                            "w-full h-72 object-cover rounded shadow cursor-pointer hover:scale-[1.02] transition-transform"
                        ).on("click", lambda u=web_url, p=img_path: open_lightbox(u, p))

                        with ui.row().classes("w-full items-center justify-between mt-2 px-1"):
                            with ui.column().classes("gap-0"):
                                ui.label(f"#{code} {label_str}").classes("text-xs font-bold text-slate-100")
                                ui.label(f"{(a['size_bytes']/1024):.0f} KB").classes("text-[10px] text-slate-400")

                            if a.get("censored_path"):
                                ui.badge("검열본 보유", color="info").props("dense text-[10px]")

    def render_matrix_view():
        """캐릭터 x 포즈 2차원 매트릭스 비교 테이블."""
        char_counts = get_character_asset_counts(state["roster"])
        # 현재 로스터에 실제로 존재하는 캐릭터만 엄격하게 필터링 (타 프로젝트 캐릭터 침범 방지)
        prefixes = [p for p in state["selected_chars"] if p in char_counts]
        codes = state["selected_codes"]

        if not prefixes:
            with content_container:
                with ui.column().classes("w-full py-12 items-center justify-center text-slate-400"):
                    ui.icon("tune", size="40px").classes("text-amber-400 mb-2")
                    ui.label("상단에서 비교할 캐릭터를 1명 이상 선택해 주십시오.").classes("text-sm font-semibold")
                    ui.label("💡 상단의 '👑 유키노 체형 6종 세트' 또는 '📷 이미지 있는 캐릭터만 선택' 버튼을 누르면 즉시 조회됩니다.").classes("text-xs text-slate-500 mt-1")
            return

        matrix = default_asset_service.get_matrix_map(prefixes, codes, roster=state["roster"])

        with content_container:
            with ui.element("table").classes("w-full border-collapse text-left"):
                # Header: 포즈 라벨
                with ui.element("thead"):
                    with ui.element("tr").classes("border-b border-slate-700 bg-slate-800/80 sticky top-0 z-10"):
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

    def render_misc_view():
        """비포즈 / 기타 에셋 (배경, 레퍼런스, 샘플) 그리드 뷰."""
        all_misc = default_asset_service.list_misc_assets(state["roster"])
        m_filter = state.get("misc_filter", "all")
        if m_filter != "all":
            assets = [a for a in all_misc if a.get("type") == m_filter]
        else:
            assets = all_misc

        with content_container:
            if not assets:
                with ui.column().classes("w-full py-16 items-center justify-center text-slate-500"):
                    ui.icon("collections", size="48px").classes("text-slate-600 mb-2")
                    ui.label(f"'{state['roster']}' 로스터에 등록된 비포즈 / 기타 에셋이 없습니다.").classes("text-sm font-semibold")
                    ui.label("💡 레퍼런스 이미지(references/)나 배경 이미지(backgrounds/)가 이곳에 자동 표시됩니다.").classes("text-xs text-slate-600 mt-1")
                return

            with ui.row().classes("w-full items-center justify-between mb-4 pb-2 border-b border-slate-800"):
                ui.label(f"✨ 비포즈 / 기타 에셋 목록 (총 {len(assets)}장)").classes("text-base font-bold text-purple-300")
                ui.label(f"현재 로스터: {state['roster']}").classes("text-xs text-slate-400 font-mono")

            # 4열 반응형 카드 그리드
            with ui.grid(columns=4).classes("w-full gap-4"):
                for a in assets:
                    img_path: Path = a["path"]
                    rel_path = img_path.relative_to(PROJECTS_DIR).as_posix()
                    web_url = f"/projects_static/{rel_path}"
                    cat_name = a["category"]
                    folder_name = a.get("folder", "")
                    type_str = a.get("type", "misc")

                    badge_color = "purple-500" if type_str == "reference" else ("blue-500" if type_str == "background" else "emerald-500")

                    with ui.card().classes("bg-slate-800/80 border border-slate-700/60 p-2 rounded-lg hover:border-purple-400 transition-all"):
                        ui.image(web_url).classes(
                            "w-full h-72 object-cover rounded shadow cursor-pointer hover:scale-[1.02] transition-transform"
                        ).on("click", lambda u=web_url, p=img_path: open_lightbox(u, p))

                        with ui.column().classes("w-full mt-2 px-1 gap-1"):
                            with ui.row().classes("w-full justify-between items-center"):
                                ui.badge(cat_name, color=badge_color).props("dense text-[10px]")
                                ui.label(f"{(a['size_bytes']/1024):.0f} KB").classes("text-[10px] text-slate-400")

                            ui.label(a["name"]).classes("text-xs font-bold text-slate-100 truncate w-full").tooltip(a["name"])
                            ui.label(f"📁 {folder_name}").classes("text-[10px] text-slate-500 font-mono truncate w-full")

    def open_lightbox(img_url: str, file_path: Path):
        curr = {"url": img_url, "path": file_path}

        with ui.dialog() as dialog, ui.card().classes(
            "max-w-6xl w-full md:w-[92vw] min-h-[450px] p-4 bg-slate-950 border border-slate-700 rounded-2xl shadow-2xl overflow-y-auto"
        ):
            header_box = ui.row().classes("w-full justify-between items-center mb-3 px-2 pb-2 border-b border-slate-800 flex-wrap gap-2")
            img_box = ui.column().classes("w-full flex-1 items-center justify-center py-2")

            def refresh_header():
                header_box.clear()
                p = curr["path"]
                with header_box:
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.icon("zoom_in", size="20px").classes("text-amber-400")
                        ui.label(p.name).classes("text-sm md:text-base font-bold text-slate-100 font-mono")

                        dims = default_upscale_service.get_image_dimensions(p)
                        if dims:
                            dim_text = f"{dims[0]}x{dims[1]}"
                            is_4k = default_upscale_service.is_already_4k(p)
                            if is_4k:
                                ui.badge("4K UHD", color="emerald-600").props("dense text-xs")
                            ui.badge(dim_text, color="slate-800").props("dense text-xs border border-slate-700 text-slate-300 font-mono")

                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        size_kb = p.stat().st_size / 1024 if p.exists() else 0
                        ui.label(f"{size_kb:.1f} KB").classes("text-xs text-slate-400 mr-2")

                        # 4K AI 업스케일 버튼
                        is_already = default_upscale_service.is_already_4k(p)

                        async def on_upscale_click():
                            upscale_btn.props("loading")
                            ui.notify("🚀 AI 초해상화(4x-UltraSharp) 연산 중입니다... (약 15~20초 소요)", type="info")
                            try:
                                res_path = await run.io_bound(default_upscale_service.upscale_file, curr["path"], overwrite=False)
                                if res_path and res_path.exists():
                                    curr["path"] = res_path
                                    rel = res_path.relative_to(PROJECTS_DIR).as_posix()
                                    curr["url"] = f"/projects_static/{rel}?t={int(time.time())}"
                                    ui.notify(f"🎉 4K 업스케일 완료: {res_path.name}", type="positive")
                                    refresh_header()
                                    refresh_img()
                                    render_content()
                                else:
                                    ui.notify("❌ 4K 업스케일 생성에 실패했습니다.", type="negative")
                            except Exception as ex:
                                ui.notify(f"❌ 업스케일 오류: {ex}", type="negative")
                            finally:
                                upscale_btn.props(remove="loading")

                        upscale_btn = ui.button(
                            "4K 완료 (재연산)" if is_already else "✨ 4K AI 업스케일",
                            icon="auto_fix_high",
                            on_click=on_upscale_click
                        ).props(
                            f"unelevated dense size=sm color={'emerald-700' if is_already else 'purple-600'} text-white"
                        ).tooltip(
                            "이미 4K 초고화질입니다 (클릭 시 재연산)" if is_already else "4x-UltraSharp 초해상화 모델로 4K(4096x6144) 무손실 업스케일"
                        )

                        # 새 탭에서 원본 전용 뷰어로 열기 (브라우저 다운로드 강제 튕김 방지 및 줌 확대)
                        view_url = f"/view_image?src={curr['url']}&name={p.name}"
                        ui.button(
                            "새 탭에서 원본 보기",
                            icon="open_in_new",
                            on_click=lambda u=view_url: ui.navigate.to(u, new_tab=True)
                        ).props(f'flat dense size=sm color=amber-400 href="{view_url}" target="_blank"').tooltip(
                            "새 탭에서 고화질 뷰어로 보기 (다운로드 방지 및 줌 확대 지원)"
                        )

                        # PC 탐색기 열기 (해당 파일 하이라이트 선택)
                        def handle_open_folder():
                            open_in_explorer(curr["path"])
                            try:
                                ui.notify(f"🖥️ PC 파일 탐색기를 열었습니다: {curr['path'].name}", type="positive")
                            except Exception:
                                pass

                        ui.button("PC 폴더 열기", icon="folder", on_click=handle_open_folder).props(
                            "flat dense size=sm color=slate-300"
                        ).tooltip("호스트 PC 파일 탐색기에서 해당 파일 위치 열기")
                        ui.button(icon="close", on_click=dialog.close).props("flat round dense color=slate-300")

            def refresh_img():
                img_box.clear()
                with img_box:
                    ui.html(
                        f'<div style="display: flex; justify-content: center; align-items: center; width: 100%; min-height: 400px;">'
                        f'<img src="{curr["url"]}" alt="{curr["path"].name}" style="max-height: 80vh; max-width: 100%; width: auto; height: auto; object-fit: contain; border-radius: 12px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); display: block;" />'
                        f'</div>'
                    )

            refresh_header()
            refresh_img()

        dialog.open()

    # 초기화: 진입 시 아무 캐릭터도 미리 올라가지 않은 깨끗한 빈 상태로 시작
    state["selected_chars"] = []
    state["single_char"] = ""

    update_control_bars()
    render_content()
