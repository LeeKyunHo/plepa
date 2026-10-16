"""
plepa_gui.pages.settings
플에파 전역 환경 설정(ComfyUI, SDXL, FLUX, 해상도, 스텝, 업스케일러 등) 편집 및 저장 페이지.
"""

from __future__ import annotations

from nicegui import ui
from plepa_engine.comfy_client import ComfyClient
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

    # ComfyUI 실시간 모델 목록 조회 (체크포인트, GGUF UNet, 업스케일러 등)
    comfy_client = ComfyClient(host=config.get("comfy_host", "127.0.0.1:8188"))
    discovered_models = comfy_client.get_available_models()

    def get_select_options(discovered: list, current_val: str) -> list:
        opts = list(discovered)
        if current_val and current_val not in opts:
            opts.insert(0, current_val)
        return opts

    # 폼 상태 바인딩
    form = dict(config)

    ckpt_options = get_select_options(discovered_models.get("checkpoints", []), form.get("sdxl_ckpt", "unholyDesireMixSinister_v90.safetensors"))
    upscaler_options = get_select_options(discovered_models.get("upscalers", []), form.get("upscaler", "4x-UltraSharp.pth"))

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
                    options=["sdxl"],
                    value="sdxl",
                    label="기본 생성 엔진 (SDXL 단일화)",
                    on_change=lambda e: form.update({"default_engine": "sdxl"})
                ).props("outlined dark dense options-dense").classes("w-48")

                ui.select(
                    options=available_rosters,
                    value=form.get("default_roster", "campus"),
                    label="기본 로스터",
                    on_change=lambda e: form.update({"default_roster": e.value})
                ).props("outlined dark dense options-dense").classes("w-40")

            # 2. SDXL 엔진 파라미터 (Unholy Mix / WAI 등)
            with ui.row().classes("w-full items-center justify-between mt-4 mb-2"):
                with ui.row().classes("items-center gap-2"):
                    ui.label("🏷️ SDXL 엔진 파라미터").classes("text-sm font-bold text-emerald-400")
                    ui.label("(플에파 단일 공식 엔진)").classes("text-xs text-slate-400")
                if discovered_models.get("checkpoints"):
                    ui.label(f"✓ ComfyUI 체크포인트 {len(discovered_models['checkpoints'])}종 감지됨").classes("text-xs text-emerald-400/80")
                else:
                    ui.label("⚠️ ComfyUI 미가동 (직접 입력 가능)").classes("text-xs text-amber-400/80")

            # 빠른 체크포인트 프로필 프리셋 바
            with ui.row().classes("w-full items-center gap-2 p-2 bg-emerald-950/30 border border-emerald-700/40 rounded-lg mb-3"):
                ui.label("⚡ 원클릭 프로필 프리셋:").classes("text-xs font-bold text-emerald-300 mr-1")

                def apply_unholy():
                    form.update({
                        "sdxl_ckpt": "unholyDesireMixSinister_v90.safetensors",
                        "sdxl_width": 832,
                        "sdxl_height": 1216,
                        "sdxl_steps": 30,
                        "sdxl_cfg": 5.0,
                        "sdxl_sampler": "dpmpp_2m",
                        "sdxl_scheduler": "karras",
                    })
                    ui.notify("🔥 Unholy Desire v9.0 프로필 적용 완료 (832x1216, CFG 5.0, 30스텝)", type="positive")
                    ui.navigate.reload()

                def apply_wai():
                    form.update({
                        "sdxl_ckpt": "waiIllustriousSDXL_v160.safetensors",
                        "sdxl_width": 896,
                        "sdxl_height": 1152,
                        "sdxl_steps": 28,
                        "sdxl_cfg": 6.0,
                        "sdxl_sampler": "euler_ancestral",
                        "sdxl_scheduler": "normal",
                    })
                    ui.notify("✨ WAI-Illustrious v16 프로필 적용 완료 (896x1152, CFG 6.0, 28스텝)", type="positive")
                    ui.navigate.reload()

                ui.button("🔥 Unholy Desire v9.0 (기본)", icon="bolt", on_click=apply_unholy).props(
                    "unelevated dense size=xs color=emerald-600 text-white font-bold"
                ).tooltip("832x1216 | 30스텝 | CFG 5.0 | dpmpp_2m karras")
                ui.button("✨ WAI-Illustrious v16", icon="auto_awesome", on_click=apply_wai).props(
                    "unelevated dense size=xs color=indigo-600 text-white font-bold"
                ).tooltip("896x1152 | 28스텝 | CFG 6.0 | euler_ancestral normal")

            with ui.column().classes("w-full gap-3 p-4 bg-slate-800/40 rounded-xl border border-slate-700/50 mb-4"):
                if ckpt_options:
                    ui.select(
                        options=ckpt_options,
                        value=form.get("sdxl_ckpt", "unholyDesireMixSinister_v90.safetensors"),
                        label="SDXL 체크포인트 모델 선택 (models/checkpoints)",
                        on_change=lambda e: form.update({"sdxl_ckpt": e.value})
                    ).props("outlined dark dense options-dense use-input new-value-mode=add-unique").classes("w-full").tooltip("드롭다운에서 선택하거나 직접 입력할 수 있습니다.")
                else:
                    ui.input(
                        "SDXL 체크포인트 모델명 (확장자 포함)",
                        value=form.get("sdxl_ckpt", "unholyDesireMixSinister_v90.safetensors"),
                        on_change=lambda e: form.update({"sdxl_ckpt": e.value})
                    ).props("outlined dark dense").classes("w-full")

                with ui.row().classes("w-full gap-4"):
                    ui.number("기본 가로 해상도 (width)", value=form.get("sdxl_width", 832), on_change=lambda e: form.update({"sdxl_width": int(e.value) if e.value is not None else 832})).props("outlined dark dense").classes("w-1/4")
                    ui.number("기본 세로 해상도 (height)", value=form.get("sdxl_height", 1216), on_change=lambda e: form.update({"sdxl_height": int(e.value) if e.value is not None else 1216})).props("outlined dark dense").classes("w-1/4")
                    ui.number("샘플링 스텝 수 (steps)", value=form.get("sdxl_steps", 30), on_change=lambda e: form.update({"sdxl_steps": int(e.value) if e.value is not None else 30})).props("outlined dark dense").classes("w-1/4")
                    ui.number("CFG 스케일 (cfg)", value=form.get("sdxl_cfg", 5.0), step=0.1, on_change=lambda e: form.update({"sdxl_cfg": float(e.value) if e.value is not None else 5.0})).props("outlined dark dense").classes("w-1/4")

                with ui.row().classes("w-full gap-4"):
                    ui.input("샘플러 (sampler)", value=form.get("sdxl_sampler", "dpmpp_2m"), on_change=lambda e: form.update({"sdxl_sampler": e.value})).props("outlined dark dense").classes("w-1/2")
                    ui.input("스케줄러 (scheduler)", value=form.get("sdxl_scheduler", "karras"), on_change=lambda e: form.update({"sdxl_scheduler": e.value})).props("outlined dark dense").classes("w-1/2")

            # 4. 보정 및 업스케일러
            ui.label("✨ AI 보정 및 업스케일러").classes("text-sm font-bold text-indigo-400 mt-4 mb-2")
            with ui.row().classes("w-full gap-4 mb-4"):
                if upscaler_options:
                    ui.select(
                        options=upscaler_options,
                        value=form.get("upscaler", "4x-UltraSharp.pth"),
                        label="4x 업스케일러 모델 선택 (models/upscale_models)",
                        on_change=lambda e: form.update({"upscaler": e.value})
                    ).props("outlined dark dense options-dense use-input new-value-mode=add-unique").classes("w-full")
                else:
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
