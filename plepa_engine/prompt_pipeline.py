"""
plepa_engine.prompt_pipeline
SDXL 프롬프트 조합을 위한 Pipeline Mutator (미들웨어) 아키텍처.
절차적으로 비대화되었던 수십 가지 도메인 규칙과 패치를 독립된 Mutator 객체 체인으로 분리하여,
세계관 확장 시 코어 코드 수정 없이 유연하게 확장 가능하도록 구성합니다.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import (
    DEFAULT_SDXL_NEGATIVE,
    DEFAULT_SDXL_QUALITY_TAGS,
    _is_no_background,
    clamp_sdxl_weights,
    get_character_outfit_prompt,
    resolve_pose_outfit_slot,
    strip_sdxl_outfit_tags,
)


@dataclass
class PromptContext:
    """프롬프트 조립 파이프라인의 상태 및 생성 산출물을 보관하는 컨텍스트."""
    char: CharacterConfig
    pose: PoseEntry
    bg_prompt: str = ""
    custom_pos: Optional[str] = None
    custom_neg: Optional[str] = None
    checkpoint_name: Optional[str] = None
    style_mode: str = field(default_factory=lambda: (os.environ.get("PLEPA_STYLE_MODE", "legacy").strip().lower() or "legacy"))

    slot: str = field(init=False)
    nude: bool = field(init=False)
    is_no_bg: bool = field(init=False)
    pose_tag: str = field(default="")
    positive_prompt: str = field(default="")
    negative_prompt: str = field(default="")

    # 감지된 메타데이터 플래그
    is_wuxia: bool = field(default=False)
    is_two_person: bool = field(default=False)
    is_interactive: bool = field(default=False)
    is_offscreen_partner: bool = field(default=False)
    is_aftermath: bool = field(default=False)
    is_solo_scene: bool = field(default=False)
    is_dark_skin: bool = field(default=False)
    is_otokonoko: bool = field(default=False)
    is_steamy_h_scene: bool = field(default=False)
    mob_tier: Optional[int] = field(default=None)
    partner_pos: Optional[str] = field(default=None)
    extra_quality_kws: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.slot = resolve_pose_outfit_slot(self.pose)
        self.nude = (self.slot == "nude")
        self.is_no_bg = _is_no_background(self.bg_prompt)
        if self.partner_pos is None:
            self.partner_pos = getattr(self.pose, "partner_pos", None)
        char_skin_desc = f"{self.char.appearance.face_and_hair} {self.char.appearance.physique} {self.char.sdxl_positive or ''} {getattr(self.char, 'sdxl_nude_positive', '') or ''}".lower()
        self.is_dark_skin = any(kw in char_skin_desc for kw in ("dark tan", "dark skin", "tanned skin", "sun-kissed skin", "tan skin", "bronze skin"))

        code_str = str(getattr(self.pose, "code", "") or "").strip()
        code_digits = re.sub(r"\D", "", code_str)
        code_num = int(code_digits) if code_digits else 0
        sec_low = (getattr(self.pose, "section", "") or "").strip().lower()
        self.is_steamy_h_scene = (
            (code_num >= 60)
            or (sec_low in ("romance", "h_scenes", "special_h", "special_female_h", "scenes_otokonoko", "special_otokonoko", "special_otokonoko_h", "adult", "bdsm"))
            or (code_str.zfill(3) in ("038", "039"))
        )

        _ckpt_lower = (self.checkpoint_name or "").lower()
        _is_illustrious = any(k in _ckpt_lower for k in ("flatbread", "wai", "illustrious", "animagine", "animefull"))
        if _is_illustrious:
            self.extra_quality_kws = []
        elif self.is_steamy_h_scene:
            self.extra_quality_kws = ["delicate anime coloring", "clean pale skin"]
        else:
            self.extra_quality_kws = ["soft lighting", "delicate anime coloring", "soft shaded skin", "clean pale skin"]


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

def _resolve_mob_tier(pose: PoseEntry, pose_tag: str) -> Optional[int]:
    """포즈 메타데이터(mob_tier) 또는 명시적 solo focus 마커로부터 0~3 노출 등급을 판별합니다."""
    explicit_tier = getattr(pose, "mob_tier", None)
    if explicit_tier in _MOB_TIER_SPECS:
        return int(explicit_tier)
    p_low = (pose_tag or "").lower()
    has_interactive = any(kw in p_low for kw in _INTERACTIVE_POSE_KEYWORDS)
    has_boy_tag = any(re.search(rf"\b{kw}\b", p_low) for kw in ("1boy", "2boys", "3boys"))
    if getattr(pose, "is_h_scene", False) and "solo focus" in p_low and not has_interactive and not has_boy_tag:
        return 0
    return None


class PromptMutator:
    """프롬프트 파이프라인의 단일 변환 단계(미들웨어) 기본 클래스."""
    def mutate(self, ctx: PromptContext) -> None:
        raise NotImplementedError


class PoseTagPreparationMutator(PromptMutator):
    """1단계: 포즈 태그 추출, 표정 치환(A00), 세계관(무협 등) 어휘 치환 및 배경 태그 주입."""

    def mutate(self, ctx: PromptContext) -> None:
        pose_tag = ctx.pose.get_prompt(ctx.char.gender).strip()

        # A00 표정 지능형 치환
        if str(ctx.pose.code).upper() == "A00":
            pos_lower = (ctx.char.sdxl_positive or "").lower()
            if any(kw in pos_lower for kw in ("kuudere", "quiet demeanor", "stoic", "aloof")):
                pose_tag = re.sub(r"\bgentle smile\b", "calm neutral expression, composed gaze", pose_tag, flags=re.IGNORECASE)
            elif any(kw in pos_lower for kw in ("shy nervous", "nervous demeanor", "timid")):
                pose_tag = re.sub(r"\bgentle smile\b", "shy nervous expression, timid gaze, slight blush", pose_tag, flags=re.IGNORECASE)

        # 세계관(무협 / 동양풍) 감지
        _faction_lower = str(getattr(ctx.char, "faction", "") or "").lower()
        ctx.is_wuxia = bool(
            any(w in _faction_lower for w in ("murim", "wuxia", "cult", "sect", "nanman", "orthodox", "unorthodox"))
            or "wuxia" in (getattr(ctx.pose, "section", "") or "").lower()
            or "murim" in str(getattr(ctx.char, "file_path", "")).lower()
            or any(k in (ctx.char.sdxl_positive or "").lower() for k in ("hanfu", "wuxia", "daoist", "sect", "cult", "jianghu", "murim"))
        )

        # 무협 프로젝트 어휘 치환
        if ctx.is_wuxia:
            pose_tag = re.sub(r"\bbed\b", "silk bedding, oriental wooden bed", pose_tag, flags=re.IGNORECASE)
            pose_tag = re.sub(r"\bbedroom\b", "ornate pavilion room, wooden inn chamber", pose_tag, flags=re.IGNORECASE)
            pose_tag = re.sub(r"\b(shower room|shower stall|modern shower|standing in shower)\b", "traditional wooden bathtub, rising steam, hot spring bath", pose_tag, flags=re.IGNORECASE)
            pose_tag = re.sub(r"\bshower sex\b", "intimacy in wooden bathtub, rising steam", pose_tag, flags=re.IGNORECASE)
            pose_tag = re.sub(r"\b(camera POV|camera lens|taking photo|flash|photograph)\b", "intimate close-up view, secret observation angle", pose_tag, flags=re.IGNORECASE)
            pose_tag = re.sub(r"\b(hidden toy|vibrating toy|hidden vibrating toy|sex toy|vibrator)\b", "aphrodisiac sensation, intense pleasure wave, shivering thighs", pose_tag, flags=re.IGNORECASE)
            if "stuck in wall" in pose_tag.lower():
                pose_tag = re.sub(r"stuck in wall", "stuck in wooden partition, rear and hips exposed on this side, upper body trapped on other side, caught helpless, wooden wall", pose_tag, flags=re.IGNORECASE)
            if ctx.slot == "default":
                pose_tag = re.sub(r"\b(skirt|blouse|shirt|t-shirt|panties|bra|modern dress|jeans|shorts)\b", "", pose_tag, flags=re.IGNORECASE)
        elif ctx.slot == "default" and ctx.char.sdxl_positive:
            char_pos_low = ctx.char.sdxl_positive.lower()
            if "skirt" not in char_pos_low and "dress" not in char_pos_low and "qipao" not in char_pos_low:
                pose_tag = re.sub(r"\b(wind blowing skirt|holding skirt down|skirt lifted|skirt hiked up|skirt)\b", "clothing shifted", pose_tag, flags=re.IGNORECASE)
            if "shirt" not in char_pos_low and "blouse" not in char_pos_low:
                pose_tag = re.sub(r"\b(taking off shirt|torn shirt|unbuttoned shirt|shirt)\b", "disheveled top", pose_tag, flags=re.IGNORECASE)
            if "tie" not in char_pos_low and "necktie" not in char_pos_low:
                pose_tag = re.sub(r",?\s*\bloose tie\b", "", pose_tag, flags=re.IGNORECASE)

        # 배경 주입
        if ctx.bg_prompt:
            p_low = pose_tag.lower()
            intrinsic_bg_keywords = (
                "bed", "shower", "bath", "sofa", "classroom", "cafe", "library",
                "festival", "cathedral", "desk", "wall"
            )
            has_intrinsic_bg = any(re.search(r"\b" + re.escape(kw) + r"\b", p_low) for kw in intrinsic_bg_keywords)
            
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
            elif ctx.is_no_bg:
                if "clean background" not in p_low:
                    pose_tag = f"{pose_tag}, single view, single shot, clean background, white background, solid background"

        if ctx.is_steamy_h_scene and not _is_outdoor_daylight_pose(pose_tag):
            pose_tag = re.sub(
                r",?\s*\b(?:soft bedroom lighting|soft ambient bedroom light|bright clean atmosphere|soft lighting)\b",
                "",
                pose_tag,
                flags=re.IGNORECASE,
            )
            pose_tag = re.sub(r"\s*,\s*", ", ", pose_tag).strip(" ,")

        ctx.pose_tag = pose_tag
        ctx.mob_tier = _resolve_mob_tier(ctx.pose, pose_tag)

        # 2인 이상 상호작용 여부 감지 (Tier 0은 오프스크린 단독 POV이므로 solo 태그를 보존)
        if ctx.mob_tier is not None:
            tier_spec = _MOB_TIER_SPECS[ctx.mob_tier]
            ctx.is_two_person = bool(tier_spec["is_two_person"])
            ctx.is_offscreen_partner = bool(tier_spec["is_offscreen_partner"])
            ctx.is_solo_scene = bool(tier_spec["is_solo_scene"])
        else:
            ctx.is_two_person = any(
                kw in pose_tag.lower()
                for kw in ("1boy", "partner", "faceless male", "bald male", "kiss", "hug", "carry", "grab", "spooning", "blowjob", "missionary", "doggystyle", "cowgirl", "fellatio", "cunnilingus", "paizuri")
            )


def harmonize_character_expression(char_part: str, pose_tag: str) -> str:
    """포즈에 구체적인 표정/감정 태그가 있을 경우, 캐릭터 기본 정의의 상반된 무표정/기본 표정 태그를 억제하여 표정 충돌을 방지한다."""
    has_explicit_pose_expression = any(
        kw in pose_tag.lower()
        for kw in (
            "smile", "smiling", "laugh", "grin", "happy", "blush", "flushed",
            "crying", "tears", "ecstasy", "screaming", "angry", "moaning",
            "pleasure", "winking", "embarrassed", "pout", "flustered", "intoxicated",
            "shock", "surprised", "panic", "comic", "wide eyes", "constricted pupils", "blank stare",
        )
    )
    if has_explicit_pose_expression:
        char_part = re.sub(
            r",?\s*\b(cool calm expression|stoic expression|calm expression|expressionless|emotionless|indifferent gaze|neutral expression)\b",
            "",
            char_part,
            flags=re.IGNORECASE,
        )
    return char_part


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


_FACE_HAIR_ACCESSORY_KEYWORDS = (
    "glasses", "eyeglasses", "sunglasses", "monocle",
    "ribbon", "hair ribbon", "hairpin", "hair clip",
    "beret", "hat", "cap", "headband", "earring", "earrings", "hair ornament",
)


def _is_face_hair_accessory(tag: str) -> bool:
    """탈의(nude) 상태에서도 유지할 얼굴/헤어 소품인지 판별합니다."""
    low = (tag or "").strip().lower()
    return any(kw in low for kw in _FACE_HAIR_ACCESSORY_KEYWORDS)


_ACCESSORY_BASE_NOUNS = _FACE_HAIR_ACCESSORY_KEYWORDS + (
    "necktie", "tie", "bowtie", "belt", "leather belt", "choker", "necklace",
    "gloves", "stockings", "thighhighs", "pantyhose",
)


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

    # 기존 2차 청크에 분산·후미 배치된 동일 소품 토큰 제거 후 전단 집중 배치
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

        elif ctx.char.sdxl_positive:
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
        else:
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


class NegativeBaseMutator(PromptMutator):
    """3단계: 기본 부정 프롬프트 로드, 테마 의상 시 의상 차단 해제, [패치 SOLO] 및 [패치 2BOYS] 적용."""

    def mutate(self, ctx: PromptContext) -> None:
        neg = ctx.char.sdxl_negative.strip() if ctx.char.sdxl_negative else DEFAULT_SDXL_NEGATIVE

        if ctx.slot != "default":
            neg = re.sub(
                r",?\s*\b(bikini|micro bikini|string bikini|bikini top|bra only|exposed bra cup|exposed bra|see-through|pantyshot|exposed panties|visible panties|corset|lace-up|apron|maid apron|frills|frilled skirt|pleated skirt|garter straps|stockings|pantyhose|socks|thighhighs)\b",
                "",
                neg,
                flags=re.IGNORECASE,
            )

        # 성인 인터랙티브 씬 또는 64번 이상의 씬에서는 파트너 노출 억제 태그 자동 정제 (바지 위 봉사 참사 방지)
        code_str = str(getattr(ctx.pose, "code", "")).strip()
        code_num = int(code_str) if code_str.isdigit() else 0
        is_adult_scene = (
            ctx.pose.section in ("h_scenes", "special_h", "scenes_otokonoko", "special_otokonoko", "special_female_h", "special_otokonoko_h")
            or code_num >= 64
        )
        if is_adult_scene or ctx.nude:
            neg = re.sub(
                r",?\s*\b(visible penis|large penis|erection|testicles|pantyshot|exposed panties|visible panties|see-through)\b",
                "",
                neg,
                flags=re.IGNORECASE,
            )

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
            multi_male_inhibit = "((3boys, multiple boys, group sex, threesome, gangbang:1.35))" if ((ctx.char.gender or "").lower() == "otokonoko" or "2boys" in ctx.pose_tag.lower()) else "((2boys, 3boys, multiple boys, multiple males, group sex, threesome, gangbang:1.35))"
            if multi_male_inhibit not in neg:
                neg = f"{neg}, {multi_male_inhibit}"

            # 기본 네거티브 조립 후 custom_neg 및 pose.negative_add는 TwoPersonMobMutator 이후 SanitizerMutator에서 결합하여
            # 2인 씬 male/1boy/2boys 정규식 제거에 의해 사용자 네거티브가 훼손되지 않도록 보호합니다.
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


def _strip_tags_preserving_parens(text: str, inner_pattern: str) -> str:
    """중첩/가중치 괄호 균형을 훼손하지 않고 일치하는 태그 토큰만 안전하게 제거합니다."""
    cleaned = re.sub(inner_pattern, "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"(:\d+(?:\.\d+)?)\s*,\s*:\d+(?:\.\d+)?", r"\1", cleaned)
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = re.sub(r"\(\s*,\s*", "(", cleaned)
        cleaned = re.sub(r",\s*(?=[:\)])", "", cleaned)
        cleaned = re.sub(r"\(\s*(?::[0-9\.]+)?\s*\)", "", cleaned)
    cleaned = re.sub(r"(,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"\bBREAK\s*,\s*", "BREAK ", cleaned)
    cleaned = re.sub(r",\s*\bBREAK\b", " BREAK", cleaned)
    return cleaned.strip(" ,")


class DefectDefenseMutator(PromptMutator):
    """4단계: 상시 결함 방어 (말풍선, 가면, 동공소실, 다중손), 무배경 패치, 무협 시대착오 차단, 태닝피부 보호, 탈의/침대/전신 방어선."""

    def mutate(self, ctx: PromptContext) -> None:
        neg = ctx.negative_prompt
        pose_tag = ctx.pose_tag

        # [패치 0] 무배경(none)
        if ctx.is_no_bg:
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

        # [패치 0-1] 상시 공통 결함 방어 (여캐 얼굴 소실/앞머리 눈가림 차단; 2인 씬에서는 모브 남캐 앞머리 눈가림을 위해 여캐 한정으로 격리)
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
            f"{neg}, "
            f"(text:1.4), (speech bubble:1.4), (dialogue:1.4), (dialogue box:1.4), (subtitles:1.4), (comic panel:1.4), (sound effects:1.4), (watermark:1.3), (signature:1.3), "
            f"(mask:1.4), (white mask:1.4), (face mask:1.4), (noh mask:1.4), (porcelain mask:1.4), (paper mask:1.4), (theatrical mask:1.4), (blindfold:1.4){covered_eye_guard}, "
            f"{hair_eye_guard}, {face_obscure_guard}, "
            f"{eye_defect_guard}, "
            f"(extra hands:1.4), (extra arms:1.4), (multiple hands:1.4), (multiple arms:1.4), (fused hands:1.4), (too many fingers:1.4), (missing fingers:1.35), (poorly drawn hands:1.35), (mutated hands:1.35), "
            f"(extra legs:1.45), (multiple legs:1.45), (too many legs:1.45), (extra feet:1.45), (multiple feet:1.45), (extra thighs:1.45), (fused legs:1.4), (malformed legs:1.4), (mutated legs:1.4), (mutated feet:1.4), (extra limbs:1.45), "
            f"(overexposed, blown highlights, harsh lighting, blinding white highlight, burnt skin, oversaturated:1.25), ((sharp teeth, pointed teeth, shark teeth, jagged teeth, animal teeth, monster teeth, vampire fangs:1.45)), ((multiple beauty marks:1.45)), ((multiple moles:1.45)), ((freckles:1.35)), ((neck blemishes, neck moles, black spots on neck, dotted line:1.45)), ((skin spots:1.35))"
        )

        # [패치 0-1-1] 엘프귀 / 뾰족귀 왜곡 원천 차단 (명시적 엘프 캐릭터 제외)
        char_desc = f"{ctx.char.appearance.face_and_hair} {ctx.char.sdxl_positive or ''}".lower()
        if "elf" not in char_desc and "pointed ears" not in char_desc:
            neg = f"{neg}, (pointed ears, elf ears, pointy ears:1.45)" 

        # [패치 0-2] 무협 시대착오 차단
        if ctx.is_wuxia:
            neg = (
                f"{neg}, "
                f"(camera:1.4), (phone:1.4), (smartphone:1.4), (tripod:1.4), (photograph:1.4), (flash:1.4), "
                f"(modern:1.4), (contemporary:1.4), (modern bed:1.4), (western bedroom:1.4), (modern room:1.4), "
                f"(tiles:1.35), (modern bathroom:1.35), (shower stall:1.35), (glass shower:1.35), "
                f"(vibrator:1.4), (sex toy:1.4), (adult toy:1.4), (modern underwear:1.4), (bra:1.4), (panties:1.4), (lace lingerie:1.4), (neon lights:1.35)"
            )

        # [패치 0-3] 구릿빛/태닝 피부 보존
        char_skin_desc = f"{ctx.char.appearance.face_and_hair} {ctx.char.appearance.physique} {ctx.char.sdxl_positive or ''} {getattr(ctx.char, 'sdxl_nude_positive', '') or ''}".lower()
        ctx.is_dark_skin = any(kw in char_skin_desc for kw in ("dark tan", "dark skin", "tanned skin", "sun-kissed skin", "tan skin", "bronze skin"))
        if ctx.is_dark_skin:
            neg = re.sub(r",?\s*\b(colored skin|dark skin|tan skin)\b", "", neg, flags=re.IGNORECASE)
            neg = f"{neg}, (pale skin:1.35), (white skin:1.35), (fair skin:1.3)"
            if "dark tan skin" not in ctx.positive_prompt.lower():
                ctx.positive_prompt = f"{ctx.positive_prompt}, (radiant dark tan skin:1.2), (sun-kissed bronze skin:1.15)"

        # [패치 A] 탈의 상태 의상 잔류 차단
        if ctx.nude:
            neg = (
                f"{neg}, (clothes:1.35), (dress:1.35), (maid dress:1.35), (apron:1.35), (frilled apron:1.35), (white apron:1.35), "
                f"(shirt:1.3), (blouse:1.3), (skirt:1.3), (shorts:1.3), (jacket:1.3), (coat:1.3), (lab coat:1.3), (doctor coat:1.3), (nurse cap:1.3), "
                f"(corset:1.3), (bodysuit:1.3), (leotard:1.3), (qipao:1.3), (cheongsam:1.3), (necktie:1.3), (lanyard:1.3), (holster:1.3), (garter belt:1.3), "
                f"(headband:1.35), (headdress:1.35), (collar:1.3), (choker:1.3), (vest:1.3), (capelet:1.3), (petticoat:1.3), "
                f"(gloves:1.3), (socks:1.3), (stockings:1.3), (thighhighs:1.3), (pantyhose:1.3), (shoes:1.3), (high heels:1.3), (boots:1.3), "
                f"(bra:1.3), (panties:1.3), (underwear:1.3), (bikini:1.3)"
            )

        # [패치 A-2] 침대 및 탈의 와인잔 차단
        if ctx.nude or "on bed" in pose_tag.lower():
            neg = f"{neg}, (wine, wine glass, champagne, glass, bottle, cup, drink, beverage:1.3)"

        # [패치 A-3] 전신 스탠딩 구도 왜곡 차단
        if "full body" in pose_tag.lower() and "standing" in pose_tag.lower():
            neg = (
                f"{neg}, "
                f"(ceiling, chandelier, sofa, couch, armchair, door, doorframe, miniature room, giantess, from below, low angle, from above, high angle, overly long legs, tiny head:1.3)"
            )

        # [패치 B] 턱올리기 손 꼬임 차단
        if "chin lift" in pose_tag.lower():
            neg = f"{neg}, (extra hands:1.35), (two hands on chin:1.35), (multiple hands:1.35), (extra arms:1.35), (four hands:1.35), (three hands:1.35)"

        # [패치 B-2] 풋잡(077/125/195) 다리 증식 특화 차단
        if "footjob" in pose_tag.lower() or ctx.pose.code in ("077", "125", "195"):
            neg = f"{neg}, (extra legs:1.5), (four legs:1.5), (three legs:1.5), (multiple legs:1.5), (extra feet:1.5), (multiple feet:1.5), (fused legs:1.45), (mutated feet:1.45), (bad foot anatomy:1.4)"

        # [패치 D] 뒷태/후방 구도 및 착의 씬 자궁문신/복부문신 방어
        p_low = pose_tag.lower()
        is_back_view = any(kw in p_low for kw in (
            "back view", "from behind", "facing away", "rear view", "doggystyle", "lying on stomach",
            "on stomach", "butt focus", "ass focus", "from back", "behind"
        )) or ctx.pose.code in ("024", "079", "084", "088", "089", "090", "118", "121", "130")

        has_tattoo_in_pos = any(kw in ctx.positive_prompt.lower() for kw in ("womb tattoo", "stomach tattoo", "belly tattoo", "navel tattoo"))
        if has_tattoo_in_pos:
            if is_back_view:
                # 후방 구도에서는 복부 문신이 등/허리(tramp stamp)로 잘못 새겨지는 현상을 원천 차단
                ctx.positive_prompt = re.sub(r",?\s*\(?womb tattoo( on lower belly)?(:[0-9\.]+)?\)?", "", ctx.positive_prompt, flags=re.IGNORECASE)
                ctx.positive_prompt = re.sub(r",?\s*\(?(stomach|belly|navel) tattoo(:[0-9\.]+)?\)?", "", ctx.positive_prompt, flags=re.IGNORECASE)
                neg = f"{neg}, (tattoo on back:1.45), (tramp stamp:1.45), (lower back tattoo:1.45), (back tattoo:1.45), (spine tattoo:1.45)"
            elif ctx.slot in ("wedding", "office", "doctor", "hanfu", "coat", "suit") or (ctx.slot not in ("default", "nude", "underwear", "swimsuit", "") and "bare stomach" not in p_low and "exposed stomach" not in p_low):
                # 배가 가려지는 의상에서는 옷감 위에 문신이 투시/인쇄되는 현상 차단
                ctx.positive_prompt = re.sub(r",?\s*\(?womb tattoo( on lower belly)?(:[0-9\.]+)?\)?", "", ctx.positive_prompt, flags=re.IGNORECASE)
                ctx.positive_prompt = re.sub(r",?\s*\(?(stomach|belly|navel) tattoo(:[0-9\.]+)?\)?", "", ctx.positive_prompt, flags=re.IGNORECASE)
                neg = f"{neg}, (tattoo on clothes:1.45), (tattoo through clothes:1.45), (printed tattoo:1.45)"

        # [패치 C] 오토코노코 성기 분기 (일반 여성 캐릭터와 엄격히 격리)
        char_gender_str = (ctx.char.gender or getattr(ctx.char, "default_mode", "") or "female").lower()
        if char_gender_str in ("female", "girl", "woman"):
            ctx.is_otokonoko = False
        else:
            ctx.is_otokonoko = char_gender_str == "otokonoko" or bool(
                ctx.char.sdxl_positive and "otokonoko" in ctx.char.sdxl_positive.lower()
            )
        code_str_clean = str(getattr(ctx.pose, "code", "")).strip().zfill(3)
        is_non_exposure_romance = code_str_clean in ("060", "061", "062", "063")
        if ctx.is_otokonoko and ctx.nude and not is_non_exposure_romance:
            neg = f"{neg}, (pussy:1.35), (vagina:1.35), (female genitalia:1.35), (cameltoe:1.35), (cleavage:1.2), (large breasts:1.3), (breasts:1.2)"
            is_upper_torso_crop = any(kw in p_low for kw in ("cropped at upper chest", "cropped at chest", "cropped at waist", "cropped at lower belly"))
            if not is_upper_torso_crop and "penis" not in ctx.positive_prompt.lower():
                ctx.positive_prompt = f"{ctx.positive_prompt}, (penis:1.2), (small erect penis:1.15), (testicles:1.15), male genitalia"

        # [패치 E] 착의 H-씬 탈의/가슴 노출 원천 차단 네거티브벽 및 상의 보존
        is_clothed_h_scene = (not ctx.nude) and (
            any(kw in pose_tag.lower() for kw in ("clothed sex", "clothed fellatio", "fully clothed except bottom", "skirt lifted", "panties aside", "underwear aside", "clothes half removed"))
            or (ctx.pose.section in ("h_scenes", "special_h", "special_female_h", "scenes_otokonoko", "special_otokonoko", "special_otokonoko_h") and getattr(ctx.pose, "required_outfit", "") == "default")
            or ctx.pose.code in ("033", "067", "068", "069", "070", "071")
        )
        if is_clothed_h_scene:
            # 상반신 착의 구강 씬에서는 화면 아래에 가려진 캐릭터 하의/가터벨트/스타킹 태그가 파트너 하반신이나 타겟 부위로 전이(검은 속옷/라텍스화)되는 현상을 원천 제거
            is_clothed_oral = any(kw in pose_tag.lower() for kw in ("fellatio", "blowjob", "deepthroat", "oral", "licking", "handjob"))
            if is_clothed_oral:
                ctx.positive_prompt = _strip_tags_preserving_parens(
                    ctx.positive_prompt,
                    r"\b(?:[a-z\-]+\s+)*(?:garter belt|attached garter straps|garter straps|garters|thighhighs|stockings|pantyhose|thigh compression|panties|underwear)\b",
                )

            has_intentional_top_exposure = any(
                kw in pose_tag.lower()
                for kw in (
                    "exposed bare breasts",
                    "unbuttoned shirt",
                    "partially unbuttoned",
                    "bra or skirt visible",
                    "disheveled unbuttoned",
                    "open collar",
                    "bare collarbone",
                )
            )
            if not has_intentional_top_exposure:
                # 포지티브에서 단추 풀림 등 탈의 유도 태그 정제 및 상의 단정 태그 주입
                ctx.positive_prompt = _strip_tags_preserving_parens(
                    ctx.positive_prompt,
                    r"\b(?:unbuttoned top button|unbuttoned|shirt unbuttoned|open shirt|clothes open)\b",
                )
                if "fully clothed" not in ctx.positive_prompt.lower():
                    ctx.positive_prompt = f"{ctx.positive_prompt}, ((wearing clothes, top on, fully buttoned shirt, buttoned clothes, covered breasts, covered chest:1.35))"
                else:
                    ctx.positive_prompt = f"{ctx.positive_prompt}, ((fully buttoned shirt, buttoned clothes, covered breasts, covered chest:1.35))"

                # 글로벌 네거티브에 nude/naked/undressed를 넣으면 파트너 타겟 부위까지 검은 천/속옷으로 덮이므로 상의 탈의(topless/bare chest)만 정밀 억제
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

        ctx.negative_prompt = neg


def _build_common_interactive_negative_guard(ctx: PromptContext, is_multi_partner: bool = False) -> str:
    """2인 이상 인터랙티브 씬 공통 다인·사지·두부 왜곡 억제 네거티브 블록을 생성합니다."""
    if is_multi_partner:
        multi_male_guard = ""
    elif ctx.is_otokonoko:
        multi_male_guard = (
            "(3boys:1.6), (multiple boys:1.6), (three men:1.6), (extra male:1.6), "
            "(group:1.5), (threesome:1.5), (duplicate male:1.5), (two male partners:1.5), (multiple partners:1.5), "
        )
    else:
        multi_male_guard = (
            "(2boys:1.6), (multiple boys:1.6), (two men:1.6), (extra male:1.6), "
            "(group:1.5), (threesome:1.5), (duplicate male:1.5), (two male partners:1.5), (second man:1.5), (multiple partners:1.5), "
        )
    limb_guard = (
        "(extra hands:1.45), (multiple hands:1.45), (extra arms:1.45), (multiple arms:1.45), "
        "(three hands:1.45), (four hands:1.45), (duplicate hands:1.45), (duplicate arms:1.45), "
        "(extra limbs:1.4), (fused hands:1.4), (poorly drawn hands:1.4), "
    )
    return (
        f"(severed head:1.4), (decapitation:1.4), (headless:1.4), (floating head:1.4), (disembodied head:1.4), "
        f"(multiple heads:1.35), (two heads:1.35), (2girls:1.35), (multiple girls:1.35), (extra girl:1.35), "
        f"(two girls:1.35), (duplicate:1.35), (reaction face:1.35), (inset:1.35), "
        f"{multi_male_guard}{limb_guard}(extra head:1.35), own hand on face, own hand on chin, "
        f"resting chin on hand, holding own chin, touching own face, touching own chin, "
        f"hand on own face, hand on own chin, gloves, orange skin, "
        f"(pitch black shadow on body:1.25), (burnt skin:1.25)"
    )


def _apply_gaze_direction_negatives(pose_tag: str, neg: str) -> str:
    """파트너 응시 또는 시선 하향 포즈에서 카메라 직시 드리프트를 억제합니다."""
    pose_low = pose_tag.lower()
    if any(kw in pose_low for kw in ("looking at partner", "look at partner", "eye contact with partner", "facing partner", "towards partner")):
        neg = f"{neg}, looking at viewer, looking straight at camera"
    if any(kw in pose_low for kw in ("looking down", "head tilted down", "downcast eyes", "head down")):
        neg = f"{neg}, looking at viewer, looking straight at camera"
    return neg


def _inject_partner_pos_inline(pos: str, partner_pos: Optional[str], pose_tag: str = "") -> str:
    """2인 구도 시 범용 BREAK 대신 첫 청크 후미(BREAK 앞)에 방향성 파트너 엣지 크롭 태그를 인라인 주입한다."""
    pose_low = (pose_tag or "").lower()
    if partner_pos == "side_kiss" and any(kw in pose_low for kw in ("kiss", "french kiss")):
        tags = (
            "over-the-shoulder angle from behind dark-haired male partner, "
            "cropped dark-haired male jaw and lips at extreme frame edge, "
            "male upper face turned away in deep shadow, male eyes out of frame, partner arms around waist"
        )
    else:
        tags = _PARTNER_POS_SPECS.get(partner_pos or "", "partner head out of frame, cropped male shoulders at frame edge")
    if not tags:
        return pos
    if " BREAK " in pos:
        head, tail = pos.split(" BREAK ", 1)
        return f"{head}, {tags} BREAK {tail}"
    return f"{pos}, {tags}"


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
                is_kiss_scene = ctx.partner_pos == "side_kiss" and any(
                    kw in pose_tag.lower() for kw in ("kiss", "french kiss")
                )
                is_poses_section = (getattr(ctx.pose, "section", "") or "").lower() == "poses"
                is_mob_shadow = bool(getattr(ctx.pose, "mob_shadow", False))
                if mob_tier == 2 and ctx.partner_pos in ("carry", "between_thighs"):
                    tier_neg = _strip_tags_preserving_parens(tier_neg, r"\bfull male head\b")
                if mob_tier == 2 and (is_poses_section or is_kiss_scene or is_mob_shadow):
                    tier_neg = _strip_tags_preserving_parens(tier_neg, r"\b(?:heavy shadow|dark silhouette)\b")
                neg = f"{neg}, {common_guard}, {tier_neg}"
                if mob_tier == 2:
                    pos = _inject_partner_pos_inline(pos, ctx.partner_pos, pose_tag)
                    if ctx.partner_pos == "carry":
                        pos = re.sub(r",?\s*\bpartner head out of frame\b", "", pos, flags=re.IGNORECASE)
                    if (is_poses_section or is_kiss_scene or is_mob_shadow) and ctx.partner_pos not in ("bury_chest", "between_thighs"):
                        # 일상/스킨십 2인 포즈(027,028,031,036) 및 밀착 키스 씬(060,061)에서는 별도 BREAK 블록으로
                        # 상안부 그림자 모브 남캐를 격리하고, 주 캐릭터 눈은 여성 한정 clear visible female eyes로 보호해
                        # 남캐 눈 역노출과 앞머리 이염을 차단.
                        # 또한 포즈 내 'shirtless male'이 주 캐릭터 외투/상의를 벗기는 교차 오염을 막기 위해 3차 청크로 격리함.
                        has_shirtless_male = bool(re.search(r"\bshirtless male\b", pos, flags=re.IGNORECASE))
                        if has_shirtless_male and not ctx.nude:
                            pos = _strip_tags_preserving_parens(pos, r"\bshirtless male\b")
                        if "closed eyes" in pose_tag.lower():
                            pos = _strip_tags_preserving_parens(
                                pos, r"\b(?:finely detailed beautiful eyes|ultra detailed eyes)\b"
                            )
                        elif not ctx.is_otokonoko:
                            pos = f"{pos}, (clear visible female eyes:1.15)"
                        mob_tail = f"{_MOB_SHADOW_EYES_POS}, shirtless male" if (has_shirtless_male and not ctx.nude) else _MOB_SHADOW_EYES_POS
                        pos = f"{pos} BREAK (tall dark-haired male mob:1.15), {mob_tail}"
                        if not ctx.nude and any(k in pos.lower() for k in ("blazer", "jacket", "cardigan", "lab coat", "coat")):
                            neg = f"{neg}, (partner wearing blazer, partner wearing jacket, partner wearing cardigan, partner wearing lab coat, sleeveless protagonist:1.2)"
                        if ctx.is_otokonoko and "ponytail" in pos.lower():
                            neg = f"{neg}, (partner with ponytail, male mob with ponytail, two ponytails, matching hairstyles:1.25)"
                    neg = f"{neg}, {_MOB_EYELESS_BANGS_NEG}"
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

            ctx.positive_prompt = pos
            ctx.negative_prompt = neg
            return

        ctx.is_offscreen_partner = any(kw in pose_tag.lower() for kw in ("off-screen", "offscreen", "completely off-screen"))

        has_interactive_keywords = any(kw in pose_tag.lower() for kw in _INTERACTIVE_POSE_KEYWORDS)

        is_daily_or_pov = (not has_interactive_keywords) and (
            ctx.pose.section in ("genit_actions", "emotions", "actions", "poses", "daily_events", "spy_actions", "wuxia_actions")
            or ctx.pose.code.startswith("B")
            or ctx.pose.code.startswith("A")
            or ctx.pose.code.startswith("S")
            or "pov" in pose_tag.lower()
        )

        ctx.is_solo_scene = is_daily_or_pov or (
            not has_interactive_keywords and (
                "solo focus" in pose_tag.lower()
                or "solo, " in pose_tag.lower()
                or ", solo" in pose_tag.lower()
                or "standing in shower" in pose_tag.lower()
                or "shower stall" in pose_tag.lower()
                or "spreading own legs" in pose_tag.lower()
            )
        )

        ctx.is_interactive = (
            has_interactive_keywords or ctx.pose.section in ("h_scenes", "scenes_otokonoko", "adult")
        ) and not ctx.is_aftermath and not ctx.is_solo_scene

        if ctx.is_interactive:
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
                    is_head_hug_scene = any(
                        kw in pose_tag.lower()
                        for kw in (
                            "head on chest", "burying face", "face buried", "holding head",
                            "hugging head", "patting head", "kissing head", "hair from behind",
                            "back of male", "back of head", "pillow talk", "lying side by side", "lying together"
                        )
                    )
                    is_rear_scene = (
                        any(kw in pose_tag.lower() for kw in ("back hug", "doggystyle", "sumata", "rear", "prone", "grabbed from behind", "hugging from behind"))
                        or ("behind" in pose_tag.lower() and not any(f in pose_tag.lower() for f in ("head from behind", "hair from behind", "face buried", "cleavage", "buried between breasts", "nestled in cleavage")))
                    )
                    rear_direction = "(from behind:1.15), " if is_rear_scene else ""

                    code_str_clean = str(getattr(ctx.pose, "code", "")).strip().zfill(3)
                    code_num_clean = int(code_str_clean) if code_str_clean.isdigit() else 0
                    is_non_exposure_romance = code_str_clean in ("060", "061", "062", "063")

                    is_underdesk_scene = (
                        code_str_clean in ("126", "127")
                        or any(kw in pose_tag.lower() for kw in ("under desk", "under table", "책상밑"))
                    )

                    if is_head_hug_scene:
                        # 이미 포즈 자체에 남성의 밀착 위치/뒤통수가 완전히 정의되어 있으므로 추가 모브 BREAK 블록을 주입하지 않음 (남성 분신 2명 방지)
                        mob_positive = ""
                        mob_boy_guard_hug = "(3boys:1.8), (multiple boys:1.8), (three men:1.8), (extra male:1.8), (duplicate male:1.8), (group:1.8), (threesome:1.8)" if ctx.is_otokonoko else "(2boys:1.8), (3boys:1.8), (multiple boys:1.8), (multiple males:1.8), (two men:1.8), (extra male:1.8), (second male:1.8), (duplicate male:1.8), (group:1.8), (threesome:1.8)"
                        mob_negative = f"(detailed male face:1.4), (detailed eyes on male:1.35), (handsome male:1.4), (attractive male face:1.3), (expressive male face:1.3), (male portrait:1.3), (bishi:1.3), (male eyelashes:1.3), (standing male:1.5), (tall male:1.5), (standing beside:1.5), (standing partner:1.5), {mob_boy_guard_hug}, (extra head:1.6), (three heads:1.6), (multiple heads:1.6)"
                    elif is_non_exposure_romance:
                        # 비성교 로맨스 씬(060 딥키스, 061 알몸키스 등): 범용 BREAK 대신 방향성 인라인 파트너 엣지 크롭 주입
                        pos = _inject_partner_pos_inline(pos, ctx.partner_pos or "side_kiss", pose_tag)
                        mob_positive = ""
                        mob_boy_guard = "(3boys:1.6), (multiple boys:1.6), (three men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6)" if ctx.is_otokonoko else "(2boys:1.6), (multiple boys:1.6), (multiple males:1.6), (two men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6), (second male:1.6)"
                        mob_negative = f"{male_face_suppression}, male clothes, male shirt, {mob_boy_guard}, (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45), (fellatio:1.4), (blowjob:1.4), (oral:1.4), (penis:1.4), (standing male legs:1.45)"
                    else:
                        head_cue = "(male head out of frame:1.15), "
                        head_suppression = male_face_suppression

                        # 구강/파이즈리 및 상반신/바스트/페이스 줌인 씬 판정 (하반신/바지 주입 바이패스)
                        is_upper_body_scene = any(
                            kw in pose_tag.lower()
                            for kw in (
                                "fellatio", "blowjob", "deepthroat", "oral sex", "oral intimacy",
                                "licking shaft", "licking penis", "mouth around shaft", "taking shaft into mouth", "taking shaft",
                                "tongue extended", "paizuri", "titfuck", "cleavage penetration", "breasts squeezing",
                                "face focus", "bust portrait", "tight close-up", "upper body close-up", "bust shot",
                                "chest focus", "head tilted back", "close-up upper body", "intimate close-up", "tight bust portrait"
                            )
                        ) and not is_underdesk_scene

                        if is_upper_body_scene:
                            lower_body = ""
                            upper_body_guard = ", (standing male legs:1.45), (male lower body:1.45), (male legs:1.45), (pants:1.45), (trousers:1.40), (full body:1.45), (standing:1.40), (feet:1.40), (bare feet:1.35), (shoes:1.35), (boots:1.35), (cowboy shot:1.45), (wide shot:1.45), (kneeling wide view:1.40)"
                        else:
                            lower_body = "(bottomless male:1.15)" if ctx.nude else "(solid black pants:1.2)"
                            upper_body_guard = ""

                        # 언더데스크(책상밑) 씬: 남성 파트너 착의(셔츠/슬랙스) 및 자연스러운 자세
                        if is_underdesk_scene:
                            male_upper_attire = "((clothed male partner:1.20)), ((wearing collared shirt, white shirt:1.20)), "
                            male_clothing_neg = ", (shirtless male:1.35), (naked male:1.35), (bare chest:1.35), (bare shoulders:1.35)"
                        else:
                            male_upper_attire = "(shirtless male:1.1), (bare shoulders:1.1), "
                            male_clothing_neg = ", male clothes, male shirt, male t-shirt, male jacket, male suit"

                        mob_boy_guard = "(3boys:1.6), (multiple boys:1.6), (three men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6)" if ctx.is_otokonoko else "(2boys:1.6), (multiple boys:1.6), (multiple males:1.6), (two men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6), (second male:1.6)"

                        if ctx.nude:
                            mob_positive = f"BREAK (single cropped male partner:1.1), (partner head out of frame:1.15), (obscured male face:1.15), {head_cue}(unseen male eyes:1.15), (male head turned away:1.15), (short black hair, shaded upper face, shadow over male eyes, eyes obscured by shadow, no visible male eyes:1.2), {rear_direction}(naked male:1.15)"
                            if lower_body:
                                mob_positive += f", {lower_body}"
                            mob_negative = f"{head_suppression}, {_MOB_EYELESS_BANGS_NEG}, male clothes, male shirt, pants, trousers, jeans, shorts, underwear, {mob_boy_guard}, (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45){upper_body_guard}"
                        else:
                            # 착의 씬이더라도 성인 구강/결합 씬(064번 이상)인 경우 파트너는 하의 탈의 상태(bottomless)여야 함
                            is_adult_intercourse = (
                                ctx.pose.section in ("h_scenes", "scenes_otokonoko", "special_h", "special_otokonoko", "special_female_h", "special_otokonoko_h")
                                or code_num_clean >= 64
                            )
                            if is_adult_intercourse:
                                mob_positive = f"BREAK (single cropped male partner:1.1), (partner head out of frame:1.15), (obscured male face:1.15), {head_cue}(unseen male eyes:1.15), (male head turned away:1.15), (short black hair, shaded upper face, shadow over male eyes, eyes obscured by shadow, no visible male eyes:1.2), {rear_direction}{male_upper_attire}(bottomless male:1.15), (natural skin tone penis, bare skin shaft:1.1)"
                                mob_negative = f"{head_suppression}{male_clothing_neg}, {_MOB_EYELESS_BANGS_NEG}, (wearing pants over crotch:1.45), (pants:1.4), (zipper on mouth:1.4), (face on clothes:1.35), (condom, black condom, sheath, clothed penis, covered penis, underwear on penis, garter on male, stockings on male:1.45), {mob_boy_guard}, (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45){upper_body_guard}"
                            else:
                                mob_positive = f"BREAK (single cropped male partner:1.1), (partner head out of frame:1.15), (obscured male face:1.15), {head_cue}(unseen male eyes:1.15), (male head turned away:1.15), (short black hair, shaded upper face, shadow over male eyes, eyes obscured by shadow, no visible male eyes:1.2), {rear_direction}{male_upper_attire}"
                                if lower_body:
                                    mob_positive += f", {lower_body}"
                                mob_negative = f"{head_suppression}{male_clothing_neg}, {_MOB_EYELESS_BANGS_NEG}, (naked male:1.2), (bottomless:1.2), (male underwear:1.2), jeans, blue pants, {mob_boy_guard}, (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45){upper_body_guard}"

                if mob_positive:
                    pos = f"{pos} {mob_positive}"
                neg = f"{neg}, {mob_negative}"

            neg = _apply_gaze_direction_negatives(pose_tag, neg)

        if ctx.is_aftermath or ctx.is_solo_scene:
            if ctx.is_otokonoko:
                neg = f"{neg}, ((2boys, partner, faceless male, multiple characters, extra face:1.35))"
            else:
                neg = f"{neg}, ((1boy, 2boys, male, masculine, partner, faceless male, multiple characters, extra face:1.35))"

        ctx.positive_prompt = pos
        ctx.negative_prompt = neg


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


def normalize_tag(raw: str) -> str:
    """
    비교 및 매칭을 위해 태그를 정규화합니다.
    괄호 및 가중치 표기를 제거하고 소문자 및 공백을 정규화합니다.
    """
    tag = raw.strip().lower().translate(_BRACKET_TABLE)
    tag = _WEIGHT_SUFFIX_PATTERN.sub("", tag)
    return " ".join(tag.split())


def split_tags(text: str) -> List[str]:
    """쉼표 및 BREAK 구분자로 텍스트를 분리하여 정규화된 태그 리스트를 반환합니다."""
    cleaned = re.sub(r"\bBREAK\b", ",", text)
    return [normalize_tag(tag) for tag in cleaned.split(",") if normalize_tag(tag)]


def find_tag_conflicts(positive: str, negative: str) -> List[str]:
    """긍정과 부정 프롬프트에 동시에 존재하는 정규화 태그 목록을 반환합니다."""
    pos_tags = set(split_tags(positive))
    neg_tags = set(split_tags(negative))
    return sorted(pos_tags & neg_tags)


def remove_conflicting_tags_from_negative(positive: str, negative: str) -> Tuple[str, List[str]]:
    """
    긍정과 부정 사이에 충돌하는 태그를 감지하고, 네거티브 프롬프트에서 해당 태그를 안전하게 제거합니다.
    다중 태그 괄호 그룹(((tag1, tag2:1.5))) 내부 조각도 괄호 쌍을 완벽하게 보존하면서 충돌 태그를 정확히 정제합니다.
    구도/인원수 제어용 보호 태그(_PROTECTED_CONTROL_TAGS)는 가드 무력화를 막기 위해 보존합니다.
    """
    conflicts = [t for t in find_tag_conflicts(positive, negative) if t not in _PROTECTED_CONTROL_TAGS]
    if not conflicts:
        return negative, []

    conflict_set = set(conflicts)
    neg_chunks = [c.strip() for c in negative.split(",") if c.strip()]
    kept_chunks: List[str] = []
    removed_tags: List[str] = []
    pending_open_parens = ""

    for chunk in neg_chunks:
        norm = normalize_tag(chunk)
        open_parens = chunk.count("(")
        close_parens = chunk.count(")")

        if norm in conflict_set:
            removed_tags.append(norm)
            if open_parens > close_parens:
                pending_open_parens += "(" * (open_parens - close_parens)
            elif close_parens > open_parens:
                needed_close = ")" * (close_parens - open_parens)
                if pending_open_parens:
                    cancel_count = min(len(pending_open_parens), len(needed_close))
                    pending_open_parens = pending_open_parens[:-cancel_count] if cancel_count else ""
                    needed_close = needed_close[cancel_count:]
                if needed_close and kept_chunks:
                    open_balance = sum(c.count("(") - c.count(")") for c in kept_chunks)
                    if open_balance > 0:
                        kept_chunks[-1] = kept_chunks[-1] + needed_close[:open_balance]
            continue

        if pending_open_parens:
            chunk = pending_open_parens + chunk
            pending_open_parens = ""

        kept_chunks.append(chunk)

    new_neg = ", ".join(kept_chunks)
    return new_neg, sorted(set(removed_tags))


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


class CompositionAntiDriftMutator(PromptMutator):
    """5.5단계: 샷 사이즈별 반대 구도 이탈 방지 네거티브를 자동 주입합니다."""

    def mutate(self, ctx: PromptContext) -> None:
        pose_low = (ctx.pose_tag or "").lower()
        if not pose_low:
            return
        for shot_kws, anti_neg in _COMPOSITION_ANTI_DRIFT_RULES:
            if "full body" in shot_kws and "portrait" in pose_low:
                continue
            if any(kw in pose_low for kw in shot_kws):
                ctx.negative_prompt = f"{ctx.negative_prompt}, {anti_neg}" if ctx.negative_prompt else anti_neg
                break


class SanitizerMutator(PromptMutator):
    """6단계: 사용자/포즈 커스텀 네거티브 보호 주입, 가중치 안전 클램핑(clamp_sdxl_weights), 태그 충돌 정제 및 BREAK 정규화."""

    def mutate(self, ctx: PromptContext) -> None:
        # 0. 모브 정규식(TwoPersonMobMutator) 종료 후 포즈별/사용자 커스텀 네거티브 안전 결합
        if getattr(ctx.pose, "negative_add", None) and ctx.pose.negative_add.strip():
            ctx.negative_prompt = f"{ctx.negative_prompt}, {ctx.pose.negative_add.strip()}"
        if ctx.custom_neg and ctx.custom_neg.strip():
            ctx.negative_prompt = f"{ctx.negative_prompt}, {ctx.custom_neg.strip()}"

        if ctx.is_steamy_h_scene:
            ctx.negative_prompt = _strip_tags_preserving_parens(
                ctx.negative_prompt,
                _STEAMY_H_NEG_UNLOCK_PATTERN,
            )

        # 1. 긍정/부정 태그 충돌 감지 및 네거티브에서 자동 제거
        # 남성 모브 전용 BREAK 블록(레거시 및 Tier 2/3)의 태그가 여주인공 본체 네거티브를 지우지 않도록 모브 블록 제외 후 검사
        pos_without_mob = re.sub(
            r"\bBREAK\s*\((?:(?:single|multiple)\s+)?faceless(?:\s+shadowed)?\s+male.*$|\bBREAK\s*\(pov\s+crotch.*$|\bBREAK\s*\(tall\s+dark-haired\s+male\s+mob.*$",
            "",
            ctx.positive_prompt,
            flags=re.IGNORECASE,
        )
        cleaned_neg, conflicts = remove_conflicting_tags_from_negative(pos_without_mob, ctx.negative_prompt)
        if conflicts:
            logger.warning(f"[WARN] 프롬프트 태그 충돌 감지: {conflicts} -> 네거티브에서 자동 제거되었습니다.")
            ctx.negative_prompt = cleaned_neg

        # 2. 가중치 클램핑
        pos = clamp_sdxl_weights(ctx.positive_prompt, max_weight=1.15)
        neg = clamp_sdxl_weights(ctx.negative_prompt, max_weight=1.25)

        pos = re.sub(r"\(\s*,\s*", "(", pos)
        pos = re.sub(r"\s*,\s*", ", ", pos).strip().strip(",")
        pos = re.sub(r",?\s*BREAK\s*,?", " BREAK ", pos).strip()
        neg = re.sub(r"\(\s*,\s*", "(", neg)
        neg = re.sub(r",\s*,+", ", ", neg)
        neg = re.sub(r"\s*,\s*", ", ", neg).strip().strip(",")

        ctx.positive_prompt = pos
        ctx.negative_prompt = neg


class SDXLPromptPipeline:
    """SDXL 프롬프트 조합 미들웨어 파이프라인 관리자."""

    def __init__(self, mutators: Optional[List[PromptMutator]] = None) -> None:
        self.mutators = mutators if mutators is not None else [
            PoseTagPreparationMutator(),
            PositiveAssemblyMutator(),
            NegativeBaseMutator(),
            DefectDefenseMutator(),
            TwoPersonMobMutator(),
            CompositionAntiDriftMutator(),
            SanitizerMutator(),
        ]

    def execute(self, ctx: PromptContext) -> Tuple[str, str, bool]:
        for mutator in self.mutators:
            mutator.mutate(ctx)
        return ctx.positive_prompt, ctx.negative_prompt, ctx.nude


default_sdxl_pipeline = SDXLPromptPipeline()
