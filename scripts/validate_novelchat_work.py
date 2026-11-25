"""
scripts/validate_novelchat_work.py
노벨챗(NovelChat) 6탭 원고 마크다운 정합성 검증 CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from plepa_engine.services.novelchat_validator import parse_frontmatter, validate_novelchat_markdown

NOVELCHAT_DOCS_DIR = ROOT_DIR / "docs" / "novelchat"


def main() -> int:
    parser = argparse.ArgumentParser(description="노벨챗(NovelChat) 6탭 원고 자동 검증기")
    parser.add_argument("work", nargs="?", type=Path, help="검증할 마크다운 파일 경로 (생략 시 docs/novelchat/ active 스캔)")
    parser.add_argument("--manifest", type=Path, help="upload_manifest.json 경로 (이미지 호출어 교차 검증)")
    parser.add_argument("--force", action="store_true", help="template/frozen 문서도 강제 검증")
    parser.add_argument("--strict", action="store_true", help="WARNING도 실패(ERROR)로 처리")
    args = parser.parse_args()

    targets: List[Path] = []
    if args.work:
        targets = [args.work]
    elif NOVELCHAT_DOCS_DIR.is_dir():
        targets = sorted(NOVELCHAT_DOCS_DIR.glob("*.md"))

    if not targets:
        print("[INFO] 검증할 노벨챗 문서가 없습니다.")
        return 0

    all_passed = True
    for file_path in targets:
        if not file_path.is_file():
            print(f"[ERROR] 파일 없음: {file_path}", file=sys.stderr)
            all_passed = False
            continue
        content = file_path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(content)
        status = meta.get("status", "active").lower()
        if status in ("template", "frozen", "archived") and not args.force and not args.work:
            print(f"⏩ [SKIP] {file_path.name} (status: {status})")
            continue

        res = validate_novelchat_markdown(content, manifest_path=args.manifest, strict=args.strict)
        print("=" * 72)
        print(f"🔍 [NovelChat 6탭 검증] {file_path.name} | 공통:{res.stats.get('common_prompt_len', 0)}자 | 캐릭:{res.stats.get('characters', 0)} | 도입부:{res.stats.get('intros', 0)} | 메모리:{res.stats.get('memorybooks', 0)}")
        print("=" * 72)
        for w in res.warnings:
            print(f"  ⚠️ [WARN] {w}")
        for e in res.errors:
            print(f"  ❌ [ERROR] {e}")
        if res.passed:
            print(f"  ✅ PASS ({file_path.name})")
        else:
            print(f"  🚨 FAIL ({len(res.errors)} errors)")
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
