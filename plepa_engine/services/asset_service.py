"""
plepa_engine.services.asset_service
생성된 캐릭터 에셋 파일 인덱싱, 갤러리 매트릭스 매핑, 레퍼런스 이미지 탐색 및 안전 삭제.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
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
        custom_path: Optional[str] = None
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
        """
        해당 캐릭터의 에셋 파일들을 검색하여 메타데이터 리스트를 반환합니다.
        반환: List[{ code, label, path, censored_path, size_bytes, mtime }]
        """
        asset_dir = self.get_character_asset_dir(prefix, roster)
        if not asset_dir.is_dir():
            return []

        # { "000": { "path": ..., "censored_path": ... } }
        items_by_code: Dict[str, Dict[str, Any]] = {}

        pattern = re.compile(rf"^{re.escape(prefix)}_(\d{{3}})(?:_(.*?))?(?:_censored)?\.(webp|png)$")

        for f in sorted(asset_dir.glob(f"{prefix}_*")):
            if not f.is_file():
                continue
            m = pattern.match(f.name)
            if not m:
                continue

            code = m.group(1)
            raw_label = m.group(2) or ""
            is_censored = "_censored" in f.name

            if code not in items_by_code:
                items_by_code[code] = {
                    "code": code,
                    "label": raw_label,
                    "path": None,
                    "censored_path": None,
                    "size_bytes": 0,
                    "mtime": 0.0,
                }

            if is_censored:
                items_by_code[code]["censored_path"] = f
            else:
                items_by_code[code]["path"] = f
                items_by_code[code]["label"] = raw_label or items_by_code[code]["label"]
                items_by_code[code]["size_bytes"] = f.stat().st_size
                items_by_code[code]["mtime"] = f.stat().st_mtime

        # 리스트로 변환 (정렬: 코드 오름차순)
        result = [v for k, v in sorted(items_by_code.items(), key=lambda x: int(x[0])) if v["path"] is not None]
        return result

    def get_matrix_map(
        self,
        prefixes: List[str],
        codes: List[str],
        roster: str = DEFAULT_ROSTER
    ) -> Dict[str, Dict[str, Optional[Path]]]:
        """
        캐릭터(행) x 포즈(열) 매트릭스 그리드를 위한 맵을 생성합니다.
        반환: { prefix: { code: Path 또는 None } }
        """
        matrix: Dict[str, Dict[str, Optional[Path]]] = {}
        for prefix in prefixes:
            matrix[prefix] = {code: None for code in codes}
            assets = self.list_character_assets(prefix, roster)
            for a in assets:
                c = a["code"]
                if c in matrix[prefix]:
                    matrix[prefix][c] = a["path"]
        return matrix

    def delete_asset(self, file_path: Path) -> Optional[Path]:
        """에셋 파일을 휴지통으로 안전하게 이동합니다."""
        return self.repo.move_to_trash(file_path)


default_asset_service = AssetService()
