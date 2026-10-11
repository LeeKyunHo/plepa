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

    @staticmethod
    def normalize_code(code: Any) -> str:
        """포즈 코드를 정규화합니다 (숫자는 3자리 000, 영문+숫자는 D01, A01 형태로 패딩)."""
        code_s = str(code).strip()
        try:
            return f"{int(code_s):03d}"
        except ValueError:
            # 영문 접두사 + 숫자 (예: D1 -> D01, A1 -> A01)
            if len(code_s) >= 2 and code_s[0].isalpha() and code_s[1:].isdigit():
                return f"{code_s[0].upper()}{int(code_s[1:]):02d}"
            return code_s.upper()

    def load_pose_db(
        self,
        engine: str = "flux",
        path: Optional[Path] = None,
        roster: Optional[str] = None,
    ) -> Dict[str, PoseEntry]:
        """기존 CLI 호환: 엔진별 포즈 DB를 로드하여 {코드: PoseEntry} 딕셔너리로 반환. 로스터/테마 포즈 자동 병합."""
        target_path = path or self._get_db_path(engine)
        if not target_path.exists():
            raise FileNotFoundError(f"포즈 데이터베이스를 찾을 수 없습니다: {target_path}")

        data = self.repo.read_json(target_path)
        entries: Dict[str, PoseEntry] = {}
        for section in SECTION_NAMES:
            sec_dict = data.get(section, {})
            for code, item in sec_dict.items():
                code_str = self.normalize_code(code)
                entries[code_str] = PoseEntry(
                    code=code_str,
                    section=section,
                    label=item.get("label", "미상"),
                    prompt=item.get("prompt", ""),
                    description=item.get("description", ""),
                    required_outfit=item.get("required_outfit", ""),
                    prompt_female=item.get("prompt_female", ""),
                    prompt_otokonoko=item.get("prompt_otokonoko", ""),
                )

        # 로스터 전용 테마 포즈 (projects/{roster}/custom_poses.json 또는 themes/*.json) 병합
        theme_files: List[Path] = []
        if roster:
            r_dir = PROJECTS_DIR / roster
            if (r_dir / "custom_poses.json").exists():
                theme_files.append(r_dir / "custom_poses.json")
            themes_dir = r_dir / "themes"
            if themes_dir.is_dir():
                theme_files.extend(themes_dir.glob("*.json"))

        # 전역 루트 themes/*.json 병합 지원
        global_themes = ROOT_DIR / "themes"
        if global_themes.is_dir():
            theme_files.extend(global_themes.glob("*.json"))

        for tf in theme_files:
            try:
                t_data = self.repo.read_json(tf)
                for sec_name, sec_dict in t_data.items():
                    if not isinstance(sec_dict, dict):
                        continue
                    for code, item in sec_dict.items():
                        code_str = self.normalize_code(code)
                        prompt_val = item.get(f"{engine.lower()}_prompt") or item.get("prompt", "")
                        prompt_f = item.get(f"{engine.lower()}_prompt_female") or item.get("prompt_female", "")
                        prompt_oto = item.get(f"{engine.lower()}_prompt_otokonoko") or item.get("prompt_otokonoko", "")
                        entries[code_str] = PoseEntry(
                            code=code_str,
                            section=sec_name,
                            label=item.get("label", "미상"),
                            prompt=prompt_val,
                            description=item.get("description", ""),
                            required_outfit=item.get("required_outfit", ""),
                            prompt_female=prompt_f,
                            prompt_otokonoko=prompt_oto,
                        )
            except Exception:
                pass

        return entries

    def resolve_pose_codes(self, expr: str, db: Dict[str, PoseEntry]) -> List[str]:
        """사용자가 지정한 포즈 표현식(all, emotions, swim, 00..19, D01,D02 등)을 코드 목록으로 해석 (기존 CLI 호환)."""
        expr = expr.strip()
        expr_lower = expr.lower()

        if expr_lower == "all":
            def sort_key(k: str):
                try:
                    return (0, int(k), "")
                except ValueError:
                    return (1, 0, k)
            return sorted(db.keys(), key=sort_key)

        if expr_lower in ("emotions", "emotion", "a"):
            return [c for c, e in db.items() if e.section == "emotions" or c.startswith("A")]
        if expr_lower in ("poses", "pose", "b"):
            return [c for c, e in db.items() if e.section == "poses" or c.startswith("B")]
        if expr_lower in ("h_scenes", "h", "scenes", "n"):
            return [c for c, e in db.items() if e.section == "h_scenes" or c.startswith("N")]
        if expr_lower in ("otokonoko", "scenes_otokonoko", "oto"):
            return [c for c, e in db.items() if e.section == "scenes_otokonoko"]
        if expr_lower in ("swimsuit", "swim", "d"):
            return [c for c, e in db.items() if e.section == "swimsuit" or c.startswith("D")]
        if expr_lower in ("bunny", "f"):
            return [c for c, e in db.items() if e.section == "bunny" or c.startswith("F")]
        if expr_lower in ("maid", "g"):
            return [c for c, e in db.items() if e.section == "maid" or c.startswith("G")]
        if expr_lower in ("combat", "battle", "i"):
            return [c for c, e in db.items() if e.section == "combat" or c.startswith("I")]

        # 범위 연산자 지원: 00..19, 000..019, D01..D07 등
        if ".." in expr:
            start_s, end_s = expr.split("..", 1)
            start_s, end_s = start_s.strip(), end_s.strip()
            # 영문 접두사 범위 (예: D01..D07 또는 D1..D7)
            if start_s and end_s and start_s[0].isalpha() and end_s[0].isalpha() and start_s[0].upper() == end_s[0].upper():
                prefix = start_s[0].upper()
                try:
                    s_num, e_num = int(start_s[1:]), int(end_s[1:])
                    codes = []
                    for i in range(s_num, e_num + 1):
                        c_str = f"{prefix}{i:02d}"
                        if c_str in db:
                            codes.append(c_str)
                    return codes
                except ValueError:
                    pass

            try:
                start, end = int(start_s), int(end_s)
                codes = []
                for i in range(start, end + 1):
                    c_str = f"{i:03d}"
                    if c_str in db:
                        codes.append(c_str)
                return codes
            except ValueError:
                pass

        # 쉼표 구분: 00,01,05 또는 D01,D02 등
        if "," in expr:
            codes = []
            for token in expr.split(","):
                token = token.strip()
                if not token:
                    continue
                c_str = self.normalize_code(token)
                if c_str in db:
                    codes.append(c_str)
            return codes

        # 단일 코드: 00 또는 D1 등
        single_code = self.normalize_code(expr)
        if single_code in db:
            return [single_code]

        # 대소문자 무시 검색 폴백
        for k in db.keys():
            if k.lower() == expr_lower:
                return [k]

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
