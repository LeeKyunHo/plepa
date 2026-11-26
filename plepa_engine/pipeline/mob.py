"""
plepa_engine.pipeline.mob
5단계(TwoPersonMobMutator): 4-Tier 모브·성기 노출 제어 및 2인 인터랙티브 씬 방향성 파트너 주입·시선 차단.
"""

from __future__ import annotations

import re
from typing import Tuple

from plepa_engine.pipeline.constants import (
    _INTERACTIVE_POSE_KEYWORDS,
    _MOB_EYELESS_BANGS_NEG,
    _MOB_SHADOW_EYES_POS,
    _MOB_TIER_SPECS,
)
from plepa_engine.pipeline.context import PromptContext, PromptMutator, _resolve_mob_tier
from plepa_engine.pipeline.mob_helpers import (
    _apply_gaze_direction_negatives,
    _build_common_interactive_negative_guard,
    _inject_partner_pos_inline,
)
from plepa_engine.pipeline.tags import _strip_tags_preserving_parens

_UPPER_BODY_KW = (
    "fellatio", "blowjob", "deepthroat", "oral sex", "oral intimacy",
    "licking shaft", "licking penis", "mouth around shaft", "taking shaft into mouth", "taking shaft",
    "tongue extended", "paizuri", "titfuck", "cleavage penetration", "breasts squeezing",
    "face focus", "bust portrait", "tight close-up", "upper body close-up", "bust shot",
    "chest focus", "head tilted back", "close-up upper body", "intimate close-up", "tight bust portrait",
)

_SOLO_POSE_KW = (
    "solo focus", "solo, ", ", solo", "standing in shower", "shower stall", "spreading own legs",
)


def _apply_tier2_positive_and_negative(
    ctx: PromptContext,
    pose_tag: str,
    pos: str,
    neg: str,
    is_poses_section: bool,
    is_kiss_scene: bool,
    is_mob_shadow: bool,
) -> Tuple[str, str]:
    pos = _inject_partner_pos_inline(pos, ctx.partner_pos, pose_tag)
    if ctx.partner_pos == "carry":
        pos = re.sub(r",?\s*\bpartner head out of frame\b", "", pos, flags=re.IGNORECASE)
    if (is_poses_section or is_kiss_scene or is_mob_shadow) and ctx.partner_pos not in ("bury_chest", "between_thighs"):
        has_shirtless_male = bool(re.search(r"\bshirtless male\b", pos, flags=re.IGNORECASE))
        if has_shirtless_male and not ctx.nude:
            pos = _strip_tags_preserving_parens(pos, r"\bshirtless male\b")
        if "closed eyes" in pose_tag.lower():
            pos = _strip_tags_preserving_parens(pos, r"\b(?:finely detailed beautiful eyes|ultra detailed eyes)\b")
        elif not ctx.is_otokonoko:
            pos = f"{pos}, (clear visible female eyes:1.15)"
        mob_tail = f"{_MOB_SHADOW_EYES_POS}, shirtless male" if (has_shirtless_male and not ctx.nude) else _MOB_SHADOW_EYES_POS
        pos = f"{pos} BREAK (tall dark-haired male mob:1.15), {mob_tail}"
        if not ctx.nude and any(k in pos.lower() for k in ("blazer", "jacket", "cardigan", "lab coat", "coat")):
            neg = f"{neg}, (partner wearing blazer, partner wearing jacket, partner wearing cardigan, partner wearing lab coat, sleeveless protagonist:1.2)"
        if ctx.is_otokonoko and "ponytail" in pos.lower():
            neg = f"{neg}, (partner with ponytail, male mob with ponytail, two ponytails, matching hairstyles:1.25)"
    neg = f"{neg}, {_MOB_EYELESS_BANGS_NEG}"
    return pos, neg


