"""
plepa_gui.app
플에파(PLEPA) NiceGUI 웹 인터페이스 메인 진입점.
로컬 호스트(127.0.0.1:8080)에 바인딩되어 동작합니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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

from nicegui import app, ui
from plepa_gui.pages.backgrounds import render_backgrounds_page
from plepa_gui.pages.characters import render_characters_page
from plepa_gui.pages.gallery import render_gallery_page
from plepa_gui.pages.generate import render_generate_page
from plepa_gui.pages.pose_sets import render_pose_sets_page
from plepa_gui.pages.poses import render_poses_page
from plepa_gui.pages.settings import render_settings_page


def setup_routes():
    """페이지 라우트 등록."""
    @ui.page("/")
    def index():
        ui.dark_mode().enable()
        render_characters_page()

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
        with ui.column().classes("w-full min-h-screen items-center justify-center p-2 gap-2"):
            if name:
                ui.label(name).classes("text-xs text-slate-400 font-mono")
            ui.html(f'<img src="{src}" alt="{name}" class="img-stage" onclick="toggleZoom(this)" title="클릭하여 확대/축소 토글" />')


setup_routes()


def start_server(host: str = "127.0.0.1", port: int = 8080, reload: bool = False):
    """NiceGUI 서버 기동."""
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
    parser.add_argument("--host", default="127.0.0.1", help="바인딩 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="포트 번호 (기본: 8080)")
    parser.add_argument("--reload", action="store_true", help="자동 리로드 활성화")
    args = parser.parse_args()

    start_server(host=args.host, port=args.port, reload=args.reload)
