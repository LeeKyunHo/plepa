"""
plepa_engine.services.pose_service
SDXL 단일 진실 공급원(SSOT) 포즈 DB CRUD, 소프트 삭제, 라벨 변경 시 에셋 파일명 리네임 트랜잭션, 포즈 세트 관리.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plepa_engine.config import (
    DEFAULT_ROSTER,
    FLUX_POSE_DB_PATH,
    POSE_DB_PATH,
    POSE_SETS_PATH,
    PROJECTS_DIR,
    ROOT_DIR,
    SDXL_POSE_DB_PATH,
    THEMES_DIR,
)
from plepa_engine.models import PoseEntry
from plepa_engine.services.pose_resolver import (
    OPTIONAL_COSTUME_SECTIONS,
    ROSTER_THEME_MAP,
    SECTION_METADATA,
    SECTION_NAMES,
    THEME_ACTION_SECTIONS,
    is_pose_allowed_for_character as _is_pose_allowed_impl,
    normalize_pose_code,
    resolve_pose_codes_expr,
)
from plepa_engine.services.pose_storage import (
    check_pose_doc_sync_impl,
    find_pose_details_dict,
    load_or_init_pose_sets,
    load_pose_db_entries,
    plan_pose_asset_renames,
)
from plepa_engine.services.repository import Repository, default_repo
from plepa_engine.services.schemas import PoseFlags, PoseItemSchema, PoseSetSchema

logger = logging.getLogger(__name__)
POSE_SETS_FILE = POSE_SETS_PATH


class PoseService:
    """듀얼 엔진 포즈 데이터베이스 및 포즈 세트 관리 서비스."""

    ROSTER_THEME_MAP: Dict[str, List[str]] = ROSTER_THEME_MAP
    OPTIONAL_COSTUME_SECTIONS: set = OPTIONAL_COSTUME_SECTIONS
    THEME_ACTION_SECTIONS: set = THEME_ACTION_SECTIONS

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or default_repo

    def _get_db_path(self, engine: str) -> Path:
        return SDXL_POSE_DB_PATH if engine.lower() == "sdxl" else FLUX_POSE_DB_PATH

    def get_section_registry(self) -> Dict[str, Dict[str, Any]]:
        """등록된 모든 섹션의 메타데이터(라벨, 아이콘, 정렬순서)를 반환합니다."""
        return SECTION_METADATA

    def get_active_sections(self, engine: str = "sdxl", roster: Optional[str] = None) -> List[Dict[str, Any]]:
        """현재 DB에 실제 포즈가 1개 이상 존재하는 활성 섹션 목록을 정렬하여 반환합니다 (UI 완전 자동 동기화용)."""
        db = self.load_pose_db(engine=engine, roster=roster)
        present_sections = {e.section for e in db.values() if e.section}
        result = []
        for sec_id, meta in sorted(SECTION_METADATA.items(), key=lambda x: x[1].get("order", 99)):
            if sec_id in present_sections:
                count = sum(1 for e in db.values() if e.section == sec_id)
                result.append({
                    "id": sec_id,
                    "name": meta["name"],
                    "short_label": meta["short_label"],
                    "icon": meta.get("icon", "📁"),
                    "count": count,
                })
        return result

    @staticmethod
    def normalize_code(code: Any) -> str:
        """포즈 코드를 정규화합니다 (숫자는 3자리 000, 영문+숫자는 D01, A01 형태로 패딩)."""
        return normalize_pose_code(code)

    def load_pose_db(
        self,
        engine: str = "sdxl",
        path: Optional[Path] = None,
        roster: Optional[str] = None,
    ) -> Dict[str, PoseEntry]:
        """기존 CLI 호환: 엔진별 포즈 DB를 로드하여 {코드: PoseEntry} 딕셔너리로 반환. 로스터/테마 포즈 자동 병합."""
        target_path = path or self._get_db_path(engine)
        return load_pose_db_entries(
            self.repo, target_path, engine, roster, PROJECTS_DIR, THEMES_DIR, ROOT_DIR
        )

    @staticmethod
    def is_pose_allowed_for_character(
        pose_entry: Optional[PoseEntry],
        char_obj: Any,
        roster: str = DEFAULT_ROSTER,
        code: str = "",
    ) -> bool:
        """포즈 메타데이터(section, target_gender, allowed_rosters) 및 캐릭터 젠더 기반 적합성을 판별합니다."""
        return _is_pose_allowed_impl(pose_entry, char_obj, roster=roster, code=code)

    def resolve_pose_codes(
        self,
        expr: str,
        db: Dict[str, PoseEntry],
        roster: Optional[str] = None,
    ) -> List[str]:
        """사용자가 지정한 포즈 표현식(all, emotions, swim, 00..19, D01,D02 등)을 코드 목록으로 해석 (기존 CLI 호환)."""
        return resolve_pose_codes_expr(expr, db, self.load_pose_sets, roster=roster)

    def get_pose_details(self, code: str) -> Dict[str, Any]:
        """SDXL 단일 진실 공급원(SSOT) DB 및 테마 JSON에서 해당 코드의 상세 정보를 읽어 반환합니다."""
        return find_pose_details_dict(
            self.repo, self.normalize_code(code), SDXL_POSE_DB_PATH, THEMES_DIR, PROJECTS_DIR
        )

    def update_pose(
        self,
        code: str,
        label: str,
        description: str,
        flags: Optional[Dict[str, Any]] = None,
        flux_prompt: Optional[str] = None,
        sdxl_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """SDXL 단일 진실 공급원(data/sdxl_pose_database.json)에 포즈 필드를 기록합니다."""
        del flux_prompt
        code_str = self.normalize_code(code)
        sdxl_raw = self.repo.read_json(SDXL_POSE_DB_PATH)

        target_section = None
        for sec in SECTION_NAMES:
            if code_str in sdxl_raw.get(sec, {}):
                target_section = sec
                break
        if not target_section:
            raise KeyError(f"포즈 코드 '{code_str}'를 SDXL 데이터베이스에서 찾을 수 없습니다.")

        s_entry = sdxl_raw.setdefault(target_section, {}).setdefault(code_str, {})
        s_entry["label"] = label.strip()
        s_entry["description"] = description.strip()
        if flags is not None:
            s_entry["flags"] = flags
        if sdxl_prompt is not None:
            s_entry["prompt"] = sdxl_prompt.strip()

        self.repo.write_json(SDXL_POSE_DB_PATH, sdxl_raw)
        return self.get_pose_details(code_str)

    def plan_asset_rename(self, code: str, old_label: str, new_label: str) -> List[Tuple[Path, Path]]:
        """라벨 변경 시 영향을 받는 기존 에셋 파일들의 변경 전/후 경로 목록을 시뮬레이션(Dry-run)합니다."""
        return plan_pose_asset_renames(PROJECTS_DIR, self.normalize_code(code), old_label, new_label)

    def apply_asset_rename(self, plan: List[Tuple[Path, Path]]) -> int:
        """plan_asset_rename으로 생성된 파일명 변경 계획을 실제 실행합니다."""
        renamed_count = 0
        for src, dst in plan:
            if src.exists() and not dst.exists():
                os.replace(src, dst)
                renamed_count += 1
        return renamed_count

    def set_pose_disabled(self, code: str, disabled: bool = True) -> None:
        """포즈 소프트 삭제/복구 (disabled 플래그 설정). 번호는 절대 당기지 않음."""
        details = self.get_pose_details(code)
        flags = dict(details.get("flags") or {})
        flags["disabled"] = disabled
        self.update_pose(
            code=code,
            label=details["label"],
            description=details["description"],
            flags=flags,
        )

    def load_pose_sets(self) -> List[PoseSetSchema]:
        """포즈 세트 목록을 로드합니다."""
        return load_or_init_pose_sets(self.repo, POSE_SETS_FILE, self.save_all_pose_sets)

    def save_all_pose_sets(self, sets: List[PoseSetSchema]) -> None:
        """전체 포즈 세트 목록을 저장합니다."""
        self.repo.write_json(POSE_SETS_FILE, [s.model_dump() for s in sets])

    def save_pose_set(self, new_set: PoseSetSchema) -> None:
        """포즈 세트를 추가하거나 기존 ID의 세트를 업데이트합니다."""
        current_sets = self.load_pose_sets()
        idx = next((i for i, s in enumerate(current_sets) if s.id == new_set.id), None)
        if idx is not None:
            current_sets[idx] = new_set
        else:
            current_sets.append(new_set)
        self.save_all_pose_sets(current_sets)

    def delete_pose_set(self, set_id: str) -> None:
        """포즈 세트를 삭제합니다."""
        current_sets = self.load_pose_sets()
        self.save_all_pose_sets([s for s in current_sets if s.id != set_id])

    def check_pose_doc_sync(
        self,
        doc_path: Optional[Path] = None,
        engine: str = "sdxl",
    ) -> Tuple[bool, List[str]]:
        """포즈 데이터베이스(SSOT)와 포즈 매핑 문서(POSE_MAPPING.md) 간의 포즈 코드 동기화 상태를 검증합니다."""
        target_doc = doc_path or (ROOT_DIR / "POSE_MAPPING.md")
        db_path = SDXL_POSE_DB_PATH if engine == "sdxl" else FLUX_POSE_DB_PATH
        return check_pose_doc_sync_impl(self.repo, db_path, target_doc)


default_pose_service = PoseService()
