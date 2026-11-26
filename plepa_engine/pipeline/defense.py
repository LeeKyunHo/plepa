"""
plepa_engine.pipeline.defense
4단계(DefectDefenseMutator): 무배경·공통 결함·무협 시대착오·태닝 피부·탈의/복부문신/오토코노코/착의 H씬 방어선.
"""

from __future__ import annotations

import re

from plepa_engine.pipeline.context import PromptContext, PromptMutator
from plepa_engine.pipeline.tags import _strip_tags_preserving_parens

_COMMON_DEFECT_PREFIX = (
    "(text:1.4), (speech bubble:1.4), (dialogue:1.4), (dialogue box:1.4), (subtitles:1.4), (comic panel:1.4), (sound effects:1.4), (watermark:1.3), (signature:1.3), "
    "(mask:1.4), (white mask:1.4), (face mask:1.4), (noh mask:1.4), (porcelain mask:1.4), (paper mask:1.4), (theatrical mask:1.4), (blindfold:1.4)"
)
_COMMON_DEFECT_LIMBS = (
    "(extra hands:1.4), (extra arms:1.4), (multiple hands:1.4), (multiple arms:1.4), (fused hands:1.4), (too many fingers:1.4), (missing fingers:1.35), (poorly drawn hands:1.35), (mutated hands:1.35), "
    "(extra legs:1.45), (multiple legs:1.45), (too many legs:1.45), (extra feet:1.45), (multiple feet:1.45), (extra thighs:1.45), (fused legs:1.4), (malformed legs:1.4), (mutated legs:1.4), (mutated feet:1.4), (extra limbs:1.45), "
    "(overexposed, blown highlights, harsh lighting, blinding white highlight, burnt skin, oversaturated:1.25), ((sharp teeth, pointed teeth, shark teeth, jagged teeth, animal teeth, monster teeth, vampire fangs:1.45)), ((multiple beauty marks:1.45)), ((multiple moles:1.45)), ((freckles:1.35)), ((neck blemishes, neck moles, black spots on neck, dotted line:1.45)), ((skin spots:1.35))"
)

_NUDE_CLOTHING_NEGATIVE = (
    "(clothes:1.35), (dress:1.35), (maid dress:1.35), (apron:1.35), (frilled apron:1.35), (white apron:1.35), "
    "(shirt:1.3), (blouse:1.3), (skirt:1.3), (shorts:1.3), (jacket:1.3), (coat:1.3), (lab coat:1.3), (doctor coat:1.3), (nurse cap:1.3), "
    "(corset:1.3), (bodysuit:1.3), (leotard:1.3), (qipao:1.3), (cheongsam:1.3), (necktie:1.3), (lanyard:1.3), (holster:1.3), (garter belt:1.3), "
    "(headband:1.35), (headdress:1.35), (collar:1.3), (choker:1.3), (vest:1.3), (capelet:1.3), (petticoat:1.3), "
    "(gloves:1.3), (socks:1.3), (stockings:1.3), (thighhighs:1.3), (pantyhose:1.3), (shoes:1.3), (high heels:1.3), (boots:1.3), "
    "(bra:1.3), (panties:1.3), (underwear:1.3), (bikini:1.3)"
)

_TOP_EXPOSURE_HINTS = (
    "exposed bare breasts", "unbuttoned shirt", "partially unbuttoned",
    "bra or skirt visible", "disheveled unbuttoned", "open collar", "bare collarbone",
)


def _apply_no_bg_defense(neg: str, pose_tag: str) -> str:
    neg = (
        f"{neg}, "
        f"(character sheet, model sheet, reference sheet, concept art, turnaround, multiple views, multiple angles, split screen, inset, chibi, pop-up, reaction face, comic, collage, photo montage:1.4), "
        f"(halftone, screentone, dot pattern, stippling, grain, speckles, noise, dithering, textured skin, rough skin, pores, white dots, spots on skin:1.3), "
        f"(severed head, decapitation, headless, floating head, disembodied head, cut off head:1.4), "
        f"(overexposed, blown highlights, washed out:1.2), (heavy shadow, shadow crush, black crush, deep black shadow, burnt skin:1.25), (cyan tint, blue tint, neon glow:1.2), "
        f"(oversaturated, high contrast, harsh lighting, blinding white highlight, oily skin:1.2), "
        f"(detailed background, complex background, outdoors, indoors, scenery, room, window, wallpaper:1.25)"
    )
    furnitures = [f for f in ("furniture", "chair", "sofa", "bed", "table", "desk", "counter") if f not in pose_tag.lower()]
    if furnitures:
        neg = f"{neg}, ({', '.join(furnitures)}:1.2)"
    return neg


