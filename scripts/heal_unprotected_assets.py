"""
scripts/heal_unprotected_assets.py
미검열 상태로 분리되지 않은 에셋을 안전하게 치유하는 스크립트:
- 1. 원본 이미지를 _origin 폴더로 안전 복사 백업 (무손실 보존)
- 2. 실루엣 검열 마스킹을 적용하여 메인 에셋 폴더에 덮어쓰기 저장
- 3. 치유 후 결과 검증
"""

import argparse
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Tuple

# Plepa 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PIL import Image
from plepa_engine.censor import censor_image, is_pose_censor_required
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.reporter import get_subfolder_for_code
from plepa_engine.services.character_service import CharacterService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HealAssets")


def heal_single_asset(roster: str, prefix: str, code: str, sector: str, file_path: Path) -> bool:
    """단일 에셋을 안전하게 원본 백업 및 실루엣 검열 처리합니다."""
    origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin" / sector
    origin_dir.mkdir(parents=True, exist_ok=True)
    backup_file = origin_dir / file_path.name

    # 1. _origin 폴더로 원본 무손실 백업
    if not backup_file.is_file():
        shutil.copy2(file_path, backup_file)
        logger.info(f"[{prefix}] #{code}: 원본 무손실 백업 완료 -> {backup_file.name}")
    else:
        logger.debug(f"[{prefix}] #{code}: 기존 원본 백업 존재함.")

    # 2. 원본 이미지를 열고 실루엣 검열 적용 (안전 앵커 폴백 활성화)
    try:
        src_img = Image.open(backup_file).convert("RGB")
        censored_img, detected_count = censor_image(
            src_img,
            style="white_silhouette",
            targets=("all",),
            pose_code=code,
            enable_anchor_fallback=True,
        )

        # 3. 메인 에셋 파일에 덮어쓰기 저장
        censored_img.save(file_path, "WEBP", quality=95)
        logger.info(f"[{prefix}] #{code}: 실루엣 검열본 덮어쓰기 완료 (감지/적용 부위: {detected_count}개)")
        return True
    except Exception as e:
        logger.error(f"[{prefix}] #{code}: 검열 처리 중 예외 발생: {e}")
        return False


def heal_roster(roster: str) -> Tuple[int, int]:
    """지정된 로스터 내의 모든 캐릭터 에셋 중 검열 대상이나 원본 분리가 안 된 항목을 치유합니다."""
    logger.info(f"=== [{roster.upper()}] 로스터 에셋 검열 및 원본 백업 치유 시작 ===")
    char_svc = CharacterService()
    chars = char_svc.list_characters(roster)
    if not chars:
        logger.warning(f"로스터 '{roster}'에 등록된 캐릭터가 없습니다.")
        return 0, 0

    pattern = re.compile(r"^[A-Za-z0-9]+_([A-Za-z0-9]+)(?:_.*)?\.(webp|png)$")
    success_count = 0
    fail_count = 0

    for item in chars:
        char = item[1] if isinstance(item, tuple) and len(item) > 1 else item
        prefix = char.prefix
        asset_dir = PROJECTS_DIR / roster / "assets" / prefix
        origin_root = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin"

        if not asset_dir.is_dir():
            continue

        files = sorted(list(asset_dir.rglob("*.webp")) + list(asset_dir.rglob("*.png")))
        files = [f for f in files if "_trash" not in f.parts and f.is_file()]

        for file_path in files:
            m = pattern.match(file_path.name)
            if not m:
                continue
            code = m.group(1)

            # 검열 필요 여부
            if not is_pose_censor_required(pose_code=code, file_path=file_path):
                continue

            # 서브섹터 확인
            rel_parts = file_path.relative_to(asset_dir).parts
            if len(rel_parts) > 1:
                sector = rel_parts[0]
            else:
                sector = get_subfolder_for_code(code)

            # 원본 백업 존재 여부 확인
            origin_file = origin_root / sector / file_path.name
            if origin_file.is_file():
                continue

            ok = heal_single_asset(roster, prefix, code, sector, file_path)
            if ok:
                success_count += 1
            else:
                fail_count += 1

    return success_count, fail_count


def main():
    parser = argparse.ArgumentParser(description="미검열 에셋 안전 치유 및 _origin 무손실 백업 도구")
    parser.add_argument("--roster", "-r", default="campus", help="치유 대상 로스터 폴더 (기본: campus)")
    args = parser.parse_args()

    success, fail = heal_roster(args.roster)

    print("\n" + "=" * 60)
    print(f"[{args.roster.upper()}] 치유 완료: 성공 {success}건 / 실패 {fail}건")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
