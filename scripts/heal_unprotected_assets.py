"""
scripts/heal_unprotected_assets.py
미검열 상태로 분리되지 않은 에셋 14건을 안전하게 치유하는 스크립트:
- 1. 원본 이미지를 _origin 폴더로 안전 복사 백업
- 2. 실루엣 검열 마스킹을 적용하여 메인 에셋 폴더에 덮어쓰기 저장
- 3. 치유 후 결과 검증
"""

import logging
import os
import shutil
import sys
from pathlib import Path

# Plepa 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PIL import Image
from plepa_engine.censor import censor_image
from plepa_engine.config import PROJECTS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HealAssets")

# 치유 대상 14건: (캐릭터 prefix, 포즈 코드, 서브섹터)
TARGET_ANOMALIES = [
    # 6인 공통 117번
    ("aya", "117", "05_h_scenes"),
    ("har", "117", "05_h_scenes"),
    ("kao", "117", "05_h_scenes"),
    ("mai", "117", "05_h_scenes"),
    ("shz", "117", "05_h_scenes"),
    ("yur", "117", "05_h_scenes"),
    # 개별 포즈
    ("aya", "067", "04_romance"),
    ("har", "065", "04_romance"),
    ("har", "066", "04_romance"),
    ("kao", "069", "04_romance"),
    ("mai", "067", "04_romance"),
    ("mai", "071", "04_romance"),
    ("shz", "071", "04_romance"),
    ("yur", "071", "04_romance"),
]


def heal_asset(roster: str, prefix: str, code: str, sector: str) -> bool:
    """단일 에셋을 안전하게 백업 및 실루엣 검열 처리합니다."""
    asset_dir = PROJECTS_DIR / roster / "assets" / prefix / sector
    origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin" / sector

    if not asset_dir.is_dir():
        logger.warning(f"에셋 디렉터리 없음: {asset_dir}")
        return False

    matches = list(asset_dir.glob(f"{prefix}_{code}*.webp"))
    if not matches:
        # 서브폴더 외에 상위 폴더 검색
        matches = list((PROJECTS_DIR / roster / "assets" / prefix).glob(f"{prefix}_{code}*.webp"))
        if not matches:
            logger.warning(f"[{prefix}] 포즈 {code} 대상 파일을 찾을 수 없습니다.")
            return False

    target_file = matches[0]

    # 1. _origin 폴더로 원본 무손실 백업
    origin_dir.mkdir(parents=True, exist_ok=True)
    backup_file = origin_dir / target_file.name

    if not backup_file.is_file():
        shutil.copy2(target_file, backup_file)
        logger.info(f"[{prefix}] 포즈 {code}: 원본 백업 완료 -> {backup_file.name}")
    else:
        logger.info(f"[{prefix}] 포즈 {code}: 기존 원본 백업 이미 존재함.")

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
        censored_img.save(target_file, "WEBP", quality=95)
        logger.info(f"[{prefix}] 포즈 {code}: 실루엣 검열본 덮어쓰기 완료 (감지/적용 부위: {detected_count}개)")
        return True
    except Exception as e:
        logger.error(f"[{prefix}] 포즈 {code}: 검열 처리 중 예외 발생: {e}")
        return False


def main():
    roster = "campus"
    logger.info(f"=== [{roster.upper()}] 미검열 에셋 14건 안전 치유 시작 ===")

    success_count = 0
    fail_count = 0

    for prefix, code, sector in TARGET_ANOMALIES:
        ok = heal_asset(roster, prefix, code, sector)
        if ok:
            success_count += 1
        else:
            fail_count += 1

    print("\n" + "=" * 60)
    print(f"치유 완료: 성공 {success_count}건 / 실패 {fail_count}건")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