def _apply_common_defect_guards(ctx: PromptContext, neg: str) -> str:
    if ctx.is_two_person:
        hair_eye_guard = "(female eyes covered by hair:1.4), (female bangs over eyes:1.4), (hair over female eyes:1.4)"
        face_obscure_guard = "(faceless female:1.45), (shadow over female eyes:1.4), (shadow over female face:1.4), (hidden female eyes:1.4), (obscured female face:1.4)"
        covered_eye_guard = ""
    else:
        hair_eye_guard = "(eyes covered by hair:1.45), (bangs over eyes:1.45), (hair over eyes:1.45)"
        face_obscure_guard = "(faceless:1.45), (shadow over eyes:1.4), (shadow over face:1.4), (no eyes:1.45), (hidden eyes:1.4), (obscured face:1.4)"
        covered_eye_guard = ", (covered eyes:1.4)"

    has_comic_expr = any(
        kw in ctx.pose_tag.lower()
        for kw in ("shock", "surprised", "panic", "comic", "wide eyes", "constricted pupils", "blank stare")
    )
    if ctx.is_two_person:
        eye_defect_guard = (
            "(empty female eyes:1.35), (blank female eyes:1.35), (eyeless female:1.4), "
            "(looking up at ceiling:1.4), (staring into distance:1.4), (vacant female eyes:1.4), (wandering eyes:1.4)"
            if has_comic_expr
            else (
                "(empty female eyes:1.35), (blank female eyes:1.35), (pupil-less female:1.35), (eyeless female:1.4), "
                "(looking up at ceiling:1.4), (staring into distance:1.4), (vacant female eyes:1.4), (unfocused eyes:1.4), (wandering eyes:1.4)"
            )
        )
    else:
        eye_defect_guard = (
            "(empty eyes:1.35), (blank eyes:1.35), (white eyes:1.35), (eyeless:1.4), "
            "(looking up at ceiling:1.4), (staring into distance:1.4), (vacant eyes:1.4), (wandering eyes:1.4)"
            if has_comic_expr
            else (
                "(empty eyes:1.35), (blank eyes:1.35), (pupil-less:1.35), (white eyes:1.35), (eyeless:1.4), "
                "(looking up at ceiling:1.4), (staring into distance:1.4), (vacant eyes:1.4), (blank stare:1.4), (unfocused eyes:1.4), (wandering eyes:1.4)"
            )
        )

    neg = (
        f"{neg}, {_COMMON_DEFECT_PREFIX}{covered_eye_guard}, "
        f"{hair_eye_guard}, {face_obscure_guard}, {eye_defect_guard}, {_COMMON_DEFECT_LIMBS}"
    )
    char_desc = f"{ctx.char.appearance.face_and_hair} {ctx.char.sdxl_positive or ''}".lower()
    if "elf" not in char_desc and "pointed ears" not in char_desc:
        neg = f"{neg}, (pointed ears, elf ears, pointy ears:1.45)"
    return neg


