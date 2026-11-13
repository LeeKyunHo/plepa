"""
plepa_engine.services.pose_service
SDXL 단일 진실 공급원(SSOT) 포즈 DB CRUD, 소프트 삭제, 라벨 변경 시 에셋 파일명 리네임 트랜잭션, 포즈 세트 관리.
"""

from __future__ import annotations

import json
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

logger = logging.getLogger(__name__)
from plepa_engine.models import PoseEntry
from plepa_engine.services.repository import Repository, default_repo
from plepa_engine.services.schemas import PoseFlags, PoseItemSchema, PoseSetSchema

POSE_SETS_FILE = POSE_SETS_PATH

# 업계 표준: 단일 진실 공급원(SSOT) 섹션 메타데이터 레지스트리
# id: {name, short_label, icon, order}
SECTION_METADATA: Dict[str, Dict[str, Any]] = {
    # ── V3 핵심 대역 체계 ──
    "emotions": {"name": "감정 표현 (000~019)", "short_label": "감정", "icon": "😊", "order": 1},
    "poses": {"name": "범용 일상 포즈 (020~050)", "short_label": "일상", "icon": "🧍", "order": 2},
    "daily_events": {"name": "로스터 일상 이벤트 (051~059)", "short_label": "이벤트", "icon": "🎬", "order": 3},
    "romance": {"name": "로맨스 & 공용 씬 (060~079)", "short_label": "로맨스", "icon": "💖", "order": 4},
    "h_scenes": {"name": "여성 성인 H-씬 (080~129)", "short_label": "성인(H)", "icon": "🔞", "order": 5},
    "special_female_h": {"name": "여성 특수 이벤트 H-씬 (130~139)", "short_label": "특수(H)", "icon": "🏫", "order": 6},
    "scenes_otokonoko": {"name": "오토코노코 성인 (150~199)", "short_label": "오토코노코", "icon": "🎀", "order": 7},
    "special_otokonoko_h": {"name": "오토코노코 특수 이벤트 (200~209)", "short_label": "특수(오토)", "icon": "🏫", "order": 8},
    # ── 레거시 및 테마 하위 호환 섹션 ──
    "events": {"name": "스토리 이벤트 (040~059)", "short_label": "레거시이벤트", "icon": "🎬", "order": 10},
    "special_h": {"name": "여성 특수 성인씬 (130~132)", "short_label": "레거시특수H", "icon": "🏫", "order": 11},
    "special_otokonoko": {"name": "오토코노코 특수 (133~135)", "short_label": "레거시특수오토", "icon": "🏫", "order": 12},
    "wuxia_actions": {"name": "무협 액션 (C01~C10)", "short_label": "무협(C)", "icon": "⚔️", "order": 13},
    "swimsuit": {"name": "수영복 (D01~D08)", "short_label": "수영복", "icon": "👙", "order": 14},
    "bunny": {"name": "바니걸 (F01~F07)", "short_label": "바니걸", "icon": "🐰", "order": 15},
    "bdsm": {"name": "BDSM (E01~E08)", "short_label": "BDSM", "icon": "⛓️", "order": 16},
    "spy_actions": {"name": "첩보 액션 (S01~S10)", "short_label": "첩보(S)", "icon": "🕵️", "order": 17},
    "adult": {"name": "레거시 성인 (adult)", "short_label": "성인(레거시)", "icon": "🔞", "order": 18},
    "genit_actions": {"name": "레거시 이벤트 (genit_actions)", "short_label": "액션(레거시)", "icon": "🎬", "order": 19},
    "genit_emotions": {"name": "레거시 표정 (genit_emotions)", "short_label": "감정(레거시)", "icon": "😊", "order": 20},
}

SECTION_NAMES = tuple(SECTION_METADATA.keys())


