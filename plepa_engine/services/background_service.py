"""
plepa_engine.services.background_service
배경 프리셋(projects/{roster}/background.json) CRUD 및 린터 경고 서비스.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.repository import Repository, default_repo

# SDXL 언홀리 및 2D 셀화에서 선화 뭉개짐이나 과도한 실사 블러를 유발하는 위험 키워드 목록
DISCOURAGED_TAGS = [
    ("depth of field", "피사계 심도로 인해 선화와 배경 디테일이 뭉개질 수 있습니다."),
    ("blurry background", "배경 블러로 인해 2D 셀화 느낌이 흐려질 수 있습니다."),
    ("bokeh", "실사 렌즈 보케 효과로 2D 애니 질감이 저하될 수 있습니다."),
    ("photorealistic", "실사 질감 키워드로 인해 애니메이션 화풍이 깨질 수 있습니다."),
]


class BackgroundService:
    """로스터별 배경 프리셋 관리자."""

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or default_repo

    def _get_bg_path(self, roster: str) -> Path:
        return PROJECTS_DIR / roster / "background.json"

    def get_backgrounds(self, roster: str) -> Dict[str, str]:
        """로스터의 전체 배경 프리셋을 {key: prompt} 형태로 반환합니다."""
        bg_path = self._get_bg_path(roster)
        if not bg_path.exists():
            return {}
        try:
            raw = self.repo.read_json(bg_path)
            return {k: str(v) for k, v in raw.items() if not k.startswith("_")}
        except Exception:
            return {}

    def get_preset(self, roster: str, key: str = "default") -> str:
        """기존 CLI 호환: 지정된 프리셋 키의 프롬프트를 반환합니다."""
        bgs = self.get_backgrounds(roster)
        return bgs.get(key, bgs.get("default", ""))

    def save_preset(self, roster: str, key: str, prompt: str) -> Path:
        """배경 프리셋을 추가하거나 수정합니다 (원자적 저장)."""
        clean_key = key.strip().lower()
        if not clean_key:
            raise ValueError("프리셋 키는 비어있을 수 없습니다.")

        bg_path = self._get_bg_path(roster)
        current = self.get_backgrounds(roster)
        current[clean_key] = prompt.strip()

        return self.repo.write_json(bg_path, current)

    def delete_preset(self, roster: str, key: str) -> Optional[Path]:
        """배경 프리셋을 삭제합니다 ('default'는 기본값이므로 삭제 불가)."""
        clean_key = key.strip().lower()
        if clean_key == "default":
            raise ValueError("'default' 배경 프리셋은 기본값이므로 삭제할 수 없습니다.")

        bg_path = self._get_bg_path(roster)
        current = self.get_backgrounds(roster)
        if clean_key in current:
            del current[clean_key]
            return self.repo.write_json(bg_path, current)
        return None

    def lint_prompt(self, prompt: str) -> List[str]:
        """배경 프롬프트 내 잠재적 화질 저하 키워드를 검사하여 경고 목록을 반환합니다."""
        p_lower = prompt.lower()
        warnings: List[str] = []
        for tag, reason in DISCOURAGED_TAGS:
            if tag in p_lower:
                warnings.append(f"[{tag}] {reason}")
        return warnings


default_background_service = BackgroundService()