def _apply_world_and_pose_defenses(ctx: PromptContext, neg: str, pose_tag: str) -> str:
    if ctx.is_wuxia:
        neg = (
            f"{neg}, "
            f"(camera:1.4), (phone:1.4), (smartphone:1.4), (tripod:1.4), (photograph:1.4), (flash:1.4), "
            f"(modern:1.4), (contemporary:1.4), (modern bed:1.4), (western bedroom:1.4), (modern room:1.4), "
            f"(tiles:1.35), (modern bathroom:1.35), (shower stall:1.35), (glass shower:1.35), "
            f"(vibrator:1.4), (sex toy:1.4), (adult toy:1.4), (modern underwear:1.4), (bra:1.4), (panties:1.4), (lace lingerie:1.4), (neon lights:1.35)"
        )

    char_skin_desc = f"{ctx.char.appearance.face_and_hair} {ctx.char.appearance.physique} {ctx.char.sdxl_positive or ''} {getattr(ctx.char, 'sdxl_nude_positive', '') or ''}".lower()
    ctx.is_dark_skin = any(kw in char_skin_desc for kw in ("dark tan", "dark skin", "tanned skin", "sun-kissed skin", "tan skin", "bronze skin"))
    if ctx.is_dark_skin:
        neg = re.sub(r",?\s*\b(colored skin|dark skin|tan skin)\b", "", neg, flags=re.IGNORECASE)
        neg = f"{neg}, (pale skin:1.35), (white skin:1.35), (fair skin:1.3)"
        if "dark tan skin" not in ctx.positive_prompt.lower():
            ctx.positive_prompt = f"{ctx.positive_prompt}, (radiant dark tan skin:1.2), (sun-kissed bronze skin:1.15)"

    if ctx.nude:
        neg = f"{neg}, {_NUDE_CLOTHING_NEGATIVE}"
    if ctx.nude or "on bed" in pose_tag.lower():
        neg = f"{neg}, (wine, wine glass, champagne, glass, bottle, cup, drink, beverage:1.3)"
    if "full body" in pose_tag.lower() and "standing" in pose_tag.lower():
        neg = (
            f"{neg}, "
            f"(ceiling, chandelier, sofa, couch, armchair, door, doorframe, miniature room, giantess, from below, low angle, from above, high angle, overly long legs, tiny head:1.3)"
        )
    if "chin lift" in pose_tag.lower():
        neg = f"{neg}, (extra hands:1.35), (two hands on chin:1.35), (multiple hands:1.35), (extra arms:1.35), (four hands:1.35), (three hands:1.35)"
    if "footjob" in pose_tag.lower() or ctx.pose.code in ("077", "125", "195"):
        neg = f"{neg}, (extra legs:1.5), (four legs:1.5), (three legs:1.5), (multiple legs:1.5), (extra feet:1.5), (multiple feet:1.5), (fused legs:1.45), (mutated feet:1.45), (bad foot anatomy:1.4)"
    return neg


def _apply_tattoo_and_otokonoko_defenses(ctx: PromptContext, neg: str, p_low: str) -> str:
    is_back_view = any(kw in p_low for kw in (
        "back view", "from behind", "facing away", "rear view", "doggystyle", "lying on stomach",
        "on stomach", "butt focus", "ass focus", "from back", "behind",
    )) or ctx.pose.code in ("024", "079", "084", "088", "089", "090", "118", "121", "130")

    has_tattoo_in_pos = any(kw in ctx.positive_prompt.lower() for kw in ("womb tattoo", "stomach tattoo", "belly tattoo", "navel tattoo"))
    if has_tattoo_in_pos:
        if is_back_view:
            ctx.positive_prompt = re.sub(r",?\s*\(?womb tattoo( on lower belly)?(:[0-9\.]+)?\)?", "", ctx.positive_prompt, flags=re.IGNORECASE)
            ctx.positive_prompt = re.sub(r",?\s*\(?(stomach|belly|navel) tattoo(:[0-9\.]+)?\)?", "", ctx.positive_prompt, flags=re.IGNORECASE)
            neg = f"{neg}, (tattoo on back:1.45), (tramp stamp:1.45), (lower back tattoo:1.45), (back tattoo:1.45), (spine tattoo:1.45)"
        elif ctx.slot in ("wedding", "office", "doctor", "hanfu", "coat", "suit") or (ctx.slot not in ("default", "nude", "underwear", "swimsuit", "") and "bare stomach" not in p_low and "exposed stomach" not in p_low):
            ctx.positive_prompt = re.sub(r",?\s*\(?womb tattoo( on lower belly)?(:[0-9\.]+)?\)?", "", ctx.positive_prompt, flags=re.IGNORECASE)
            ctx.positive_prompt = re.sub(r",?\s*\(?(stomach|belly|navel) tattoo(:[0-9\.]+)?\)?", "", ctx.positive_prompt, flags=re.IGNORECASE)
            neg = f"{neg}, (tattoo on clothes:1.45), (tattoo through clothes:1.45), (printed tattoo:1.45)"

    char_gender_str = (ctx.char.gender or getattr(ctx.char, "default_mode", "") or "female").lower()
    if char_gender_str in ("female", "girl", "woman"):
        ctx.is_otokonoko = False
    else:
        ctx.is_otokonoko = char_gender_str == "otokonoko" or bool(
            ctx.char.sdxl_positive and "otokonoko" in ctx.char.sdxl_positive.lower()
        )
    code_str_clean = str(getattr(ctx.pose, "code", "")).strip().zfill(3)
    if ctx.is_otokonoko and ctx.nude and code_str_clean not in ("060", "061", "062", "063"):
        neg = f"{neg}, (pussy:1.35), (vagina:1.35), (female genitalia:1.35), (cameltoe:1.35), (cleavage:1.2), (large breasts:1.3), (breasts:1.2)"
        is_upper_torso_crop = any(kw in p_low for kw in ("cropped at upper chest", "cropped at chest", "cropped at waist", "cropped at lower belly"))
        if not is_upper_torso_crop and "penis" not in ctx.positive_prompt.lower():
            ctx.positive_prompt = f"{ctx.positive_prompt}, (penis:1.2), (small erect penis:1.15), (testicles:1.15), male genitalia"
    return neg


