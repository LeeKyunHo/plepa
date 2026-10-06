"""
plepa_gui.components.header
상단 네비게이션 바 및 ComfyUI 연결 상태 모니터 컴포넌트.
"""

from __future__ import annotations

from nicegui import ui
from plepa_engine.comfy_client import ComfyClient
from plepa_engine.config import COMFY_HOST


def render_header(current_page: str = "") -> None:
    """공통 상단 네비게이션 헤더 렌더링."""
    with ui.header().classes("bg-slate-900 text-white shadow-md px-6 py-3 items-center justify-between"):
        with ui.row().classes("items-center gap-4"):
            ui.label("⚡ PLEPA").classes("text-xl font-bold tracking-wider text-amber-400 cursor-pointer").on(
                "click", lambda: ui.navigate.to("/")
            )
            ui.label("플에파 에셋 스튜디오").classes("text-sm text-slate-400 font-medium")

        # 네비게이션 버튼들
        with ui.row().classes("items-center gap-1"):
            nav_items = [
                ("캐릭터 관리", "/characters", "person"),
                ("포즈 DB", "/poses", "accessibility_new"),
                ("배경 프리셋", "/backgrounds", "wallpaper"),
                ("포즈 세트", "/pose-sets", "collections_bookmark"),
                ("배치 생성", "/generate", "auto_awesome"),
                ("갤러리", "/gallery", "photo_library"),
            ]
            for label, route, icon in nav_items:
                is_active = (current_page == route) or (route == "/characters" and current_page in ("", "/"))
                btn = ui.button(label, icon=icon, on_click=lambda r=route: ui.navigate.to(r))
                if is_active:
                    btn.props("flat color=amber-400").classes("font-semibold text-amber-300 border-b-2 border-amber-400")
                else:
                    btn.props("flat color=white").classes("hover:text-amber-200")

        # ComfyUI 연결 상태 뱃지
        with ui.row().classes("items-center gap-2"):
            client = ComfyClient(host=COMFY_HOST)
            is_connected = client.check_connection()
            status_color = "positive" if is_connected else "negative"
            status_text = "ComfyUI 연결됨" if is_connected else "ComfyUI 오프라인"
            badge = ui.badge(status_text, color=status_color).props("rounded").classes("px-3 py-1 text-xs")

            def refresh_status():
                connected = client.check_connection()
                badge.set_text("ComfyUI 연결됨" if connected else "ComfyUI 오프라인")
                badge.props(f"color={'positive' if connected else 'negative'}")
                if connected:
                    ui.notify("ComfyUI 서버와 정상 연결되었습니다.", type="positive")
                else:
                    ui.notify("ComfyUI 서버에 연결할 수 없습니다. (127.0.0.1:8188)", type="warning")

            ui.button(icon="refresh", on_click=refresh_status).props("flat round dense size=sm color=slate-400").tooltip("연결 상태 새로고침")
