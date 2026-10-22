"""tests/test_export_context.py
scripts/export_context.py 스냅샷 생성기 무결성 및 정상 생성 단위 테스트.
"""

from pathlib import Path
try:
    import pytest
except ImportError:
    pytest = None

from scripts.export_context import (
    sha,
    parse_module,
    extract_constants,
    extract_signatures,
    extract_dataclass_fields,
    build_tier1,
    build_tier2,
    build_readme,
    git_info,
    PLEPA_ROOT,
)


def test_sha():
    py_file = PLEPA_ROOT / "plepa_engine" / "models.py"
    file_sha = sha(py_file)
    assert len(file_sha) == 8
    assert file_sha != "missing"


def test_extract_constants_and_signatures():
    py_file = PLEPA_ROOT / "plepa_engine" / "config.py"
    tree = parse_module(py_file)
    assert tree is not None

    consts = dict(extract_constants(tree))
    assert "DEFAULT_CKPT" in consts or "DEFAULT_ENGINE" in consts or "DEFAULT_PROMPT_CONFIG" in consts

    sigs = extract_signatures(tree)
    assert isinstance(sigs, list)


def test_extract_dataclass_fields():
    # PoseEntry from models.py
    py_models = PLEPA_ROOT / "plepa_engine" / "models.py"
    tree_models = parse_module(py_models)
    assert tree_models is not None
    pose_fields = extract_dataclass_fields(tree_models, "PoseEntry")
    assert len(pose_fields) >= 5
    pose_field_names = [f[0] for f in pose_fields]
    assert "code" in pose_field_names
    assert "prompt" in pose_field_names

    # GenerationParams from generation_service.py
    py_gen = PLEPA_ROOT / "plepa_engine" / "services" / "generation_service.py"
    tree_gen = parse_module(py_gen)
    assert tree_gen is not None
    gen_fields = extract_dataclass_fields(tree_gen, "GenerationParams")
    assert len(gen_fields) >= 30
    gen_field_names = [f[0] for f in gen_fields]
    assert "character_expr" in gen_field_names
    assert "pose_expr" in gen_field_names
    assert "auto_qc" in gen_field_names


def test_build_tier1_content():
    dummy_snap = {
        "snapshot_id": "TEST-SNAPSHOT-ID",
        "generated_at": "2026-10-16 00:00:00",
        "plepa": {"sha": "1111111", "branch": "main", "dirty": 0, "dirty_files": []},
        "kiro": {"sha": "2222222", "branch": "main", "dirty": 0, "dirty_files": []},
    }
    tier1_md = build_tier1(dummy_snap)
    assert "TEST-SNAPSHOT-ID" in tier1_md
    assert "V2 포즈 번호 대역" in tier1_md
    assert "플에파(PLEPA) 에이전트 규칙" in tier1_md


def test_build_tier2_content():
    dummy_snap = {
        "snapshot_id": "TEST-SNAPSHOT-ID",
        "generated_at": "2026-10-16 00:00:00",
        "plepa": {"sha": "1111111", "branch": "main", "dirty": 0, "dirty_files": []},
        "kiro": {"sha": "2222222", "branch": "main", "dirty": 0, "dirty_files": []},
    }
    tier2_md = build_tier2(dummy_snap, include_prompts=False)
    assert "TEST-SNAPSHOT-ID" in tier2_md
    assert "SDXLPromptPipeline" in tier2_md or "Mutator" in tier2_md
    assert "GenerationParams" in tier2_md
    assert "Auto-QC 파라미터" in tier2_md
    assert "포즈 DB 현황" in tier2_md


def test_build_readme_content():
    dummy_snap = {
        "snapshot_id": "TEST-SNAPSHOT-ID",
        "generated_at": "2026-10-16 00:00:00",
        "plepa": {"sha": "1111111", "branch": "main", "dirty": 0, "dirty_files": []},
        "kiro": {"sha": "2222222", "branch": "main", "dirty": 0, "dirty_files": []},
    }
    files = ["00_README_FOR_AI.md", "10_TIER1_CONSTITUTION.md"]
    delta = ["- plepa_engine/censor.py (modified)"]
    readme_md = build_readme(dummy_snap, delta, "PREV-SNAPSHOT-ID", files)

    assert "TEST-SNAPSHOT-ID" in readme_md
    assert "PREV-SNAPSHOT-ID" in readme_md
    assert "외부 AI 읽기 규칙" in readme_md
    assert "폐지 목록 (Deprecation Ledger)" in readme_md
    assert "censor.py" in readme_md
