"""
plepa_engine.pipeline.assembly
2단계(PositiveAssemblyMutator): 캐릭터 외형/의상/소품과 포즈를 결합한 긍정 프롬프트 1차 조립 모듈.
"""

from __future__ import annotations

import re
from typing import List

from plepa_engine.pipeline.constants import (
    _ACCESSORY_BASE_NOUNS,
    _DAILY_AMBIENT_CLEANUP_RE,
    _DAILY_POSE_LIGHT_CLEANUP_RE,
    _FACE_HAIR_ACCESSORY_KEYWORDS,
    _H_SCENE_MOOD_LIGHTING_TAGS,
    _H_SCENE_WET_SKIN_TAGS,
    _STYLE_POSITIVE_BALANCED_TAGS,
    _STYLE_POSITIVE_GUARD_TAGS,
    _is_outdoor_daylight_pose,
)
from plepa_engine.pipeline.context import PromptContext, PromptMutator
from plepa_engine.pipeline.tags import (
    _strip_tags_preserving_parens,
    harmonize_character_expression,
    normalize_tag,
)
from plepa_engine.prompt_builder import (
    DEFAULT_SDXL_QUALITY_TAGS,
    get_character_outfit_prompt,
    strip_sdxl_outfit_tags,
)


def _inject_style_positive_guard(quality_clean: str, ctx: PromptContext) -> str:
    """style_mode(legacy/balanced/glossy)에 따라 화풍 가드 태그를 중복 없이 주입한다."""
    mode = (getattr(ctx, "style_mode", "legacy") or "legacy").strip().lower()
    if mode == "legacy":
        return quality_clean
    tags = _STYLE_POSITIVE_GUARD_TAGS if mode == "glossy" else _STYLE_POSITIVE_BALANCED_TAGS
    low = quality_clean.lower()
    for tag in tags:
        if ctx.is_dark_skin and tag == "smooth pale skin":
            continue
        if ctx.nude and tag == "detailed fabric texture":
            continue
        if tag.lower() not in low:
            quality_clean = f"{quality_clean}, {tag}"
            low = quality_clean.lower()
    return quality_clean


def _inject_wet_skin_tags(text: str, ctx: PromptContext) -> str:
    """ADR-102/S3: H-씬(is_steamy_h_scene)일 때 수분광·땀방울·열기 및 심야 무드 라이팅 태그를 1번째 청크에 중복 없이 주입한다."""
    if not ctx.is_steamy_h_scene:
        return text
    tags = list(_H_SCENE_WET_SKIN_TAGS)
    if not _is_outdoor_daylight_pose(ctx.pose_tag):
        tags.extend(_H_SCENE_MOOD_LIGHTING_TAGS)
    low = text.lower()
    for tag in tags:
        core = tag.strip("()").split(":")[0].strip().lower()
        if core not in low and tag.lower() not in low:
            text = f"{text}, {tag}"
            low = text.lower()
    return text


