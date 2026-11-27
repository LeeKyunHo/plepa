"""
tests/test_wave5a_gui_refactor.py
Wave 5-A(plepa_gui 정적 에셋 분리, 대형 페이지/라우터 모듈화, AST Allowlist 0건 달성) 회귀 테스트.
"""

from __future__ import annotations

import ast
from pathlib import Path

from plepa_engine.config import ROOT_DIR
import plepa_gui.api_routes as api_routes_mod
from plepa_gui.components import retouch_editor
from plepa_gui.pages import (
    backgrounds,
    characters,
    gallery,
    generate,
    mobile_viewer,
    pose_sets,
    poses,
    settings,
)
from tests.test_contract_guards import (
    _FUNCTION_LINE_RATCHET_CAPS,
    _MODULE_LINE_RATCHET_CAPS,
)


def test_plepa_gui_ast_caps_and_no_allowlist_entries():
    """plepa_gui/ 하위 전 파이썬 파일 <= 350줄, 전 함수 <= 120줄, Allowlist 0건 및 run_batch 직접 호출 0건을 검증합니다."""
    gui_root = ROOT_DIR / "plepa_gui"
    py_files = sorted(gui_root.rglob("*.py"))
    assert len(py_files) >= 15

    over_mod = []
    over_fn = []
    direct_run_batch = []
    for path in py_files:
        src = path.read_text(encoding="utf-8")
        lines = len(src.splitlines())
        rel = path.relative_to(ROOT_DIR).as_posix()
        if lines > 350:
            over_mod.append((rel, lines))
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                if span > 120:
                    over_fn.append((rel, node.name, span))
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run_batch"
            ):
                direct_run_batch.append((rel, node.lineno))

    assert over_mod == [], f"350줄 초과 GUI 모듈 존재: {over_mod}"
    assert over_fn == [], f"120줄 초과 GUI 함수 존재: {over_fn}"
    assert direct_run_batch == [], f"GlobalJobManager 우회 run_batch 호출 발견: {direct_run_batch}"

    gui_mod_caps = [k for k in _MODULE_LINE_RATCHET_CAPS if k.startswith("plepa_gui/")]
    gui_fn_caps = [k for k, _ in _FUNCTION_LINE_RATCHET_CAPS if k.startswith("plepa_gui/")]
    assert gui_mod_caps == [], f"plepa_gui 모듈 Allowlist 잔여 항목: {gui_mod_caps}"
    assert gui_fn_caps == [], f"plepa_gui 함수 Allowlist 잔여 항목: {gui_fn_caps}"


def test_static_gui_assets_exist_and_render_cleanly(monkeypatch):
    """plepa_gui/static/ 6종 파일이 존재하고 플레이스홀더 누수나 f-string 중괄호 이스케이프 잔재가 없는지 검증합니다."""
    static_dir = ROOT_DIR / "plepa_gui" / "static"
    expected_files = (
        "retouch_editor.css",
        "retouch_editor.html",
        "retouch_editor.js",
        "mobile_viewer.css",
        "mobile_viewer.html",
        "mobile_viewer.js",
    )
    for fname in expected_files:
        fp = static_dir / fname
        assert fp.is_file(), f"정적 파일 누락: {fp}"
        assert len(fp.read_text(encoding="utf-8").strip()) > 0

    assert '<style id="plepa-retouch-css">' in retouch_editor.RETOUCH_EDITOR_CSS
    assert 'id="plepaRetouchModal"' in retouch_editor.RETOUCH_EDITOR_HTML
    rendered_script = retouch_editor.build_retouch_editor_script(
        on_saved_js="window.__SAVED__(savedPayload);",
        on_notify_js="window.__NOTIFY__(msg);",
    )
    assert "<script id=\"plepa-retouch-script\">" in rendered_script
    assert "window.__SAVED__(savedPayload);" in rendered_script
    assert "window.__NOTIFY__(msg);" in rendered_script
    for sentinel in ("__ON_SAVED_JS__", "__ON_NOTIFY_JS__", "{{", "}}"):
        assert sentinel not in rendered_script

    monkeypatch.setattr(
        mobile_viewer,
        "get_mobile_gallery_data",
        lambda roster=None: {
            "roster": roster or "campus",
            "rosters": ["campus", "oto"],
            "chars": [{"id": "aya", "name": "아야 (aya)", "short_name": "아야", "count": 1}],
            "items": [
                {
                    "char": "aya",
                    "char_name": "아야 (aya)",
                    "char_short_name": "아야",
                    "code": "000",
                    "label": "평상",
                    "filename": "aya_000_평상.webp",
                    "url": "/projects_static/campus/assets/aya/01_normal/aya_000_평상.webp",
                    "origin_url": "",
                    "rel_path": "campus/assets/aya/01_normal/aya_000_평상.webp",
                    "is_recent": True,
                    "is_new": True,
                    "mtime": 1700000000.0,
                    "qc_passed": True,
                    "qc_reason": None,
                }
            ],
            "total_missing": 0,
        },
    )
    html_doc = mobile_viewer.generate_mobile_viewer_html("campus")
    assert "<!DOCTYPE html>" in html_doc
    assert "function escapeHtml(str) {" in html_doc
    assert "function escapeHtml(str) {{" not in html_doc
    assert "aya (1)" not in html_doc
    assert "아야 (1)" in html_doc
    for leftover in (
        "__MOBILE_VIEWER_CSS__",
        "__MOBILE_VIEWER_JS__",
        "__DATA_JSON__",
        "__INITIAL_MODE__",
        "__ROSTER_OPTIONS_HTML__",
        "__CHAR_BUTTONS_HTML__",
        "__RETOUCH_EDITOR_CSS__",
        "__RETOUCH_EDITOR_HTML__",
        "__RETOUCH_SCRIPT_HTML__",
    ):
        assert leftover not in html_doc, f"미치환 템플릿 토큰 잔여: {leftover}"


def test_gui_public_facade_exports_intact():
    """분해 후에도 테스트 및 app.py가 참조하는 모든 공개 심볼과 페이지 엔트리포인트가 유지되는지 검증합니다."""
    assert api_routes_mod.api_router.prefix == "/api/assets"
    for sym in (
        "DeleteAssetRequest",
        "UndoAssetRequest",
        "RerollRequest",
        "FillMissingRequest",
        "RestoreOriginAssetRequest",
        "ReapplyCensorAssetRequest",
        "RetouchAssetRequest",
        "get_optional_mobile_token",
        "verify_optional_request_auth",
        "_validate_roster_name",
        "_resolve_safe_project_file",
    ):
        assert hasattr(api_routes_mod, sym), f"api_routes 공개 심볼 누락: {sym}"

    for mod, fn_names in (
        (gallery, ("render_gallery_page", "parse_manifest_items_map", "get_roster_gallery_pose_scope", "detect_best_default_roster")),
        (generate, ("render_generate_page",)),
        (characters, ("render_characters_page", "build_updated_character_schema")),
        (poses, ("render_poses_page", "SECTION_LABELS")),
        (pose_sets, ("render_pose_sets_page",)),
        (backgrounds, ("render_backgrounds_page",)),
        (settings, ("render_settings_page", "apply_settings_preset")),
        (mobile_viewer, ("render_mobile_viewer_page", "generate_mobile_viewer_html", "get_mobile_gallery_data", "_short_char_label")),
    ):
        for fn_name in fn_names:
            assert hasattr(mod, fn_name), f"{mod.__name__} 공개 심볼 누락: {fn_name}"
