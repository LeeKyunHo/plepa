"""
plepa_upscaler.py
플에파(PLEPA) 완성된 에셋 전용 4K AI 초고화질 업스케일러 CLI.
- 4x-UltraSharp.pth AI 모델을 사용하여 장당 2~3초 만에 4096x6144 초고화질로 변환.
- 원본의 구도, 표정, 디테일을 100% 온전히 보존하며 선화와 텍스처만 선명하게 강화.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR, configure_stdio
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.services.upscale_service import default_upscale_service

configure_stdio()


def collect_target_files(
    image_path: Optional[str] = None,
    roster: str = DEFAULT_ROSTER,
    character_expr: Optional[str] = None,
    pose_expr: str = "all",
) -> List[Path]:
    """업스케일 대상 이미지 파일 목록을 수집합니다."""
    if image_path:
        p = Path(image_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"지정한 이미지 파일을 찾을 수 없습니다: {p}")
        return [p]

    if not character_expr:
        raise ValueError("-i/--image 파일 또는 -c/--char 캐릭터를 지정해야 합니다.")

    chars = default_character_service.resolve_characters(character_expr, roster=roster)
    db = default_pose_service.load_db("sdxl")
    codes = default_pose_service.resolve_pose_codes(pose_expr, db=db)

    files: List[Path] = []
    for char, actual_roster in chars:
        char_dir = PROJECTS_DIR / actual_roster / "assets" / char.prefix
        if not char_dir.exists():
            continue

        for code in codes:
            # {prefix}_{code}로 시작하는 모든 .webp 파일 탐색 (_4k 및 _censored 제외)
            matches = [
                f for f in char_dir.glob(f"{char.prefix}_{code}*.webp")
                if not f.name.endswith("_4k.webp") and not f.name.endswith("_censored.webp")
            ]
            files.extend(matches)

    return sorted(list(set(files)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plepa_upscaler",
        description="플에파 완성 에셋 전용 4K AI 초고화질 업스케일러 (4x-UltraSharp)"
    )
    parser.add_argument("-i", "--image", default=None, help="업스케일할 단일 이미지 파일 경로")
    parser.add_argument("-r", "--roster", default=DEFAULT_ROSTER, help=f"로스터 폴더 (기본: {DEFAULT_ROSTER})")
    parser.add_argument("-c", "--char", "--character", default=None, help="대상 캐릭터 식별자 (예: mal, all)")
    parser.add_argument("-p", "--pose", "--codes", default="all", help="포즈 코드/범위 (all, emotions, 000..019, 034 등)")
    parser.add_argument("-f", "--overwrite", action="store_true", help="기존 원본 파일을 4K 업스케일본으로 직접 교체 (기본: _4k.webp 신규 생성)")
    parser.add_argument("--model", default="4x-UltraSharp.pth", help="사용할 업스케일러 모델 (기본: 4x-UltraSharp.pth)")

    args = parser.parse_args(argv)

    try:
        targets = collect_target_files(
            image_path=args.image,
            roster=args.roster,
            character_expr=args.char,
            pose_expr=args.pose,
        )
    except Exception as e:
        print(f"[오류] 대상 파일 수집 실패: {e}")
        return 1

    if not targets:
        print("[안내] 업스케일 대상 이미지 파일을 찾을 수 없습니다.")
        return 0

    print("=" * 70)
    print("  [플에파] 4K AI 초고화질 단독 업스케일러 가동")
    print(f"  대상 파일: 총 {len(targets)}개")
    print(f"  업스케일 모델: {args.model}")
    print(f"  저장 방식: {'원본 직접 교체 (--overwrite)' if args.overwrite else '_4k.webp 별도 보존'}")
    print("=" * 70)

    success_count = 0
    start_total = time.time()

    for idx, f in enumerate(targets, 1):
        try:
            w_orig, h_orig = default_upscale_service.get_image_dimensions(f)
            t0 = time.time()
            out = default_upscale_service.upscale_file(f, overwrite=args.overwrite, upscale_model=args.model)
            dt = time.time() - t0
            w_new, h_new = default_upscale_service.get_image_dimensions(out)

            print(f"  [{idx:02d}/{len(targets):02d}] {f.name} -> {out.name} ({w_orig}x{h_orig} -> {w_new}x{h_new}) [{dt:.1f}초]")
            success_count += 1
        except Exception as e:
            print(f"  [{idx:02d}/{len(targets):02d}] ❌ {f.name} 업스케일 실패: {e}")

    total_time = time.time() - start_total
    avg_time = (total_time / success_count) if success_count else 0.0

    print("=" * 70)
    print(f"  [완료] 총 {success_count}/{len(targets)}개 성공 | 소요 시간: {total_time:.1f}초 (장당 평균 {avg_time:.1f}초)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
