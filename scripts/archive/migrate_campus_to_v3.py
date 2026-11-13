"""
scripts/migrate_campus_to_v3.py
캠퍼스(campus) 로스터 에셋을 V3 대역별 6대 계층 서브폴더로 무손실 원자적 마이그레이션.

대역 구조:
- 01_emotions: 000~019 (감정 표현)
- 02_daily:    020~050 (범용 일상)
- 03_events:   051~059 (로스터 일상 이벤트)
- 04_romance:  060~079 (로맨스 & 공용 구강)
- 05_h_scenes: 080~129, 150~199 (범용 H씬 체위)
- 06_special_h: 130~139, 200~209 (로스터 특색 이벤트 H씬)
"""

import re
import sys
import shutil
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# plepa 루트 임포트 경로 확보
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plepa_engine.reporter import get_subfolder_for_code

CHARS = ["aya", "har", "kao", "mai", "shz", "yur"]
ASSETS_DIR = PROJECT_ROOT / "projects" / "campus" / "assets"
CODE_PATTERN = re.compile(r"^[a-z0-9]+_([0-9]{3})(?:_.*)?\.webp$")


def migrate_folder(target_dir: Path, is_origin: bool = False) -> dict:
    if not target_dir.exists():
        return {"total_before": 0, "moved": 0, "already_sub": 0, "total_after": 0}

    # 1. 마이그레이션 전 전체 파일 확인
    all_webp_before = list(target_dir.rglob("*.webp"))
    direct_webp = [f for f in target_dir.iterdir() if f.is_file() and f.suffix == ".webp"]

    moved_count = 0
    already_sub_count = len(all_webp_before) - len(direct_webp)

    for f in direct_webp:
        m = CODE_PATTERN.match(f.name)
        if not m:
            print(f"  [경고] 규칙 불일치 파일 건너뜀: {f.name}")
            continue

        code = m.group(1)
        subfolder = get_subfolder_for_code(code)
        dest_dir = target_dir / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f.name

        # 대상 경로로 원자적 이동
        if dest_path.exists():
            # 이미 존재할 경우 동일 파일인지 확인 후 기존 루트 파일 제거
            if dest_path.stat().st_size == f.stat().st_size:
                f.unlink()
            else:
                dest_path.unlink()
                f.rename(dest_path)
        else:
            f.rename(dest_path)

        moved_count += 1

    all_webp_after = list(target_dir.rglob("*.webp"))
    assert len(all_webp_before) == len(all_webp_after), (
        f"파일 손실 발생! 전: {len(all_webp_before)}, 후: {len(all_webp_after)}"
    )

    return {
        "total_before": len(all_webp_before),
        "moved": moved_count,
        "already_sub": already_sub_count,
        "total_after": len(all_webp_after),
    }


def main():
    print("=" * 65)
    print("  [플에파 V3] 캠퍼스 에셋 서브폴더 무손실 마이그레이션 시작")
    print("=" * 65)

    grand_total_main = 0
    grand_total_origin = 0

    # 1. 메인 에셋 폴더 마이그레이션
    print("\n[1] 메인 에셋 (projects/campus/assets/{prefix}/)")
    for char in CHARS:
        char_dir = ASSETS_DIR / char
        stats = migrate_folder(char_dir, is_origin=False)
        grand_total_main += stats["total_after"]
        print(f"  • {char:<5}: 이동 {stats['moved']}개 / 유지 {stats['already_sub']}개 ➔ 총 {stats['total_after']}개")

    # 2. 백업 원본 폴더 마이그레이션
    print("\n[2] 백업 원본 (projects/campus/assets/{prefix}_origin/)")
    for char in CHARS:
        origin_dir = ASSETS_DIR / f"{char}_origin"
        stats = migrate_folder(origin_dir, is_origin=True)
        grand_total_origin += stats["total_after"]
        print(f"  • {char + '_origin':<11}: 이동 {stats['moved']}개 / 유지 {stats['already_sub']}개 ➔ 총 {stats['total_after']}개")

    print("\n" + "=" * 65)
    print(f"  마이그레이션 완료 검증:")
    print(f"  • 메인 에셋 합계: {grand_total_main}개 (기대값: 648개)")
    print(f"  • 백업 원본 합계: {grand_total_origin}개 (기대값: 442개)")
    print("=" * 65)

    if grand_total_main == 648 and grand_total_origin == 442:
        print("  >>> [성공] 단 1장의 손실 없이 V3 서브폴더 구조로 100% 정합성 검증 완료!")
    else:
        print("  >>> [주의] 파일 개수를 확인해 주십시오.")


if __name__ == "__main__":
    main()
