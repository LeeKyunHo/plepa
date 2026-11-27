"""
tests/test_wave5b_scripts_cleanup.py
Wave 5-B(scripts/ 3단 계층 정리, 운영 CLI 3종 슬림화, 전체 활성 코드 AST Allowlist 0건 달성) 검증.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import plepa_engine.config as cfg
from scripts.context_exporter.ast_extract import ast_telemetry, collect_active_modules, count_quarantined_scripts
from scripts.context_exporter.report_builders import build_refactoring_plan
from tests.test_contract_guards import (
    _FUNCTION_LINE_RATCHET_CAPS,
    _GUI_DIRECT_RUN_BATCH_ALLOWLIST,
    _MODULE_LINE_RATCHET_CAPS,
    _REVERSE_LAYER_ALLOWLIST,
    _iter_active_python_files,
)


def test_entire_active_codebase_ast_caps_and_zero_allowlists():
    """전체 활성 코드베이스(batch_generator, plepa_engine, plepa_gui, 활성 scripts) 전 파일 <=350L · 전 함수 <=120L 및 Allowlist 0건을 검증합니다."""
    assert _MODULE_LINE_RATCHET_CAPS == {}
    assert _FUNCTION_LINE_RATCHET_CAPS == {}
    assert _REVERSE_LAYER_ALLOWLIST == set()
    assert _GUI_DIRECT_RUN_BATCH_ALLOWLIST == set()

    active_files = list(_iter_active_python_files())
    assert len(active_files) >= 100

    over_mod, over_fn = [], []
    for p in active_files:
        rel = p.relative_to(cfg.ROOT_DIR).as_posix()
        src = p.read_text(encoding="utf-8-sig")
        lc = len(src.splitlines())
        if lc > 350:
            over_mod.append((rel, lc))
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno is not None:
                span = node.end_lineno - node.lineno + 1
                if span > 120:
                    over_fn.append((rel, node.name, span))

    assert over_mod == [], f"350줄 초과 활성 모듈 존재: {over_mod}"
    assert over_fn == [], f"120줄 초과 활성 함수 존재: {over_fn}"


def test_operational_cli_scripts_compatibility_and_kiro_guard():
    """핵심 운영 CLI 3종 공개 심볼/CLI 및 scripts/README.md, sync_to_kiro 기본 차단 가드를 검증합니다."""
    assert (cfg.ROOT_DIR / "scripts" / "README.md").is_file()

    import scripts.audit_asset_alignment as aaa
    import scripts.audit_sector_assets as asa
    import scripts.validate_genit_work as vgw

    for sym in ("load_full_pose_catalog", "audit_character_alignment", "normalize_label_for_comparison", "main"):
        assert callable(getattr(aaa, sym, None)), f"audit_asset_alignment 누락: {sym}"
    assert callable(getattr(asa, "audit_character", None))
    assert callable(getattr(asa, "main", None))
    for sym in ("run_all_validations", "validate_document", "parse_frontmatter"):
        assert callable(getattr(vgw, sym, None)), f"validate_genit_work 누락: {sym}"

    res_kiro = subprocess.run(
        [sys.executable, str(cfg.ROOT_DIR / "scripts" / "sync_to_kiro.py"), "--dry-run"],
        cwd=str(cfg.ROOT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    assert res_kiro.returncode == 2


def test_moved_scripts_hierarchy_root_depth_and_deprecation_markers():
    """scripts/{ml,benchmarks,archive}/ 이동 스크립트의 루트 경로 깊이, cross-import 및 구 :8085 폐기 주석을 검증합니다."""
    ml_mod = importlib.import_module("scripts.ml.benchmark_censor_metrics")
    assert ml_mod.ROOT.resolve() == cfg.ROOT_DIR.resolve()

    bench_mod = importlib.import_module("scripts.benchmarks.run_artist_benchmark_v2")
    assert (cfg.ROOT_DIR / "scripts" / "benchmarks" / "evaluate_h1_pilot.py").is_file()
    assert callable(getattr(bench_mod, "generate_html_viewer_v2", None))

    for arch_name in ("generate_inspection_viewer", "serve_benchmark_mobile", "mobile_gallery"):
        p = cfg.ROOT_DIR / "scripts" / "archive" / f"{arch_name}.py"
        assert p.is_file()
        head_txt = "\n".join(p.read_text(encoding="utf-8").splitlines()[:10])
        assert "plepa_gui/pages/mobile_viewer.py" in head_txt
        assert "scripts/start_remote.py" in head_txt
        mod = importlib.import_module(f"scripts.archive.{arch_name}")
        assert mod.ROOT.resolve() == cfg.ROOT_DIR.resolve()


def test_plepa_guard_and_context_exporter_wave5b_telemetry():
    """plepa_guard.py의 scripts/archive·benchmarks 읽기 차단 및 context_exporter AST 0건 대시보드를 검증합니다."""
    guard_path = cfg.ROOT_DIR / ".agents" / "hooks" / "plepa_guard.py"
    spec = importlib.util.spec_from_file_location("plepa_guard_w5b", str(guard_path))
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)

    assert guard.evaluate_hook({"toolCall": {"name": "read_file", "args": {"Path": str(cfg.ROOT_DIR / "scripts/archive/serve_benchmark_mobile.py")}}})["decision"] == "deny"
    assert guard.evaluate_hook({"toolCall": {"name": "read_file", "args": {"Path": str(cfg.ROOT_DIR / "scripts/benchmarks/evaluate_h1_pilot.py")}}})["decision"] == "deny"
    assert guard.evaluate_hook({"toolCall": {"name": "run_command", "args": {"CommandLine": r".\.venv\Scripts\python.exe scripts/export_context.py"}}})["decision"] == "allow"

    mods = collect_active_modules()
    tel = ast_telemetry(mods)
    assert tel["oversized_modules"] == []
    assert tel["oversized_functions"] == []

    q_counts = count_quarantined_scripts()
    assert q_counts["archive"] >= 3
    assert q_counts["benchmarks"] >= 10
    assert q_counts["ml"] >= 3

    plan_md = build_refactoring_plan({"modules": mods})
    assert ">350L` 0건" in plan_md
    assert ">120L` 0건" in plan_md
    assert "scripts/{archive,benchmarks,ml}" in plan_md
