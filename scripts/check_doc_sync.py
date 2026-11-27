"""
scripts/check_doc_sync.py
Active SSOT 문서·스킬·물리 가드 간 서류 드리프트 감지, --diff 영향 서류 매핑 및 --fix 정형 자동 동기화 CLI.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from scripts.doc_sync_rules import (
    DocDriftIssue,
    apply_deterministic_fixes,
    compute_affected_docs,
    run_all_doc_sync_checks,
)


def collect_git_changed_files(root_dir: Path, base_ref: Optional[str] = None) -> List[str]:
    """`git diff --name-only` + 워킹트리 변경/미추적 파일 목록을 수집합니다."""
    changed: List[str] = []
    cmds = (
        [["diff", "--name-only", base_ref, "HEAD"]]
        if base_ref
        else [["diff", "--name-only"], ["diff", "--name-only", "--cached"], ["ls-files", "--others", "--exclude-standard"]]
    )
    for args in cmds:
        try:
            res = subprocess.run(
                ["git", *args],
                cwd=str(root_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    clean = line.strip()
                    if clean and clean not in changed:
                        changed.append(clean)
        except Exception:
            pass
    return changed


def format_issue_report(issues: Sequence[DocDriftIssue]) -> str:
    """드리프트 위반 목록을 파일명·줄번호·사유·수정 가이드 형식으로 포매팅합니다."""
    if not issues:
        return "✅ [PASS] Active SSOT 서류·스킬·가드 드리프트 0건 확인!"
    lines = [f"🚨 [DRIFT] 총 {len(issues)}건의 서류/가드 불일치 감지:"]
    for idx, issue in enumerate(issues, 1):
        lines.append(
            f"  [{idx}] {issue.file_path}:{issue.line_no} ({issue.rule}) {issue.message}\n"
            f"      ➔ 수정 가이드: {issue.fix_hint}"
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """서류 드리프트 감지기 CLI 진입점."""
    parser = argparse.ArgumentParser(description="Active SSOT 서류·스킬·가드 드리프트 감지기")
    parser.add_argument("--root", type=Path, default=ROOT_DIR, help="검사 대상 프로젝트 루트 경로")
    parser.add_argument(
        "--diff",
        nargs="?",
        const="",
        default=None,
        metavar="BASE_REF",
        help="git 변경 파일 기준 영향받는 서류 체크리스트 출력 (선택: 기준 커밋/브랜치)",
    )
    parser.add_argument("--fix", action="store_true", help="ADR 번호 범위 등 안전한 정형 필드만 자동 동기화")
    parser.add_argument("--quiet", action="store_true", help="요약 출력 최소화")
    args = parser.parse_args(argv)

    root_dir = args.root.resolve()

    if args.fix:
        for msg in apply_deterministic_fixes(root_dir):
            print(f"🔧 [FIX] {msg}")

    if args.diff is not None:
        base_ref = args.diff.strip() or None
        changed = collect_git_changed_files(root_dir, base_ref=base_ref)
        affected = compute_affected_docs(changed)
        print(f"📋 [--diff] 변경 파일 {len(changed)}건 분석 ➔ 확인 권장 Active 서류 {len(affected)}종:")
        for doc_rel, triggers in sorted(affected.items()):
            preview = ", ".join(triggers[:3]) + (f" 외 {len(triggers) - 3}건" if len(triggers) > 3 else "")
            print(f"  - [ ] {doc_rel}  (사유: {preview})")

    issues = run_all_doc_sync_checks(root_dir)
    if not args.quiet or issues:
        print(format_issue_report(issues))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
