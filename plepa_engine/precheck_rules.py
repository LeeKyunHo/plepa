"""
plepa_engine.precheck_rules
이미지 생산 사전 점검기(precheck)의 포즈/배경/캐릭터/조합/ComfyUI 노드 검증 규칙 헬퍼 모듈.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Tuple

from plepa_engine.prompt_builder import (
    assemble_sdxl_prompt,
    resolve_pose_outfit_slot,
    strip_sdxl_outfit_tags,
)

# 캐릭터별 기본 착의(default) 고유 시그니처 의상 핵심 키워드 (spy 로스터 기준, 타 로스터는 appearance.outfit에서 자동 추출)
_SIGNATURE_OUTFIT_TOKENS: Dict[str, Tuple[str, ...]] = {
    # spy 로스터
    "kzk": ("doctor coat", "halter bikini top", "garter belt"),
    "chl": ("cheongsam qipao", "gold embroidery", "high side slits"),
    "rvn": ("collared shirt", "loose black necktie", "micro pencil skirt"),
    "dom": ("black lace robe", "crimson", "micro corset"),
    "evl": ("nurse cap", "nurse uniform mini dress", "white thighhighs"),
    "srh": ("bunny suit", "bolero jacket", "black bunny ears"),
    "vic": ("white silk blouse", "navy corset vest", "black pencil skirt"),
    "cla": ("collared blouse", "slate-navy blue corset vest", "micro pencil skirt"),
    "viv": ("collared blouse", "leather shoulder holster", "garter straps"),
    "scl": ("cropped leather jacket", "buckle strap across chest", "leather micro shorts"),
    # campus 로스터
    "aya": ("dress shirt", "shorts"),
    "har": ("knit cardigan", "skirt"),
    "kao": ("black dress", "denim jacket"),
    "mai": ("lab coat", "sweater"),
    "shz": ("sweatshirt", "hotpants"),
    "yur": ("knit top", "miniskirt"),
    # ykn 로스터
    "hay": ("button-up blouse", "pleated skirt"),
    "ser": ("knit cardigan", "blouse", "pleated skirt"),
    "sia": ("trench jacket", "collared blouse", "pleated skirt"),
    "yua": ("knit cardigan", "collared blouse", "pleated skirt"),
}
_SPY_SIGNATURE_OUTFIT_TOKENS = _SIGNATURE_OUTFIT_TOKENS

# 탈의(nude) 및 테마 스왑 시 캐릭터 본체 파트(BREAK 뒷단)에 절대 남아있으면 안 되는 기본 의상 키워드
_FORBIDDEN_LEAK_TOKENS_IN_NUDE: Tuple[str, ...] = (
    "doctor coat",
    "cheongsam",
    "qipao",
    "loose black necktie",
    "micro pencil skirt",
    "pencil skirt",
    "black lace robe",
    "nurse cap",
    "nurse uniform",
    "bolero jacket",
    "navy corset vest",
    "slate-navy blue corset vest",
    "leather shoulder holster",
    "cropped leather jacket",
    "leather micro shorts",
    "ankle boots",
)

_FORBIDDEN_POSE_WORDS = (
    "introduction pose",
    "blank face",
    "featureless face",
    "mermaid",
    "fishtail",
    "chandelier",
    "curtains",
    "pulling collar down",
    "bra strap",
)

_FORBIDDEN_CHAR_WORDS = (
    "holding ",
    "syringe",
    "cigarette holder",
    "folder",
    "front tie",
    "front button",
    "wrap front",
    "front cleavage",
    "exposed cleavage",
    "heavy cleavage",
    "mermaid",
    "clean background",
    "soft lighting",
)


def check_pose_db_rules(sdxl_db: Dict[str, Any], report: Any) -> None:
    """[1단계] 포즈 DB 제작 규칙(라벨 길이, description, 금지어, 1girl/배경 하드코딩)을 전수 검사합니다."""
    for code, entry in sdxl_db.items():
        if not (2 <= len(entry.label) <= 15):
            report.errors.append(
                f"[포즈규칙] sdxl:{code} 라벨 길이 규격 위반 ({entry.label!r}, 길이={len(entry.label)})"
            )
        if not entry.description or len(entry.description.strip()) < 5:
            report.errors.append(f"[포즈규칙] sdxl:{code} description 누락 또는 너무 짧음")

        for field_name, p_field in (
            ("prompt", entry.prompt),
            ("prompt_female", entry.prompt_female),
            ("prompt_otokonoko", entry.prompt_otokonoko),
        ):
            if not p_field:
                continue
            low = p_field.lower()
            for bad in _FORBIDDEN_POSE_WORDS:
                if re.search(r"\b" + re.escape(bad) + r"\b", low):
                    report.errors.append(f"[포즈규칙] sdxl:{code} ({field_name}) 금지어 포함 ({bad!r})")
            if "parted lips" in low and "puckered lips" in low:
                report.errors.append(
                    f"[포즈규칙] sdxl:{code} ({field_name}) 구강 왜곡 유발 동시 사용 (parted lips + puckered lips)"
                )

            if entry.section == "scenes_otokonoko" or field_name == "prompt_otokonoko":
                if re.search(r"\b1girl\b", low):
                    report.errors.append(
                        f"[포즈규칙] sdxl:{code} ({field_name}) 오토코노코 프롬프트 내 1girl 하드코딩 금지 위반"
                    )
            elif entry.section in ("emotions", "poses", "romance", "spy_actions", "wuxia_actions"):
                if field_name == "prompt" and not entry.prompt_otokonoko and re.search(r"\b1girl\b", low):
                    report.errors.append(
                        f"[포즈규칙] sdxl:{code} 공용 섹션({entry.section}) 내 prompt_otokonoko 분기 없이 1girl 하드코딩 금지 위반"
                    )

            if entry.section in ("emotions", "poses", "romance", "h_scenes", "scenes_otokonoko"):
                for bad_bg in ("classroom", "school hallway", "cafe setting", "salon lounge", "maid cafe"):
                    if re.search(r"\b" + re.escape(bad_bg) + r"\b", low):
                        report.errors.append(
                            f"[포즈규칙] sdxl:{code} ({field_name}) 공용 섹션 내 로스터 종속 배경 하드코딩 금지 위반 ({bad_bg!r}) — projects/{{roster}}/pose_background_mapping.json에 위임하세요"
                        )


def check_default_background_rules(roster: str, bg_file: Path, report: Any) -> None:
    """기본 배경 프리셋 내 전신 스케일 왜곡 유발 어휘 포함 여부를 검사합니다."""
    if not bg_file.exists():
        return
    bg_raw = json.loads(bg_file.read_text(encoding="utf-8"))
    default_sdxl_bg = bg_raw.get("presets", {}).get("default", {}).get("sdxl", "").lower()
    for bad_bg in ("chandelier", "ceiling", "sofa", "couch", "curtains", "drapes"):
        if re.search(r"\b" + re.escape(bad_bg) + r"\b", default_sdxl_bg):
            report.errors.append(
                f"[배경규칙] {roster}/background.json default 프리셋에 전신 스케일 왜곡 유발 어휘 포함 ({bad_bg!r})"
            )


def extract_char_signature_tokens(char: Any, pfx: str) -> Tuple[str, ...]:
    """캐릭터 고유 시그니처 의상 핵심 키워드를 추출합니다."""
    explicit_sig = getattr(char, "signature_outfit_tokens", None)
    if explicit_sig:
        return tuple(explicit_sig)

    pos_body = (
        char.sdxl_positive.split(" BREAK ", 1)[1]
        if char.sdxl_positive and " BREAK " in char.sdxl_positive
        else (char.sdxl_positive or "")
    )
    if not pos_body:
        return _SPY_SIGNATURE_OUTFIT_TOKENS.get(pfx, ())

    stripped_body = strip_sdxl_outfit_tags(pos_body)
    kept_tags = {
        t.strip().translate(str.maketrans("", "", "()[]{}")).split(":")[0].strip().lower()
        for t in stripped_body.split(",")
        if t.strip()
    }
    excluded_clothed_h_fragments = (
        "unbuttoned", "open shirt", "clothes open",
        "garter", "thighhigh", "stocking", "pantyhose", "panties", "underwear",
    )
    extracted = []
    for raw_t in pos_body.split(","):
        clean_t = raw_t.strip().translate(str.maketrans("", "", "()[]{}")).split(":")[0].strip()
        low_t = clean_t.lower()
        if (
            len(clean_t) > 3
            and low_t not in kept_tags
            and not any(frag in low_t for frag in excluded_clothed_h_fragments)
        ):
            extracted.append(clean_t)
    return tuple(extracted[:3])


def check_character_json_rules(char: Any, pfx: str, report: Any) -> None:
    """[2단계] 개별 캐릭터 JSON의 BREAK 구분자·비율·금지어·네거티브 무결성을 검사합니다."""
    pos = char.sdxl_positive or ""
    nude_pos = getattr(char, "sdxl_nude_positive", "") or ""
    neg = char.sdxl_negative or ""

    if " BREAK " not in pos:
        report.errors.append(f"[캐릭터규칙] {pfx}: sdxl_positive에 ' BREAK ' 구분자 누락")
    if not nude_pos or " BREAK " not in nude_pos:
        report.errors.append(f"[캐릭터규칙] {pfx}: sdxl_nude_positive 누락 또는 ' BREAK ' 구분자 누락")
    if "long slender limbs" in pos.lower() or "long slender limbs" in nude_pos.lower():
        report.errors.append(f"[캐릭터규칙] {pfx}: 9~10등신 기형 유발 태그 'long slender limbs' 잔류")

    for bad_char in _FORBIDDEN_CHAR_WORDS:
        if bad_char in pos.lower() or bad_char in nude_pos.lower():
            report.errors.append(f"[캐릭터규칙] {pfx}: 캐릭터 JSON 금지어 포함 ({bad_char!r})")

    for bad_neg in ("sweat,", "liquid", "splatter"):
        if bad_neg in neg.lower():
            report.errors.append(f"[캐릭터규칙] {pfx}: sdxl_negative에 체액 차단 금지어 포함 ({bad_neg!r})")


def simulate_prompt_combinations(
    char: Any, pfx: str, sig_tokens: Tuple[str, ...], sdxl_db: Dict[str, Any], report: Any
) -> None:
    """[3~5단계] 전 포즈 조립 시뮬레이션(착의 고정·H씬 알몸 전환·테마 의상 격리)을 수행합니다."""
    for code, pose in sdxl_db.items():
        report.total_combinations_checked += 1
        slot = resolve_pose_outfit_slot(pose)
        pos_out, neg_out, is_nude = assemble_sdxl_prompt(char, pose)
        char_chunk = pos_out.split(" BREAK ")[1].lower() if " BREAK " in pos_out else pos_out.lower()

        if slot == "default":
            if is_nude:
                report.errors.append(f"[착의고정] {pfx}:{code} default 슬롯인데 is_nude=True 반환")
            for tok in sig_tokens:
                if tok.lower() not in char_chunk:
                    report.errors.append(f"[착의고정] {pfx}:{code} 착의 씬에서 고유 의상 토큰 누락 ({tok!r})")
            if "completely nude" in char_chunk:
                report.errors.append(f"[착의고정] {pfx}:{code} 착의 씬에 completely nude 오주입")
        elif slot == "nude":
            if not is_nude:
                report.errors.append(f"[알몸전환] {pfx}:{code} nude 슬롯인데 is_nude=False 반환")
            if "nude, completely nude" not in pos_out.lower():
                report.errors.append(f"[알몸전환] {pfx}:{code} 긍정 프롬프트에 'nude, completely nude' 누락")
            for leak in _FORBIDDEN_LEAK_TOKENS_IN_NUDE:
                if leak in char_chunk:
                    report.errors.append(f"[알몸전환] {pfx}:{code} H씬/탈의 프롬프트에 기본 의상 잔류 ({leak!r})")
            if "(clothes:1.25)" not in neg_out.lower() and "(clothes:1.35)" not in neg_out.lower():
                report.errors.append(f"[알몸전환] {pfx}:{code} 부정 프롬프트에 [패치 A] 의상 차단 태그 누락")
        else:
            if is_nude:
                report.errors.append(f"[테마스왑] {pfx}:{code} 테마 슬롯({slot})인데 is_nude=True 반환")
            if slot != "combat":
                for leak in ("doctor coat", "cheongsam", "nurse uniform", "cropped leather jacket"):
                    if leak in char_chunk:
                        report.errors.append(f"[테마스왑] {pfx}:{code} ({slot}) 프롬프트에 기본 의상 잔류 ({leak!r})")


def check_pose_background_mapping(roster: str, bg_file: Path, mapping_file: Path, report: Any) -> None:
    """[6단계] 로스터별 포즈 배경 매핑(`pose_background_mapping.json`) 무결성을 검사합니다."""
    if not mapping_file.exists():
        return
    try:
        map_data = json.loads(mapping_file.read_text(encoding="utf-8"))
        default_bg_key = map_data.get("default_background", "default")

        valid_bg_keys = set()
        if bg_file.exists():
            bg_raw = json.loads(bg_file.read_text(encoding="utf-8"))
            valid_bg_keys = set(bg_raw.keys())
            if "presets" in bg_raw:
                valid_bg_keys.update(bg_raw["presets"].keys())

        if valid_bg_keys and default_bg_key not in valid_bg_keys:
            report.errors.append(
                f"[배경매핑규칙] {roster}/pose_background_mapping.json의 default_background '{default_bg_key}'가 background.json에 정의되어 있지 않습니다."
            )

        for code_pattern, mapped_bg in map_data.get("pose_mappings", {}).items():
            if mapped_bg not in ("none", "auto") and valid_bg_keys and mapped_bg not in valid_bg_keys:
                report.errors.append(
                    f"[배경매핑규칙] {roster} 포즈 대역 '{code_pattern}'에 매핑된 배경 '{mapped_bg}'가 background.json에 실존하지 않습니다."
                )
    except Exception as e:
        report.errors.append(f"[배경매핑규칙] {roster}/pose_background_mapping.json 파싱 실패: {e}")


def check_comfy_nodes(report: Any) -> None:
    """ComfyUI 필수 커스텀 노드 사전 검증을 수행합니다."""
    try:
        from plepa_engine.comfy_client import verify_required_nodes
        ok, missing = verify_required_nodes()
        if not ok:
            if "SERVER_UNREACHABLE" in missing:
                report.warnings.append(f"[ComfyUI점검] {missing['SERVER_UNREACHABLE']}")
            else:
                for node, pack in missing.items():
                    report.errors.append(
                        f"[ComfyUI점검] 필수 커스텀 노드 '{node}'가 누락되었습니다! (필요 확장팩: {pack})"
                    )
    except Exception as e:
        report.warnings.append(f"[ComfyUI점검] 노드 사전 검증 중 예외 발생: {e}")