def _apply_tiered_mob(ctx: PromptContext, mob_tier: int, pose_tag: str, pos: str, neg: str) -> Tuple[str, str]:
    spec = _MOB_TIER_SPECS[mob_tier]
    ctx.is_two_person = bool(spec["is_two_person"])
    ctx.is_offscreen_partner = bool(spec["is_offscreen_partner"])
    ctx.is_solo_scene = bool(spec["is_solo_scene"])
    ctx.is_interactive = bool(spec["is_interactive"]) and not ctx.is_aftermath

    if mob_tier == 0:
        tier0_neg = "2boys, disembodied limb" if ctx.is_otokonoko else spec["negative_tags"]
        neg = f"{neg}, {tier0_neg}"
    elif ctx.is_interactive:
        pos = re.sub(r",\s*solo\b", "", pos, flags=re.IGNORECASE)
        neg = re.sub(r",?\s*\b1boy\b", "", neg, flags=re.IGNORECASE)
        neg = re.sub(r",?\s*\bmale\b(?!\s+(?:face|partner|body|head|eyes|clothes|hair|torso))", "", neg, flags=re.IGNORECASE)
        common_guard = _build_common_interactive_negative_guard(ctx, is_multi_partner=False)
        tier_neg = spec["negative_tags"]
        is_kiss_scene = ctx.partner_pos == "side_kiss" and any(kw in pose_tag.lower() for kw in ("kiss", "french kiss"))
        is_poses_section = (getattr(ctx.pose, "section", "") or "").lower() == "poses"
        is_mob_shadow = bool(getattr(ctx.pose, "mob_shadow", False))
        if mob_tier == 2 and ctx.partner_pos in ("carry", "between_thighs"):
            tier_neg = _strip_tags_preserving_parens(tier_neg, r"\bfull male head\b")
        if mob_tier == 2 and (is_poses_section or is_kiss_scene or is_mob_shadow):
            tier_neg = _strip_tags_preserving_parens(tier_neg, r"\b(?:heavy shadow|dark silhouette)\b")
        neg = f"{neg}, {common_guard}, {tier_neg}"
        if mob_tier == 2:
            pos, neg = _apply_tier2_positive_and_negative(
                ctx, pose_tag, pos, neg, is_poses_section, is_kiss_scene, is_mob_shadow
            )
        elif spec["positive_tags"]:
            pos = f"{pos} {spec['positive_tags']}" if spec["break_chunk"] else f"{pos}, {spec['positive_tags']}"
            if mob_tier == 1 and ctx.partner_pos and ctx.partner_pos != "offscreen":
                pos = _inject_partner_pos_inline(pos, ctx.partner_pos, pose_tag)
            if mob_tier == 3 and (
                str(getattr(ctx.pose, "code", "")).strip().zfill(3) in ("126", "127")
                or any(kw in pose_tag.lower() for kw in ("under desk", "under table", "책상밑"))
            ):
                pos = f"{pos}, ((clothed male partner:1.20)), ((wearing collared shirt, white shirt:1.20))"
                neg = f"{neg}, (shirtless male:1.35), (naked male:1.35), (bare chest:1.35), (bare shoulders:1.35)"
        neg = _apply_gaze_direction_negatives(pose_tag, neg)

    if ctx.is_aftermath or ctx.is_solo_scene:
        if ctx.is_otokonoko:
            neg = f"{neg}, ((2boys, partner, faceless male, multiple characters, extra face:1.35))"
        else:
            neg = f"{neg}, ((1boy, 2boys, male, masculine, partner, faceless male, multiple characters, extra face:1.35))"
    return pos, neg


