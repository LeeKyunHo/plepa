"""
plepa_engine.services.pose_service
FLUX & SDXL 듀얼 포즈 DB 동기화 CRUD, 소프트 삭제, 라벨 변경 시 에셋 파일명 리네임 트랜잭션, 포즈 세트 관리.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plepa_engine.config import (
    FLUX_POSE_DB_PATH,
    POSE_DB_PATH,
    PROJECTS_DIR,
    ROOT_DIR,
    SDXL_POSE_DB_PATH,
)
from plepa_engine.models import PoseEntry
from plepa_engine.services.repository import Repository, default_repo
from plepa_engine.services.schemas import PoseFlags, PoseItemSchema, PoseSetSchema

POSE_SETS_FILE = ROOT_DIR / "pose_sets.json"
SECTION_NAMES = ("emotions", "poses", "h_scenes", "scenes_otokonoko")


class PoseService:
    """듀얼 엔진 포즈 데이터베이스 및 포즈 세트 관리 서비스."""

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or default_repo

    def _get_db_path(self, engine: str) -> Path:
        return SDXL_POSE_DB_PATH if engine.lower() == "sdxl" else FLUX_POSE_DB_PATH

    def load_pose_db(self, engine: str = "flux", path: Optional[Path] = None) -> Dict[str, PoseEntry]:
        """기존 CLI 호환: 엔진별 포즈 DB를 로드하여 {코드: PoseEntry} 딕셔너리로 반환."""
        target_path = path or self._get_db_path(engine)
        if not target_path.exists():
            raise FileNotFoundError(f"포즈 데이터베이스를 찾을 수 없습니다: {target_path}")

        data = self.repo.read_json(target_path)
        entries: Dict[str, PoseEntry] = {}
        for section in SECTION_NAMES:
            sec_dict = data.get(section, {})
            for code, item in sec_dict.items():
                code_str = f"{int(code):03d}"
                entries[code_str] = PoseEntry(
                    code=code_str,
                    section=section,
                    label=item.get("label", "미상"),
                    prompt=item.get("prompt", ""),
                    description=item.get("description", "")
                )
        return entries

    def resolve_pose_codes(self, expr: str, db: Dict[str, PoseEntry]) -> List[str]:
        """사용자가 지정한 포즈 표현식(all, emotions, 00..19, 01,02 등)을 코드 목록으로 해석 (기존 CLI 호환)."""
        expr = expr.strip().lower()
        if expr == "all":
            return sorted(db.keys(), key=lambda x: int(x))
        if expr in ("emotions", "emotion"):
            return [c for c, e in db.items() if e.section == "emotions"]
        if expr in ("poses", "pose"):
            return [c for c, e in db.items() if e.section == "poses"]
        if expr in ("h_scenes", "h", "scenes"):
            return [c for c, e in db.items() if e.section == "h_scenes"]
        if expr in ("otokonoko", "scenes_otokonoko", "oto"):
            return [c for c, e in db.items() if e.section == "scenes_otokonoko"]

        # 범위 연산자 지원: 00..19, 000..019 등
        if ".." in expr:
            start_s, end_s = expr.split("..", 1)
            start, end = int(start_s), int(end_s)
            codes = []
            for i in range(start, end + 1):
                c_str = f"{i:03d}"
                if c_str in db:
                    codes.append(c_str)
            return codes

        # 쉼표 구분: 00,01,05 또는 000,001 등
        if "," in expr:
            codes = []
            for token in expr.split(","):
                token = token.strip()
                if not token:
                    continue
                c_str = f"{int(token):03d}"
                if c_str in db:
                    codes.append(c_str)
            return codes

        # 단일 코드: 00 또는 000 등
        single_code = f"{int(expr):03d}"
        if single_code in db:
            return [single_code]

        raise ValueError(f"유효하지 않은 포즈 코드/표현식입니다: {expr}")

    def get_pose_details(self, code: str) -> Dict[str, Any]:
        """
        SDXL과 FLUX 양쪽 DB에서 해당 코드의 상세 정보를 읽어 병합 반환합니다.
        반환값: {
            code, section, label, description, flags,
            flux_prompt, sdxl_prompt
        }
        """
        code_str = f"{int(code):03d}"
        flux_raw = self.repo.read_json(FLUX_POSE_DB_PATH)
        sdxl_raw = self.repo.read_json(SDXL_POSE_DB_PATH)

        target_section = None
        f_item = None
        for sec in SECTION_NAMES:
            if code_str in flux_raw.get(sec, {}):
                target_section = sec
                f_item = flux_raw[sec][code_str]
                break

        if not f_item or not target_section:
            raise KeyError(f"포즈 코드 '{code_str}'를 데이터베이스에서 찾을 수 없습니다.")

        s_item = sdxl_raw.get(target_section, {}).get(code_str, {})

        return {
            "code": code_str,
            "section": target_section,
            "label": f_item.get("label", s_item.get("label", "")),
            "description": f_item.get("description", s_item.get("description", "")),
            "flags": f_item.get("flags") or s_item.get("flags") or {},
            "flux_prompt": f_item.get("prompt", ""),
            "sdxl_prompt": s_item.get("prompt", ""),
        }

    def update_pose(
        self,
        code: str,
        label: str,
        description: str,
        flags: Optional[Dict[str, Any]] = None,
        flux_prompt: Optional[str] = None,
        sdxl_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        SDXL과 FLUX 양쪽 DB에 공유 필드(label, description, flags)를 동시에 동기화 기록합니다.
        프롬프트는 전달된 경우에만 각 엔진 DB에 반영합니다.
        """
        code_str = f"{int(code):03d}"
        flux_raw = self.repo.read_json(FLUX_POSE_DB_PATH)
        sdxl_raw = self.repo.read_json(SDXL_POSE_DB_PATH)

        target_section = None
        for sec in SECTION_NAMES:
            if code_str in flux_raw.get(sec, {}):
                target_section = sec
                break

        if not target_section:
            raise KeyError(f"포즈 코드 '{code_str}'를 찾을 수 없습니다.")

        # FLUX 업데이트
        f_sec = flux_raw.setdefault(target_section, {})
        f_entry = f_sec.setdefault(code_str, {})
        f_entry["label"] = label.strip()
        f_entry["description"] = description.strip()
        if flags is not None:
            f_entry["flags"] = flags
        if flux_prompt is not None:
            f_entry["prompt"] = flux_prompt.strip()

        # SDXL 업데이트
        s_sec = sdxl_raw.setdefault(target_section, {})
        s_entry = s_sec.setdefault(code_str, {})
        s_entry["label"] = label.strip()
        s_entry["description"] = description.strip()
        if flags is not None:
            s_entry["flags"] = flags
        if sdxl_prompt is not None:
            s_entry["prompt"] = sdxl_prompt.strip()

        # 두 파일 원자적 동시 저장
        self.repo.write_json(FLUX_POSE_DB_PATH, flux_raw)
        self.repo.write_json(SDXL_POSE_DB_PATH, sdxl_raw)

        return self.get_pose_details(code_str)

    def plan_asset_rename(self, code: str, old_label: str, new_label: str) -> List[Tuple[Path, Path]]:
        """
        라벨 변경 시 영향을 받는 기존 에셋 파일들의 변경 전/후 경로 목록을 시뮬레이션(Dry-run)합니다.
        형식: prefix_000_old_label.webp -> prefix_000_new_label.webp
        """
        code_str = f"{int(code):03d}"
        plan: List[Tuple[Path, Path]] = []
        if not old_label or old_label == new_label:
            return plan

        for proj in PROJECTS_DIR.iterdir():
            if not proj.is_dir():
                continue
            assets_dir = proj / "assets"
            if not assets_dir.is_dir():
                continue
            for char_dir in assets_dir.iterdir():
                if not char_dir.is_dir():
                    continue
                # 패턴 매칭: prefix_000_old_label*.webp
                for f in char_dir.glob(f"*_{code_str}_{old_label}*.webp"):
                    new_name = f.name.replace(f"_{code_str}_{old_label}", f"_{code_str}_{new_label}")
                    plan.append((f, f.with_name(new_name)))

        return plan

    def apply_asset_rename(self, plan: List[Tuple[Path, Path]]) -> int:
        """plan_asset_rename으로 생성된 파일명 변경 계획을 실제 실행합니다."""
        renamed_count = 0
        for src, dst in plan:
            if src.exists() and not dst.exists():
                src.rename(dst)
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
            flags=flags
        )

    # 포즈 세트(Pose Sets) 관리
    def load_pose_sets(self) -> List[PoseSetSchema]:
        """포즈 세트 목록을 로드합니다."""
        if not POSE_SETS_FILE.exists():
            # 기본 프리셋 생성
            default_sets = [
                PoseSetSchema(
                    id="shower_trio",
                    name="샤워 3종 세트",
                    description="038 샤워실 뒤태, 039 샤워창 밀착, 057 샤워벽치기",
                    codes=["038", "039", "057"]
                ),
                PoseSetSchema(
                    id="adult_testing",
                    name="체형 테스트 24~59",
                    description="24번부터 59번까지 전신 포즈 및 H-씬",
                    codes=[f"{i:03d}" for i in range(24, 60)]
                ),
                PoseSetSchema(
                    id="emotions_all",
                    name="기본 표정 20종",
                    description="000부터 019까지 감정 표현",
                    codes=[f"{i:03d}" for i in range(0, 20)]
                ),
                PoseSetSchema(
                    id="h_scenes_all",
                    name="H-씬 20종",
                    description="040부터 059까지 성인 씬",
                    codes=[f"{i:03d}" for i in range(40, 60)]
                )
            ]
            self.save_all_pose_sets(default_sets)
            return default_sets

        try:
            raw = self.repo.read_json(POSE_SETS_FILE)
            if isinstance(raw, list):
                return [PoseSetSchema.model_validate(item) for item in raw]
            return []
        except Exception:
            return []

    def save_all_pose_sets(self, sets: List[PoseSetSchema]) -> None:
        """전체 포즈 세트 목록을 저장합니다."""
        dumped = [s.model_dump() for s in sets]
        self.repo.write_json(POSE_SETS_FILE, dumped)

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
        filtered = [s for s in current_sets if s.id != set_id]
        self.save_all_pose_sets(filtered)


default_pose_service = PoseService()
