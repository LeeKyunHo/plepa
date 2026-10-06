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

from nicegui import app, ui
from plepa_gui.pages.backgrounds import render_backgrounds_page
from plepa_gui.pages.characters import render_characters_page
from plepa_gui.pages.gallery import render_gallery_page
from plepa_gui.pages.generate import render_generate_page
from plepa_gui.pages.pose_sets import render_pose_sets_page
from plepa_gui.pages.poses import render_poses_page


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PLEPA NiceGUI Server")
    parser.add_argument("--host", default="127.0.0.1", help="바인딩 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="포트 번호 (기본: 8080)")
    parser.add_argument("--reload", action="store_true", help="자동 리로드 활성화")
    args = parser.parse_args()

    start_server(host=args.host, port=args.port, reload=args.reload)