def _assemble_positive_prompt(base_pos: str, pose_tag: str, ctx: PromptContext) -> str:
    """BREAK 유무에 따라 캐릭터 표현 조화, 2인 solo 제거, 추가 품질 키워드 및 custom_pos를 일관되게 조립합니다."""
    clean_pose_tag = _DAILY_POSE_LIGHT_CLEANUP_RE.sub("", pose_tag).strip(" ,") if not ctx.is_steamy_h_scene else pose_tag
    if " BREAK " in base_pos:
        quality_part, char_part = base_pos.split(" BREAK ", 1)
        char_part = harmonize_character_expression(char_part, clean_pose_tag)
        if ctx.is_two_person:
            char_part = re.sub(
                r",?\s*\b(1girl,\s*solo|1boy,\s*solo)\b",
                lambda m: ", 1girl" if "1girl" in m.group(0).lower() else ", 1boy",
                char_part,
                flags=re.IGNORECASE,
            )
            char_part = re.sub(r",?\s*\bsolo\b", "", char_part, flags=re.IGNORECASE)
            char_part = re.sub(r"^\s*,\s*", "", char_part)
        if not ctx.is_steamy_h_scene:
            quality_clean = _DAILY_AMBIENT_CLEANUP_RE.sub("", quality_part).strip(" ,")
        else:
            quality_clean = re.sub(
                r",?\s*(HDR|high contrast|cartoon|photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|volumetric lighting)",
                "",
                quality_part,
                flags=re.IGNORECASE,
            ).strip(" ,")
            if not _is_outdoor_daylight_pose(clean_pose_tag):
                quality_clean = re.sub(r",?\s*\bsoft lighting\b", "", quality_clean, flags=re.IGNORECASE).strip(" ,")
        for kw in ctx.extra_quality_kws:
            if kw.lower() not in quality_clean.lower():
                quality_clean = f"{quality_clean}, {kw}"
        quality_clean = _inject_style_positive_guard(quality_clean, ctx)
        if "unholy-aesthetic" not in quality_clean.lower():
            quality_clean = f"unholy-aesthetic, {quality_clean}" if quality_clean else "unholy-aesthetic"
        prefix_tags = f"{ctx.custom_pos.strip()}, {quality_clean.strip()}" if ctx.custom_pos and ctx.custom_pos.strip() else quality_clean.strip()
        first_chunk = f"{prefix_tags}, {clean_pose_tag}" if clean_pose_tag else prefix_tags
        first_chunk = _inject_wet_skin_tags(first_chunk, ctx)
        return f"{first_chunk} BREAK {char_part.strip()}"

    base_pos = harmonize_character_expression(base_pos, clean_pose_tag)
    if not ctx.is_steamy_h_scene:
        base_pos = _DAILY_POSE_LIGHT_CLEANUP_RE.sub("", base_pos).strip(" ,")
    if ctx.is_two_person:
        base_pos = re.sub(r",?\s*\b(solo|1girl, solo)\b", ", 1girl", base_pos, flags=re.IGNORECASE)
    base_pos = _inject_style_positive_guard(base_pos, ctx)
    if "unholy-aesthetic" not in base_pos.lower():
        base_pos = f"unholy-aesthetic, {base_pos}" if base_pos else "unholy-aesthetic"
    prefix_tags = f"{ctx.custom_pos.strip()}, {base_pos}" if ctx.custom_pos and ctx.custom_pos.strip() else base_pos
    assembled = f"{prefix_tags}, {clean_pose_tag}" if clean_pose_tag else prefix_tags
    return _inject_wet_skin_tags(assembled, ctx)


def _is_face_hair_accessory(tag: str) -> bool:
    """탈의(nude) 상태에서도 유지할 얼굴/헤어 소품인지 판별합니다."""
    low = (tag or "").strip().lower()
    return any(kw in low for kw in _FACE_HAIR_ACCESSORY_KEYWORDS)


def _strip_accessory_negative_conflicts(neg: str, accessories: List[str]) -> str:
    """활성화된 signature_accessories와 충돌하는 네거티브 전체구문·핵심 소품 명사를 함께 제거합니다."""
    if not accessories:
        return neg
    patterns: List[str] = []
    for sig_acc in accessories:
        acc_core = normalize_tag(sig_acc)
        if not acc_core:
            continue
        patterns.append(re.escape(acc_core))
        for noun in _ACCESSORY_BASE_NOUNS:
            if re.search(rf"\b{re.escape(noun)}\b", acc_core):
                patterns.append(re.escape(noun))
    if not patterns:
        return neg
    combined = r"\b(?:" + "|".join(sorted(set(patterns), key=len, reverse=True)) + r")\b(?::[0-9\.]+)?"
    return _strip_tags_preserving_parens(neg, combined)


def _select_active_signature_accessories(ctx: PromptContext) -> List[str]:
    """현재 슬롯(착의/탈의)에 맞춰 활성화할 캐릭터 고유 장신구·소품 목록을 반환합니다."""
    raw = getattr(ctx.char, "signature_accessories", None) or []
    items = [str(item).strip() for item in raw if str(item).strip()]
    if ctx.nude:
        return [item for item in items if _is_face_hair_accessory(item)]
    return items


def _inject_signature_accessories(base_pos: str, ctx: PromptContext) -> str:
    """signature_accessories를 2차 청크 선두(CLIP 75토큰 이내)에 중복 없이 우선 배치합니다."""
    active = _select_active_signature_accessories(ctx)
    if not active:
        return base_pos

    if " BREAK " in base_pos:
        head, char_part = base_pos.split(" BREAK ", 1)
    else:
        head, char_part = "", base_pos

    cleaned_char = char_part
    formatted_tags: List[str] = []
    for acc in active:
        core = normalize_tag(acc)
        if not core:
            continue
        cleaned_char = _strip_tags_preserving_parens(
            cleaned_char,
            rf"\(?{re.escape(core)}(?::[0-9\.]+)?\)?",
        )
        formatted_tags.append(acc if ":" in acc else f"({core}:1.10)")

    if not formatted_tags:
        return base_pos

    char_tokens = [t.strip() for t in cleaned_char.split(",") if t.strip()]
    anchor_kws = ("1girl", "1boy", "solo", "androgynous", "otokonoko", "femboy")
    insert_idx = 0
    for idx, tok in enumerate(char_tokens[:4]):
        tok_low = normalize_tag(tok)
        if any(k in tok_low for k in anchor_kws):
            insert_idx = idx + 1
    new_char_tokens = char_tokens[:insert_idx] + formatted_tags + char_tokens[insert_idx:]
    new_char_part = ", ".join(new_char_tokens)
    return f"{head} BREAK {new_char_part}" if head else new_char_part


