"""
tests/test_directory_structure.py
리팩토링된 디렉토리 구조(data/, data/themes/, docs/, scripts/) 및 config.py 경로 상수 무결성 검증 테스트.
"""

from pathlib import Path
from plepa_engine.config import (
    DATA_DIR,
    DOCS_DIR,
    FLUX_POSE_DB_PATH,
    POSE_DB_PATH,
    POSE_SETS_PATH,
    PROJECTS_DIR,
    ROOT_DIR,
    SCRIPTS_DIR,
    SDXL_POSE_DB_PATH,
    THEMES_DIR,
)
from plepa_engine.services.pose_service import default_pose_service


def test_core_directories_exist():
    """핵심 폴더(data, data/themes, docs, scripts, projects)가 모두 존재하는지 검증."""
    assert DATA_DIR.is_dir(), f"DATA_DIR 누락: {DATA_DIR}"
    assert THEMES_DIR.is_dir(), f"THEMES_DIR 누락: {THEMES_DIR}"
    assert DOCS_DIR.is_dir(), f"DOCS_DIR 누락: {DOCS_DIR}"
    assert SCRIPTS_DIR.is_dir(), f"SCRIPTS_DIR 누락: {SCRIPTS_DIR}"
    assert PROJECTS_DIR.is_dir(), f"PROJECTS_DIR 누락: {PROJECTS_DIR}"


def test_data_files_exist_and_loadable():
    """data/ 내부의 포즈 데이터베이스, 포즈 세트, 테마 파일들이 정상 로드되는지 검증."""
    assert SDXL_POSE_DB_PATH.is_file(), f"SDXL 포즈 DB 누락: {SDXL_POSE_DB_PATH}"
    assert FLUX_POSE_DB_PATH.is_file(), f"FLUX 포즈 DB 누락: {FLUX_POSE_DB_PATH}"
    assert POSE_DB_PATH == SDXL_POSE_DB_PATH
    assert POSE_SETS_PATH.is_file(), f"포즈 세트 파일 누락: {POSE_SETS_PATH}"

    theme_files = list(THEMES_DIR.glob("*.json"))
    assert len(theme_files) >= 7, f"data/themes/ 내 테마 팩 누락: {len(theme_files)}개 발견"

    # 실제 서비스를 통한 로드 검증
    sdxl_db = default_pose_service.load_pose_db(engine="sdxl")
    flux_db = default_pose_service.load_pose_db(engine="flux")
    assert len(sdxl_db) >= 120
    assert len(flux_db) >= 120
    assert "A00" in sdxl_db
    assert "A00" in flux_db

    pose_sets = default_pose_service.load_pose_sets()
    assert len(pose_sets) > 0


def test_root_directory_cleanliness():
    """루트 디렉토리에 낱개 포즈 JSON이나 불필요한 문서가 흩어져 있지 않은지 검증."""
    assert not (ROOT_DIR / "sdxl_pose_database.json").exists()
    assert not (ROOT_DIR / "flux_pose_database.json").exists()
    assert not (ROOT_DIR / "pose_sets.json").exists()
    assert not (ROOT_DIR / "themes").exists()

    # 필수 루트 파일 존재 확인
    assert (ROOT_DIR / "flux_batch_generator.py").is_file()
    assert (ROOT_DIR / "run_gui.bat").is_file()
    assert (ROOT_DIR / "GEMINI.md").is_file()
    assert (ROOT_DIR / "README.md").is_file()


def test_docs_and_scripts_exist():
    """docs/ 및 scripts/ 내 주요 문서와 스크립트 존재 검증."""
    assert (DOCS_DIR / "AI_HANDOVER_GUIDE.md").is_file()
    assert (DOCS_DIR / "DOCUMENTATION_GUIDE.md").is_file()
    assert (DOCS_DIR / "플에파_기능명세.md").is_file()
    assert (DOCS_DIR / "개발일지.md").is_file()
    assert (SCRIPTS_DIR / "plepa_upscaler.py").is_file()