def _build_standard_single_mob_pair(
    ctx: PromptContext, pose_tag: str, pos: str, male_face_suppression: str
) -> Tuple[str, str, str]:
    p_low = pose_tag.lower()
    is_head_hug_scene = any(
        kw in p_low
        for kw in (
            "head on chest", "burying face", "face buried", "holding head",
            "hugging head", "patting head", "kissing head", "hair from behind",
            "back of male", "back of head", "pillow talk", "lying side by side", "lying together",
        )
    )
    is_rear_scene = (
        any(kw in p_low for kw in ("back hug", "doggystyle", "sumata", "rear", "prone", "grabbed from behind", "hugging from behind"))
        or ("behind" in p_low and not any(f in p_low for f in ("head from behind", "hair from behind", "face buried", "cleavage", "buried between breasts", "nestled in cleavage")))
    )
    rear_direction = "(from behind:1.15), " if is_rear_scene else ""
    code_str_clean = str(getattr(ctx.pose, "code", "")).strip().zfill(3)
    code_num_clean = int(code_str_clean) if code_str_clean.isdigit() else 0
    is_underdesk_scene = code_str_clean in ("126", "127") or any(kw in p_low for kw in ("under desk", "under table", "책상밑"))

    if is_head_hug_scene:
        mob_boy_guard_hug = (
            "(3boys:1.8), (multiple boys:1.8), (three men:1.8), (extra male:1.8), (duplicate male:1.8), (group:1.8), (threesome:1.8)"
            if ctx.is_otokonoko
            else "(2boys:1.8), (3boys:1.8), (multiple boys:1.8), (multiple males:1.8), (two men:1.8), (extra male:1.8), (second male:1.8), (duplicate male:1.8), (group:1.8), (threesome:1.8)"
        )
        return pos, "", (
            f"(detailed male face:1.4), (detailed eyes on male:1.35), (handsome male:1.4), (attractive male face:1.3), "
            f"(expressive male face:1.3), (male portrait:1.3), (bishi:1.3), (male eyelashes:1.3), (standing male:1.5), "
            f"(tall male:1.5), (standing beside:1.5), (standing partner:1.5), {mob_boy_guard_hug}, "
            f"(extra head:1.6), (three heads:1.6), (multiple heads:1.6)"
        )

    if code_str_clean in ("060", "061", "062", "063"):
        pos = _inject_partner_pos_inline(pos, ctx.partner_pos or "side_kiss", pose_tag)
        mob_boy_guard = (
            "(3boys:1.6), (multiple boys:1.6), (three men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6)"
            if ctx.is_otokonoko
            else "(2boys:1.6), (multiple boys:1.6), (multiple males:1.6), (two men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6), (second male:1.6)"
        )
        return pos, "", (
            f"{male_face_suppression}, male clothes, male shirt, {mob_boy_guard}, "
            "(extra hands:1.45), (multiple hands:1.45), (extra arms:1.45), (fellatio:1.4), (blowjob:1.4), (oral:1.4), (penis:1.4), (standing male legs:1.45)"
        )

    head_cue = "(male head out of frame:1.15), "
    is_upper_body_scene = any(kw in p_low for kw in _UPPER_BODY_KW) and not is_underdesk_scene
    if is_upper_body_scene:
        lower_body = ""
        upper_body_guard = ", (standing male legs:1.45), (male lower body:1.45), (male legs:1.45), (pants:1.45), (trousers:1.40), (full body:1.45), (standing:1.40), (feet:1.40), (bare feet:1.35), (shoes:1.35), (boots:1.35), (cowboy shot:1.45), (wide shot:1.45), (kneeling wide view:1.40)"
    else:
        lower_body = "(bottomless male:1.15)" if ctx.nude else "(solid black pants:1.2)"
        upper_body_guard = ""

    if is_underdesk_scene:
        male_upper_attire = "((clothed male partner:1.20)), ((wearing collared shirt, white shirt:1.20)), "
        male_clothing_neg = ", (shirtless male:1.35), (naked male:1.35), (bare chest:1.35), (bare shoulders:1.35)"
    else:
        male_upper_attire = "(shirtless male:1.1), (bare shoulders:1.1), "
        male_clothing_neg = ", male clothes, male shirt, male t-shirt, male jacket, male suit"

    mob_boy_guard = (
        "(3boys:1.6), (multiple boys:1.6), (three men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6)"
        if ctx.is_otokonoko
        else "(2boys:1.6), (multiple boys:1.6), (multiple males:1.6), (two men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6), (second male:1.6)"
    )

    if ctx.nude:
        mob_positive = f"BREAK (single cropped male partner:1.1), (partner head out of frame:1.15), (obscured male face:1.15), {head_cue}(unseen male eyes:1.15), (male head turned away:1.15), (short black hair, shaded upper face, shadow over male eyes, eyes obscured by shadow, no visible male eyes:1.2), {rear_direction}(naked male:1.15)"
        if lower_body:
            mob_positive += f", {lower_body}"
        mob_negative = f"{male_face_suppression}, {_MOB_EYELESS_BANGS_NEG}, male clothes, male shirt, pants, trousers, jeans, shorts, underwear, {mob_boy_guard}, (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45){upper_body_guard}"
        return pos, mob_positive, mob_negative

    is_adult_intercourse = (
        ctx.pose.section in ("h_scenes", "scenes_otokonoko", "special_h", "special_otokonoko", "special_female_h", "special_otokonoko_h")
        or code_num_clean >= 64
    )
    if is_adult_intercourse:
        mob_positive = f"BREAK (single cropped male partner:1.1), (partner head out of frame:1.15), (obscured male face:1.15), {head_cue}(unseen male eyes:1.15), (male head turned away:1.15), (short black hair, shaded upper face, shadow over male eyes, eyes obscured by shadow, no visible male eyes:1.2), {rear_direction}{male_upper_attire}(bottomless male:1.15), (natural skin tone penis, bare skin shaft:1.1)"
        mob_negative = f"{male_face_suppression}{male_clothing_neg}, {_MOB_EYELESS_BANGS_NEG}, (wearing pants over crotch:1.45), (pants:1.4), (zipper on mouth:1.4), (face on clothes:1.35), (condom, black condom, sheath, clothed penis, covered penis, underwear on penis, garter on male, stockings on male:1.45), {mob_boy_guard}, (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45){upper_body_guard}"
        return pos, mob_positive, mob_negative

    mob_positive = f"BREAK (single cropped male partner:1.1), (partner head out of frame:1.15), (obscured male face:1.15), {head_cue}(unseen male eyes:1.15), (male head turned away:1.15), (short black hair, shaded upper face, shadow over male eyes, eyes obscured by shadow, no visible male eyes:1.2), {rear_direction}{male_upper_attire}"
    if lower_body:
        mob_positive += f", {lower_body}"
    mob_negative = f"{male_face_suppression}{male_clothing_neg}, {_MOB_EYELESS_BANGS_NEG}, (naked male:1.2), (bottomless:1.2), (male underwear:1.2), jeans, blue pants, {mob_boy_guard}, (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45){upper_body_guard}"
    return pos, mob_positive, mob_negative


