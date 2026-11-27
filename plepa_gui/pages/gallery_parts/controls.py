"""
plepa_gui.pages.gallery_parts.controls
갤러리 뷰 모드별 필터 바 (매트릭스·단일 캐릭터·기타 에셋) 렌더링 헬퍼.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from nicegui import ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.reporter import open_in_explorer


def _render_matrix_presets(char_asset_counts: Dict[str, int], cbs: Dict[str, Callable]) -> None:
    """매트릭스 뷰 상단 빠른 캐릭터 프리셋 및 포즈 범위/정렬 컨트롤을 렌더링합니다."""
    if any(k in char_asset_counts for k in ["aa", "bb", "cc", "dd", "ee", "ff", "gg", "hh", "ii", "jj"]):
        ui.button("🏮 무협 10인 전원", icon="auto_awesome", on_click=cbs["select_murim_all_preset"]).props("unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40").tooltip("무협 아포칼립스 10인(aa~jj) 전원 선택")
        ui.button("🗡️ 정파 3인 (aa, bb, cc)", icon="shield", on_click=cbs["select_murim_orthodox_preset"]).props("unelevated dense size=xs color=cyan-500/20 text-color=cyan-300 border border-cyan-500/40").tooltip("정파 3인 (백설아, 제갈혜진, 남궁소율) 선택")

    if any(k in char_asset_counts for k in ["yua", "serin", "sia", "hayul", "ykn_1st", "ykn_2nd", "ykn_3rd", "ykn_4th"]):
        ui.button("🌸 네쌍둥이 4인 (전체 포즈)", icon="auto_awesome", on_click=cbs["select_quadruplets_preset"]).props("unelevated dense size=xs color=rose-500/20 text-color=rose-300 border border-rose-500/40").tooltip("설유아, 설세린, 설시아, 설하율 4인의 전체 포즈 비교")

    if any(k in char_asset_counts for k in ["ykn_brd_a", "ykn_brd_b", "ykn_brd_c"]):
        ui.button("🎀 땋은머리 샘플 3종", icon="face", on_click=cbs["select_ykn_braid_preset"]).props("unelevated dense size=xs color=purple-500/20 text-color=purple-300 border border-purple-500/40").tooltip("ykn_brd_a, ykn_brd_b, ykn_brd_c (000 평상) 선택")

    if any(k in char_asset_counts for k in ["ykn_sle", "ykn_std", "ykn_mat"]):
        ui.button("👑 유키노 체형 6종 세트", icon="group", on_click=cbs["select_ykn_preset"]).props("unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40").tooltip("ykn_sle, ykn_std, ykn_mat, ykn_crv, ykn_gla, ykn_gla_up 일괄 선택")

    if any(k in char_asset_counts for k in ["ykn_bun", "ykn_nur", "ykn_mai"]):
        ui.button("👗 유키노 의상 6종 세트", icon="checkroom", on_click=cbs["select_ykn_outfit_preset"]).props("unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40").tooltip("ykn_bun, ykn_nur, ykn_mai, ykn_swm, ykn_qip, ykn_gya 일괄 선택")


def render_matrix_controls(
    matrix_controls: Any,
    state: Dict[str, Any],
    roster_scope: Dict[str, Any],
    cbs: Dict[str, Callable],
) -> None:
    """매트릭스 뷰 전용 필터 바를 렌더링합니다."""
    char_asset_counts = roster_scope["char_counts"]
    set_opts = roster_scope["set_options"]

    with matrix_controls:
        with ui.row().classes("items-center gap-2 flex-wrap"):
            ui.label("빠른 캐릭터 프리셋:").classes("text-xs font-semibold text-slate-400 mr-1")
            _render_matrix_presets(char_asset_counts, cbs)
            ui.button("📷 이미지 있는 캐릭터만 선택", icon="filter_alt", on_click=cbs["select_has_assets"]).props("flat dense size=xs color=emerald-400")
            ui.button("전체 선택", icon="done_all", on_click=lambda: cbs["select_all_chars"](True)).props("flat dense size=xs color=slate-400")
            ui.button("선택 해제", icon="remove_done", on_click=lambda: cbs["select_all_chars"](False)).props("flat dense size=xs color=slate-500")

            ui.label("포즈 범위:").classes("text-xs text-slate-400 font-semibold ml-4")
            ui.select(options=set_opts, value=state["pose_set"], on_change=lambda e: cbs["on_set_changed"](e.value)).props("dense outlined dark options-dense").classes("w-56 text-xs")

            ui.label("정렬:").classes("text-xs text-slate-400 font-semibold ml-2")
            ui.toggle(
                {"code_asc": "🔢 포즈 번호순", "mtime_desc": "🕒 최근 생성순 (NEW 먼저)"},
                value=state.get("matrix_sort", "code_asc"),
                on_change=lambda e: (state.update({"matrix_sort": e.value}), cbs["render_content"]()),
            ).props("dense dark").classes("text-xs")

        with ui.row().classes("items-center gap-2 flex-wrap mt-1"):
            ui.label("대상 캐릭터:").classes("text-xs font-semibold text-slate-400 mr-1")
            for prefix, cnt in char_asset_counts.items():
                is_selected = prefix in state["selected_chars"]
                chip_label = f"{prefix} ({cnt}장)" if cnt > 0 else f"{prefix} (0)"
                color_props = "color=amber-600 text-color=white" if is_selected else "color=slate-800 text-color=slate-300"
                ui.chip(chip_label, selectable=True, selected=is_selected, on_selection_change=lambda e, p=prefix: cbs["toggle_char"](p, e.value)).props(f"dense text-xs {color_props}")


def render_single_controls(
    single_controls: Any,
    state: Dict[str, Any],
    char_asset_counts: Dict[str, int],
    render_content_cb: Callable[[], None],
) -> None:
    """단일 캐릭터 전체 갤러리 필터 바를 렌더링합니다."""
    with single_controls:
        with ui.row().classes("items-center gap-4 flex-wrap"):
            ui.label("캐릭터 선택:").classes("text-xs text-slate-400 font-semibold")
            char_opts = {p: f"{p} ({cnt}장)" for p, cnt in char_asset_counts.items() if cnt > 0}
            if not char_opts:
                char_opts = {p: f"{p} (0장)" for p in char_asset_counts.keys()}

            ui.select(
                options=char_opts,
                value=state["single_char"] if state["single_char"] in char_opts else None,
                on_change=lambda e: (state.update({"single_char": e.value}), render_content_cb()),
            ).props("dense outlined dark options-dense").classes("w-60 text-sm")

            ui.label("정렬:").classes("text-xs text-slate-400 font-semibold ml-2")
            ui.toggle(
                {"mtime_desc": "🕒 최신 생성순 (NEW 먼저)", "code_asc": "🔢 포즈 번호순"},
                value=state.get("single_sort", "mtime_desc"),
                on_change=lambda e: (state.update({"single_sort": e.value}), render_content_cb()),
            ).props("dense dark").classes("text-xs")


def render_misc_controls(
    misc_controls: Any,
    state: Dict[str, Any],
    rebuild_cb: Callable[[], None],
) -> None:
    """기타/비포즈 에셋 필터 바를 렌더링합니다."""
    with misc_controls:
        with ui.row().classes("items-center justify-between w-full flex-wrap gap-3"):
            with ui.row().classes("items-center gap-2 flex-wrap"):
                ui.label("카테고리 필터:").classes("text-xs font-semibold text-slate-400 mr-1")
                filter_opts = {"all": "전체 보기", "reference": "레퍼런스 이미지", "background": "배경 (BG)", "sample": "비규격/샘플"}
                for f_key, f_label in filter_opts.items():
                    is_active = state.get("misc_filter", "all") == f_key
                    color = "color=purple-600 text-color=white" if is_active else "color=slate-800 text-color=slate-300"
                    ui.chip(
                        f_label, selectable=True, selected=is_active,
                        on_selection_change=lambda e, k=f_key: (state.update({"misc_filter": k}), rebuild_cb()) if e.value else None,
                    ).props(f"dense text-xs {color}")

            with ui.row().classes("items-center gap-2"):
                ref_dir = PROJECTS_DIR / state["roster"] / "references"
                ui.button("레퍼런스 폴더 열기", icon="folder", on_click=lambda: open_in_explorer(ref_dir)).props("flat dense size=xs color=purple-300")
