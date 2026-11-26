"""
plepa_engine.pipeline.negative_base
3단계(NegativeBaseMutator): 기본 부정 프롬프트 로드, 테마/성인 씬 해제, [패치 SOLO] 및 [패치 2BOYS] 적용.
"""

from __future__ import annotations

import re

from plepa_engine.pipeline.assembly import (
    _select_active_signature_accessories,
    _strip_accessory_negative_conflicts,
)
from plepa_engine.pipeline.constants import (
    _STEAMY_H_NEG_UNLOCK_PATTERN,
    _STYLE_NEGATIVE_BALANCED_GUARD,
    _STYLE_NEGATIVE_GUARD,
    _is_outdoor_daylight_pose,
)
from plepa_engine.pipeline.context import PromptContext, PromptMutator
from plepa_engine.pipeline.tags import _strip_tags_preserving_parens
from plepa_engine.prompt_builder import DEFAULT_SDXL_NEGATIVE

_THEME_NEG_STRIP_RE = re.compile(
    r",?\s*\b(bikini|micro bikini|string bikini|bikini top|bra only|exposed bra cup|exposed bra|see-through|"
    r"pantyshot|exposed panties|visible panties|corset|lace-up|apron|maid apron|frills|frilled skirt|"
    r"pleated skirt|garter straps|stockings|pantyhose|socks|thighhighs)\b",
    flags=re.IGNORECASE,
)

_ADULT_NEG_STRIP_RE = re.compile(
    r",?\s*\b(visible penis|large penis|erection|testicles|pantyshot|exposed panties|visible panties|see-through)\b",
    flags=re.IGNORECASE,
)


class NegativeBaseMutator(PromptMutator):
    """3단계: 기본 부정 프롬프트 로드, 테마 의상 시 의상 차단 해제, [패치 SOLO] 및 [패치 2BOYS] 적용."""

    def mutate(self, ctx: PromptContext) -> None:
        neg = ctx.char.sdxl_negative.strip() if ctx.char.sdxl_negative else DEFAULT_SDXL_NEGATIVE

        if ctx.slot != "default":
            neg = _THEME_NEG_STRIP_RE.sub("", neg)

        # 성인 인터랙티브 씬 또는 64번 이상의 씬에서는 파트너 노출 억제 태그 자동 정제 (바지 위 봉사 참사 방지)
        code_str = str(getattr(ctx.pose, "code", "")).strip()
        code_num = int(code_str) if code_str.isdigit() else 0
        is_adult_scene = (
            ctx.pose.section in ("h_scenes", "special_h", "scenes_otokonoko", "special_otokonoko", "special_female_h", "special_otokonoko_h")
            or code_num >= 64
        )
        if is_adult_scene or ctx.nude:
            neg = _ADULT_NEG_STRIP_RE.sub("", neg)

        if ctx.is_two_person:
            neg = re.sub(r",?\s*\b1boy\b", "", neg, flags=re.IGNORECASE)
            neg = re.sub(r",?\s*\bmale\b(?!\s+(?:face|partner|body|head|eyes|clothes|hair))", "", neg, flags=re.IGNORECASE)
            neg = re.sub(r",?\s*\bmasculine\b", "", neg, flags=re.IGNORECASE)
            neg = re.sub(r",?\s*\(?multiple characters(:[0-9\.]+)?\)?", "", neg, flags=re.IGNORECASE)

            # [패치 SOLO]
            solo_inhibit = "(solo:1.4), (single person:1.4), (one person:1.3)"
            if solo_inhibit not in neg:
                neg = f"{neg}, {solo_inhibit}"

            # [패치 2BOYS]
            multi_male_inhibit = (
                "((3boys, multiple boys, group sex, threesome, gangbang:1.35))"
                if ((ctx.char.gender or "").lower() == "otokonoko" or "2boys" in ctx.pose_tag.lower())
                else "((2boys, 3boys, multiple boys, multiple males, group sex, threesome, gangbang:1.35))"
            )
            if multi_male_inhibit not in neg:
                neg = f"{neg}, {multi_male_inhibit}"

        if not ctx.nude:
            pos_low = ctx.positive_prompt.lower()
            for acc in ("choker", "necklace"):
                if acc in pos_low:
                    neg = re.sub(rf",?\s*\(?\b{acc}\b(?::[0-9\.]+)?\)?", "", neg, flags=re.IGNORECASE)
        neg = _strip_accessory_negative_conflicts(neg, _select_active_signature_accessories(ctx))

        if "(photorealistic, realistic, 3d" not in neg:
            char_mult_guard = "" if ctx.is_two_person else "(multiple characters, character sheet, concept art, reference sheet, mannequin:1.3), "
            neg = f"(photorealistic, realistic, 3d, render, cgi:1.25), {char_mult_guard}{neg}"
        mode = (getattr(ctx, "style_mode", "legacy") or "legacy").strip().lower()
        if mode == "glossy":
            if _STYLE_NEGATIVE_GUARD not in neg:
                neg = f"{neg}, {_STYLE_NEGATIVE_GUARD}"
        elif mode == "balanced":
            if _STYLE_NEGATIVE_BALANCED_GUARD not in neg:
                neg = f"{neg}, {_STYLE_NEGATIVE_BALANCED_GUARD}"

        if ctx.is_steamy_h_scene:
            neg = _strip_tags_preserving_parens(neg, _STEAMY_H_NEG_UNLOCK_PATTERN)
            if not _is_outdoor_daylight_pose(ctx.pose_tag):
                neg = f"{neg}, (bright daylight, harsh studio lighting, fluorescent light, flat bright lighting, overexposed background:1.25)"

        ctx.negative_prompt = neg
