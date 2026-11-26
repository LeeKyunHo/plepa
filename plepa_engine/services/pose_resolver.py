"""
plepa_engine.services.pose_resolver
포즈 섹션 메타데이터 SSOT 레지스트리, 코드 정규화, 젠더/로스터 적합성 판정 및 표현식 해석기.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from plepa_engine.config import DEFAULT_ROSTER
from plepa_engine.models import PoseEntry
from plepa_engine.services.schemas import PoseSetSchema

# 단일 진실 공급원(SSOT) 섹션 메타데이터 레지스트리 (id: {name, short_label, icon, order})
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

ROSTER_THEME_MAP: Dict[str, List[str]] = {
    "murim": ["wuxia_actions"],
    "wuxia": ["wuxia_actions"],
    "maid": ["maid"],
}
OPTIONAL_COSTUME_SECTIONS: set = {"swimsuit", "bdsm", "bunny"}
THEME_ACTION_SECTIONS: set = {"spy_actions", "wuxia_actions", "maid", "combat"}

_LEGACY_SET_ALIASES: Dict[str, str] = {
    "campus_106": "campus_108",
    "emotions_all": "emotions_20",
    "h_scenes_all": "h_scenes_52",
}

_SECTION_EXPR_RULES: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...], Optional[str]], ...] = (
    (("emotions", "emotion", "a"), ("emotions",), "A"),
    (("poses", "pose", "b"), ("poses",), "B"),
    (("events", "event", "genit_actions", "daily_events"), ("events", "genit_actions", "daily_events"), "B"),
    (("romance", "rom"), ("romance",), None),
    (("h_scenes", "h", "scenes", "n"), ("h_scenes", "special_h", "special_female_h"), "N"),
    (("special_h", "special", "sph", "special_female_h"), ("special_h", "special_female_h"), None),
    (("otokonoko", "scenes_otokonoko", "oto"), ("scenes_otokonoko", "special_otokonoko", "special_otokonoko_h"), None),
    (("special_otokonoko", "sp_oto", "special_otokonoko_h"), ("special_otokonoko", "special_otokonoko_h"), None),
    (("swimsuit", "swim", "d"), ("swimsuit",), "D"),
    (("bunny", "f"), ("bunny",), "F"),
    (("maid", "g"), ("maid",), "G"),
    (("combat", "battle", "i"), ("combat",), "I"),
    (("spy", "spy_actions", "s"), ("spy_actions",), "S"),
    (("wuxia", "wuxia_actions", "c"), ("wuxia_actions",), "C"),
)


def normalize_pose_code(code: Any) -> str:
    """포즈 코드를 정규화합니다 (숫자는 3자리 000, 영문+숫자는 D01, A01 형태로 패딩)."""
    code_s = str(code).strip()
    try:
        return f"{int(code_s):03d}"
    except ValueError:
        if len(code_s) >= 2 and code_s[0].isalpha() and code_s[1:].isdigit():
            return f"{code_s[0].upper()}{int(code_s[1:]):02d}"
        return code_s.upper()


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

    try:
        code_num = int(effective_code)
        if char_gender == "otokonoko" and 80 <= code_num <= 139:
            return False
        if char_gender != "otokonoko" and ((133 <= code_num <= 135) or (150 <= code_num <= 209)):
            return False
    except ValueError:
        pass

    return True


def _resolve_all_codes(db: Dict[str, PoseEntry], roster: Optional[str]) -> List[str]:
    allowed_themes = set(ROSTER_THEME_MAP.get(roster.lower(), [])) if roster else set()

    def _allowed(entry: PoseEntry) -> bool:
        if not entry.is_active:
            return False
        if entry.section in OPTIONAL_COSTUME_SECTIONS:
            return False
        if entry.section in THEME_ACTION_SECTIONS:
            return entry.section in allowed_themes
        return entry.code.isdigit()

    def _sort_key(k: str) -> Tuple[int, int, str]:
        try:
            return (0, int(k), "")
        except ValueError:
            return (1, 0, k)

    return sorted([c for c, e in db.items() if _allowed(e)], key=_sort_key)


def _resolve_section_alias(expr_lower: str, db: Dict[str, PoseEntry]) -> Optional[List[str]]:
    for aliases, sections, prefix in _SECTION_EXPR_RULES:
        if expr_lower in aliases:
            return [
                c for c, e in db.items()
                if e.is_active and (e.section in sections or (prefix is not None and c.startswith(prefix)))
            ]
    return None


def _resolve_range_expr(expr: str, db: Dict[str, PoseEntry]) -> Optional[List[str]]:
    start_s, end_s = (part.strip() for part in expr.split("..", 1))
    if start_s and end_s and start_s[0].isalpha() and end_s[0].isalpha() and start_s[0].upper() == end_s[0].upper():
        prefix = start_s[0].upper()
        try:
            s_num, e_num = int(start_s[1:]), int(end_s[1:])
            return [
                f"{prefix}{i:02d}" for i in range(s_num, e_num + 1)
                if f"{prefix}{i:02d}" in db and db[f"{prefix}{i:02d}"].is_active
            ]
        except ValueError:
            pass
    try:
        start, end = int(start_s), int(end_s)
        return [
            f"{i:03d}" for i in range(start, end + 1)
            if f"{i:03d}" in db and db[f"{i:03d}"].is_active
        ]
    except ValueError:
        return None


def resolve_pose_codes_expr(
    expr: str,
    db: Dict[str, PoseEntry],
    load_pose_sets_fn: Callable[[], List[PoseSetSchema]],
    roster: Optional[str] = None,
) -> List[str]:
    """포즈 표현식(all, 섹션명, 쉼표 나열, 세트 ID, 범위, 단일 코드)을 활성 코드 목록으로 해석합니다."""
    expr = expr.strip()
    expr_lower = expr.lower()

    if expr_lower == "all":
        return _resolve_all_codes(db, roster)

    section_match = _resolve_section_alias(expr_lower, db)
    if section_match is not None:
        return section_match

    if "," in expr:
        codes: List[str] = []
        for token in (tok.strip() for tok in expr.split(",") if tok.strip()):
            for sub_c in resolve_pose_codes_expr(token, db, load_pose_sets_fn, roster=roster):
                if sub_c not in codes:
                    codes.append(sub_c)
        return codes

    target_set_id = _LEGACY_SET_ALIASES.get(expr_lower, expr_lower)
    for pset in load_pose_sets_fn():
        if pset.id.lower() == target_set_id:
            return [c for c in pset.codes if c in db]

    if ".." in expr:
        range_codes = _resolve_range_expr(expr, db)
        if range_codes is not None:
            return range_codes

    single_code = normalize_pose_code(expr)
    if single_code in db:
        return [single_code]

    for k in db.keys():
        if k.lower() == expr_lower:
            return [k]

    raise ValueError(f"유효하지 않은 포즈 코드/표현식입니다: {expr}")
