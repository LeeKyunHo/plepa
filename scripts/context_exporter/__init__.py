"""
scripts.context_exporter
외부 Gemini 노트북 & 저사양 모델 협업을 위한 5대 고정 컨텍스트 스냅샷 패키지.
"""

from __future__ import annotations

from plepa_engine.config import ROOT_DIR as PLEPA_ROOT

from .ast_extract import (
    ModuleSummary,
    ast_telemetry,
    extract_constants,
    extract_dataclass_fields,
    extract_signatures,
    parse_module,
    sha,
)
from .builders import build_readme, build_tier1, build_tier2
from .report_builders import (
    build_code_bundle,
    build_refactoring_plan,
    build_tier3,
    enforce_budget,
)
from .runtime_and_telemetry import (
    COLLECTED_FILE_BUDGETS,
    DEFAULT_BASE_TOTAL_BUDGET,
    build_asset_matrix,
    build_drift,
    cleanup_stale_snapshots,
    collect_genit_status,
    collect_skills_catalog,
    extract_adrs,
    git_info,
    parse_refactoring_progress,
)

__all__ = [
    "PLEPA_ROOT",
    "ModuleSummary",
    "ast_telemetry",
    "sha",
    "parse_module",
    "extract_constants",
    "extract_signatures",
    "extract_dataclass_fields",
    "build_tier1",
    "build_tier2",
    "build_tier3",
    "build_readme",
    "build_refactoring_plan",
    "build_code_bundle",
    "enforce_budget",
    "git_info",
    "build_asset_matrix",
    "build_drift",
    "cleanup_stale_snapshots",
    "collect_genit_status",
    "collect_skills_catalog",
    "extract_adrs",
    "parse_refactoring_progress",
    "COLLECTED_FILE_BUDGETS",
    "DEFAULT_BASE_TOTAL_BUDGET",
]