def _apply_legacy_interactive_mob(ctx: PromptContext, pose_tag: str, pos: str, neg: str) -> Tuple[str, str]:
    neg = re.sub(r",?\s*\b1boy\b", "", neg, flags=re.IGNORECASE)
    neg = re.sub(r",?\s*\bmale\b(?!\s+(?:face|partner|body|head|eyes|clothes|hair|torso))", "", neg, flags=re.IGNORECASE)
    is_multi_partner = any(
        kw in pose_tag.lower()
        for kw in ("3boys", "multiple boys", "gangbang", "threesome", "foursome", "group sex", "bukkake", "surrounded", "harem")
    )
    common_guard = _build_common_interactive_negative_guard(ctx, is_multi_partner=is_multi_partner)
    neg = f"{neg}, {common_guard}"

    if ctx.is_offscreen_partner:
        neg = f"{neg}, ((male body, male torso, male lower body, male legs, pants, trousers, black pants, jeans, lap, sitting between legs, legs of partner, 1boy:1.35))"
    else:
        pos = re.sub(r",\s*solo\b", "", pos, flags=re.IGNORECASE)
        male_face_suppression = "(detailed male face, male eyes, full male head:1.25)"
        is_non_sexual_support = any(kw in pose_tag.lower() for kw in ("non-sexual", "channeling qi", "transferring internal energy", "hands resting on back", "palms on upper back"))
        if is_non_sexual_support:
            mob_positive = "BREAK (faceless male partner:1.15), (obscured face:1.15), (head out of frame:1.15), (from behind:1.15), sitting behind her, hands gently resting on her upper back, traditional oriental martial robes, non-sexual, serene healing"
            mob_negative = f"{male_face_suppression}, (naked male:1.5), (shirtless:1.4), (bare chest:1.4), (penis:1.5), (sexual:1.5), (groping:1.5), (grabbing breasts:1.5), (kissing:1.5), (2boys:1.5), (multiple boys:1.5), (cross-section:1.5)"
        elif is_multi_partner:
            neg = re.sub(r",?\s*\b(2boys|multiple boys|multiple males|two men|extra male|group|threesome|group sex)\b(:[0-9\.]+)?", "", neg, flags=re.IGNORECASE)
            if ctx.nude:
                mob_positive = "BREAK (multiple faceless males:1.15), (group of faceless men surrounding:1.15), (obscured male faces:1.15), (unseen male eyes:1.15), (male head turned away:1.15), (from behind:1.1), (naked males:1.15), (bottomless males:1.15)"
                mob_negative = f"{male_face_suppression}, male clothes, male shirt, pants, trousers, jeans, shorts, underwear"
            else:
                mob_positive = "BREAK (multiple faceless males:1.15), (group of faceless men surrounding:1.15), (obscured male faces:1.15), (unseen male eyes:1.15), (male head turned away:1.15), (from behind:1.1), (solid black pants:1.2)"
                mob_negative = f"{male_face_suppression}, male clothes, male shirt, male t-shirt, male jacket, male suit, (naked male:1.2), (bottomless:1.2), (male underwear:1.2), jeans, blue pants"
        else:
            pos, mob_positive, mob_negative = _build_standard_single_mob_pair(ctx, pose_tag, pos, male_face_suppression)

        if mob_positive:
            pos = f"{pos} {mob_positive}"
        neg = f"{neg}, {mob_negative}"

    return pos, _apply_gaze_direction_negatives(pose_tag, neg)