def _apply_clothed_h_defenses(ctx: PromptContext, neg: str, pose_tag: str) -> str:
    p_low = pose_tag.lower()
    is_clothed_h_scene = (not ctx.nude) and (
        any(kw in p_low for kw in ("clothed sex", "clothed fellatio", "fully clothed except bottom", "skirt lifted", "panties aside", "underwear aside", "clothes half removed"))
        or (ctx.pose.section in ("h_scenes", "special_h", "special_female_h", "scenes_otokonoko", "special_otokonoko", "special_otokonoko_h") and getattr(ctx.pose, "required_outfit", "") == "default")
        or ctx.pose.code in ("033", "067", "068", "069", "070", "071")
    )
    if is_clothed_h_scene:
        if any(kw in p_low for kw in ("fellatio", "blowjob", "deepthroat", "oral", "licking", "handjob")):
            ctx.positive_prompt = _strip_tags_preserving_parens(
                ctx.positive_prompt,
                r"\b(?:[a-z\-]+\s+)*(?:garter belt|attached garter straps|garter straps|garters|thighhighs|stockings|pantyhose|thigh compression|panties|underwear)\b",
            )
        if not any(kw in p_low for kw in _TOP_EXPOSURE_HINTS):
            ctx.positive_prompt = _strip_tags_preserving_parens(
                ctx.positive_prompt,
                r"\b(?:unbuttoned top button|unbuttoned|shirt unbuttoned|open shirt|clothes open)\b",
            )
            if "fully clothed" not in ctx.positive_prompt.lower():
                ctx.positive_prompt = f"{ctx.positive_prompt}, ((wearing clothes, top on, fully buttoned shirt, buttoned clothes, covered breasts, covered chest:1.35))"
            else:
                ctx.positive_prompt = f"{ctx.positive_prompt}, ((fully buttoned shirt, buttoned clothes, covered breasts, covered chest:1.35))"
            neg = (
                f"{neg}, "
                f"((topless, bare breasts, exposed breasts, nipples, exposed nipples, "
                f"open shirt, unbuttoned, unbuttoned shirt, shirt pulled up, shirt lift, lifted shirt, clothes lift, open clothes, "
                f"breast out, breasts out, areola, cleavage, exposed cleavage, deep cleavage, underboob, "
                f"no shirt, flashing, exposed chest, bare chest:1.45))"
            )

    if not ctx.nude:
        pos_low = ctx.positive_prompt.lower()
        if "tucked into" in pos_low and "belt" in pos_low:
            neg = f"{neg}, (untucked shirt, shirt over belt, belt over shirt, long untucked hem:1.25)"
    return neg


class DefectDefenseMutator(PromptMutator):
    """4단계: 상시 결함 방어 (말풍선, 가면, 동공소실, 다중손), 무배경 패치, 무협 시대착오 차단, 태닝피부 보호, 탈의/침대/전신 방어선."""

    def mutate(self, ctx: PromptContext) -> None:
        neg = ctx.negative_prompt
        pose_tag = ctx.pose_tag
        if ctx.is_no_bg:
            neg = _apply_no_bg_defense(neg, pose_tag)
        neg = _apply_common_defect_guards(ctx, neg)
        neg = _apply_world_and_pose_defenses(ctx, neg, pose_tag)
        neg = _apply_tattoo_and_otokonoko_defenses(ctx, neg, pose_tag.lower())
        neg = _apply_clothed_h_defenses(ctx, neg, pose_tag)
        ctx.negative_prompt = neg
