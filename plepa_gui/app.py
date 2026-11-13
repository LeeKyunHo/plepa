"""
plepa_gui.app
플에파(PLEPA) NiceGUI 웹 인터페이스 메인 진입점.
로컬 호스트(127.0.0.1:8080)에 바인딩되어 동작합니다.
"""

from __future__ import annotations

import argparse
import hmac
import html
import sys
from pathlib import Path
from typing import Optional

# 루트 디렉터리를 sys.path에 추가
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Windows cp949 환경에서 유니코드 출력 시 crash 방지
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import mimetypes

# 브라우저 새 탭에서 WebP 이미지가 다운로드되지 않고 정상 표시되도록 MIME 타입 등록
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from nicegui import app, ui
from plepa_engine.config import PROJECTS_DIR
from plepa_gui.api_routes import (
    api_router,
    get_optional_mobile_token,
    verify_optional_request_auth,
)
from plepa_gui.components.header import get_active_roster
from plepa_gui.pages.backgrounds import render_backgrounds_page
from plepa_gui.pages.characters import render_characters_page
from plepa_gui.pages.gallery import render_gallery_page
from plepa_gui.pages.generate import render_generate_page
from plepa_gui.pages.mobile_viewer import generate_mobile_viewer_html, render_mobile_viewer_page
from plepa_gui.pages.pose_sets import render_pose_sets_page
from plepa_gui.pages.poses import render_poses_page
from plepa_gui.pages.settings import render_settings_page


def register_optional_token_middleware(target_app) -> None:
    """PLEPA_MOBILE_TOKEN 설정 시 원격 ?token= 쿠키 발급 및 보호 미들웨어 등록."""
    if getattr(target_app.state, "_plepa_token_mw_registered", False):
        return
    target_app.state._plepa_token_mw_registered = True

    @target_app.middleware("http")
    async def _plepa_optional_token_middleware(request: Request, call_next):
        expected = get_optional_mobile_token()
        if not expected:
            return await call_next(request)

        path = request.url.path or "/"
        is_protected_path = (
            path.startswith("/api/")
            or path.startswith("/projects_static/")
            or path in {"/mobile", "/m", "/otoko", "/o", "/compare", "/c"}
        )
        if is_protected_path:
            is_mutating = path.startswith("/api/") and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
            try:
                verify_optional_request_auth(request, check_origin=is_mutating)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail, "error": exc.detail}, status_code=exc.status_code)

        response = await call_next(request)

        q_token = (request.query_params.get("token") or "").strip()
        if q_token and hmac.compare_digest(q_token, expected):
            is_https = (
                request.url.scheme == "https"
                or (request.headers.get("x-forwarded-proto") or "").lower() == "https"
            )
            response.set_cookie(
                key="plepa_token",
                value=expected,
                httponly=True,
                samesite="lax",
                secure=is_https,
                path="/",
                max_age=86400,
            )
        return response


def setup_routes():
    """페이지 라우트, 정적 리소스 마운트 및 REST API 등록."""
    register_optional_token_middleware(app)
    app.add_static_files("/projects_static", str(PROJECTS_DIR))
    app.include_router(api_router)
    @ui.page("/")
    def index():
        ui.dark_mode().enable()
        render_gallery_page()

    @ui.page("/characters")
    def page_characters():
        ui.dark_mode().enable()
        render_characters_page()

    @ui.page("/poses")
    def page_poses():
        ui.dark_mode().enable()
        render_poses_page()

    @ui.page("/backgrounds")
    def page_backgrounds():
        ui.dark_mode().enable()
        render_backgrounds_page()

    @ui.page("/pose-sets")
    def page_pose_sets():
        ui.dark_mode().enable()
        render_pose_sets_page()

    @ui.page("/generate")
    def page_generate():
        ui.dark_mode().enable()
        render_generate_page()

    @ui.page("/gallery")
    def page_gallery():
        ui.dark_mode().enable()
        render_gallery_page()

    @app.get("/mobile", response_class=HTMLResponse)
    @app.get("/m", response_class=HTMLResponse)
    def api_mobile_viewer(roster: Optional[str] = None):
        """스마트폰 전용 무경량 고속 터치 스와이프 뷰어 (Vue/Quasar 미로드, 덮어쓰기 버그 원천 차단)."""
        target_roster = roster or get_active_roster()
        return HTMLResponse(content=generate_mobile_viewer_html(target_roster))

    @app.get("/otoko")
    @app.get("/o")
    def api_otoko_benchmark():
        """오토코노코 40인 화풍 5대 H씬 벤치마크 뷰어 즉시 이동."""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/projects_static/maid/otoko_benchmark/index.html")

    @app.get("/compare")
    @app.get("/c")
    def api_compare_benchmark():
        """검열 방식 3대 모드 비교 뷰어 즉시 이동."""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/projects_static/maid/otoko_benchmark/compare.html")

    @ui.page("/settings")
    def page_settings():
        ui.dark_mode().enable()
        render_settings_page()

    @ui.page("/view_image")
    def page_view_image(src: str = "", name: str = ""):
        """새 탭 전용 무손실 이미지 뷰어 (모바일 다운로드 튕김 방지 및 줌 지원)."""
        ui.dark_mode().enable()
        ui.add_head_html("""
        <style>
            body { margin: 0; background: #07090e; display: flex; align-items: center; justify-content: center; min-height: 100vh; overflow: auto; }
            .img-stage { max-width: 96vw; max-height: 92vh; width: auto; height: auto; object-fit: contain; border-radius: 8px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.8); cursor: zoom-in; }
            .img-stage.zoomed { max-width: none; max-height: none; cursor: zoom-out; }
        </style>
        <script>
            function toggleZoom(el) { el.classList.toggle('zoomed'); }
        </script>
        """)
        safe_src = src.strip()
        is_allowed_src = safe_src.startswith("/projects_static/") and ".." not in safe_src
        with ui.column().classes("w-full min-h-screen items-center justify-center p-2 gap-2"):
            if name:
                ui.label(name).classes("text-xs text-slate-400 font-mono")
            if is_allowed_src:
                escaped_src = html.escape(safe_src, quote=True)
                escaped_name = html.escape(name, quote=True)
                ui.html(f'<img src="{escaped_src}" alt="{escaped_name}" class="img-stage" onclick="toggleZoom(this)" title="클릭하여 확대/축소 토글" />')
            else:
                ui.label("유효하지 않은 이미지 경로입니다.").classes("text-xs text-rose-400")


setup_routes()


def start_server(host: str = "0.0.0.0", port: int = 8080, reload: bool = False):
    """NiceGUI 서버 기동 (0.0.0.0 바인딩으로 동일 네트워크 모바일 접속 지원)."""
    ui.run(
        host=host,
        port=port,
        title="PLEPA - 플에파 에셋 스튜디오",
        favicon="⚡",
        dark=True,
        reload=reload,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    parser = argparse.ArgumentParser(description="PLEPA NiceGUI Server")
    parser.add_argument("--host", default="0.0.0.0", help="바인딩 호스트 (기본: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="포트 번호 (기본: 8080)")
    parser.add_argument("--reload", action="store_true", help="자동 리로드 활성화")
    args = parser.parse_args()

    start_server(host=args.host, port=args.port, reload=args.reload)
