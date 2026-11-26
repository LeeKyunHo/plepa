"""
plepa_engine.pipeline.pose_prep
1단계(PoseTagPreparationMutator): 포즈 태그 추출, A00 표정 치환, 세계관(무협 등) 어휘 치환 및 배경 주입.
"""

from __future__ import annotations

import re

from plepa_engine.pipeline.constants import _MOB_TIER_SPECS, _is_outdoor_daylight_pose
from plepa_engine.pipeline.context import PromptContext, PromptMutator, _resolve_mob_tier

_TWO_PERSON_KW = (
    "1boy", "partner", "faceless male", "bald male", "kiss", "hug", "carry",
    "grab", "spooning", "blowjob", "missionary", "doggystyle", "cowgirl",
    "fellatio", "cunnilingus", "paizuri",
)

_INTRINSIC_BG_KW = (
    "bed", "shower", "bath", "sofa", "classroom", "cafe", "library",
    "festival", "cathedral", "desk", "wall",
)


def _apply_a00_expression_substitution(ctx: PromptContext, pose_tag: str) -> str:
    if str(ctx.pose.code).upper() != "A00":
        return pose_tag
    pos_lower = (ctx.char.sdxl_positive or "").lower()
    if any(kw in pos_lower for kw in ("kuudere", "quiet demeanor", "stoic", "aloof")):
        return re.sub(r"\bgentle smile\b", "calm neutral expression, composed gaze", pose_tag, flags=re.IGNORECASE)
    if any(kw in pos_lower for kw in ("shy nervous", "nervous demeanor", "timid")):
        return re.sub(r"\bgentle smile\b", "shy nervous expression, timid gaze, slight blush", pose_tag, flags=re.IGNORECASE)
    return pose_tag


def _rewrite_wuxia_or_outfit_vocab(ctx: PromptContext, pose_tag: str) -> str:
    if ctx.is_wuxia:
        pose_tag = re.sub(r"\bbed\b", "silk bedding, oriental wooden bed", pose_tag, flags=re.IGNORECASE)
        pose_tag = re.sub(r"\bbedroom\b", "ornate pavilion room, wooden inn chamber", pose_tag, flags=re.IGNORECASE)
        pose_tag = re.sub(
            r"\b(shower room|shower stall|modern shower|standing in shower)\b",
            "traditional wooden bathtub, rising steam, hot spring bath",
            pose_tag, flags=re.IGNORECASE,
        )
        pose_tag = re.sub(r"\bshower sex\b", "intimacy in wooden bathtub, rising steam", pose_tag, flags=re.IGNORECASE)
        pose_tag = re.sub(
            r"\b(camera POV|camera lens|taking photo|flash|photograph)\b",
            "intimate close-up view, secret observation angle",
            pose_tag, flags=re.IGNORECASE,
        )
        pose_tag = re.sub(
            r"\b(hidden toy|vibrating toy|hidden vibrating toy|sex toy|vibrator)\b",
            "aphrodisiac sensation, intense pleasure wave, shivering thighs",
            pose_tag, flags=re.IGNORECASE,
        )
        if "stuck in wall" in pose_tag.lower():
            pose_tag = re.sub(
                r"stuck in wall",
                "stuck in wooden partition, rear and hips exposed on this side, upper body trapped on other side, caught helpless, wooden wall",
                pose_tag, flags=re.IGNORECASE,
            )
        if ctx.slot == "default":
            pose_tag = re.sub(r"\b(skirt|blouse|shirt|t-shirt|panties|bra|modern dress|jeans|shorts)\b", "", pose_tag, flags=re.IGNORECASE)
        return pose_tag

    if ctx.slot == "default" and ctx.char.sdxl_positive:
        char_pos_low = ctx.char.sdxl_positive.lower()
        if "skirt" not in char_pos_low and "dress" not in char_pos_low and "qipao" not in char_pos_low:
            pose_tag = re.sub(r"\b(wind blowing skirt|holding skirt down|skirt lifted|skirt hiked up|skirt)\b", "clothing shifted", pose_tag, flags=re.IGNORECASE)
        if "shirt" not in char_pos_low and "blouse" not in char_pos_low:
            pose_tag = re.sub(r"\b(taking off shirt|torn shirt|unbuttoned shirt|shirt)\b", "disheveled top", pose_tag, flags=re.IGNORECASE)
        if "tie" not in char_pos_low and "necktie" not in char_pos_low:
            pose_tag = re.sub(r",?\s*\bloose tie\b", "", pose_tag, flags=re.IGNORECASE)
    return pose_tag


