"""
plepa_gui.pages.settings
플에파 전역 환경 설정(ComfyUI, SDXL, FLUX, 해상도, 스텝, 업스케일러 등) 편집 및 저장 페이지.
"""

from __future__ import annotations

from nicegui import ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.config_service import DEFAULT_CONFIG, default_config_service
from plepa_gui.components.header import render_header


def render_settings_page() -> None:
    """환경 설정 페이지 렌더링."""
    render_header("/settings")

    config = default_config_service.get_config()

    available_rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    if not available_rosters:
        available_rosters = ["don", "default"]

    # 폼 상태 바인딩
    form = dict(config)

    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-6"):
        with ui.card().classes("w-full bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg"):
            # 상단 헤더
            with ui.row().classes("w-full justify-between items-center mb-6 pb-4 border-b border-slate-800"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("settings", size="28px").classes("text-amber-400")
                    with ui.column().classes("gap-0"):
                        ui.label("⚙️ 환경 설정 (Configuration)").classes("text-xl font-bold text-slate-100")
                        ui.label("ComfyUI 연동 주소, 기본 체크포인트, 해상도 및 샘플링 파라미터를 수정합니다.").classes("text-xs text-slate-400")

                with ui.row().classes("items-center gap-2"):
                    ui.button("기본값 복원", icon="restart_alt", on_click=lambda: reset_to_defaults()).props(
                        "outline color=slate-400 dense size=sm"
                    )
                    ui.button("설정 저장", icon="save", on_click=lambda: save_settings()).props(
                        "unelevated color=amber-500 text-color=slate-950 font-bold px-5"
                    )

            # 1. 기본 런타임 설정
            ui.label("🌐 시스템 및 ComfyUI 기본 연결").classes("text-sm font-bold text-amber-400 mb-2")
            with ui.row().classes("w-full gap-4 mb-4"):
                ui.input("ComfyUI 호스트 주소 (기본: 127.0.0.1:8188)", value=form.get("comfy_host", "127.0.0.1:8188"), on_change=lambda e: form.update({"comfy_host": e.value})).props(
                    "outlined dark dense"
                ).classes("flex-1")

                ui.select(
                    options=["sdxl", "flux"],
                    value=form.get("default_engine", "sdxl"),
                    label="기본 생성 엔진",
                    on_change=lambda e: form.update({"default_engine": e.value})
                ).props("outlined dark dense options-dense").classes("w-40")

                ui.select(
                    options=available_rosters,
                    value=form.get("default_roster", "don"),
                    label="기본 로스터",
                    on_change=lambda e: form.update({"default_roster": e.value})
                ).props("outlined dark dense options-dense").classes("w-40")

            # 2. SDXL 엔진 파라미터 (Unholy Mix 등)
            ui.label("🏷️ SDXL 엔진 파라미터").classes("text-sm font-bold text-emerald-400 mt-4 mb-2")
            with ui.column().classes("w-full gap-3 p-4 bg-slate-800/40 rounded-xl border border-slate-700/50 mb-4"):
                ui.input(
                    "SDXL 체크포인트 모델명 (확장자 포함)",
                    value=form.get("sdxl_ckpt", "unholyDesireMixSinister_v90.safetensors"),
                    on_change=lambda e: form.update({"sdxl_ckpt": e.value})
                ).props("outlined dark dense").classes("w-full")

                with ui.row().classes("w-full gap-4"):
                    ui.number("기본 가로 해상도 (width)", value=form.get("sdxl_width", 832), on_change=lambda e: form.update({"sdxl_width": int(e.value) if e.value is not None else 832})).props("outlined dark dense").classes("w-1/4")
                    ui.number("기본 세로 해상도 (height)", value=form.get("sdxl_height", 1216), on_change=lambda e: form.update({"sdxl_height": int(e.value) if e.value is not None else 1216})).props("outlined dark dense").classes("w-1/4")
                    ui.number("샘플링 스텝 수 (steps)", value=form.get("sdxl_steps", 28), on_change=lambda e: form.update({"sdxl_steps": int(e.value) if e.value is not None else 28})).props("outlined dark dense").classes("w-1/4")
                    ui.number("CFG 스케일 (cfg)", value=form.get("sdxl_cfg", 6.5), step=0.1, on_change=lambda e: form.update({"sdxl_cfg": float(e.value) if e.value is not None else 6.5})).props("outlined dark dense").classes("w-1/4")

                with ui.row().classes("w-full gap-4"):
                    ui.input("샘플러 (sampler)", value=form.get("sdxl_sampler", "dpmpp_sde"), on_change=lambda e: form.update({"sdxl_sampler": e.value})).props("outlined dark dense").classes("w-1/2")
                    ui.input("스케줄러 (scheduler)", value=form.get("sdxl_scheduler", "karras"), on_change=lambda e: form.update({"sdxl_scheduler": e.value})).props("outlined dark dense").classes("w-1/2")

            # 3. FLUX 엔진 파라미터 (GGUF Q6_K 등)
            ui.label("📝 FLUX.1 [dev] GGUF 파라미터").classes("text-sm font-bold text-amber-400 mt-4 mb-2")
            with ui.column().classes("w-full gap-3 p-4 bg-slate-800/40 rounded-xl border border-slate-700/50 mb-4"):
                ui.input(
                    "FLUX GGUF UNet 파일명",
                    value=form.get("flux_unet", "flux1-dev-Q6_K.gguf"),
                    on_change=lambda e: form.update({"flux_unet": e.value})
                ).props("outlined dark dense").classes("w-full")

                with ui.row().classes("w-full gap-4"):
                    ui.number("FLUX 가로 해상도", value=form.get("flux_width", 896), on_change=lambda e: form.update({"flux_width": int(e.value) if e.value is not None else 896})).props("outlined dark dense").classes("w-1/4")
                    ui.number("FLUX 세로 해상도", value=form.get("flux_height", 1152), on_change=lambda e: form.update({"flux_height": int(e.value) if e.value is not None else 1152})).props("outlined dark dense").classes("w-1/4")
                    ui.number("FLUX 스텝 수", value=form.get("flux_steps", 20), on_change=lambda e: form.update({"flux_steps": int(e.value) if e.value is not None else 20})).props("outlined dark dense").classes("w-1/4")
                    ui.number("Guidance 스케일", value=form.get("flux_guidance", 3.5), step=0.1, on_change=lambda e: form.update({"flux_guidance": float(e.value) if e.value is not None else 3.5})).props("outlined dark dense").classes("w-1/4")

                with ui.row().classes("w-full gap-4"):
                    ui.input("FLUX LoRA 파일명", value=form.get("flux_lora", "modern-anime-lora.safetensors"), on_change=lambda e: form.update({"flux_lora": e.value})).props("outlined dark dense").classes("flex-1")
                    ui.number("LoRA 가중치", value=form.get("flux_lora_weight", 0.9), step=0.05, on_change=lambda e: form.update({"flux_lora_weight": float(e.value) if e.value is not None else 0.9})).props("outlined dark dense").classes("w-40")

            # 4. 보정 및 업스케일러
            ui.label("✨ AI 보정 및 업스케일러").classes("text-sm font-bold text-indigo-400 mt-4 mb-2")
            with ui.row().classes("w-full gap-4 mb-4"):
                ui.input(
                    "4x 업스케일러 모델명 (ComfyUI models/upscale_models)",
                    value=form.get("upscaler", "4x-UltraSharp.pth"),
                    on_change=lambda e: form.update({"upscaler": e.value})
                ).props("outlined dark dense").classes("w-full")

    def save_settings():
        try:
            default_config_service.save_config(form)
            ui.notify("환경 설정이 안전하게 저장되었으며 런타임에 즉시 반영되었습니다!", type="positive")
        except Exception as ex:
            ui.notify(f"저장 실패: {ex}", type="negative")

    def reset_to_defaults():
        try:
            default_config_service.save_config(DEFAULT_CONFIG)
            ui.notify("기본 설정값으로 복원되었습니다. 페이지를 새로고침합니다.", type="info")
            ui.navigate.to("/settings")
        except Exception as ex:
            ui.notify(f"초기화 실패: {ex}", type="negative")
