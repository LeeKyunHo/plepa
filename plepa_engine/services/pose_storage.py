"""
plepa_engine.services.pose_storage
포즈 DB/로스터 오버라이드 병합 로드, 상세 탐색, 에셋 리네임 계획, 세트 I/O 및 문서 동기화 검사 헬퍼.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from plepa_engine.models import PoseEntry
from plepa_engine.services.pose_resolver import SECTION_NAMES, normalize_pose_code
from plepa_engine.services.repository import Repository
from plepa_engine.services.schemas import PoseSetSchema

logger = logging.getLogger(__name__)


def build_default_pose_sets() -> List[PoseSetSchema]:
    """V3 표준 기본 포즈 세트 프리셋 목록을 반환합니다."""
    return [
        PoseSetSchema(
            id="sample10",
            name="10대 대표 골든 샘플러 (10종)",
            description="핵심 10대 대표 포즈: 000, 020, 034, 044, 048, 060, 088, 067, 130, 131",
            codes=["000", "020", "034", "044", "048", "060", "088", "067", "130", "131"],
        ),
        PoseSetSchema(
            id="emotions_20",
            name="🎭 기본 감정 20종 (000~019)",
            description="V3 기본 감정 표현 스탠딩 20종 (000~019)",
            codes=[f"{i:03d}" for i in range(0, 20)],
        ),
        PoseSetSchema(
            id="v3_daily_53",
            name="☀️ 일상·감정·이벤트 53종 (000~052)",
            description="비성인 일상 전체: 기본 감정(000~019) + 일상 전신(020~039) + 일상/캠퍼스 이벤트(040~052)",
            codes=[f"{i:03d}" for i in range(0, 53)],
        ),
        PoseSetSchema(
            id="h_scenes_52",
            name="🔥 통합 성인 H-씬 52종",
            description="로맨스(060~063) + 활성 봉사·성인 H-씬 52종 전체",
            codes=[
                "060", "061", "062", "063",
                "080", "081", "082", "083", "084", "085", "086", "087",
                "088", "089", "090", "091", "092", "093", "094", "095",
                "064", "074", "073", "099", "100", "101", "067", "103",
                "104", "105", "106", "107", "108", "109", "110", "111",
                "112", "113", "114", "115", "116", "075", "118", "119",
                "076", "079", "122", "123", "124", "077", "068", "069",
            ],
        ),
    ]


def collect_theme_and_override_files(
    roster: Optional[str],
    projects_dir: Path,
    themes_dir: Path,
    root_dir: Path,
) -> List[Path]:
    """로스터 이벤트(pose_overrides -> events -> custom_poses) 및 전역 테마 파일 순서를 수집합니다."""
    theme_files: List[Path] = []
    if roster:
        r_dir = projects_dir / roster
        for fname in ("pose_overrides.json", "events.json", "custom_poses.json"):
            cand = r_dir / fname
            if cand.exists():
                theme_files.append(cand)
        themes_sub = r_dir / "themes"
        if themes_sub.is_dir():
            theme_files.extend(themes_sub.glob("*.json"))

    for g_themes in (themes_dir, root_dir / "themes"):
        if g_themes.is_dir():
            theme_files.extend(g_themes.glob("*.json"))
    return theme_files


def load_pose_db_entries(
    repo: Repository,
    target_path: Path,
    engine: str,
    roster: Optional[str],
    projects_dir: Path,
    themes_dir: Path,
    root_dir: Path,
) -> Dict[str, PoseEntry]:
    """코어 포즈 DB에 로스터 이벤트·테마 포즈를 순서대로 병합해 반환합니다."""
    if not target_path.exists():
        raise FileNotFoundError(f"포즈 데이터베이스를 찾을 수 없습니다: {target_path}")

    data = repo.read_json(target_path)
    entries: Dict[str, PoseEntry] = {}
    for section in SECTION_NAMES:
        for code, item in data.get(section, {}).items():
            code_str = normalize_pose_code(code)
            entries[code_str] = PoseEntry.from_dict(code_str, section, item, engine=engine)

    for tf in collect_theme_and_override_files(roster, projects_dir, themes_dir, root_dir):
        try:
            t_data = repo.read_json(tf)
            for sec_name, sec_dict in t_data.items():
                if not isinstance(sec_dict, dict):
                    continue
                for code, item in sec_dict.items():
                    code_str = normalize_pose_code(code)
                    default_allowed = [roster] if roster and tf.name in ("pose_overrides.json", "events.json") else None
                    entries[code_str] = PoseEntry.from_dict(
                        code_str,
                        sec_name,
                        item,
                        engine=engine,
                        default_allowed_rosters=default_allowed,
                    )
        except Exception as exc:
            logger.warning("[PoseService] 테마 포즈 파일 로드 스킵 (%s): %s", tf, exc)
    return entries


def find_pose_details_dict(
    repo: Repository,
    code_str: str,
    sdxl_db_path: Path,
    themes_dir: Path,
    projects_dir: Path,
) -> Dict[str, Any]:
    """코어 DB 및 테마·events.json 폴백을 탐색해 상세 딕셔너리를 반환합니다."""
    sdxl_raw = repo.read_json(sdxl_db_path)
    target_section = None
    s_item = None
    for sec in SECTION_NAMES:
        if code_str in sdxl_raw.get(sec, {}):
            target_section = sec
            s_item = sdxl_raw[sec][code_str]
            break

    if not target_section:
        extra_files: List[Path] = list(sorted(themes_dir.glob("*.json")))
        if projects_dir.is_dir():
            extra_files.extend(sorted(projects_dir.glob("*/events.json")))
        for tf in extra_files:
            try:
                t_data = repo.read_json(tf)
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


def plan_pose_asset_renames(
    projects_dir: Path,
    code_str: str,
    old_label: str,
    new_label: str,
) -> List[Tuple[Path, Path]]:
    """라벨 변경 시 영향을 받는 에셋 파일들의 변경 전/후 경로 목록을 계산합니다."""
    plan: List[Tuple[Path, Path]] = []
    if not old_label or old_label == new_label:
        return plan

    for proj in projects_dir.iterdir():
        assets_dir = proj / "assets" if proj.is_dir() else None
        if not assets_dir or not assets_dir.is_dir():
            continue
        for char_dir in assets_dir.iterdir():
            if not char_dir.is_dir() or char_dir.name in ("_trash", "legacy_backups"):
                continue
            for f in sorted(char_dir.rglob(f"*_{code_str}_{old_label}*.webp")):
                if any(skip in f.parts for skip in ("_trash", "legacy_backups", "_origin")):
                    continue
                new_name = f.name.replace(f"_{code_str}_{old_label}", f"_{code_str}_{new_label}")
                plan.append((f, f.with_name(new_name)))
    return plan


def load_or_init_pose_sets(
    repo: Repository,
    pose_sets_file: Path,
    save_all_fn: Callable[[List[PoseSetSchema]], None],
) -> List[PoseSetSchema]:
    """포즈 세트 파일을 로드하고 미존재 시 V3 기본 세트를 초기화합니다."""
    if not pose_sets_file.exists():
        default_sets = build_default_pose_sets()
        save_all_fn(default_sets)
        return default_sets
    try:
        raw = repo.read_json(pose_sets_file)
        if not isinstance(raw, list):
            return []
        valid_sets: List[PoseSetSchema] = []
        for item in raw:
            if not isinstance(item, dict) or "_category" in item or "id" not in item:
                continue
            try:
                valid_sets.append(PoseSetSchema.model_validate(item))
            except Exception:
                continue
        return valid_sets
    except Exception:
        return []


def check_pose_doc_sync_impl(
    repo: Repository,
    db_path: Path,
    target_doc: Path,
) -> Tuple[bool, List[str]]:
    """포즈 DB의 3자리 숫자 코드와 POSE_MAPPING.md 문서 간 동기화를 검증합니다."""
    if not target_doc.exists():
        return False, [f"문서 파일 없음: {target_doc}"]

    raw_db = repo.read_json(db_path)
    core_codes = set()
    if isinstance(raw_db, dict):
        for k, v in raw_db.items():
            if isinstance(v, dict) and not k.startswith("_"):
                for code_key in v.keys():
                    if len(code_key) == 3 and code_key.isdigit():
                        core_codes.add(code_key)

    doc_text = target_doc.read_text(encoding="utf-8")
    doc_codes = set(re.findall(r"(?<!\d)(\d{3})(?!\d)", doc_text)) & core_codes
    missing_in_doc = sorted(list(core_codes - doc_codes))
    return len(missing_in_doc) == 0, missing_in_doc
