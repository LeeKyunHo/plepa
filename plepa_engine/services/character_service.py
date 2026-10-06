"""
plepa_engine.services.character_service
캐릭터 CRUD, 전역 prefix 중복 검증, 복제 마법사(Clone Wizard) 및 기존 CLI 호환 탐색기.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.models import CharacterConfig
from plepa_engine.services.repository import Repository, default_repo
from plepa_engine.services.schemas import CharacterSchema


class CharacterService:
    """캐릭터 설정 관리 서비스."""

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or default_repo

    def list_characters(self, roster: Optional[str] = None) -> List[Tuple[str, CharacterSchema, Path]]:
        """
        등록된 캐릭터 목록 반환.
        roster가 지정되면 해당 로스터만, None이면 전체 projects/*/characters/ 탐색.
        반환값: List[(roster_name, CharacterSchema, file_path)]
        """
        results: List[Tuple[str, CharacterSchema, Path]] = []
        target_rosters = (
            [PROJECTS_DIR / roster]
            if roster
            else sorted(p for p in PROJECTS_DIR.iterdir() if p.is_dir())
        )

        for r_dir in target_rosters:
            char_dir = r_dir / "characters"
            if not char_dir.is_dir():
                continue
            for f in sorted(char_dir.glob("*.json")):
                try:
                    data = self.repo.read_json(f)
                    char = CharacterSchema.model_validate(data)
                    results.append((r_dir.name, char, f))
                except Exception as e:
                    print(f"[경고] 캐릭터 JSON 로드 실패 ({f.name}): {e}")
        return results

    def find_character(self, char_name: str, roster: str = DEFAULT_ROSTER) -> Tuple[CharacterConfig, str]:
        """
        캐릭터 JSON을 찾아 CharacterConfig와 실제 로스터명을 반환합니다 (기존 CLI 100% 호환).
        """
        clean_name = char_name[:-5] if char_name.endswith(".json") else char_name

        # 1. 지정 로스터 우선 탐색
        char_file = PROJECTS_DIR / roster / "characters" / f"{clean_name}.json"
        if char_file.exists():
            data = self.repo.read_json(char_file)
            return CharacterConfig.from_dict(data, file_path=char_file), roster

        # 2. projects/* 전체에서 탐색
        for proj in sorted(PROJECTS_DIR.iterdir()):
            if proj.is_dir() and proj.name != roster:
                candidate = proj / "characters" / f"{clean_name}.json"
                if candidate.exists():
                    data = self.repo.read_json(candidate)
                    return CharacterConfig.from_dict(data, file_path=candidate), proj.name

        raise FileNotFoundError(f"캐릭터 설정 파일을 찾을 수 없습니다: {char_name} (로스터: {roster})")

    def resolve_characters(self, char_expr: str, roster: str = DEFAULT_ROSTER) -> List[Tuple[CharacterConfig, str]]:
        """
        'all', 쉼표 구분, 또는 단일 캐릭터 표현식을 해석하여 캐릭터 목록 반환 (기존 CLI 100% 호환).
        """
        expr = char_expr.strip().lower()
        if expr == "all":
            char_dir = PROJECTS_DIR / roster / "characters"
            if not char_dir.exists():
                raise FileNotFoundError(f"로스터 캐릭터 폴더를 찾을 수 없습니다: {char_dir}")
            results = []
            for file in sorted(char_dir.glob("*.json")):
                data = self.repo.read_json(file)
                results.append((CharacterConfig.from_dict(data, file_path=file), roster))
            if not results:
                raise FileNotFoundError(f"로스터에 등록된 캐릭터 JSON 파일이 없습니다: {roster}")
            return results

        if "," in char_expr:
            results = []
            for token in char_expr.split(","):
                token = token.strip()
                if token:
                    results.append(self.find_character(token, roster=roster))
            return results

        return [self.find_character(char_expr, roster=roster)]

    def validate_prefix_unique(self, prefix: str, exclude_file: Optional[Path] = None) -> bool:
        """
        동일한 prefix를 가진 캐릭터 파일이 다른 로스터를 포함한 전체 projects에 존재하는지 검사합니다.
        유일하면 True, 중복이 발견되면 False 반환.
        """
        target_prefix = prefix.strip().lower()
        exclude_resolved = exclude_file.resolve() if exclude_file else None

        for r_dir in PROJECTS_DIR.iterdir():
            if not r_dir.is_dir():
                continue
            char_dir = r_dir / "characters"
            if not char_dir.is_dir():
                continue
            for f in char_dir.glob("*.json"):
                if exclude_resolved and f.resolve() == exclude_resolved:
                    continue
                try:
                    data = self.repo.read_json(f)
                    if str(data.get("prefix", "")).strip().lower() == target_prefix:
                        return False
                except Exception:
                    pass
        return True

    def save_character(self, roster: str, char: CharacterSchema, original_file: Optional[Path] = None) -> Path:
        """
        캐릭터를 저장합니다.
        신규 생성이거나 prefix가 변경된 경우 전역 중복 검증을 통과해야 합니다.
        """
        dest_dir = PROJECTS_DIR / roster / "characters"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{char.prefix}.json"

        # 중복 검증
        if not self.validate_prefix_unique(char.prefix, exclude_file=original_file):
            raise ValueError(f"식별자(prefix) '{char.prefix}'는 이미 다른 캐릭터에서 사용 중입니다.")

        # 저장 실행
        saved_path = self.repo.write_json(dest_file, char)

        # prefix 변경으로 인해 파일명이 달라진 경우 구 파일 안전 삭제(휴지통)
        if original_file and original_file.resolve() != dest_file.resolve() and original_file.exists():
            self.repo.move_to_trash(original_file)

        return saved_path

    def delete_character(self, roster: str, prefix: str) -> Optional[Path]:
        """캐릭터 JSON을 휴지통(_trash/)으로 이동하여 안전하게 삭제합니다."""
        target = PROJECTS_DIR / roster / "characters" / f"{prefix}.json"
        if target.exists():
            return self.repo.move_to_trash(target)
        return None

    def clone_character(
        self,
        src_prefix: str,
        src_roster: str,
        new_prefix: str,
        new_name: str,
        target_roster: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        기존 캐릭터를 복제하여 새로운 식별자 및 이름으로 저장합니다 (복제 마법사).
        overrides로 외형(appearance.physique 등)을 즉시 수정할 수 있습니다.
        """
        src_char, _ = self.find_character(src_prefix, roster=src_roster)
        dest_roster = target_roster or src_roster

        # CharacterConfig -> dict -> CharacterSchema
        char_dict = {
            "prefix": new_prefix,
            "name": new_name,
            "gender": src_char.gender,
            "appearance": {
                "face_and_hair": src_char.appearance.face_and_hair,
                "physique": src_char.appearance.physique,
                "outfit": src_char.appearance.outfit,
            },
            "lora": {
                "name": src_char.lora.name,
                "weight": src_char.lora.weight,
            },
            "style_keywords": src_char.style_keywords,
            "sdxl_positive": src_char.sdxl_positive,
            "sdxl_negative": src_char.sdxl_negative,
            "ref_weight": src_char.ref_weight,
            "profiles": dict(src_char.profiles),
            "is_adult": True,
        }

        if overrides:
            if "appearance" in overrides and isinstance(overrides["appearance"], dict):
                char_dict["appearance"].update(overrides["appearance"])
            for k, v in overrides.items():
                if k != "appearance":
                    char_dict[k] = v

        new_schema = CharacterSchema.model_validate(char_dict)
        return self.save_character(roster=dest_roster, char=new_schema)


default_character_service = CharacterService()
