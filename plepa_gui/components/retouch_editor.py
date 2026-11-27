"""
plepa_gui.components.retouch_editor
PC 갤러리(/gallery)와 모바일 뷰어(/mobile)에서 공용으로 사용하는 HTML5 캔버스 수동 검열/덧칠 에디터 컴포넌트.
정적 CSS/HTML/JS 리소스(plepa_gui/static/retouch_editor.*)를 로드하여 제공합니다.
"""

from __future__ import annotations

from pathlib import Path

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _read_static(filename: str) -> str:
    return (_STATIC_DIR / filename).read_text(encoding="utf-8")


RETOUCH_EDITOR_CSS: str = f'\n<style id="plepa-retouch-css">\n{_read_static("retouch_editor.css").rstrip()}\n</style>\n'

RETOUCH_EDITOR_HTML: str = f'\n{_read_static("retouch_editor.html")}'


def build_retouch_editor_script(
    on_saved_js: str = "",
    on_notify_js: str = "console.log(msg);",
) -> str:
    """PC 갤러리 및 모바일 뷰어에서 공용으로 삽입할 수동 검열 캔버스 JS 블록을 생성합니다."""
    js_body = (
        _read_static("retouch_editor.js")
        .rstrip()
        .replace("__ON_NOTIFY_JS__", on_notify_js)
        .replace("__ON_SAVED_JS__", on_saved_js)
    )
    return f'\n<script id="plepa-retouch-script">\n{js_body}\n</script>\n'
