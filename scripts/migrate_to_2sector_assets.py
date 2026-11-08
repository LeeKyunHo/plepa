"""
scripts/migrate_to_2sector_assets.py
기존 6대 서브폴더 체계(01_emotions ~ 06_special_h)의 에셋들을
사용자 요청에 맞춘 2대 통합 서브폴더 체계(01_normal, 02_h_scenes)로 무손실 안전 마이그레이션.

- 01_normal: 01_emotions, 02_daily, 03_events (000~059)
- 02_h_scenes: 04_romance, 05_h_scenes, 06_special_h (060~209+)
"""

import shutil
from pathlib import Path
from typing import Dict, List, Tuple

PROJECTS_DIR = Path("projects")

MAPPING: Dict[str, str] = {
    "01_emotions": "01_normal",
    "02_daily": "01_normal",
    "03_events": "01_normal",
    "04_romance": "02_h_scenes",
    "05_h_scenes": "02_h_scenes",
    "06_special_h": "02_h_scenes",
}


def migrate_assets(dry_run: bool = False) -> Tuple[int, int, List[str]]:
    """모든 로스터의 assets 및 _origin 서브폴더를 2대 체계로 안전 이동."""
    moved_count = 0
    removed_dirs = 0
    logs = []

    for roster_dir in sorted(PROJECTS_DIR.iterdir()):
        if not roster_dir.is_dir():
            continue
        assets_dir = roster_dir / "assets"
        if not assets_dir.is_dir():
            continue

        for char_dir in sorted(assets_dir.iterdir()):
            if not char_dir.is_dir():
                continue

            for old_sub, new_sub in MAPPING.items():
                old_path = char_dir / old_sub
                if not old_path.is_dir():
                    continue

                target_dir = char_dir / new_sub
                if not dry_run:
                    target_dir.mkdir(parents=True, exist_ok=True)

                for item in list(old_path.iterdir()):
                    if item.is_file():
                        dst_file = target_dir / item.name
                        if dst_file.exists():
                            # 동일 파일 존재 시 크기 확인
                            if dst_file.stat().st_size == item.stat().st_size:
                                logs.append(f"[중복보존] {item} -> {dst_file} (동일 크기이므로 기존 유지)")
                                if not dry_run:
                                    item.unlink()
                            else:
                                logs.append(f"[충돌경고] {item} -> {dst_file} (크기 상이, 원본 보존 유지)")
                                continue
                        else:
                            if not dry_run:
                                shutil.move(str(item), str(dst_file))
                            moved_count += 1

                # 빈 디렉터리 정리
                remaining = list(old_path.iterdir())
                if len(remaining) == 0:
                    if not dry_run:
                        old_path.rmdir()
                    removed_dirs += 1
                else:
                    logs.append(f"[남은파일] {old_path}에 {len(remaining)}개 파일 잔여로 삭제 보류")

    return moved_count, removed_dirs, logs


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    print(f"=== 플에파 에셋 2대 서브폴더 체계(01_normal, 02_h_scenes) 마이그레이션 (dry_run={dry}) ===")
    moved, removed, logs = migrate_assets(dry_run=dry)
    for l in logs:
        print(l)
    print(f"\n완료: 총 {moved}개 에셋 이동, {removed}개 구버전 서브폴더 정리 완료.")
