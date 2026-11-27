"""
tests/test_doc_sync_guard.py
서류 드리프트 감지기(check_doc_sync.py) 및 Git post-commit 훅 설치기(install_git_hooks.py) 회귀·단위 테스트.
"""

from __future__ import annotations

from pathlib import Path

from plepa_engine.config import ROOT_DIR
import scripts.check_doc_sync as check_cli
from scripts.doc_sync_rules import (
    apply_deterministic_fixes,
    check_deprecated_keywords,
    check_guard_and_gemini_sync,
    check_inventory_and_adr_sync,
    check_path_existence,
    compute_affected_docs,
    run_all_doc_sync_checks,
)
import scripts.install_git_hooks as hook_cli


def test_real_repo_has_zero_doc_sync_drift():
    """실제 레포의 Active SSOT 서류·스킬·물리 가드 정합성 드리프트가 0건인지 전체 pytest에서 상시 검증합니다."""
    issues = run_all_doc_sync_checks(ROOT_DIR)
    assert issues == [], check_cli.format_issue_report(issues)


def test_broken_path_and_archive_context_rules(tmp_path: Path):
    """깨진 백틱 경로는 적발하고, 아카이브/이관 맥락 및 와일드카드는 오탐 없이 허용하는지 검증합니다."""
    (tmp_path / "plepa_engine").mkdir()
    (tmp_path / "plepa_engine" / "real_mod.py").write_text("", encoding="utf-8")
    (tmp_path / "docs").mkdir()

    (tmp_path / "README.md").write_text(
        "- 현역 모듈: `plepa_engine/real_mod.py`\n"
        "- 글롭 패턴: `plepa_engine/*.py`\n"
        "- 아카이브 이관 설명: 구 `plepa_engine/old_removed.py`는 이관 완료\n"
        "- 깨진 참조: `plepa_engine/missing_mod.py`\n",
        encoding="utf-8",
    )

    issues = check_path_existence(tmp_path)
    assert len(issues) == 1
    assert issues[0].rule == "BROKEN_PATH"
    assert "missing_mod.py" in issues[0].message


def test_deprecated_keyword_detection_and_retirement_context(tmp_path: Path):
    """폐지 키워드가 현역 안내 본문에 남아 있으면 적발하고 은퇴/폐지 맥락에서는 허용하는지 검증합니다."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "RUNBOOK.md").write_text(
        "- 구 `:8085/inspect` 뷰어는 은퇴 및 아카이브 이관됨\n"
        "- 웹 뷰어 URL: `:8085/inspect`\n"
        "- 스냅샷 구성: `40_CORE_CODE.md` 기본 생성\n",
        encoding="utf-8",
    )
    issues = check_deprecated_keywords(tmp_path)
    terms = [i.message for i in issues]
    assert len(issues) == 2
    assert any(":8085/inspect" in m for m in terms)
    assert any("40_CORE_CODE.md" in m for m in terms)


def test_inventory_adr_sync_fix_and_guard_desync(tmp_path: Path):
    """인벤토리 누락, ADR 범위 지연 + `--fix` 자동 보정, `plepa_guard` ↔ `GEMINI.md` 11장 불일치를 검증합니다."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "AI_HANDOVER_GUIDE.md").write_text("### ADR-116 (2026-11-27)\n", encoding="utf-8")
    (tmp_path / "docs" / "NEW_GUIDE.md").write_text("# new\n", encoding="utf-8")
    (tmp_path / "docs" / "DOCUMENTATION_GUIDE.md").write_text(
        "| **결정이력** | `AI_HANDOVER_GUIDE.md` | Active ADR(`ADR-80~110+`) 요약 |\n"
        "| **가이드** | `DOCUMENTATION_GUIDE.md` | 본문 |\n",
        encoding="utf-8",
    )

    issues = check_inventory_and_adr_sync(tmp_path)
    rules = {i.rule for i in issues}
    assert "INVENTORY_GAP" in rules
    assert "ADR_RANGE_STALE" in rules

    applied = apply_deterministic_fixes(tmp_path)
    assert len(applied) == 1
    fixed_text = (tmp_path / "docs" / "DOCUMENTATION_GUIDE.md").read_text(encoding="utf-8")
    assert "ADR-80~116+" in fixed_text
    assert "| **가이드** | `DOCUMENTATION_GUIDE.md` | 본문 |" in fixed_text

    (tmp_path / ".agents" / "hooks").mkdir(parents=True)
    (tmp_path / ".agents" / "hooks" / "plepa_guard.py").write_text(
        '_BLOCKED_READ_SUBTREES = ("scripts/archive/", "scripts/benchmarks/")\n',
        encoding="utf-8",
    )
    (tmp_path / "GEMINI.md").write_text("## 11. 미니 에이전트\n- `legacy/`만 차단\n", encoding="utf-8")
    guard_issues = check_guard_and_gemini_sync(tmp_path)
    assert len(guard_issues) == 2
    assert all(i.rule == "GUARD_DOC_DESYNC" for i in guard_issues)


def test_diff_mapping_and_git_hook_installer(tmp_path: Path):
    """--diff 파일 매핑과 install_git_hooks의 설치/상태/제거 멱등성을 검증합니다."""
    affected = compute_affected_docs([
        "plepa_engine/services/generation_options.py",
        "plepa_engine/censor/pipeline.py",
    ])
    assert "사용법.txt" in affected
    assert "docs/GUI_GUIDE.md" in affected
    assert "docs/AI_HANDOVER_GUIDE.md" in affected

    fake_git = tmp_path / ".git"
    assert hook_cli.main(["--status", "--git-dir", str(fake_git)]) == 0
    assert not hook_cli.is_hook_installed(fake_git)

    assert hook_cli.main(["--install", "--git-dir", str(fake_git)]) == 0
    assert hook_cli.is_hook_installed(fake_git)
    # 중복 설치 시 블록이 중복 삽입되지 않아야 함
    assert hook_cli.main(["--install", "--git-dir", str(fake_git)]) == 0
    hook_text = (fake_git / "hooks" / "post-commit").read_text(encoding="utf-8")
    assert hook_text.count("PLEPA AUTO CONTEXT SNAPSHOT") == 2  # START + END 1쌍
    assert "export_context.py" in hook_text

    assert hook_cli.main(["--uninstall", "--git-dir", str(fake_git)]) == 0
    assert not hook_cli.is_hook_installed(fake_git)
