"""
plepa_engine.profile_resolver
Kiro 호환 _profiles 로드, 성별 및 캐릭터 프로필 매칭, 프롬프트 주입 해석기.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from plepa_engine.models import CharacterConfig


# Kiro pose_database.json 표준 3대 빌트인 프로필
BUILTIN_PROFILES: Dict[str, Dict[str, str]] = {
    "female": {
        "base_positive": (
            "masterpiece, best quality, highly detailed, clean background, "
            "soft lighting, character portrait, cowboy shot, 1girl, solo"
        ),
        "base_negative": (
            "worst quality, low quality, blurry, bad anatomy, bad hands, "
            "extra fingers, extra limbs, deformed, disfigured, watermark, "
            "signature, text, jpeg artifacts, cropped, 1boy, male, masculine, "
            "beard, mustache, facial hair, muscular, animal ears, cat ears, "
            "beast ears, fox ears, dog ears, animal tail"
        ),
    },
    "male": {
        "base_positive": (
            "masterpiece, best quality, highly detailed, clean background, "
            "soft lighting, character portrait, cowboy shot, 1boy, solo, masculine"
        ),
        "base_negative": (
            "worst quality, low quality, blurry, bad anatomy, bad hands, "
            "extra fingers, extra limbs, deformed, disfigured, watermark, "
            "signature, text, jpeg artifacts, cropped, 1girl, female, breasts, feminine"
        ),
    },
    "male_otokonoko": {
        "base_positive": (
            "masterpiece, best quality, highly detailed, clean background, "
            "soft lighting, character portrait, cowboy shot, 1boy, solo, androgynous, "
            "feminine face, slender build, flat chest, delicate features"
        ),
        "base_negative": (
            "worst quality, low quality, blurry, bad anatomy, bad hands, animal ears, "
            "cat ears, beast ears, fox ears, dog ears, animal tail, extra fingers, "
            "extra limbs, deformed, disfigured, watermark, signature, text, jpeg artifacts, "
            "cropped, 2boys, multiple characters, clone, duplicate, 1girl, female, "
            "breasts, large breasts, heavy cleavage, female genitalia, female anatomy, "
            "muscular, manly, beard, mustache, facial hair, uncensored, no censor, "
            "thin censorship, visible penis, large penis, erection, testicles, "
            "freckles, skin spots, blemishes, complex background"
        ),
    },
}


def load_global_profiles(pose_db: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    pose_database 딕셔너리에서 _profiles 섹션을 로드하여 정규화된 딕셔너리로 반환합니다.

    Args:
        pose_db (Dict[str, Any]): pose_database.json 원본 딕셔너리

    Returns:
        Dict[str, Dict[str, str]]: {프로필명: {"base_positive": str, "base_negative": str}} 매핑.
                                   _profiles 섹션이 누락되었거나 비어있을 경우 내장 기본 프로필(BUILTIN_PROFILES)을 반환합니다.
    """
    raw_profiles = pose_db.get("_profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        return {k: dict(v) for k, v in BUILTIN_PROFILES.items()}

    profiles: Dict[str, Dict[str, str]] = {}
    for name, body in raw_profiles.items():
        if not isinstance(body, dict):
            continue
        pos = str(body.get("base_positive") or body.get("positive") or "").strip()
        neg = str(body.get("base_negative") or body.get("negative") or "").strip()
        if pos:
            profiles[str(name).strip()] = {
                "base_positive": pos,
                "base_negative": neg,
            }

    # 기본 필수 프로필(female, male, male_otokonoko)이 누락되었을 경우 내장값으로 폴백 보충
    for k, v in BUILTIN_PROFILES.items():
        if k not in profiles:
            profiles[k] = dict(v)

    return profiles


def resolve_character_profile(
    char: CharacterConfig,
    gender: str,
    global_profiles: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, str]:
    """
    캐릭터 설정과 성별 문자열을 기반으로 최적의 프로필 딕셔너리를 결정합니다.

    우선순위:
    1. gender 인자 또는 char.gender 성별 문자열 정규화 (otokonoko, male, female 매핑)
    2. global_profiles (또는 내장 BUILTIN_PROFILES)에서 일치하는 프로필 매칭
    3. 캐릭터 고유의 커스텀 sdxl_positive / sdxl_negative 속성이 있다면 char_positive/char_negative로 포함

    Args:
        char (CharacterConfig): 캐릭터 설정 객체
        gender (str): 대상 성별 문자열 ("female", "male", "male_otokonoko", "otokonoko" 등)
        global_profiles (Optional[Dict[str, Dict[str, str]]]): 로드된 전역 프로필 딕셔너리

    Returns:
        Dict[str, str]: {"name": str, "base_positive": str, "base_negative": str, ...} 구조의 딕셔너리
    """
    profiles = global_profiles if global_profiles is not None else BUILTIN_PROFILES

    # 성별 문자열 정규화
    g_raw = (gender or getattr(char, "gender", "female") or "female").strip().lower()

    if g_raw in ("otokonoko", "male_otokonoko", "oto", "scenes_otokonoko", "femboy"):
        target_key = "male_otokonoko"
    elif g_raw in ("male", "m", "man", "boy"):
        target_key = "male"
    else:
        target_key = "female"

    base_prof = profiles.get(target_key, BUILTIN_PROFILES.get(target_key, BUILTIN_PROFILES["female"]))

    result: Dict[str, str] = {
        "name": target_key,
        "base_positive": base_prof.get("base_positive", ""),
        "base_negative": base_prof.get("base_negative", ""),
    }

    if getattr(char, "sdxl_positive", None):
        result["char_positive"] = char.sdxl_positive.strip()
    if getattr(char, "sdxl_negative", None):
        result["char_negative"] = char.sdxl_negative.strip()

    return result


def _join_and_dedup_tags(*parts: str) -> str:
    """쉼표로 구분된 태그들을 결합하고 순서를 유지하며 대소문자 중복을 제거합니다."""
    combined = ", ".join(p.strip() for p in parts if p and p.strip())
    tags = [t.strip() for t in combined.split(",") if t.strip()]
    seen = set()
    deduped = []
    for tag in tags:
        lower_tag = tag.lower()
        if lower_tag not in seen:
            seen.add(lower_tag)
            deduped.append(tag)
    return ", ".join(deduped)


def apply_profile_to_prompt(prompt: str, profile: Dict[str, str]) -> str:
    """
    기존 프롬프트 문자열에 프로필의 base_positive 태그를 적절히 결합합니다.

    - BREAK 문법이 포함되어 있을 경우 품질/구도와 외형 청크로 분리 결합
    - 일반 쉼표 태그 프롬프트의 경우 base_positive 최전방 결합 및 중복 정리

    Args:
        prompt (str): 기존 프롬프트 (포즈, 외형 태그 등)
        profile (Dict[str, str]): {"base_positive": str, ...} 구조의 프로필 딕셔너리

    Returns:
        str: 프로필이 주입된 최종 프롬프트 문자열
    """
    base_pos = (profile.get("base_positive") or profile.get("positive") or "").strip()
    p_clean = (prompt or "").strip()

    if not base_pos:
        return p_clean
    if not p_clean:
        return base_pos

    # 1. 기존 prompt 에 BREAK 가 있는 경우: [base_pos, first_chunk] BREAK [second_chunk]
    if " BREAK " in p_clean:
        first_chunk, second_chunk = p_clean.split(" BREAK ", 1)
        joined_first = _join_and_dedup_tags(base_pos, first_chunk)
        return f"{joined_first} BREAK {second_chunk.strip()}"

    # 2. base_pos 에 BREAK 가 있는 경우: [quality_part, p_clean] BREAK [char_part]
    if " BREAK " in base_pos:
        quality_part, char_part = base_pos.split(" BREAK ", 1)
        joined_first = _join_and_dedup_tags(quality_part, p_clean)
        return f"{joined_first} BREAK {char_part.strip()}"

    # 3. 단순 쉼표 태그 결합 및 공백/중복 정리
    return _join_and_dedup_tags(base_pos, p_clean)

