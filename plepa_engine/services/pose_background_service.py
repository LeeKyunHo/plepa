"""포즈별 배경 자동 매핑 서비스."""
import json
from pathlib import Path
from typing import Dict, Optional

from plepa_engine.config import PROJECTS_DIR


class PoseBackgroundService:
    """로스터별 포즈-배경 자동 매핑을 관리하는 서비스."""
    
    def __init__(self):
        self.cache: Dict[str, Dict] = {}
    
    def load_mapping(self, roster: str) -> Dict:
        """로스터의 포즈-배경 매핑 데이터를 로드합니다."""
        if roster in self.cache:
            return self.cache[roster]
        
        mapping_file = PROJECTS_DIR / roster / "pose_background_mapping.json"
        
        if not mapping_file.exists():
            # 매핑 파일이 없으면 기본값 반환
            default_mapping = {
                "default_background": "default",
                "pose_mappings": {}
            }
            self.cache[roster] = default_mapping
            return default_mapping
        
        try:
            with open(mapping_file, "r", encoding="utf-8") as f:
                mapping = json.load(f)
                self.cache[roster] = mapping
                return mapping
        except Exception as e:
            print(f"[WARNING] 포즈-배경 매핑 로드 실패 ({roster}): {e}")
            default_mapping = {
                "default_background": "default",
                "pose_mappings": {}
            }
            self.cache[roster] = default_mapping
            return default_mapping
    
    @staticmethod
    def _normalize_code(pose_code: str) -> str:
        """포즈 코드를 정규화합니다 (예: '0' -> '000', 'A0' -> 'A00', 'N1' -> 'N01')."""
        s = str(pose_code).strip().upper()
        if s.isdigit():
            return f"{int(s):03d}"
        if len(s) >= 2 and s[0].isalpha() and s[1:].isdigit():
            return f"{s[0]}{int(s[1:]):02d}"
        return s

    @classmethod
    def _in_range(cls, norm_code: str, range_key: str) -> bool:
        """정규화된 포즈 코드가 '000-019' 또는 'A00-A32' 범위 키에 속하는지 확인합니다."""
        if "-" not in range_key:
            return False
        start_s, end_s = [part.strip().upper() for part in range_key.split("-", 1)]
        if norm_code.isdigit() and start_s.isdigit() and end_s.isdigit():
            return int(start_s) <= int(norm_code) <= int(end_s)
        if (
            len(norm_code) >= 2 and norm_code[0].isalpha() and norm_code[1:].isdigit()
            and len(start_s) >= 2 and start_s[0].isalpha() and start_s[1:].isdigit()
            and len(end_s) >= 2 and end_s[0].isalpha() and end_s[1:].isdigit()
            and norm_code[0] == start_s[0] == end_s[0]
        ):
            return int(start_s[1:]) <= int(norm_code[1:]) <= int(end_s[1:])
        return False

    def get_background_for_pose(self, roster: str, pose_code: str) -> str:
        """특정 포즈에 매핑된 배경 프리셋 키를 반환합니다."""
        mapping = self.load_mapping(roster)
        pose_mappings = mapping.get("pose_mappings", {})
        default_bg = mapping.get("default_background", "default")
        norm_code = self._normalize_code(pose_code)
        
        # 정확한 포즈 코드 매칭
        if norm_code in pose_mappings:
            return pose_mappings[norm_code]
        if pose_code in pose_mappings:
            return pose_mappings[pose_code]
        
        # 범위 매칭 (예: "000-019", "040-059", "A00-A32", "N01-N83")
        for key, bg in pose_mappings.items():
            if self._in_range(norm_code, key):
                return bg
        
        # 매칭 실패 시 기본 배경 반환
        return default_bg
    
    def get_backgrounds_for_poses(self, roster: str, pose_codes: list) -> Dict[str, str]:
        """여러 포즈에 대한 배경 매핑을 반환합니다."""
        result = {}
        for code in pose_codes:
            result[code] = self.get_background_for_pose(roster, code)
        return result

    def get_recommended_background_for_poses(self, roster: str, pose_codes: list) -> str:
        """선택된 포즈 코드 목록에서 가장 비중이 높은 추천 배경 프리셋 키를 반환합니다."""
        mapping = self.load_mapping(roster)
        default_bg = mapping.get("default_background", "default")
        if not pose_codes:
            return default_bg
        counts: Dict[str, int] = {}
        for code in pose_codes:
            bg = self.get_background_for_pose(roster, code)
            counts[bg] = counts.get(bg, 0) + 1
        if not counts:
            return default_bg
        return max(counts.items(), key=lambda item: item[1])[0]
    
    def clear_cache(self):
        """캐시를 초기화합니다."""
        self.cache.clear()


# 전역 싱글톤 인스턴스
default_pose_bg_service = PoseBackgroundService()
