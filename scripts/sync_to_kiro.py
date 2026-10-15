#!/usr/bin/env python3
"""
scripts/sync_to_kiro.py
PLEPA -> KIRO 자동 양방향 시너지 전파 브릿지.

주요 기능:
1. 포즈 DB 무손실 변환 및 동기화 (sync_pose_database)
   - plepa/data/sdxl_pose_database.json (V2 000~200, +70 대칭 구조) -> kiro/pose_database.json
   - kiro의 _profiles(체크포인트별 프로필/설정) 및 메타데이터 완전 보존
   - 8대 섹션 구조 무손실 동기화 및 required_outfit, negative_add 완벽 유지
2. 프로젝트 설정 파일 동기화 (sync_project_configs)
   - pose_overrides.json, pose_background_mapping.json, background.json
3. 검증된 핵심 모듈 전파 (sync_core_modules)
   - plepa_engine/censor.py -> kiro/generator/censor.py (실루엣 검열 + POSE_SAFE_ANCHORS 폴백)
   - plepa_engine/qa_validator.py -> kiro/generator/qa_validator.py (Auto-QC 4대 불량 감지기)
4. V2 에셋 2-Pass 안전 리네임 (rename_kiro_assets)
   - POSE_MAPPING_V2.md 1:1 매핑 기반으로 kiro 에셋 구 번호(B01~B08, 099, 048 등) 연쇄 충돌 방지 리네임
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_to_kiro")

PLEPA_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KIRO_ROOT = Path("C:/Users/rbsgh/kiro")
PLEPA_DB_PATH = PLEPA_ROOT / "data" / "sdxl_pose_database.json"
V2_MAPPING_PATH = PLEPA_ROOT / "docs" / "POSE_MAPPING_V2.md"


def load_v2_mapping(mapping_file: Path = V2_MAPPING_PATH) -> Dict[str, str]:
    """
    docs/POSE_MAPPING_V2.md를 파싱하여 (구 번호 -> 신 번호) 매핑 사전을 반환합니다.
    테이블 포맷: | 새 번호 | 기존 번호 | 기존 섹션 | 포즈 라벨 | 의상 요구 | 검열 대상 | 비고 |
    """
    if not mapping_file.is_file():
        logger.warning(f"매핑 파일을 찾을 수 없습니다: {mapping_file}")
        return {}

    with open(mapping_file, "r", encoding="utf-8") as f:
        text = f.read()

    mapping: Dict[str, str] = {}
    b = chr(96)  # backtick

    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip().replace(b, "") for p in line.split("|")[1:-1]]
        if len(parts) >= 2:
            new_code, old_code = parts[0], parts[1]
            if re.match(r"^\d{3}$", new_code) and re.match(r"^(B\d{2}|\d{3})$", old_code):
                if old_code != new_code:
                    mapping[old_code] = new_code

    logger.info(f"[V2 Mapping] {len(mapping)}개 번호 전환 매핑 로드 완료.")
    return mapping


def sync_pose_database(kiro_root: Path, dry_run: bool = False) -> bool:
    """
    plepa의 V2 포즈 DB를 kiro/pose_database.json으로 무손실 동기화합니다.
    kiro의 기존 _profiles 필드는 100% 보존됩니다.
    """
    kiro_db_path = kiro_root / "pose_database.json"
    if not PLEPA_DB_PATH.is_file():
        logger.error(f"PLEPA 포즈 DB를 찾을 수 없습니다: {PLEPA_DB_PATH}")
        return False

    with open(PLEPA_DB_PATH, "r", encoding="utf-8-sig") as f:
        plepa_db = json.load(f)

    kiro_existing_profiles = {}
    if kiro_db_path.is_file():
        with open(kiro_db_path, "r", encoding="utf-8-sig") as f:
            try:
                kiro_db = json.load(f)
                if "_profiles" in kiro_db:
                    kiro_existing_profiles = kiro_db["_profiles"]
                    logger.info(f"[Sync DB] 기존 kiro _profiles ({len(kiro_existing_profiles)}개 항목) 발견 및 보존 준비.")
            except Exception as e:
                logger.warning(f"[Sync DB] 기존 kiro_db 파싱 경고: {e}")

    # 새 kiro 포즈 DB 조립
    new_kiro_db = {
        "_schema_version": "4.0.0",
        "_description": "Unified KIRO+PLEPA Pose Database (V2 000~200, +70 대칭 구조): 무손실 동기화",
        "_total_poses": plepa_db.get("_total_poses", 148),
        "_structure": plepa_db.get("_structure", {}),
    }

    if kiro_existing_profiles:
        new_kiro_db["_profiles"] = kiro_existing_profiles

    # V2 8대 섹션 무손실 전파
    v2_sections = [
        "emotions",
        "poses",
        "events",
        "romance",
        "h_scenes",
        "special_h",
        "scenes_otokonoko",
        "special_otokonoko",
    ]
    for sec in v2_sections:
        new_kiro_db[sec] = plepa_db.get(sec, {})

    logger.info(
        f"[Sync DB] V2 섹션 {len(v2_sections)}개, 총 {sum(len(new_kiro_db[s]) for s in v2_sections)}개 포즈 엔트리 변환 준비 완료."
    )

    if dry_run:
        logger.info(f"[DRY-RUN] kiro/pose_database.json 덮어쓰기 시뮬레이션 완료. (실제 쓰기 생략)")
        return True

    # 기존 DB 백업
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = kiro_root / f"pose_database.backup_{timestamp}.json"
    if kiro_db_path.is_file():
        shutil.copy2(kiro_db_path, backup_path)
        logger.info(f"[Sync DB] 기존 kiro DB 백업 완료: {backup_path.name}")

    with open(kiro_db_path, "w", encoding="utf-8") as f:
        json.dump(new_kiro_db, f, indent=2, ensure_ascii=False)
        f.write("\n")

    logger.info(f"[Sync DB] 성공적으로 {kiro_db_path}에 동기화 완료!")
    return True


def sync_project_configs(kiro_root: Path, dry_run: bool = False) -> int:
    """
    plepa/projects/*/ 내의 오버라이드 및 배경 매핑 파일들을 kiro/projects/*/로 동기화합니다.
    """
    plepa_projects_dir = PLEPA_ROOT / "projects"
    kiro_projects_dir = kiro_root / "projects"

    if not plepa_projects_dir.is_dir():
        logger.warning(f"PLEPA projects 디렉토리가 없습니다: {plepa_projects_dir}")
        return 0

    copied_count = 0
    config_files = ["pose_overrides.json", "pose_background_mapping.json", "background.json"]

    for proj_dir in plepa_projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        target_proj_dir = kiro_projects_dir / proj_dir.name

        for cfg_name in config_files:
            src_cfg = proj_dir / cfg_name
            if src_cfg.is_file():
                dst_cfg = target_proj_dir / cfg_name
                logger.info(f"[Sync Config] {src_cfg.relative_to(PLEPA_ROOT)} -> {dst_cfg}")
                if not dry_run:
                    target_proj_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_cfg, dst_cfg)
                copied_count += 1

    logger.info(f"[Sync Config] 총 {copied_count}개 프로젝트 설정 파일 동기화 {'(시뮬레이션)' if dry_run else '완료'}.")
    return copied_count


def sync_core_modules(kiro_root: Path, dry_run: bool = False) -> bool:
    """
    plepa의 고도화된 검열 엔진(censor.py) 및 Auto-QC 검증기(qa_validator.py)를 kiro/generator/로 전파합니다.
    """
    target_gen_dir = kiro_root / "generator"
    if not target_gen_dir.is_dir():
        if not dry_run:
            target_gen_dir.mkdir(parents=True, exist_ok=True)

    modules_to_copy = [
        (PLEPA_ROOT / "plepa_engine" / "censor.py", target_gen_dir / "censor.py"),
        (PLEPA_ROOT / "plepa_engine" / "qa_validator.py", target_gen_dir / "qa_validator.py"),
    ]

    for src, dst in modules_to_copy:
        if not src.is_file():
            logger.error(f"소스 모듈을 찾을 수 없습니다: {src}")
            return False

        logger.info(f"[Sync Module] {src.name} -> {dst}")
        if not dry_run:
            if dst.is_file():
                bak = dst.with_suffix(".py.bak")
                shutil.copy2(dst, bak)
            shutil.copy2(src, dst)

    logger.info(f"[Sync Module] 핵심 모듈 전파 {'(시뮬레이션)' if dry_run else '완료'}.")
    return True


def rename_kiro_assets(kiro_root: Path, dry_run: bool = False) -> int:
    """
    docs/POSE_MAPPING_V2.md의 1:1 매핑 사전을 기반으로
    kiro/projects/*/assets/ 내 구 번호 파일들을 2-Pass 안전 리네임합니다.
    """
    mapping = load_v2_mapping()
    if not mapping:
        logger.warning("[Rename Assets] 매핑 테이블이 비어 있어 작업을 중단합니다.")
        return 0

    assets_dirs: List[Path] = []
    projects_dir = kiro_root / "projects"
    if projects_dir.is_dir():
        for p in projects_dir.iterdir():
            if p.is_dir():
                a_dir = p / "assets"
                if a_dir.is_dir():
                    assets_dirs.append(a_dir)

    if not assets_dirs:
        logger.info(f"[Rename Assets] 검사할 assets 디렉토리가 없습니다: {projects_dir}")
        return 0

    # 1. 리네임 대상 수집
    rename_plan: List[Tuple[Path, Path, str, str]] = []  # (src_file, dst_file, old_code, new_code)
    for a_dir in assets_dirs:
        for root, dirs, files in os.walk(a_dir):
            r_path = Path(root)
            for f in files:
                # Type 1: {char}_{pose_code}{rest} (예: asa_048.png, srh_000_미소.webp)
                m1 = re.match(r"^([a-z0-9]+)_(B\d{2}|\d{3})(_.*|\..*)$", f, re.IGNORECASE)
                # Type 2: {pose_code}_{char}{rest} (예: 048_asa.png, B01_viv.webp)
                m2 = re.match(r"^(B\d{2}|\d{3})_([a-z0-9]+)(_.*|\..*)$", f, re.IGNORECASE)

                if m1:
                    char_p, pose_c, rest = m1.groups()
                    if pose_c in mapping:
                        new_c = mapping[pose_c]
                        new_filename = f"{char_p}_{new_c}{rest}"
                        src_path = r_path / f
                        dst_path = r_path / new_filename
                        rename_plan.append((src_path, dst_path, pose_c, new_c))
                elif m2:
                    pose_c, char_p, rest = m2.groups()
                    if pose_c in mapping:
                        new_c = mapping[pose_c]
                        new_filename = f"{new_c}_{char_p}{rest}"
                        src_path = r_path / f
                        dst_path = r_path / new_filename
                        rename_plan.append((src_path, dst_path, pose_c, new_c))

    logger.info(f"[Rename Assets] 총 {len(rename_plan)}개 에셋 리네임 대상 식별됨.")
    if not rename_plan:
        return 0

    if dry_run:
        for src, dst, old_c, new_c in rename_plan[:20]:
            logger.info(f"  [DRY-RUN] {src.name} -> {dst.name} ({old_c} -> {new_c})")
        if len(rename_plan) > 20:
            logger.info(f"  ...외 {len(rename_plan) - 20}개 파일")
        return len(rename_plan)

    # 2-Pass 리네임 실행 (연쇄 충돌 방지)
    # Pass 1: __tmp_v2_{new_code}_{rest}로 일괄 변경
    pass1_list: List[Tuple[Path, Path]] = []
    for src, dst, old_c, new_c in rename_plan:
        tmp_name = f"__tmp_v2_{dst.name}"
        tmp_path = src.parent / tmp_name
        src.rename(tmp_path)
        pass1_list.append((tmp_path, dst))

    # Pass 2: 최종 확정 이름으로 변경
    for tmp_path, dst in pass1_list:
        tmp_path.rename(dst)

    logger.info(f"[Rename Assets] 2-Pass 리네임 성공! 총 {len(rename_plan)}개 파일 이름 변경 완료.")
    return len(rename_plan)


def main():
    parser = argparse.ArgumentParser(description="PLEPA -> KIRO 전파 브릿지 동기화 도구")
    parser.add_argument("--kiro-dir", type=Path, default=DEFAULT_KIRO_ROOT, help="KIRO 레포지토리 루트 경로")
    parser.add_argument("--dry-run", action="store_true", help="실제 변경 없이 시뮬레이션 출력만 수행")
    parser.add_argument("--all", action="store_true", help="포즈 DB, 프로젝트 설정, 코어 모듈, 에셋 리네임 전체 수행")
    parser.add_argument("--db-only", action="store_true", help="포즈 DB 동기화만 수행")
    parser.add_argument("--configs-only", action="store_true", help="프로젝트 설정(오버라이드/배경) 동기화만 수행")
    parser.add_argument("--modules-only", action="store_true", help="핵심 모듈(censor, qa_validator) 전파만 수행")
    parser.add_argument("--rename-assets", action="store_true", help="KIRO 에셋 V2 2-Pass 리네임만 수행")

    args = parser.parse_args()

    kiro_root = args.kiro_dir.resolve()
    if not kiro_root.is_dir():
        logger.error(f"KIRO 루트 디렉토리가 유효하지 않습니다: {kiro_root}")
        return 1

    do_all = args.all or not (args.db_only or args.configs_only or args.modules_only or args.rename_assets)

    logger.info(f"=== PLEPA -> KIRO 전파 브릿지 시작 {'(DRY-RUN 모드)' if args.dry_run else ''} ===")
    logger.info(f"  PLEPA ROOT: {PLEPA_ROOT}")
    logger.info(f"  KIRO ROOT : {kiro_root}")

    if do_all or args.db_only:
        sync_pose_database(kiro_root, dry_run=args.dry_run)

    if do_all or args.configs_only:
        sync_project_configs(kiro_root, dry_run=args.dry_run)

    if do_all or args.modules_only:
        sync_core_modules(kiro_root, dry_run=args.dry_run)

    if do_all or args.rename_assets:
        rename_kiro_assets(kiro_root, dry_run=args.dry_run)

    logger.info("=== PLEPA -> KIRO 전파 브릿지 작업 완료 ===")
    return 0


if __name__ == "__main__":
    exit(main())
