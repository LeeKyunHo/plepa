"""
plepa_engine.pipeline.constants
SDXL 프롬프트 파이프라인 공용 상수, 스타일 가드, 모브 Tier 사양 및 정규식 패턴 정의.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

_INTERACTIVE_POSE_KEYWORDS = (
    "partner", "faceless male", "bald male", "kiss", "hug", "carry", "grab", "spooning",
    "blowjob", "missionary", "doggystyle", "cowgirl", "straddling", "penetration",
    "fellatio", "cunnilingus", "paizuri", "titfuck", "groping", "grabbed from behind",
    "hugging from behind", "shower sex", "standing sex", "anal sex", "vaginal penetration",
    "anal penetration", "alley sex", "covert sex",
)

_STYLE_POSITIVE_GUARD_TAGS = (
    "delicate colored lineart",
    "ultra-fine linework",
    "2d cute anime face",
    "dot nose",
    "smooth pale skin",
    "soft peach blush",
    "iridescent hair highlights",
    "detailed fabric texture",
    "cinematic rim lighting",
)
_STYLE_NEGATIVE_GUARD = (
    "(realistic nose, photorealistic face, 3d, thick lips, nasolabial folds:1.25), "
    "(oily skin, greasy skin, heavy dark shadows, muddy colors:1.2), thick black outlines"
)

_STYLE_POSITIVE_BALANCED_TAGS = (
    "delicate colored lineart",
    "ultra-fine linework",
    "soft peach blush",
)
_STYLE_NEGATIVE_BALANCED_GUARD = (
    "(realistic nose, photorealistic face, 3d, thick lips, nasolabial folds:1.2), "
    "(oily skin, greasy skin:1.15), thick black outlines"
)

_H_SCENE_WET_SKIN_TAGS = (
    "(moist glistening skin, sweaty skin:1.15)",
    "(beads of sweat rolling down face and body, water droplets on skin:1.15)",
    "(specular skin highlights, dewy skin texture:1.1)",
    "damp hair strands clinging to sweaty cheeks and neck",
    "heavy facial blush, blush lines",
    "hot breath, subtle steam",
)

_H_SCENE_MOOD_LIGHTING_TAGS = (
    "(dimly lit bedroom, moody intimate lighting, low-key atmospheric lighting:1.15)",
    "(deep soft shadows, clean ambient occlusion:1.1)",
)

_OUTDOOR_DAYLIGHT_HINTS = (
    "outdoor", "daylight", "sunlight", "sunny", "beach", "pool", "bright daylight", "park", "rooftop"
)


def _is_outdoor_daylight_pose(pose_tag: str) -> bool:
    """실외/주광 포즈 키워드 포함 여부를 판별합니다."""
    low = (pose_tag or "").lower()
    return any(kw in low for kw in _OUTDOOR_DAYLIGHT_HINTS)


_MOB_SHADOW_EYES_POS = (
    "(dark-haired male mob:1.15), (short black hair, shaded upper face, "
    "heavy shadow over upper face, shadow over male eyes, eyes obscured by shadow, no visible male eyes:1.2)"
)
_MOB_EYELESS_BANGS_NEG = (
    "(visible male eyes, detailed male eyes, visible male pupils, detailed male face, "
    "handsome male face, attractive male face, expressive male face, male eyelashes, "
    "detailed male side profile, visible male eye crease, silver-haired male, blonde male:1.25)"
)

_STEAMY_H_NEG_UNLOCK_PATTERN = r"\b(?:oily skin|greasy skin|shiny skin|white dots|spots on skin)\b(?::[0-9\.]+)?"

_PARTNER_POS_SPECS: Dict[str, str] = {
    "above": "male hands pressing beside shoulders and gripping waist tightly, chest pressed close, partner shoulders at top edge, partner head out of frame",
    "below": "male hands gripping her waist and hips from below, intimate close embrace, partner head out of frame",
    "behind": "male torso tightly embracing from behind, male hands gripping her hips and waist firmly, lower body occluded, partner head out of frame",
    "side_kiss": "cropped male torso and shoulder at edge, partner head out of frame, partner arms around waist",
    "side_cuddle": "male partner sitting beside her at frame edge, cropped male shoulder at side edge, male upper face in shadow",
    "offscreen": "partner head out of frame, cropped male hands at frame edge",
    "carry": "carried in dark-haired male partner's arms, male torso and shoulders supporting her",
    "bury_chest": "back of dark-haired male head buried in her chest, male face completely obscured, partner arms around waist",
    "between_thighs": "kneeling male partner positioned low between spread thighs, male hands pushing inner thighs open in foreground, rear of male head centered at crotch level",
}

_MOB_TIER_SPECS: Dict[int, Dict[str, Any]] = {
    0: {
        "is_two_person": False,
        "is_offscreen_partner": True,
        "is_solo_scene": True,
        "is_interactive": False,
        "break_chunk": False,
        "positive_tags": "",
        "negative_tags": "1boy, male body, penis, disembodied limb",
    },
    1: {
        "is_two_person": True,
        "is_offscreen_partner": True,
        "is_solo_scene": False,
        "is_interactive": True,
        "break_chunk": False,
        "positive_tags": "(pov, disembodied male hands:1.05), cropped male arms, female focus",
        "negative_tags": "(detailed male face, male eyes, full male head:1.25), male torso, muscular chest, full male body, lower body focus, crotch focus",
    },
    2: {
        "is_two_person": True,
        "is_offscreen_partner": True,
        "is_solo_scene": False,
        "is_interactive": True,
        "break_chunk": False,
        "positive_tags": "",
        "negative_tags": "(detailed male face, male eyes, full male head:1.25), dark silhouette, heavy shadow, full body, wide shot, crotch focus",
    },
    3: {
        "is_two_person": True,
        "is_offscreen_partner": True,
        "is_solo_scene": False,
        "is_interactive": True,
        "break_chunk": True,
        "positive_tags": "BREAK (pov crotch:1.05), disembodied penis, (partially visible glans, compact shaft:1.05), cropped male lower torso",
        "negative_tags": "(giant penis, hyper penis, huge penis:1.25), full male body, (detailed male face, male eyes, full male head:1.25), muscular chest",
    },
}

_DAILY_AMBIENT_CLEANUP_RE = re.compile(
    r",?\s*(?:HDR|high contrast|cartoon|glossy skin|photorealistic(?::[0-9\.]+)?|"
    r"depth of field|blurry background|fairy lights|warm afternoon sunlight(?:\s+through\s+sheer\s+white\s+curtains)?|"
    r"soft shaded skin(?::[0-9\.]+)?|smooth skin(?::[0-9\.]+)?|wet skin|sweatdrop|\bsweat\b|volumetric lighting)",
    flags=re.IGNORECASE,
)
_DAILY_POSE_LIGHT_CLEANUP_RE = re.compile(
    r",?\s*(?:depth of field|blurry background|fairy lights|warm afternoon sunlight(?:\s+through\s+sheer\s+white\s+curtains)?)",
    flags=re.IGNORECASE,
)

_FACE_HAIR_ACCESSORY_KEYWORDS = (
    "glasses", "eyeglasses", "sunglasses", "monocle",
    "ribbon", "hair ribbon", "hairpin", "hair clip",
    "beret", "hat", "cap", "headband", "earring", "earrings", "hair ornament",
)
_ACCESSORY_BASE_NOUNS = _FACE_HAIR_ACCESSORY_KEYWORDS + (
    "necktie", "tie", "bowtie", "belt", "leather belt", "choker", "necklace",
    "gloves", "stockings", "thighhighs", "pantyhose",
)

_BRACKET_TABLE = str.maketrans("", "", "()[]{}")
_WEIGHT_SUFFIX_PATTERN = re.compile(r":[0-9]+(?:\.[0-9]+)?$")

# 파이프라인이 구도/시선/인원수 제어를 위해 의도적으로 제어하는 보호 태그 (자동 충돌 제거 제외)
_PROTECTED_CONTROL_TAGS = frozenset({
    "1boy",
    "2boys",
    "1girl",
    "2girls",
    "male",
    "masculine",
    "solo",
    "looking at viewer",
    "looking straight at camera",
})

_COMPOSITION_ANTI_DRIFT_RULES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (
        ("tight bust portrait", "close-up bust shot", "intimate close-up"),
        "(cowboy shot, full body, lower body, wide shot, knees, feet:1.25)",
    ),
    (
        ("cowboy shot",),
        "(tight bust portrait, close-up face, full body, wide shot, dutch angle, fisheye:1.2)",
    ),
    (
        ("full body",),
        "(cropped legs, tight bust portrait, close-up face, dutch angle, fisheye:1.2)",
    ),
)