class PositiveAssemblyMutator(PromptMutator):
    """2단계: 캐릭터 외형/의상과 포즈를 결합하여 긍정 프롬프트(Positive Prompt) 1차 조립."""

    def mutate(self, ctx: PromptContext) -> None:
        pose_tag = ctx.pose_tag

        if (ctx.nude or ctx.slot != "default") and getattr(ctx.char, "sdxl_nude_positive", None):
            base_pos = ctx.char.sdxl_nude_positive.strip()
            if not ctx.is_steamy_h_scene:
                base_pos = re.sub(r",?\s*(photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|wet skin|sweatdrop|\bsweat\b|volumetric lighting)", "", base_pos, flags=re.IGNORECASE)
            if ctx.nude:
                base_pos = f"{base_pos}, nude, completely nude"
            else:
                theme_outfit = get_character_outfit_prompt(ctx.char, ctx.slot)
                if theme_outfit:
                    base_pos = f"{base_pos}, {theme_outfit}"
            base_pos = _inject_signature_accessories(base_pos, ctx)
            ctx.positive_prompt = _assemble_positive_prompt(base_pos, pose_tag, ctx)
            return

        if ctx.char.sdxl_positive:
            base_pos = ctx.char.sdxl_positive.strip()
            base_pos = re.sub(r",?\s*\(?hourglass\s*(shape)?(:[0-9\.]+)?\)?", "", base_pos, flags=re.IGNORECASE)
            if not ctx.is_steamy_h_scene:
                base_pos = re.sub(r",?\s*(photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|wet skin|sweatdrop|\bsweat\b|volumetric lighting)", "", base_pos, flags=re.IGNORECASE)
            if ctx.nude:
                base_pos = strip_sdxl_outfit_tags(base_pos)
                base_pos = f"{base_pos}, nude, completely nude"
            elif ctx.slot != "default":
                theme_outfit = get_character_outfit_prompt(ctx.char, ctx.slot)
                base_pos = strip_sdxl_outfit_tags(base_pos)
                if theme_outfit:
                    base_pos = f"{base_pos}, {theme_outfit}"
            base_pos = _inject_signature_accessories(base_pos, ctx)
            ctx.positive_prompt = _assemble_positive_prompt(base_pos, pose_tag, ctx)
            return

        char_gender_val = (ctx.char.gender or getattr(ctx.char, "default_mode", "") or "female").lower()
        gender_tag = "1boy, male" if char_gender_val in ("male", "otokonoko") else "1girl"
        char_desc = f"{ctx.char.appearance.face_and_hair}, {ctx.char.appearance.physique}".strip(", ")
        if ctx.nude:
            char_desc += ", nude, completely nude"
        else:
            outfit_tag = get_character_outfit_prompt(ctx.char, ctx.slot) or ctx.char.appearance.outfit
            if outfit_tag:
                char_desc += f", {outfit_tag}"

        quality_tags = DEFAULT_SDXL_QUALITY_TAGS
        if ctx.checkpoint_name:
            try:
                from plepa_engine.checkpoint_service import CheckpointService
                ckpt_prof = CheckpointService().get_profile_for_checkpoint(ctx.checkpoint_name, engine="sdxl")
                if ckpt_prof and ckpt_prof.quality_positive:
                    quality_tags = ckpt_prof.quality_positive
            except Exception:
                pass

        if ctx.custom_pos and ctx.custom_pos.strip():
            quality_tags = f"{ctx.custom_pos.strip()}, {quality_tags}"
        first_chunk = f"{quality_tags}, {pose_tag}" if pose_tag else quality_tags.strip()
        solo_tag = "" if ctx.is_two_person else "solo, "
        raw_fallback = f"{first_chunk} BREAK {gender_tag}, {solo_tag}{char_desc}"
        ctx.positive_prompt = _inject_signature_accessories(raw_fallback, ctx)
