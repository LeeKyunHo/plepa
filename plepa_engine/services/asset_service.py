"""
plepa_engine.services.asset_service
생성된 캐릭터 에셋 파일 인덱싱, 갤러리 매트릭스 매핑, 레퍼런스 이미지 탐색 및 안전 삭제.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.asset_helpers import (
    build_character_audit_summary,
    move_asset_bundle_to_trash,
    restore_file_from_origin,
    restore_trash_bundle,
    scan_character_assets,
    scan_misc_assets_in_roster,
)
from plepa_engine.services.repository import Repository, default_repo


class AssetService:
    """에셋 파일 및 갤러리 데이터 관리 서비스."""

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or default_repo

    def get_character_asset_dir(self, prefix: str, roster: str = DEFAULT_ROSTER) -> Path:
        """캐릭터 에셋 디렉터리 경로 반환."""
        return PROJECTS_DIR / roster / "assets" / prefix

    def find_reference_image(
        self,
        prefix: str,
        roster: str = DEFAULT_ROSTER,
        custom_path: Optional[str] = None,
    ) -> Optional[Path]:
        """캐릭터의 참조 이미지를 탐색합니다 (지정 경로 -> references/{prefix}.{ext} 순)."""
        if custom_path:
            p = Path(custom_path)
            if p.is_file():
                return p
            cand = PROJECTS_DIR / roster / "references" / custom_path
            if cand.is_file():
                return cand
            raise FileNotFoundError(f"지정한 레퍼런스 이미지를 찾을 수 없습니다: {custom_path}")

        ref_dir = PROJECTS_DIR / roster / "references"
        if not ref_dir.is_dir():
            return None

        for ext in (".webp", ".png", ".jpg", ".jpeg"):
            cand = ref_dir / f"{prefix}{ext}"
            if cand.is_file():
                return cand

        return None

    def list_character_assets(self, prefix: str, roster: str = DEFAULT_ROSTER) -> List[Dict[str, Any]]:
        """해당 캐릭터의 에셋 파일들을 검색하여 메타데이터 리스트를 반환합니다."""
        asset_dir = self.get_character_asset_dir(prefix, roster)
        origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin"
        return scan_character_assets(asset_dir, origin_dir, prefix)

    def get_matrix_map(
        self,
        prefixes: List[str],
        codes: List[str],
        roster: str = DEFAULT_ROSTER,
    ) -> Dict[str, Dict[str, Optional[Path]]]:
        """캐릭터(행) x 포즈(열) 매트릭스 그리드를 위한 맵을 생성합니다."""
        matrix: Dict[str, Dict[str, Optional[Path]]] = {}
        for prefix in prefixes:
            matrix[prefix] = {code: None for code in codes}
            for a in self.list_character_assets(prefix, roster):
                c = a["code"]
                if c in matrix[prefix]:
                    matrix[prefix][c] = a["path"]
        return matrix

    def delete_asset(self, file_path: Path) -> Optional[Path]:
        """에셋 파일을 휴지통으로 안전하게 이동합니다."""
        return self.repo.move_to_trash(file_path)

    def delete_asset_bundle(self, file_path: Path) -> Dict[str, Any]:
        """에셋 파일과 관련된 쌍둥이 에셋(원본 _origin, 검열본 _censored)을 함께 휴지통으로 안전 이동합니다."""
        return move_asset_bundle_to_trash(self.repo, file_path)

    def restore_asset_bundle(self, moved_list: List[Dict[str, str]]) -> bool:
        """휴지통으로 이동되었던 에셋 번들을 원래 위치로 원자적으로 복원(Undo)합니다."""
        return restore_trash_bundle(moved_list, PROJECTS_DIR)

    def get_missing_poses_by_character(self, roster: str = DEFAULT_ROSTER) -> Dict[str, List[str]]:
        """로스터 내 각 캐릭터별로 아직 생성되지 않은(누락된) 포즈 코드 목록을 전수 계산합니다."""
        from plepa_engine.services.character_service import default_character_service
        from plepa_engine.services.pose_service import default_pose_service

        chars = default_character_service.list_characters(roster=roster)
        pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
        expected_base_codes = default_pose_service.resolve_pose_codes("all", pose_db, roster=roster)

        missing_map: Dict[str, List[str]] = {}
        for char_item in chars:
            if isinstance(char_item, tuple):
                char_obj = char_item[1]
                prefix = getattr(char_obj, "prefix", str(char_item[0]))
            else:
                prefix, char_obj = char_item.prefix, char_item
            existing_codes = {a["code"] for a in self.list_character_assets(prefix, roster)}
            expected_codes = {
                c for c in expected_base_codes
                if default_pose_service.is_pose_allowed_for_character(
                    pose_db.get(c), char_obj, roster=roster, code=c
                )
            }
            missing_map[prefix] = sorted(list(expected_codes - existing_codes))

        return missing_map

    def list_misc_assets(self, roster: str = DEFAULT_ROSTER) -> List[Dict[str, Any]]:
        """포즈 번호 규격에 묶이지 않은 비포즈 에셋(레퍼런스, 배경, 샘플, 비규격 이미지)을 모두 검색합니다."""
        return scan_misc_assets_in_roster(PROJECTS_DIR / roster)

    def restore_from_origin(self, prefix: str, code: str, roster: str = DEFAULT_ROSTER) -> bool:
        """assets/{prefix}_origin/ 폴더의 원본 파일을 assets/{prefix}/로 덮어써서 무검열 원본으로 복원합니다."""
        from plepa_engine.reporter import get_subfolder_for_code
        from plepa_engine.services.pose_service import default_pose_service

        origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin"
        asset_dir = self.get_character_asset_dir(prefix, roster)
        code_str = default_pose_service.normalize_code(code)
        subfolder = get_subfolder_for_code(code_str)
        return restore_file_from_origin(origin_dir, asset_dir, prefix, code_str, subfolder)

    def audit_roster_assets(self, roster: str = DEFAULT_ROSTER) -> List[Dict[str, Any]]:
        """지정된 로스터 내 모든 캐릭터의 에셋 완비 상태, 누락 포즈, 구버전 라벨 불일치, _origin 백업 보유 여부를 감사하여 반환합니다."""
        from plepa_engine.services.character_service import default_character_service
        from plepa_engine.services.pose_service import default_pose_service

        char_dir = PROJECTS_DIR / roster / "characters"
        if not char_dir.is_dir():
            return []

        pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
        expected_codes = default_pose_service.resolve_pose_codes("all", pose_db, roster=roster)
        results: List[Dict[str, Any]] = []

        for cf in sorted(char_dir.glob("*.json")):
            try:
                char_obj, _ = default_character_service.find_character(cf.stem, roster=roster)
            except Exception:
                continue

            prefix = char_obj.prefix
            char_expected_codes = [
                c for c in expected_codes
                if default_pose_service.is_pose_allowed_for_character(
                    pose_db.get(c), char_obj, roster=roster, code=c
                )
            ]
            assets = self.list_character_assets(prefix, roster=roster)
            results.append(build_character_audit_summary(char_obj, char_expected_codes, assets, pose_db))

        return results


default_asset_service = AssetService()