class PoseService:
    """듀얼 엔진 포즈 데이터베이스 및 포즈 세트 관리 서비스."""

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
        present_sections = set(e.section for e in db.values() if e.section)
        
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
        engine: str = "sdxl",
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
                    negative_add=item.get("negative_add", ""),
                    status=item.get("status", "active"),
                    canonical_code=item.get("canonical_code"),
                )

        # 로스터 전용 포즈 오버라이드 파일 (projects/{roster}/pose_overrides.json) 로드
        theme_files: List[Path] = []
        if roster:
            r_dir = PROJECTS_DIR / roster
            # 1순위: 레거시 pose_overrides.json
            if (r_dir / "pose_overrides.json").exists():
                theme_files.append(r_dir / "pose_overrides.json")
            # 2순위(최우선): V3 events.json (로스터 특색 일상 이벤트 및 특수 H씬이 최종 덮어씀)
            if (r_dir / "events.json").exists():
                theme_files.append(r_dir / "events.json")
            # 레거시: custom_poses.json
            if (r_dir / "custom_poses.json").exists():
                theme_files.append(r_dir / "custom_poses.json")
            # 테마 디렉토리
            themes_dir = r_dir / "themes"
            if themes_dir.is_dir():
                theme_files.extend(themes_dir.glob("*.json"))

        # 전역 data/themes/*.json (및 레거시 themes/*.json) 병합 지원
        for g_themes in (THEMES_DIR, ROOT_DIR / "themes"):
            if g_themes.is_dir():
                theme_files.extend(g_themes.glob("*.json"))

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
                        target_g = item.get("target_gender")
                        allowed_r = item.get("allowed_rosters") or ([roster] if roster and tf.name in ("pose_overrides.json", "events.json") else None)
                        entries[code_str] = PoseEntry(
                            code=code_str,
                            section=sec_name,
                            label=item.get("label", "미상"),
                            prompt=prompt_val,
                            description=item.get("description", ""),
                            required_outfit=item.get("required_outfit", ""),
                            prompt_female=prompt_f,
                            prompt_otokonoko=prompt_oto,
                            target_gender=target_g,
                            allowed_rosters=allowed_r,
                            negative_add=item.get("negative_add", ""),
                            status=item.get("status", "active"),
                            canonical_code=item.get("canonical_code"),
                        )

            except Exception as exc:
                logger.warning("[PoseService] 테마 포즈 파일 로드 스킵 (%s): %s", tf, exc)

        return entries

    @staticmethod
    def is_pose_allowed_for_character(
        pose_entry: Optional[PoseEntry],
        char_obj: Any,
        roster: str = DEFAULT_ROSTER,
        code: str = "",
    ) -> bool:
        """포즈 메타데이터(section, target_gender, allowed_rosters) 및 캐릭터 젠더 기반 적합성을 판별합니다."""
        effective_code = str(getattr(pose_entry, "code", "") or code).strip()
        target_gender = getattr(pose_entry, "target_gender", None) if pose_entry else None
        allowed_rosters = getattr(pose_entry, "allowed_rosters", None) if pose_entry else None
        section = getattr(pose_entry, "section", "") if pose_entry else ""

        if allowed_rosters and roster not in allowed_rosters:
            return False

        pose_restrictions = getattr(char_obj, "pose_restrictions", {}) or {}
        if isinstance(pose_restrictions, dict):
            restricted_rosters = pose_restrictions.get("roster_only")
            if isinstance(restricted_rosters, dict):
                allowed_for_code = restricted_rosters.get(effective_code)
                if allowed_for_code and roster not in allowed_for_code:
                    return False
            campus_only_poses = set(pose_restrictions.get("campus_only", []))
            if effective_code in campus_only_poses and roster != "campus":
                if not allowed_rosters or roster not in allowed_rosters:
                    return False

        char_gender = (getattr(char_obj, "gender", "") or "").lower().strip()
        if target_gender:
            if target_gender == "otokonoko" and char_gender != "otokonoko":
                return False
            if target_gender in ("female", "girl") and char_gender == "otokonoko":
                return False
            return True

        if section in ("scenes_otokonoko", "special_otokonoko", "special_otokonoko_h") and char_gender != "otokonoko":
            return False
        if section in ("h_scenes", "special_h", "special_female_h") and char_gender == "otokonoko":
            return False

        # 하위 호환 숫자 대역 폴백 (V3 규격: 080~139 여성 H, 133~135 & 150~209 오토코노코)
        try:
            code_num = int(effective_code)
            if char_gender == "otokonoko" and 80 <= code_num <= 139:
                return False
            if char_gender != "otokonoko" and ((133 <= code_num <= 135) or (150 <= code_num <= 209)):
                return False
        except ValueError:
            pass

        return True


    ROSTER_THEME_MAP: Dict[str, List[str]] = {
        "spy": ["spy_actions"],
        "murim": ["wuxia_actions"],
        "wuxia": ["wuxia_actions"],
        "maid": ["maid"],
    }
    OPTIONAL_COSTUME_SECTIONS: set = {"swimsuit", "bdsm", "bunny"}
    THEME_ACTION_SECTIONS: set = {"spy_actions", "wuxia_actions", "maid", "combat"}

    def resolve_pose_codes(
        self,
        expr: str,
        db: Dict[str, PoseEntry],
        roster: Optional[str] = None,
    ) -> List[str]:
        """사용자가 지정한 포즈 표현식(all, emotions, swim, 00..19, D01,D02 등)을 코드 목록으로 해석 (기존 CLI 호환)."""
        expr = expr.strip()
        expr_lower = expr.lower()

        def _is_active(entry: PoseEntry) -> bool:
            return getattr(entry, "status", "active") != "deprecated"

        if expr_lower == "all":
            allowed_themes = set(self.ROSTER_THEME_MAP.get(roster.lower(), [])) if roster else set()

            def is_allowed_for_all(entry: PoseEntry) -> bool:
                if not _is_active(entry):
                    return False
                # 1. 특수 코스튬 팩(수영복, BDSM, 바니걸 등)은 기본 전부생산에서 제외 (명시적 요청 시에만 생성)
                if entry.section in self.OPTIONAL_COSTUME_SECTIONS:
                    return False
                # 2. 테마 액션 팩인 경우: 현재 로스터에 배정된 테마만 포함, 타 로스터 테마는 제외
                if entry.section in self.THEME_ACTION_SECTIONS:
                    return entry.section in allowed_themes
                # 3. 신규 통합 코어(000~199 숫자 코드)만 항상 포함.
                #    N/A/B 계열(adult, genit_emotions, genit_actions의 영문 코드)은 은퇴되어 명시 지정 시에만 생성
                return entry.code.isdigit()

            def sort_key(k: str):
                try:
                    return (0, int(k), "")
                except ValueError:
                    return (1, 0, k)

            return sorted([c for c, e in db.items() if is_allowed_for_all(e)], key=sort_key)

        if expr_lower in ("emotions", "emotion", "a"):
            return [c for c, e in db.items() if _is_active(e) and (e.section == "emotions" or c.startswith("A"))]
        if expr_lower in ("poses", "pose", "b"):
            return [c for c, e in db.items() if _is_active(e) and (e.section == "poses" or c.startswith("B"))]
        if expr_lower in ("events", "event", "genit_actions", "daily_events"):
            return [c for c, e in db.items() if _is_active(e) and (e.section in ("events", "genit_actions", "daily_events") or c.startswith("B"))]
        if expr_lower in ("romance", "rom"):
            return [c for c, e in db.items() if _is_active(e) and e.section == "romance"]
        if expr_lower in ("h_scenes", "h", "scenes", "n"):
            return [c for c, e in db.items() if _is_active(e) and (e.section in ("h_scenes", "special_h", "special_female_h") or c.startswith("N"))]
        if expr_lower in ("special_h", "special", "sph", "special_female_h"):
            return [c for c, e in db.items() if _is_active(e) and e.section in ("special_h", "special_female_h")]
        if expr_lower in ("otokonoko", "scenes_otokonoko", "oto"):
            return [c for c, e in db.items() if _is_active(e) and e.section in ("scenes_otokonoko", "special_otokonoko", "special_otokonoko_h")]
        if expr_lower in ("special_otokonoko", "sp_oto", "special_otokonoko_h"):
            return [c for c, e in db.items() if _is_active(e) and e.section in ("special_otokonoko", "special_otokonoko_h")]
        if expr_lower in ("swimsuit", "swim", "d"):
            return [c for c, e in db.items() if _is_active(e) and (e.section == "swimsuit" or c.startswith("D"))]
        if expr_lower in ("bunny", "f"):
            return [c for c, e in db.items() if _is_active(e) and (e.section == "bunny" or c.startswith("F"))]
        if expr_lower in ("maid", "g"):
            return [c for c, e in db.items() if _is_active(e) and (e.section == "maid" or c.startswith("G"))]
        if expr_lower in ("combat", "battle", "i"):
            return [c for c, e in db.items() if _is_active(e) and (e.section == "combat" or c.startswith("I"))]
        if expr_lower in ("spy", "spy_actions", "s"):
            return [c for c, e in db.items() if _is_active(e) and (e.section == "spy_actions" or c.startswith("S"))]
        if expr_lower in ("wuxia", "wuxia_actions", "c"):
            return [c for c, e in db.items() if _is_active(e) and (e.section == "wuxia_actions" or c.startswith("C"))]

        # 쉼표 구분 복합 표현식 지원: "00,01,05" 또는 "A00..A23,S01..S10,B01..B22" 등
        if "," in expr:
            codes = []
            for token in expr.split(","):
                token = token.strip()
                if not token:
                    continue
                for sub_c in self.resolve_pose_codes(token, db, roster=roster):
                    if sub_c not in codes:
                        codes.append(sub_c)
            return codes

        # 포즈 세트 ID 매칭 지원 (예: spy_full, genit_full, genit_costumes 등)
        for pset in self.load_pose_sets():
            if pset.id.lower() == expr_lower:
                return [c for c in pset.codes if c in db]

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
                        if c_str in db and _is_active(db[c_str]):
                            codes.append(c_str)
                    return codes
                except ValueError:
                    pass

            try:
                start, end = int(start_s), int(end_s)
                codes = []
                for i in range(start, end + 1):
                    c_str = f"{i:03d}"
                    if c_str in db and _is_active(db[c_str]):
                        codes.append(c_str)
                return codes
            except ValueError:
                pass

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
        SDXL 단일 진실 공급원(SSOT) DB 및 테마 JSON에서 해당 코드의 상세 정보를 읽어 반환합니다.
        반환값: {
            code, section, label, description, flags, sdxl_prompt
        }
        """
        code_str = self.normalize_code(code)
        sdxl_raw = self.repo.read_json(SDXL_POSE_DB_PATH)

        target_section = None
        s_item = None
        for sec in SECTION_NAMES:
            if code_str in sdxl_raw.get(sec, {}):
                target_section = sec
                s_item = sdxl_raw[sec][code_str]
                break

        if not target_section:
            # 테마 디렉토리(data/themes/*.json) 및 로스터 events.json 탐색 폴백
            extra_files: List[Path] = []
            for tf in sorted(THEMES_DIR.glob("*.json")):
                extra_files.append(tf)
            if PROJECTS_DIR.is_dir():
                for evf in sorted(PROJECTS_DIR.glob("*/events.json")):
                    extra_files.append(evf)
            for tf in extra_files:
                try:
                    t_data = self.repo.read_json(tf)
                    for sec_name, sec_dict in t_data.items():
                        if isinstance(sec_dict, dict) and code_str in sec_dict:
                            target_section = sec_name
                            s_item = sec_dict[code_str]
                            break
                    if target_section:
                        break
                except Exception as exc:
                    logger.warning("[PoseService] 상세 조회 테마 파일 스킵 (%s): %s", tf, exc)

        if not target_section:
            raise KeyError(f"포즈 코드 '{code_str}'를 SDXL 데이터베이스에서 찾을 수 없습니다.")

        s_item = s_item or {}
        sdxl_prompt = s_item.get("sdxl_prompt") or s_item.get("prompt", "")

        return {
            "code": code_str,
            "section": target_section,
            "label": s_item.get("label", ""),
            "description": s_item.get("description", ""),
            "flags": s_item.get("flags") or {},
            "sdxl_prompt": sdxl_prompt,
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
        SDXL 단일 진실 공급원(data/sdxl_pose_database.json)에 포즈 필드(label, description, flags, sdxl_prompt)를 기록합니다.
        (레거시 FLUX DB는 GEMINI.md 단일화 원칙에 따라 일체 수정·동기화하지 않음; flux_prompt 인수는 하위 호환용 무시)
        """
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

        # SDXL DB 업데이트
        s_sec = sdxl_raw.setdefault(target_section, {})
        s_entry = s_sec.setdefault(code_str, {})
        s_entry["label"] = label.strip()
        s_entry["description"] = description.strip()
        if flags is not None:
            s_entry["flags"] = flags
        if sdxl_prompt is not None:
            s_entry["prompt"] = sdxl_prompt.strip()

        # SDXL DB 단일 진실 공급원 원자적 저장
        self.repo.write_json(SDXL_POSE_DB_PATH, sdxl_raw)

        return self.get_pose_details(code_str)

    def plan_asset_rename(self, code: str, old_label: str, new_label: str) -> List[Tuple[Path, Path]]:
        """
        라벨 변경 시 영향을 받는 기존 에셋 파일들의 변경 전/후 경로 목록을 시뮬레이션(Dry-run)합니다.
        형식: prefix_000_old_label.webp -> prefix_000_new_label.webp (V3 서브폴더 rglob 지원)
        """
        code_str = self.normalize_code(code)
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
                if not char_dir.is_dir() or char_dir.name in ("_trash", "legacy_backups"):
                    continue
                # V3 서브폴더(01_normal, 02_h_scenes) 포함 재귀 매칭, 휴지통/백업 스킵
                for f in sorted(char_dir.rglob(f"*_{code_str}_{old_label}*.webp")):
                    if any(skip in f.parts for skip in ("_trash", "legacy_backups", "_origin")):
                        continue
                    new_name = f.name.replace(f"_{code_str}_{old_label}", f"_{code_str}_{new_label}")
                    plan.append((f, f.with_name(new_name)))

        return plan

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
                valid_sets: List[PoseSetSchema] = []
                for item in raw:
                    if not isinstance(item, dict) or "_category" in item or "id" not in item:
                        continue
                    try:
                        valid_sets.append(PoseSetSchema.model_validate(item))
                    except Exception:
                        continue
                return valid_sets
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
