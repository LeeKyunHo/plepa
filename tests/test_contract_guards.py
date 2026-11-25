"""
tests/test_contract_guards.py
하위 모델 유지보수 시 구조 붕괴를 자동 차단하는 Wave 1 기계적 계약 테스트:
1. AST 모듈/함수 줄수 래칫(Ratchet) 가드: 신규 파일 <= 350L, 신규 함수 <= 120L, 기존 30개 비대 파일·45개 함수 증대 차단
2. 아키텍처 레이어 역방향 import(engine -> gui/scripts) 및 legacy 재유입 래칫 가드
3. GUI GlobalJobManager 작업 큐 우회 직접 run_batch 호출 래칫 가드
4. batch_generator.create_parser()._actions 기반 argparse <-> GENERATION_OPTION_SPECS 정밀 동기화
5. CharacterConfig <-> CharacterSchema 필드 대칭 및 PoseSetSchema 영숫자 코드 정렬 왕복 계약
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from batch_generator import create_parser
from plepa_engine.config import ROOT_DIR
from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.services.generation_service import GENERATION_OPTION_SPECS
from plepa_engine.services.schemas import CharacterSchema, PoseItemSchema, PoseSetSchema


_MODULE_LINE_LIMIT = 350
_FUNCTION_LINE_LIMIT = 120

# Wave 3~5 분해 전까지 현행 줄수 상한을 동결하는 래칫 Allowlist (줄수 감소 시 하향 조정, 신규 추가 금지)
_MODULE_LINE_RATCHET_CAPS: Dict[str, int] = {
    "plepa_engine/censor.py": 3787,
    "plepa_engine/comfy_client.py": 462,
    "plepa_engine/precheck.py": 392,
    "plepa_engine/prompt_pipeline.py": 1381,
    "plepa_engine/qa_validator.py": 404,
    "plepa_engine/services/asset_service.py": 438,
    "plepa_engine/services/generation_service.py": 1044,
    "plepa_engine/services/health_service.py": 712,
    "plepa_engine/services/pose_service.py": 646,
    "plepa_gui/api_routes.py": 456,
    "plepa_gui/components/retouch_editor.py": 563,
    "plepa_gui/pages/characters.py": 387,
    "plepa_gui/pages/gallery.py": 1641,
    "plepa_gui/pages/generate.py": 544,
    "plepa_gui/pages/mobile_viewer.py": 1640,
    "scripts/audit_asset_alignment.py": 506,
    "scripts/benchmark_censor_metrics.py": 372,
    "scripts/benchmark_spy_batch.py": 674,
    "scripts/evaluate_h1_pilot.py": 857,
    "scripts/extract_censor_seg_dataset.py": 956,
    "scripts/generate_inspection_viewer.py": 1408,
    "scripts/mobile_gallery.py": 574,
    "scripts/run_artist_benchmark.py": 505,
    "scripts/run_artist_benchmark_v2.py": 507,
    "scripts/serve_benchmark_mobile.py": 1401,
    "scripts/train_censor_seg.py": 386,
    "scripts/validate_genit_work.py": 419,
}

# (rel_posix_path, func_name) -> 현재 최대 줄수 상한 래칫
_FUNCTION_LINE_RATCHET_CAPS: Dict[Tuple[str, str], int] = {
    ("plepa_engine/censor.py", "_extract_hand_occlusion_mask"): 130,
    ("plepa_engine/censor.py", "_extract_semantic_sam_prompts"): 130,
    ("plepa_engine/censor.py", "apply_silhouette"): 534,
    ("plepa_engine/censor.py", "_detect_target_candidates"): 141,
    ("plepa_engine/censor.py", "_resolve_hybrid_targets_with_priors"): 373,
    ("plepa_engine/comfy_client.py", "generate_image"): 196,
    ("plepa_engine/precheck.py", "run_pregeneration_check"): 268,
    ("plepa_engine/prompt_pipeline.py", "mutate"): 242,
    ("plepa_engine/qa_validator.py", "validate_generated_image"): 195,
    ("plepa_engine/services/generation_service.py", "run_batch"): 658,
    ("plepa_engine/services/pose_service.py", "resolve_pose_codes"): 131,
    ("plepa_engine/workflow_templates.py", "build_sdxl_workflow"): 226,
    ("plepa_gui/components/retouch_editor.py", "build_retouch_editor_script"): 356,
    ("plepa_gui/pages/backgrounds.py", "render_backgrounds_page"): 171,
    ("plepa_gui/pages/characters.py", "render_characters_page"): 328,
    ("plepa_gui/pages/characters.py", "render_form"): 137,
    ("plepa_gui/pages/gallery.py", "render_gallery_page"): 1487,
    ("plepa_gui/pages/gallery.py", "sync_queue_panel"): 162,
    ("plepa_gui/pages/gallery.py", "open_genit_export_dialog"): 134,
    ("plepa_gui/pages/gallery.py", "update_control_bars"): 162,
    ("plepa_gui/pages/gallery.py", "open_lightbox"): 399,
    ("plepa_gui/pages/gallery.py", "refresh_header"): 264,
    ("plepa_gui/pages/generate.py", "render_generate_page"): 504,
    ("plepa_gui/pages/mobile_viewer.py", "generate_mobile_viewer_html"): 1457,
    ("plepa_gui/pages/pose_sets.py", "render_pose_sets_page"): 188,
    ("plepa_gui/pages/poses.py", "render_poses_page"): 235,
    ("plepa_gui/pages/settings.py", "render_settings_page"): 152,
    ("scripts/audit_asset_alignment.py", "load_full_pose_catalog"): 131,
    ("scripts/audit_asset_alignment.py", "audit_character_alignment"): 187,
    ("scripts/audit_sector_assets.py", "audit_character"): 173,
    ("scripts/benchmark_spy_batch.py", "render_spy_gallery_html"): 496,
    ("scripts/evaluate_h1_pilot.py", "generate_comparison_html"): 460,
    ("scripts/evaluate_h1_pilot.py", "evaluate_pilot"): 164,
    ("scripts/evaluate_overnight_audit.py", "main"): 220,
    ("scripts/extract_censor_seg_dataset.py", "build_yolo_seg_dataset"): 251,
    ("scripts/generate_inspection_viewer.py", "generate_inspection_html"): 1347,
    ("scripts/mobile_gallery.py", "index"): 395,
    ("scripts/run_artist_benchmark.py", "generate_html_viewer"): 279,
    ("scripts/run_artist_benchmark_v2.py", "generate_html_viewer_v2"): 283,
    ("scripts/serve_benchmark_mobile.py", "index_view"): 430,
    ("scripts/train_censor_seg.py", "train_censor_seg"): 175,
    ("scripts/validate_genit_work.py", "validate_document"): 222,
}

# Wave 4~5 해소 대상 기존 결합 예외 Allowlist
_REVERSE_LAYER_ALLOWLIST: Set[str] = {"plepa_engine/services/health_service.py"}
_LEGACY_IMPORT_ALLOWLIST: Set[str] = {
    "plepa_engine/prompt_builder.py",
    "plepa_engine/workflow_templates.py",
}
_GUI_DIRECT_RUN_BATCH_ALLOWLIST: Set[str] = set()


def _iter_active_python_files() -> Iterable[Path]:
    bg = ROOT_DIR / "batch_generator.py"
    if bg.is_file():
        yield bg
    for folder in ("plepa_engine", "plepa_gui", "scripts"):
        base = ROOT_DIR / folder
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if {"legacy", "archive", "__pycache__"} & set(p.parts):
                continue
            yield p


def test_ast_module_line_ratchet():
    """신규 모듈 <= 350줄 및 기존 비대 모듈(30개) 줄수 증가 차단을 강제합니다."""
    violations: List[str] = []
    for p in _iter_active_python_files():
        rel = p.relative_to(ROOT_DIR).as_posix()
        line_cnt = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        cap = _MODULE_LINE_RATCHET_CAPS.get(rel, _MODULE_LINE_LIMIT)
        if line_cnt > cap:
            violations.append(f"{rel}: {line_cnt}줄 > 상한 {cap}줄")
    assert not violations, "모듈 줄수 래칫 위반:\n" + "\n".join(violations)


def test_ast_function_line_ratchet():
    """신규 함수 <= 120줄 및 기존 비대 함수 줄수 증가 차단을 강제합니다."""
    violations: List[str] = []
    for p in _iter_active_python_files():
        rel = p.relative_to(ROOT_DIR).as_posix()
        src = p.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno is not None:
                length = node.end_lineno - node.lineno + 1
                cap = _FUNCTION_LINE_RATCHET_CAPS.get((rel, node.name), _FUNCTION_LINE_LIMIT)
                if length > cap:
                    violations.append(f"{rel}::{node.name}@{node.lineno}: {length}줄 > 상한 {cap}줄")
    assert not violations, "함수 줄수 래칫 위반:\n" + "\n".join(violations)


def test_architecture_layer_boundary_ratchet():
    """plepa_engine이 plepa_gui/scripts를 역방향 import하거나 legacy 모듈을 신규 import하지 않도록 차단합니다."""
    reverse_violations: List[str] = []
    legacy_violations: List[str] = []

    for p in _iter_active_python_files():
        rel = p.relative_to(ROOT_DIR).as_posix()
        tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            else:
                continue
            for mod in mods:
                if rel.startswith("plepa_engine/") and (mod.startswith("plepa_gui") or mod.startswith("scripts")):
                    if rel not in _REVERSE_LAYER_ALLOWLIST:
                        reverse_violations.append(f"{rel} -> {mod}")
                if "legacy" in mod.split("."):
                    if rel not in _LEGACY_IMPORT_ALLOWLIST:
                        legacy_violations.append(f"{rel} -> {mod}")

    assert not reverse_violations, "역방향 레이어 결합 위반:\n" + "\n".join(reverse_violations)
    assert not legacy_violations, "FLUX 레거시 import 유입 위반:\n" + "\n".join(legacy_violations)


def test_gui_no_direct_run_batch_ratchet():
    """GUI 모듈은 GlobalJobManager 큐를 우회하여 .run_batch()를 직접 호출할 수 없습니다."""
    violations: List[str] = []
    for p in _iter_active_python_files():
        rel = p.relative_to(ROOT_DIR).as_posix()
        if not rel.startswith("plepa_gui/"):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"), filename=rel)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run_batch"
                and rel not in _GUI_DIRECT_RUN_BATCH_ALLOWLIST
            ):
                violations.append(f"{rel}:{node.lineno}")
    assert not violations, "GlobalJobManager 우회 run_batch 호출 감지:\n" + "\n".join(violations)


def test_argparse_trinity_sync_exact():
    """create_parser()._actions를 직접 검사하여 GENERATION_OPTION_SPECS의 cli_flag 및 dest 일치를 검증합니다."""
    parser = create_parser()
    flag_to_dest: Dict[str, str] = {}
    for action in parser._actions:
        for opt in action.option_strings:
            flag_to_dest[opt] = action.dest

    for spec in GENERATION_OPTION_SPECS:
        flag = spec["cli_flag"]
        field = spec["field"]
        assert flag in flag_to_dest, f"파서 미등록 CLI 플래그: {flag}"
        assert flag_to_dest[flag] == field, (
            f"CLI 파서 dest({flag_to_dest[flag]}) != 스펙 field({field}) [{flag}]"
        )


def test_character_config_and_schema_field_parity():
    """CharacterConfig의 핵심 직렬화 필드가 CharacterSchema에도 모두 선언되어 있는지 검증합니다."""
    cfg_fields = {
        f.name for f in dataclasses.fields(CharacterConfig)
        if f.name not in {"file_path", "active_profile"}
    }
    schema_fields = set(CharacterSchema.model_fields.keys())
    missing = sorted(cfg_fields - schema_fields)
    assert not missing, f"CharacterSchema에 누락된 CharacterConfig 필드: {missing}"


def test_pose_entry_and_schema_field_parity():
    """PoseEntry의 핵심 직렬화 필드가 PoseItemSchema에도 모두 선언되어 있는지 검증합니다."""
    entry_fields = {
        f.name for f in dataclasses.fields(PoseEntry)
        if f.name not in {"code", "section"}
    }
    schema_fields = set(PoseItemSchema.model_fields.keys())
    missing = sorted(entry_fields - schema_fields)
    assert not missing, f"PoseItemSchema에 누락된 PoseEntry 필드: {missing}"


def test_pose_sets_alphanumeric_sort_roundtrip():
    """PoseSetSchema가 영숫자 테마 코드(D01, S01, C01)와 3자리 숫자 코드를 예외 없이 처리하는지 검증합니다."""
    ps = PoseSetSchema(
        id="mixed_theme_set",
        name="혼합 테마 세트",
        codes=["D01", "000", "S02", "C01", "034"],
    )
    sorted_codes = sorted(ps.codes, key=lambda x: (0, f"{int(x):05d}") if str(x).isdigit() else (1, str(x)))
    assert sorted_codes == ["000", "034", "C01", "D01", "S02"]
