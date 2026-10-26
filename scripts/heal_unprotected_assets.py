"""
scripts/heal_unprotected_assets.py
미검열 상태로 분리되지 않은 에셋을 안전하게 치유하고 남성기(penis) 전용 검열을 정합화하는 스크립트:
- 1. 원본 이미지를 _origin 폴더로 안전 복사 백업 (무손실 보존)
- 2. 사용자 정책에 따라 남성기(penis) 부위만 실루엣 마스킹 적용 (여성 신체 부위는 100% 무손실 보존)
- 3. 남성기 미검출 씬 및 여성 단독 노출 씬(목욕/샤워 등)은 마스킹 없이 깨끗한 원본으로 자동 복원
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
    """단일 에셋을 안전하게 원본 백업 및 남성기(penis) 전용 실루엣 검열 처리합니다."""
    origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin" / sector
    origin_dir.mkdir(parents=True, exist_ok=True)
    backup_file = origin_dir / file_path.name

    # 1. _origin 폴더로 원본 무손실 백업
    if not backup_file.is_file():
        shutil.copy2(file_path, backup_file)
        logger.info(f"[{prefix}] #{code}: 원본 무손실 백업 완료 -> {backup_file.name}")
    else:
        logger.debug(f"[{prefix}] #{code}: 기존 원본 백업 존재함.")

    # 2. 원본 이미지를 열고 남성기(penis) 전용 실루엣 검열 적용 (여성 신체는 100% 보존)
    try:
        src_img = Image.open(backup_file).convert("RGB")
        censored_img, detected_count = censor_image(
            src_img,
            style="white_silhouette",
            targets=("penis",),
            pose_code=code,
            enable_anchor_fallback=False,
        )

        # 3. 메인 에셋 파일에 저장: 남성기 미검출 시 깨끗한 원본 그대로 복원, 검출 시 마스킹본 적용
        if detected_count > 0:
            censored_img.save(file_path, "WEBP", quality=95)
            logger.info(f"[{prefix}] #{code}: 남성기 실루엣 검열본 적용 완료 (감지 부위: {detected_count}개)")
        else:
            shutil.copy2(backup_file, file_path)
            logger.info(f"[{prefix}] #{code}: 남성기 없음(여성 단독 씬 등) -> 무손실 원본 복원 완료")
        return True
    except Exception as e:
        logger.error(f"[{prefix}] #{code}: 검열 처리 중 예외 발생: {e}")
        return False


def heal_roster(roster: str, reapply: bool = False) -> Tuple[int, int]:
    """지정된 로스터 내의 모든 캐릭터 에셋을 점검하고 남성기 전용 검열 및 원본 복원을 수행합니다."""
    logger.info(f"=== [{roster.upper()}] 로스터 에셋 남성기 전용 검열 및 무손실 원본 정합성 작업 시작 ===")
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

            # 서브섹터 확인
            rel_parts = file_path.relative_to(asset_dir).parts
            if len(rel_parts) > 1:
                sector = rel_parts[0]
            else:
                sector = get_subfolder_for_code(code)

            origin_file = origin_root / sector / file_path.name

            # 여성 단독 노출 씬 등 검열 대상이 아닌 포즈가 과거에 마스킹된 경우 무손실 원본으로 깨끗이 복원
            if not is_pose_censor_required(pose_code=code, file_path=file_path):
                if origin_file.is_file():
                    shutil.copy2(origin_file, file_path)
                    logger.info(f"[{prefix}] #{code}: 비검열 여성 씬 무손실 원본 복원 완료 -> {file_path.name}")
                    success_count += 1
                continue

            # 이미 원본 백업이 존재하고 재적용 모드가 아니면 스킵
            if origin_file.is_file() and not reapply:
                continue

            ok = heal_single_asset(roster, prefix, code, sector, file_path)
            if ok:
                success_count += 1
            else:
                fail_count += 1

    return success_count, fail_count


def main():
    parser = argparse.ArgumentParser(description="남성기 전용 안전 치유 및 _origin 무손실 복원 도구")
    parser.add_argument("--roster", "-r", default="campus", help="치유 대상 로스터 폴더 (기본: campus)")
    parser.add_argument("--reapply", action="store_true", help="기존 백업본에 대해 남성기 전용 검열을 재적용")
    args = parser.parse_args()

    success, fail = heal_roster(args.roster, reapply=args.reapply)

    print("\n" + "=" * 60)
    print(f"[{args.roster.upper()}] 정합화 완료: 성공 {success}건 / 실패 {fail}건")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
