"""
scripts/install_git_hooks.py
로컬 `.git/hooks/post-commit`을 통해 커밋 직후 `context_snapshot/` 5개 파일을 자동 갱신하는 옵트인 훅 설치기.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_HOOK_START = "# >>> PLEPA AUTO CONTEXT SNAPSHOT >>>"
_HOOK_END = "# <<< PLEPA AUTO CONTEXT SNAPSHOT <<<"

_HOOK_BLOCK = f"""{_HOOK_START}
if [ -f "scripts/export_context.py" ]; then
    if [ -x ".venv/Scripts/python.exe" ]; then
        ".venv/Scripts/python.exe" scripts/export_context.py >/dev/null 2>&1 || echo "[PLEPA post-commit] context_snapshot refresh warning (commit kept)"
    elif [ -x ".venv/bin/python" ]; then
        ".venv/bin/python" scripts/export_context.py >/dev/null 2>&1 || echo "[PLEPA post-commit] context_snapshot refresh warning (commit kept)"
    elif command -v python >/dev/null 2>&1; then
        python scripts/export_context.py >/dev/null 2>&1 || echo "[PLEPA post-commit] context_snapshot refresh warning (commit kept)"
    fi
fi
{_HOOK_END}
"""


def _resolve_hook_path(git_dir: Optional[Path] = None) -> Path:
    base = (git_dir or (ROOT_DIR / ".git")).resolve()
    return base / "hooks" / "post-commit"


def is_hook_installed(git_dir: Optional[Path] = None) -> bool:
    """`post-commit` 훅에 PLEPA 자동 스냅샷 블록이 설치되어 있는지 확인합니다."""
    hook_path = _resolve_hook_path(git_dir)
    if not hook_path.is_file():
        return False
    return _HOOK_START in hook_path.read_text(encoding="utf-8", errors="replace")


def install_post_commit_hook(git_dir: Optional[Path] = None) -> Path:
    """`.git/hooks/post-commit`에 안전한 스냅샷 자동 갱신 블록을 설치합니다 (멱등성 보장)."""
    hook_path = _resolve_hook_path(git_dir)
    hook_path.parent.mkdir(parents=True, exist_ok=True)

    existing = hook_path.read_text(encoding="utf-8", errors="replace") if hook_path.is_file() else ""
    if _HOOK_START in existing:
        return hook_path

    if not existing.strip():
        new_content = "#!/bin/sh\n\n" + _HOOK_BLOCK
    else:
        sep = "\n" if existing.endswith("\n") else "\n\n"
        new_content = existing + sep + _HOOK_BLOCK

    hook_path.write_text(new_content, encoding="utf-8", newline="\n")
    try:
        hook_path.chmod(hook_path.stat().st_mode | 0o111)
    except Exception:
        pass
    return hook_path


def uninstall_post_commit_hook(git_dir: Optional[Path] = None) -> bool:
    """`.git/hooks/post-commit`에서 PLEPA 자동 스냅샷 블록만 안전하게 제거합니다."""
    hook_path = _resolve_hook_path(git_dir)
    if not hook_path.is_file():
        return False
    text = hook_path.read_text(encoding="utf-8", errors="replace")
    if _HOOK_START not in text or _HOOK_END not in text:
        return False

    pre, _, rest = text.partition(_HOOK_START)
    _, _, post = rest.partition(_HOOK_END)
    cleaned = (pre.rstrip() + "\n" + post.lstrip()).strip()
    if not cleaned or cleaned == "#!/bin/sh":
        hook_path.unlink(missing_ok=True)
    else:
        hook_path.write_text(cleaned + "\n", encoding="utf-8", newline="\n")
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Git post-commit 훅 설치기 CLI."""
    parser = argparse.ArgumentParser(description="로컬 Git post-commit context_snapshot 자동 갱신 훅 관리")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install", action="store_true", help="post-commit 스냅샷 훅 설치")
    group.add_argument("--uninstall", action="store_true", help="post-commit 스냅샷 훅 제거")
    group.add_argument("--status", action="store_true", help="설치 상태 확인")
    parser.add_argument("--git-dir", type=Path, default=None, help="대상 .git 디렉터리 경로")
    args = parser.parse_args(argv)

    if args.install:
        hp = install_post_commit_hook(args.git_dir)
        print(f"✅ post-commit 자동 스냅샷 훅 설치 완료: {hp}")
        return 0
    if args.uninstall:
        removed = uninstall_post_commit_hook(args.git_dir)
        print("🗑️ post-commit 자동 스냅샷 훅 제거 완료" if removed else "ℹ️ 제거할 훅 블록이 없습니다.")
        return 0
    installed = is_hook_installed(args.git_dir)
    print(f"📌 post-commit 자동 스냅샷 훅 상태: {'설치됨 (ACTIVE)' if installed else '미설치'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
