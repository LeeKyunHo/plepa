"""
plepa_gui.components.header
상단 네비게이션 바, 전역 백그라운드 배치 상태 모니터 및 ComfyUI 연결 감시 컴포넌트.
"""

from __future__ import annotations

from nicegui import ui
from plepa_engine.comfy_client import ComfyClient
from plepa_engine.config import COMFY_HOST
from plepa_engine.services.job_manager import global_job_manager


def render_header(current_page: str = "") -> None:
    """공통 상단 네비게이션 헤더 렌더링."""
    with ui.header().classes("bg-slate-900 text-white shadow-md px-6 py-2.5 items-center justify-between sticky top-0 z-50"):
        with ui.row().classes("items-center gap-4"):
            ui.label("⚡ PLEPA").classes("text-xl font-bold tracking-wider text-amber-400 cursor-pointer").on(
                "click", lambda: ui.navigate.to("/")
            )
            ui.label("플에파 스튜디오").classes("text-xs text-slate-400 font-medium")

        # 네비게이션 버튼들
        with ui.row().classes("items-center gap-1"):
            nav_items = [
                ("캐릭터 관리", "/characters", "person"),
                ("포즈 DB", "/poses", "accessibility_new"),
                ("배경 프리셋", "/backgrounds", "wallpaper"),
                ("포즈 세트", "/pose-sets", "collections_bookmark"),
                ("배치 생성", "/generate", "auto_awesome"),
                ("갤러리", "/gallery", "photo_library"),
                ("환경 설정", "/settings", "settings"),
            ]
            for label, route, icon in nav_items:
                is_active = (current_page == route) or (route == "/characters" and current_page in ("", "/"))
                btn = ui.button(label, icon=icon, on_click=lambda r=route: ui.navigate.to(r))
                if is_active:
                    btn.props("flat color=amber-400").classes("font-semibold text-amber-300 border-b-2 border-amber-400 text-xs py-1")
                else:
                    btn.props("flat color=white").classes("hover:text-amber-200 text-xs py-1")

        # 우측: 전역 백그라운드 생성 상태 및 ComfyUI 연결 뱃지
        with ui.row().classes("items-center gap-3"):
            # 전역 작업 진행 뱃지
            job_badge = ui.badge("", color="amber-600").props("rounded").classes("px-3 py-1 text-xs cursor-pointer").on(
                "click", lambda: ui.navigate.to("/generate")
            )
            job_badge.set_visibility(False)

            def update_job_status():
                status = global_job_manager.get_status()
                if status["is_running"]:
                    pct = int(status["percentage"] * 100)
                    job_badge.set_text(f"⚡ 생성 진행 중: {status['current']}/{status['total']} ({pct}%)")
                    job_badge.props("color=amber-500 text-color=slate-950 font-bold")
                    job_badge.set_visibility(True)
                else:
                    job_badge.set_visibility(False)

            ui.timer(1.0, update_job_status)

            # ComfyUI 연결 상태 뱃지
            client = ComfyClient(host=COMFY_HOST)
            is_connected = client.check_connection()
            status_color = "positive" if is_connected else "negative"
            status_text = "ComfyUI 연결됨" if is_connected else "ComfyUI 오프라인"
            comfy_badge = ui.badge(status_text, color=status_color).props("rounded").classes("px-2.5 py-1 text-xs")

            def refresh_status():
                connected = client.check_connection()
                comfy_badge.set_text("ComfyUI 연결됨" if connected else "ComfyUI 오프라인")
                comfy_badge.props(f"color={'positive' if connected else 'negative'}")
                if connected:
                    ui.notify("ComfyUI 서버와 정상 연결되었습니다.", type="positive")
                else:
                    ui.notify("ComfyUI 서버에 연결할 수 없습니다. (127.0.0.1:8188)", type="warning")

            ui.button(icon="refresh", on_click=refresh_status).props("flat round dense size=sm color=slate-400").tooltip("ComfyUI 연결 새로고침")