class TwoPersonMobMutator(PromptMutator):
    """5단계: 4-Tier 모브·성기 노출 제어 및 2인 인터랙티브 씬 방향성 인라인 파트너 주입, 시선 차단."""

    def mutate(self, ctx: PromptContext) -> None:
        pose_tag = ctx.pose_tag
        neg = ctx.negative_prompt
        pos = ctx.positive_prompt

        mob_tier = ctx.mob_tier if ctx.mob_tier in _MOB_TIER_SPECS else _resolve_mob_tier(ctx.pose, pose_tag)
        ctx.mob_tier = mob_tier
        ctx.is_aftermath = any(kw in pose_tag.lower() for kw in ("aftermath", "aftersex"))

        if mob_tier in _MOB_TIER_SPECS:
            ctx.positive_prompt, ctx.negative_prompt = _apply_tiered_mob(ctx, mob_tier, pose_tag, pos, neg)
            return

        p_low = pose_tag.lower()
        ctx.is_offscreen_partner = any(kw in p_low for kw in ("off-screen", "offscreen", "completely off-screen"))
        has_interactive_keywords = any(kw in p_low for kw in _INTERACTIVE_POSE_KEYWORDS)
        is_daily_or_pov = (not has_interactive_keywords) and (
            ctx.pose.section in ("genit_actions", "emotions", "actions", "poses", "daily_events", "spy_actions", "wuxia_actions")
            or ctx.pose.code.startswith(("B", "A", "S"))
            or "pov" in p_low
        )
        ctx.is_solo_scene = is_daily_or_pov or (
            not has_interactive_keywords and any(kw in p_low for kw in _SOLO_POSE_KW)
        )
        ctx.is_interactive = (
            has_interactive_keywords or ctx.pose.section in ("h_scenes", "scenes_otokonoko", "adult")
        ) and not ctx.is_aftermath and not ctx.is_solo_scene

        if ctx.is_interactive:
            pos, neg = _apply_legacy_interactive_mob(ctx, pose_tag, pos, neg)

        if ctx.is_aftermath or ctx.is_solo_scene:
            if ctx.is_otokonoko:
                neg = f"{neg}, ((2boys, partner, faceless male, multiple characters, extra face:1.35))"
            else:
                neg = f"{neg}, ((1boy, 2boys, male, masculine, partner, faceless male, multiple characters, extra face:1.35))"

        ctx.positive_prompt = pos
        ctx.negative_prompt = neg
