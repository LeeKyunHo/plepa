"""
tests/test_agent_hooks_and_skills.py
Antigravity .agents/hooks.json, plepa_guard.py 물리 차단 가드 및 6대 미니 에이전트 SKILL.md 계약 검증.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

from plepa_engine.config import ROOT_DIR


AGENTS_DIR = ROOT_DIR / ".agents"
HOOKS_JSON = AGENTS_DIR / "hooks.json"
GUARD_SCRIPT = AGENTS_DIR / "hooks" / "plepa_guard.py"

EXPECTED_SKILLS = (
    "plepa-pose-curator",
    "plepa-roster-character",
    "plepa-pipeline-qc-tuner",
    "plepa-trinity-gui-sync",
    "plepa-batch-operator",
    "plepa-doc-notebook-sync",
)


def _load_guard_module():
    spec = importlib.util.spec_from_file_location("plepa_guard", str(GUARD_SCRIPT))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hooks_json_and_guard_script_valid():
    """Antigravity 공식 hooks.json 구조와 상대경로 가드 스크립트 존재를 검증합니다."""
    assert HOOKS_JSON.is_file()
    assert GUARD_SCRIPT.is_file()
    assert not (AGENTS_DIR / "tasks").exists(), "구 .agents/tasks 디렉토리는 docs/archive/로 이관되어야 합니다."

    cfg = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    assert "plepa-safety-guard" in cfg
    pre_list = cfg["plepa-safety-guard"]["PreToolUse"]
    assert isinstance(pre_list, list) and len(pre_list) >= 1
    matcher = pre_list[0]["matcher"]
    for tool_name in ("run_command", "read_file", "write_file", "edit_file"):
        assert tool_name in matcher
    cmd = pre_list[0]["hooks"][0]["command"]
    assert "plepa_guard.py" in cmd


def test_all_six_mini_agent_skills_valid():
    """6대 미니 에이전트 SKILL.md 파일 존재, frontmatter, 필수 레일 섹션, 경량 줄수(<=100L)를 검증합니다."""
    for skill_name in EXPECTED_SKILLS:
        skill_file = AGENTS_DIR / "skills" / skill_name / "SKILL.md"
        assert skill_file.is_file(), f"스킬 파일 누락: {skill_file}"
        text = skill_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 100, f"{skill_name} SKILL.md가 과도하게 깁니다: {len(lines)}줄"
        assert text.startswith("---\n")
        assert f"name: {skill_name}" in text
        assert "description:" in text
        assert "허용" in text and "금지" in text and "검증" in text


@pytest.mark.parametrize(
    "payload,expected_decision",
    [
        # 1. 생성 에셋 직접 읽기/쓰기 차단 (워크스페이스 내부)
        (
            {"toolCall": {"name": "read_file", "args": {"Path": str(ROOT_DIR / "projects/campus/assets/aya/01_normal/aya_000_평상.webp")}}},
            "deny",
        ),
        (
            {"toolCall": {"name": "write_file", "args": {"Path": str(ROOT_DIR / "projects/campus/assets/aya_origin/test.webp")}}},
            "deny",
        ),
        # 2. 워크스페이스 외부 첨부 이미지는 정상 허용
        (
            {"toolCall": {"name": "read_file", "args": {"Path": "C:/Users/rbsgh/.gemini/antigravity/brain/conv-1/media.png"}}},
            "allow",
        ),
        # 3. FLUX 레거시 및 워크플로우 JSON 차단
        (
            {"toolCall": {"name": "read_file", "args": {"Path": str(ROOT_DIR / "data/legacy/flux_pose_database.json")}}},
            "deny",
        ),
        (
            {"toolCall": {"name": "edit_file", "args": {"Path": str(ROOT_DIR / "plepa_engine/legacy/flux_workflows.py")}}},
            "deny",
        ),
        (
            {"toolCall": {"name": "read_file", "args": {"Path": str(ROOT_DIR / "data/sample_workflow.json")}}},
            "deny",
        ),
        # 4. sdxl_pose_database.json 범위 미지정 전체 열람 차단 vs <=250줄 범위 지정 허용
        (
            {"toolCall": {"name": "read_file", "args": {"Path": str(ROOT_DIR / "data/sdxl_pose_database.json")}}},
            "deny",
        ),
        (
            {"toolCall": {"name": "read_file", "args": {"Path": str(ROOT_DIR / "data/sdxl_pose_database.json"), "StartLine": 195, "EndLine": 230}}},
            "allow",
        ),
        # 5. 읽기 전용 검증·감사 CLI는 오탐 없이 전부 허용
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": r".\.venv\Scripts\python.exe -m pytest -q"}}},
            "allow",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": r".\.venv\Scripts\python.exe -m plepa_engine.precheck -r campus"}}},
            "allow",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": r".\.venv\Scripts\python.exe scripts/export_context.py"}}},
            "allow",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": r".\.venv\Scripts\python.exe scripts/audit_asset_alignment.py --roster campus"}}},
            "allow",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": r".\.venv\Scripts\python.exe scripts/validate_genit_work.py --force"}}},
            "allow",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": r".\.venv\Scripts\python.exe batch_generator.py -r campus -p 000 --dry-run"}}},
            "allow",
        ),
        # 6. 쉘에서 assets 파괴 조작 및 sync_to_kiro 일반 실행 차단
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "Remove-Item projects/campus/assets/aya/01_normal/*.webp"}}},
            "deny",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "pytest; rm -rf projects/spy/assets"}}},
            "deny",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "python scripts/sync_to_kiro.py --dry-run"}}},
            "deny",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "git add -- scripts/sync_to_kiro.py"}}},
            "allow",
        ),
        # 7. 커밋 메시지 검증 (기술적 메시지 허용 / 민감어 차단)
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": 'git commit -m "feat: SDXL 파이프라인 계약 테스트 보강"'}}},
            "allow",
        ),
        (
            {"toolCall": {"name": "run_command", "args": {"CommandLine": 'git commit -m "fix: bad nude prompt fix"'}}},
            "deny",
        ),
    ],
)
def test_plepa_guard_evaluate_hook(payload: Dict[str, Any], expected_decision: str):
    """plepa_guard.evaluate_hook이 금지 동작만 정밀 차단하고 검증 스크립트는 오탐 없이 허용하는지 검증합니다."""
    guard = _load_guard_module()
    enriched = dict(payload)
    enriched.setdefault("workspacePaths", [str(ROOT_DIR)])
    enriched.setdefault("cwd", str(ROOT_DIR))
    res = guard.evaluate_hook(enriched)
    assert res["decision"] == expected_decision


def test_plepa_guard_subprocess_hooks_cwd():
    """.agents/ 작업 디렉토리에서 hooks.json과 동일한 stdin/stdout JSON 계약으로 동작하는지 E2E 검증합니다."""
    payload = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "python -m plepa_engine.precheck -r campus"},
        },
        "workspacePaths": [str(ROOT_DIR)],
        "cwd": str(ROOT_DIR),
    }
    proc = subprocess.run(
        [sys.executable, "hooks/plepa_guard.py"],
        cwd=str(AGENTS_DIR),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out == {"decision": "allow"}
