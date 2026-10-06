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


# 전체 프로젝트 공용 배경 프리셋 (단색/무배경/미니멀 스튜디오)
COMMON_BACKGROUND_PRESETS: Dict[str, Dict[str, str]] = {
    "none": {
        "name": "배경 없음 (순백색/단색 스튜디오)",
        "sdxl": "simple background, white background, solid background, studio background",
        "flux": "Isolated on a completely solid pure white background, clean minimalist studio backdrop, plain empty background with no objects, no furniture, no scenery",
        "description": "배경 소품, 가구, 풍경을 원천 차단하고 인물만 깔끔하게 돋보이게 하는 순백색 단색 배경.",
    },
    "white_studio": {
        "name": "화이트 스튜디오 (미니멀)",
        "sdxl": "simple background, white background, clean studio lighting, soft shadows",
        "flux": "A clean pure white studio setting, minimal diffused soft light, subtle ground shadow, no background objects",
        "description": "발밑에 은은한 바닥 그림자가 떨어지는 깔끔한 미니멀 화이트 스튜디오.",
    },
    "grey_studio": {
        "name": "그레이 스튜디오 (뉴트럴 톤)",
        "sdxl": "simple background, light grey background, clean studio lighting",
        "flux": "A sleek light grey studio backdrop, neutral studio lighting, clean minimalist composition, no background objects",
        "description": "차분하고 모던한 그레이 톤의 단색 스튜디오 배경.",
    },
}


def is_no_background_preset(key: str, prompt: str = "") -> bool:
    """해당 프리셋 또는 프롬프트가 '배경 없음(순백색/단색 스튜디오)' 설정인지 판별합니다."""
    clean_key = (key or "").strip().lower()
    if clean_key in ("none", "no_bg", "nobg", "white_bg", "empty", "solid_white"):
        return True
    p_lower = (prompt or "").lower()
    if "white background" in p_lower and "simple background" in p_lower:
        return True
    if "completely solid pure white background" in p_lower:
        return True
    return False


class BackgroundService:
    """로스터별 배경 프리셋 관리자 (공용 단색/무배경 프리셋 통합 지원)."""

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or default_repo

    def _get_bg_path(self, roster: str) -> Path:
        return PROJECTS_DIR / roster / "background.json"

    def get_common_presets(self) -> Dict[str, Dict[str, str]]:
        """전역 공용 배경 프리셋 메타데이터를 반환합니다."""
        return COMMON_BACKGROUND_PRESETS

    def get_backgrounds(self, roster: str, engine: str = "sdxl") -> Dict[str, str]:
        """
        로스터의 전체 배경 프리셋을 {key: prompt} 형태로 반환합니다.
        공용 배경 프리셋('none', 'white_studio', 'grey_studio')이 항상 우선 배치됩니다.
        """
        result: Dict[str, str] = {}

        # 1. 공용 프리셋 우선 등록 (none 최우선)
        eng_key = "flux" if engine == "flux" else "sdxl"
        for k, info in COMMON_BACKGROUND_PRESETS.items():
            result[k] = info.get(eng_key, info.get("sdxl", ""))

        # 2. 로스터 전용 프리셋 병합
        bg_path = self._get_bg_path(roster)
        if bg_path.exists():
            try:
                raw = self.repo.read_json(bg_path)
                for k, v in raw.items():
                    if not k.startswith("_"):
                        clean_k = str(k).strip()
                        # 로스터에 정의된 커스텀 배경 추가/오버라이드
                        result[clean_k] = str(v).strip()
            except Exception:
                pass

        # 3. 키 정렬: 'none' -> 'white_studio' -> 'grey_studio' -> 'default' -> 가나다순
        priority_keys = ["none", "white_studio", "grey_studio", "default"]
        ordered: Dict[str, str] = {}
        for pk in priority_keys:
            if pk in result:
                ordered[pk] = result[pk]
        for k in sorted(result.keys()):
            if k not in ordered:
                ordered[k] = result[k]

        return ordered

    def get_preset(self, roster: str, key: str = "default", engine: str = "sdxl") -> str:
        """기존 CLI 호환: 지정된 프리셋 키의 프롬프트를 반환합니다."""
        clean_key = (key or "default").strip().lower()

        # 공용 프리셋 특수 처리 (엔진별 프롬프트 분기 지원)
        if clean_key in COMMON_BACKGROUND_PRESETS:
            info = COMMON_BACKGROUND_PRESETS[clean_key]
            eng_key = "flux" if engine == "flux" else "sdxl"
            # 로스터 파일에 사용자가 직접 덮어쓴 값이 있는지 먼저 확인
            bg_path = self._get_bg_path(roster)
            if bg_path.exists():
                try:
                    raw = self.repo.read_json(bg_path)
                    if clean_key in raw and raw[clean_key].strip():
                        custom_val = str(raw[clean_key]).strip()
                        # 단, FLUX 엔진인데 SDXL 단축 태그(simple background 등)만 적혀있는 경우 FLUX용 공용 프롬프트 반환
                        if engine == "flux" and "isolated on" not in custom_val.lower() and "background" in custom_val.lower():
                            return info.get("flux", custom_val)
                        return custom_val
                except Exception:
                    pass
            return info.get(eng_key, info.get("sdxl", ""))

        bgs = self.get_backgrounds(roster, engine=engine)
        return bgs.get(clean_key, bgs.get("default", ""))

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
        """배경 프리셋을 삭제합니다 ('default' 및 시스템 공용 'none'은 기본값이므로 삭제 불가)."""
        clean_key = key.strip().lower()
        if clean_key in ("default", "none", "white_studio", "grey_studio"):
            raise ValueError(f"'{clean_key}' 프리셋은 필수 시스템 프리셋이므로 삭제할 수 없습니다.")

        bg_path = self._get_bg_path(roster)
        if not bg_path.exists():
            return None
        current = self.repo.read_json(bg_path)
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

