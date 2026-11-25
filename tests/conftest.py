"""
tests/conftest.py
전체 테스트 스위트가 공유하는 데이터 주도형(Data-Driven) 동적 Fixture 모음.
포즈 DB, 로스터, 캐릭터, 프리셋이 변경되면 모든 테스트에 실시간으로 자동 반영됩니다.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# PYTHONPATH 없이도 프로젝트 루트를 패키지 검색 경로에 안전하게 삽입
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

from plepa_engine.config import PROJECTS_DIR
from plepa_engine.models import PoseEntry
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service


def _snapshot_project_assets() -> Dict[str, Tuple[int, int]]:
    """projects/*/assets 하위의 모든 기존 파일 경로 -> (size, mtime_ns) 스냅샷을 수집합니다."""
    snap: Dict[str, Tuple[int, int]] = {}
    if not PROJECTS_DIR.is_dir():
        return snap

    def _walk_scandir(root_dir: str, prefix: str) -> None:
        try:
            with os.scandir(root_dir) as it:
                for entry in it:
                    rel = f"{prefix}/{entry.name}" if prefix else entry.name
                    if entry.is_dir(follow_symlinks=False):
                        _walk_scandir(entry.path, rel)
                    elif entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        snap[rel] = (st.st_size, st.st_mtime_ns)
        except OSError:
            pass

    try:
        with os.scandir(PROJECTS_DIR) as proj_it:
            for proj in proj_it:
                if not proj.is_dir(follow_symlinks=False):
                    continue
                assets_path = os.path.join(proj.path, "assets")
                if os.path.isdir(assets_path):
                    _walk_scandir(assets_path, f"{proj.name}/assets")
    except OSError:
        pass
    return snap


@pytest.fixture(scope="session", autouse=True)
def guard_project_assets_immutability():
    """pytest 전체 세션 전후로 projects/*/assets 및 *_origin/ 파일이 단 1바이트도 변하지 않았음을 보증합니다."""
    before = _snapshot_project_assets()
    yield
    after = _snapshot_project_assets()
    if before != after:
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        modified = sorted(k for k in (set(before) & set(after)) if before[k] != after[k])
        raise AssertionError(
            "테스트 실행 중 projects/*/assets/ 무결성이 훼손되었습니다! "
            f"(added={added[:5]}, removed={removed[:5]}, modified={modified[:5]})"
        )


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
