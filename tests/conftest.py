"""
tests/conftest.py
전체 테스트 스위트가 공유하는 데이터 주도형(Data-Driven) 동적 Fixture 모음.
포즈 DB, 로스터, 캐릭터, 프리셋이 변경되면 모든 테스트에 실시간으로 자동 반영됩니다.
"""

from pathlib import Path
from typing import Dict, List
import pytest

from plepa_engine.config import PROJECTS_DIR
from plepa_engine.models import PoseEntry
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service


@pytest.fixture(scope="session")
def core_sdxl_db() -> Dict[str, PoseEntry]:
    """코어 SDXL 포즈 DB."""
    return default_pose_service.load_pose_db(engine="sdxl")


@pytest.fixture(scope="session")
def campus_sdxl_db() -> Dict[str, PoseEntry]:
    """캠퍼스 로스터 이벤트가 병합된 SDXL 포즈 DB."""
    return default_pose_service.load_pose_db(engine="sdxl", roster="campus")


@pytest.fixture(scope="session")
def active_rosters() -> List[str]:
    """실제 캐릭터 JSON이 존재하는 활성 로스터 목록을 동적으로 스캔."""
    rosters = []
    if PROJECTS_DIR.is_dir():
        for d in sorted(PROJECTS_DIR.iterdir()):
            if d.is_dir() and (d / "characters").is_dir():
                if any((d / "characters").glob("*.json")):
                    rosters.append(d.name)
    return rosters