def _apply_pose_background_and_lighting(ctx: PromptContext, pose_tag: str) -> str:
    if ctx.bg_prompt:
        p_low = pose_tag.lower()
        has_intrinsic_bg = any(re.search(r"\b" + re.escape(kw) + r"\b", p_low) for kw in _INTRINSIC_BG_KW)
        # emotions는 항상 적용, 그 외 섹션은 자체 배경 키워드가 없는 일반 스탠딩/일상 포즈(020~024, 030, 041~042, 047 등)에 적용
        apply_bg = (
            ctx.pose.section in ("emotions", "genit_emotions")
            or (not has_intrinsic_bg and ctx.pose.section not in ("h_scenes", "scenes_otokonoko", "adult"))
        )

        if apply_bg:
            if "clean background" in p_low:
                pose_tag = re.sub(r"clean\s+background", ctx.bg_prompt.strip(), pose_tag, flags=re.IGNORECASE)
            else:
                pose_tag = f"{pose_tag}, {ctx.bg_prompt.strip()}"
            if ctx.is_no_bg and "single view" not in p_low:
                pose_tag = f"{pose_tag}, single view, single shot"
        elif ctx.is_no_bg and "clean background" not in p_low:
            pose_tag = f"{pose_tag}, single view, single shot, clean background, white background, solid background"

    if ctx.is_steamy_h_scene and not _is_outdoor_daylight_pose(pose_tag):
        pose_tag = re.sub(
            r",?\s*\b(?:soft bedroom lighting|soft ambient bedroom light|bright clean atmosphere|soft lighting)\b",
            "", pose_tag, flags=re.IGNORECASE,
        )
        pose_tag = re.sub(r"\s*,\s*", ", ", pose_tag).strip(" ,")
    return pose_tag


class PoseTagPreparationMutator(PromptMutator):
    """1단계: 포즈 태그 추출, 표정 치환(A00), 세계관(무협 등) 어휘 치환 및 배경 태그 주입."""

    def mutate(self, ctx: PromptContext) -> None:
        pose_tag = ctx.pose.get_prompt(ctx.char.gender).strip()
        pose_tag = _apply_a00_expression_substitution(ctx, pose_tag)

        _faction_lower = str(getattr(ctx.char, "faction", "") or "").lower()
        ctx.is_wuxia = bool(
            any(w in _faction_lower for w in ("murim", "wuxia", "cult", "sect", "nanman", "orthodox", "unorthodox"))
            or "wuxia" in (getattr(ctx.pose, "section", "") or "").lower()
            or "murim" in str(getattr(ctx.char, "file_path", "")).lower()
            or any(k in (ctx.char.sdxl_positive or "").lower() for k in ("hanfu", "wuxia", "daoist", "sect", "cult", "jianghu", "murim"))
        )

        pose_tag = _rewrite_wuxia_or_outfit_vocab(ctx, pose_tag)
        pose_tag = _apply_pose_background_and_lighting(ctx, pose_tag)

        ctx.pose_tag = pose_tag
        ctx.mob_tier = _resolve_mob_tier(ctx.pose, pose_tag)

        # 2인 이상 상호작용 여부 감지 (Tier 0은 오프스크린 단독 POV이므로 solo 태그를 보존)
        if ctx.mob_tier is not None:
            tier_spec = _MOB_TIER_SPECS[ctx.mob_tier]
            ctx.is_two_person = bool(tier_spec["is_two_person"])
            ctx.is_offscreen_partner = bool(tier_spec["is_offscreen_partner"])
            ctx.is_solo_scene = bool(tier_spec["is_solo_scene"])
        else:
            ctx.is_two_person = any(kw in pose_tag.lower() for kw in _TWO_PERSON_KW)
