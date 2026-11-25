"""
scripts/novelchat_asset_mapper.py
노벨챗(NovelChat) 에셋 자동 태깅 및 500장 예산 패키징 CLI 래퍼.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from plepa_engine.services.novelchat_exporter import NOVELCHAT_LIMITS, NovelchatExporter


def main() -> int:
    parser = argparse.ArgumentParser(description="노벨챗(NovelChat) 에셋 자동 태깅 & 500장 예산 패키저")
    parser.add_argument("-r", "--roster", required=True, help="대상 로스터 (예: campus, spy)")
    parser.add_argument("--chars", nargs="*", help="특정 캐릭터 prefix만 선택 (생략 시 전체)")
    parser.add_argument("--out-dir", type=Path, help="출력 경로 (기본: dist/novelchat/{roster})")
    parser.add_argument("--include-adult", action="store_true", help="성인 포즈 풀 포함")
    parser.add_argument(
        "--max-total",
        type=int,
        default=NOVELCHAT_LIMITS["MAX_TOTAL_ASSETS"],
        help="총 에셋 상한 (기본: 500)",
    )
    parser.add_argument("--trim-to-limit", action="store_true", help="상한 초과 시 우선순위/균등 트리밍")
    parser.add_argument("--pool-config", type=Path, help="커스텀 호출어 풀 JSON 경로")
    parser.add_argument("--dry-run", action="store_true", help="파일 생성 없이 집계 및 예산 트리밍만 시뮬레이션")
    args = parser.parse_args()

    exporter = NovelchatExporter()
    try:
        res = exporter.export_roster(
            roster=args.roster,
            chars=args.chars,
            out_dir=args.out_dir,
            include_adult=args.include_adult,
            max_total=args.max_total,
            trim_to_limit=args.trim_to_limit,
            pool_config=args.pool_config,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"[ERROR] 패키징 실패: {exc}", file=sys.stderr)
        return 1

    m = res["manifest"]
    mode_tag = "[DRY-RUN]" if res["dry_run"] else "[EXPORTED]"
    print("=" * 72)
    print(f"{mode_tag} NovelChat 에셋 패키징 결과 — 로스터: {m['roster']}")
    print("=" * 72)
    print(f"  - 발견 에셋: {m['total_found']}장 | 패키징: {m['exported_count']}장 / 상한 {m['max_total']}장 | 제외: {m['excluded_count']}장")
    print(f"  - 성인 풀 포함: {m['include_adult']} | 5MB 최적화: {res['optimized_count']}장")
    print(f"  - 출력 경로: {res['out_dir']}")
    print("\n[캐릭터별 호출어 풀 요약]")
    for prefix, info in m["characters"].items():
        print(f"  * {prefix}: {info['total']}장 | 풀 {len(info['pools'])}종 | 기본(★): {info['default_image']}")
    if res["warnings"]:
        print(f"\n[경고 {len(res['warnings'])}건]")
        for w in res["warnings"][:10]:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
