"""
plepa_gui.components.prompt_inspector
최종 프롬프트 조립 결과, 탈의 판정 및 린터 경고 실시간 검사기 컴포넌트.
"""

from __future__ import annotations

from nicegui import ui
from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import assemble_flux_prompt, assemble_sdxl_prompt
from plepa_engine.services.background_service import default_background_service


def open_prompt_inspector_dialog(char_config: CharacterConfig, pose_entry: PoseEntry, bg_prompt: str = "") -> None:
    """프롬프트 인스펙터 모달 다이얼로그 열기."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-4xl p-6 bg-slate-900 text-slate-100 border border-slate-700"):
        with ui.row().classes("w-full justify-between items-center mb-4"):
            with ui.column().classes("gap-0"):
                ui.label(f"🔍 프롬프트 인스펙터: {char_config.name} ({char_config.prefix}) x #{pose_entry.code} {pose_entry.label}").classes("text-lg font-bold text-amber-400")
                ui.label(f"섹션: {pose_entry.section} | 설명: {pose_entry.description}").classes("text-xs text-slate-400")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense color=slate-400")

        # 조립 실행
        sdxl_pos, sdxl_neg, sdxl_nude = assemble_sdxl_prompt(char_config, pose_entry, bg_prompt=bg_prompt)
        flux_pos, flux_nude = assemble_flux_prompt(char_config, pose_entry, bg_prompt=bg_prompt)

        # 린터 경고 수집
        warnings = []
        if bg_prompt:
            warnings.extend(default_background_service.lint_prompt(bg_prompt))
        if "break" in flux_pos.lower():
            warnings.append("[FLUX] 서술형 프롬프트에 금지된 BREAK 문법이 포함되어 있습니다.")

        with ui.tabs().classes("w-full text-amber-400") as tabs:
            tab_sdxl = ui.tab("SDXL (Unholy Mix)")
            tab_flux = ui.tab("FLUX.1 [dev] (GGUF)")

        with ui.tab_panels(tabs, value=tab_sdxl).classes("w-full bg-slate-800 text-slate-200 p-4 rounded-lg mt-2"):
            # SDXL 패널
            with ui.tab_panel(tab_sdxl):
                with ui.row().classes("items-center gap-4 mb-2"):
                    ui.badge(f"탈의 판정: {'나체 (Nude)' if sdxl_nude else '착의 (Clothed)'}", color="negative" if sdxl_nude else "info").props("rounded")
                    ui.label(f"Positive: {len(sdxl_pos)}자 | Negative: {len(sdxl_neg)}자").classes("text-xs text-slate-400")

                ui.label("Positive Prompt (Danbooru 태그 + BREAK 구조):").classes("text-xs font-semibold text-emerald-400 mt-2")
                ui.textarea(value=sdxl_pos).props("readonly outlined autogrow rows=4").classes("w-full bg-slate-900 font-mono text-xs text-slate-200")

                ui.label("Negative Prompt:").classes("text-xs font-semibold text-rose-400 mt-2")
                ui.textarea(value=sdxl_neg).props("readonly outlined autogrow rows=3").classes("w-full bg-slate-900 font-mono text-xs text-slate-200")

            # FLUX 패널
            with ui.tab_panel(tab_flux):
                with ui.row().classes("items-center gap-4 mb-2"):
                    ui.badge(f"탈의 판정: {'나체 (Nude)' if flux_nude else '착의 (Clothed)'}", color="negative" if flux_nude else "info").props("rounded")
                    ui.label(f"Prompt 길이: {len(flux_pos)}자").classes("text-xs text-slate-400")

                ui.label("FLUX Prompt (T5-XXL 서술형 자연어):").classes("text-xs font-semibold text-amber-400 mt-2")
                ui.textarea(value=flux_pos).props("readonly outlined autogrow rows=6").classes("w-full bg-slate-900 font-mono text-xs text-slate-200")

        if warnings:
            with ui.column().classes("w-full mt-3 p-3 bg-amber-950 border border-amber-600 rounded"):
                ui.label("⚠️ 프롬프트 린터 경고").classes("text-xs font-bold text-amber-400")
                for w in warnings:
                    ui.label(f"• {w}").classes("text-xs text-amber-200")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("닫기", on_click=dialog.close).props("flat color=white")

    dialog.open()
