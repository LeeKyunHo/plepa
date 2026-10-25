"""
plepa_gui.components.header
상단 네비게이션 바, 전역 백그라운드 배치 상태 모니터 및 ComfyUI 연결 감시 컴포넌트.
"""

from __future__ import annotations

from typing import List, Optional
from nicegui import ui, run
from plepa_engine.comfy_client import ComfyClient
from plepa_engine.config import COMFY_HOST, DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.health_service import (
    DiagnosticResult,
    default_health_service,
)
from plepa_engine.services.job_manager import global_job_manager

_ACTIVE_ROSTER = {"value": "campus"}


def get_available_rosters() -> List[str]:
    """사용 가능한 로스터 폴더 목록을 반환합니다."""
    rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    return rosters or [DEFAULT_ROSTER]


def get_active_roster() -> str:
    """현재 전역 활성 로스터를 반환합니다."""
    available = get_available_rosters()
    if _ACTIVE_ROSTER["value"] in available:
        return _ACTIVE_ROSTER["value"]
    if "campus" in available:
        _ACTIVE_ROSTER["value"] = "campus"
    elif available:
        _ACTIVE_ROSTER["value"] = available[0]
    return _ACTIVE_ROSTER["value"]


def set_active_roster(roster: str) -> None:
    """전역 활성 로스터를 설정합니다."""
    _ACTIVE_ROSTER["value"] = roster


def open_diagnostics_dialog() -> None:
    """시스템 10단계 통합 무결성 자가 진단 모달 열기."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-4xl p-6 bg-slate-900 text-slate-100 border border-slate-700"):
        with ui.row().classes("w-full justify-between items-center mb-4"):
            with ui.row().classes("items-center gap-2"):
                ui.label("🩺 시스템 10단계 통합 무결성 진단").classes("text-lg font-bold text-amber-400")
                ui.label("(Unified Diagnostics)").classes("text-xs text-slate-400")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense color=slate-400")

        container = ui.column().classes("w-full gap-3")

        def run_test():
            container.clear()
            with container:
                with ui.row().classes("items-center gap-3 py-6 justify-center w-full"):
                    ui.spinner("dots", size="lg", color="amber")
                    ui.label("시스템 10개 핵심 코어 무결성 전수 검증 중... (약 5~8초 소요)").classes("text-sm text-amber-300 font-medium")

            def worker():
                return default_health_service.run_full_diagnostics(check_comfy=True)

            async def on_complete():
                results = await run.io_bound(worker)
                container.clear()
                with container:
                    # 요약 통계 카드
                    pass_cnt = sum(1 for r in results if r.status == "PASS")
                    warn_cnt = sum(1 for r in results if r.status == "WARN")
                    fail_cnt = sum(1 for r in results if r.status == "FAIL")
                    total_ms = sum(r.duration_ms for r in results)

                    summary_bg = "bg-emerald-950/60 border-emerald-500/50" if fail_cnt == 0 else "bg-rose-950/60 border-rose-500/50"
                    with ui.card().classes(f"w-full p-4 border rounded-lg {summary_bg} text-slate-200"):
                        with ui.row().classes("w-full justify-between items-center"):
                            with ui.row().classes("items-center gap-4"):
                                if fail_cnt == 0:
                                    ui.label("✔ 정상 가동 보장").classes("text-base font-bold text-emerald-400")
                                else:
                                    ui.label("🚨 시스템 결함 발견").classes("text-base font-bold text-rose-400")
                                ui.label(f"검사 항목: 10개 중 {pass_cnt} 통과 | {warn_cnt} 주의 | {fail_cnt} 결함").classes("text-xs text-slate-300")
                            ui.label(f"총 소요: {total_ms/1000.0:.2f}초").classes("text-xs font-mono text-slate-400")

                    # 10단계 결과 리스트
                    with ui.column().classes("w-full gap-2 mt-2"):
                        for r in results:
                            badge_color = "positive" if r.status == "PASS" else ("warning" if r.status == "WARN" else "negative")
                            icon_name = "check_circle" if r.status == "PASS" else ("warning" if r.status == "WARN" else "error")

                            with ui.card().classes("w-full p-3 bg-slate-800/80 border border-slate-700/60 rounded-lg hover:border-slate-500 transition-all"):
                                with ui.row().classes("w-full justify-between items-center"):
                                    with ui.row().classes("items-center gap-3"):
                                        ui.badge(f"{r.stage_index:02d}", color="slate-700").props("rounded")
                                        ui.icon(icon_name, color=badge_color).classes("text-lg")
                                        with ui.column().classes("gap-0"):
                                            ui.label(f"{r.category} · {r.name}").classes("text-sm font-bold text-slate-200")
                                            ui.label(r.message).classes("text-xs text-slate-400")
                                    with ui.row().classes("items-center gap-3"):
                                        ui.badge(r.status, color=badge_color).props("rounded font-bold")
                                        ui.label(f"{r.duration_ms:.1f}ms").classes("text-xs font-mono text-slate-400")

                                if r.details:
                                    with ui.expansion("상세 내역 보기", icon="info").classes("w-full text-xs text-slate-400 mt-1"):
                                        for d in r.details:
                                            ui.label(f"• {d}").classes("font-mono text-slate-300 text-xs py-0.5")

            ui.timer(0.1, on_complete, once=True)

        run_test()

        with ui.row().classes("w-full justify-between items-center mt-4 pt-2 border-t border-slate-800"):
            ui.button("🔄 재진단", icon="refresh", on_click=run_test).props("outline color=amber-400 text-xs")
            ui.button("닫기", on_click=dialog.close).props("flat color=white text-xs")

    dialog.open()


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
                ("📱 모바일 뷰어", "/mobile", "smartphone"),
                ("환경 설정", "/settings", "settings"),
            ]
            for label, route, icon in nav_items:
                is_active = (current_page == route) or (route == "/gallery" and current_page in ("", "/"))
                btn = ui.button(label, icon=icon, on_click=lambda r=route: ui.navigate.to(r))
                if is_active:
                    btn.props("flat color=amber-400").classes("font-semibold text-amber-300 border-b-2 border-amber-400 text-xs py-1")
                else:
                    btn.props("flat color=white").classes("hover:text-amber-200 text-xs py-1")

        # 우측: 전역 로스터 셀렉터, 백그라운드 생성 상태 및 진단 & ComfyUI 연결 뱃지
        with ui.row().classes("items-center gap-3"):
            # 🩺 시스템 진단 버튼
            ui.button("🩺 진단", on_click=open_diagnostics_dialog).props("flat dense color=amber-400").classes(
                "text-xs font-semibold px-2 hover:bg-slate-800 rounded"
            ).tooltip("플에파 10단계 시스템 통합 무결성 자가 진단")

            # 전역 활성 로스터 셀렉터
            available_rosters = get_available_rosters()
            current_r = get_active_roster()

            def on_roster_changed(e):
                set_active_roster(e.value)
                ui.notify(f"📁 활성 로스터가 '{e.value}'(으)로 변경되었습니다.", type="info")
                ui.navigate.reload()

            ui.label("📁").classes("text-sm text-slate-400")
            ui.select(
                options=available_rosters,
                value=current_r,
                on_change=on_roster_changed
            ).props("dense outlined dark options-dense").classes("w-28 text-xs font-bold text-amber-300").tooltip("전역 활성 로스터 선택 (페이지 공통 적용)")

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

