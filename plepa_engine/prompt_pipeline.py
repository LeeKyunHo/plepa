"""
plepa_engine.prompt_pipeline
SDXL 프롬프트 조합을 위한 Pipeline Mutator (미들웨어) 아키텍처.
절차적으로 비대화되었던 수십 가지 도메인 규칙과 패치를 독립된 Mutator 객체 체인으로 분리하여,
세계관 확장 시 코어 코드 수정 없이 유연하게 확장 가능하도록 구성합니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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
    extra_quality_kws: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.slot = resolve_pose_outfit_slot(self.pose)
        self.nude = (self.slot == "nude")
        self.is_no_bg = _is_no_background(self.bg_prompt)

        _ckpt_lower = (self.checkpoint_name or "").lower()
        _is_illustrious = any(k in _ckpt_lower for k in ("flatbread", "wai", "illustrious", "animagine", "animefull"))
        self.extra_quality_kws = [] if _is_illustrious else ["soft lighting", "delicate anime coloring", "soft shaded skin", "clean pale skin"]


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

        ctx.pose_tag = pose_tag

        # 2인 이상 상호작용 여부 감지
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
            "pleasure", "winking", "embarrassed", "pout", "flustered", "intoxicated"
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


class PositiveAssemblyMutator(PromptMutator):
    """2단계: 캐릭터 외형/의상과 포즈를 결합하여 긍정 프롬프트(Positive Prompt) 1차 조립."""

    def mutate(self, ctx: PromptContext) -> None:
        pose_tag = ctx.pose_tag

        if (ctx.nude or ctx.slot != "default") and getattr(ctx.char, "sdxl_nude_positive", None):
            base_pos = ctx.char.sdxl_nude_positive.strip()
            base_pos = re.sub(r",?\s*(photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|wet skin|sweatdrop|sweat|volumetric lighting)", "", base_pos, flags=re.IGNORECASE)
            if ctx.nude:
                base_pos = f"{base_pos}, nude, completely nude"
            else:
                theme_outfit = get_character_outfit_prompt(ctx.char, ctx.slot)
                if theme_outfit:
                    base_pos = f"{base_pos}, {theme_outfit}"
            if " BREAK " in base_pos:
                quality_part, char_part = base_pos.split(" BREAK ", 1)
                char_part = harmonize_character_expression(char_part, pose_tag)
                if ctx.is_two_person:
                    char_part = re.sub(r",?\s*\b(solo|1girl, solo)\b", ", 1girl", char_part, flags=re.IGNORECASE)
                    char_part = re.sub(r"^\s*,\s*", "", char_part)
                quality_clean = re.sub(r",?\s*(HDR|high contrast|cartoon|glossy skin|photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|wet skin|sweatdrop|sweat|volumetric lighting)", "", quality_part, flags=re.IGNORECASE)
                for kw in ctx.extra_quality_kws:
                    if kw.lower() not in quality_clean.lower():
                        quality_clean = f"{quality_clean}, {kw}"
                prefix_tags = f"{ctx.custom_pos.strip()}, {quality_clean.strip()}" if ctx.custom_pos and ctx.custom_pos.strip() else quality_clean.strip()
                first_chunk = f"{prefix_tags}, {pose_tag}" if pose_tag else prefix_tags
                ctx.positive_prompt = f"{first_chunk} BREAK {char_part.strip()}"
            else:
                base_pos = harmonize_character_expression(base_pos, pose_tag)
                if ctx.is_two_person:
                    base_pos = re.sub(r",?\s*\b(solo|1girl, solo)\b", ", 1girl", base_pos, flags=re.IGNORECASE)
                prefix_tags = f"{ctx.custom_pos.strip()}, {base_pos}" if ctx.custom_pos and ctx.custom_pos.strip() else base_pos
                ctx.positive_prompt = f"{prefix_tags}, {pose_tag}" if pose_tag else prefix_tags

        elif ctx.char.sdxl_positive:
            base_pos = ctx.char.sdxl_positive.strip()
            base_pos = re.sub(r",?\s*\(?hourglass\s*(shape)?(:[0-9\.]+)?\)?", "", base_pos, flags=re.IGNORECASE)
            base_pos = re.sub(r",?\s*(photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|wet skin|sweatdrop|sweat|volumetric lighting)", "", base_pos, flags=re.IGNORECASE)
            if ctx.nude:
                base_pos = strip_sdxl_outfit_tags(base_pos)
                base_pos = f"{base_pos}, nude, completely nude"
            elif ctx.slot != "default":
                theme_outfit = get_character_outfit_prompt(ctx.char, ctx.slot)
                base_pos = strip_sdxl_outfit_tags(base_pos)
                if theme_outfit:
                    base_pos = f"{base_pos}, {theme_outfit}"

            if " BREAK " in base_pos:
                quality_part, char_part = base_pos.split(" BREAK ", 1)
                char_part = harmonize_character_expression(char_part, pose_tag)
                if ctx.is_two_person:
                    char_part = re.sub(r",?\s*\b(solo|1girl, solo)\b", ", 1girl", char_part, flags=re.IGNORECASE)
                    char_part = re.sub(r"^\s*,\s*", "", char_part)
                quality_clean = re.sub(r",?\s*(HDR|high contrast|cartoon|glossy skin|photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|wet skin|sweatdrop|sweat|volumetric lighting)", "", quality_part, flags=re.IGNORECASE)
                for kw in ctx.extra_quality_kws:
                    if kw.lower() not in quality_clean.lower():
                        quality_clean = f"{quality_clean}, {kw}"
                prefix_tags = f"{ctx.custom_pos.strip()}, {quality_clean.strip()}" if ctx.custom_pos and ctx.custom_pos.strip() else quality_clean.strip()
                first_chunk = f"{prefix_tags}, {pose_tag}" if pose_tag else prefix_tags
                ctx.positive_prompt = f"{first_chunk} BREAK {char_part.strip()}"
            else:
                base_pos = harmonize_character_expression(base_pos, pose_tag)
                if ctx.is_two_person:
                    base_pos = re.sub(r",?\s*\b(solo|1girl, solo)\b", ", 1girl", base_pos, flags=re.IGNORECASE)
                prefix_tags = f"{ctx.custom_pos.strip()}, {base_pos}" if ctx.custom_pos and ctx.custom_pos.strip() else base_pos
                ctx.positive_prompt = f"{prefix_tags}, {pose_tag}" if pose_tag else prefix_tags
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
            if ctx.custom_pos and ctx.custom_pos.strip():
                quality_tags = f"{ctx.custom_pos.strip()}, {quality_tags}"
            first_chunk = f"{quality_tags}, {pose_tag}" if pose_tag else quality_tags.strip()
            solo_tag = "" if ctx.is_two_person else "solo, "
            ctx.positive_prompt = f"{first_chunk} BREAK {gender_tag}, {solo_tag}{char_desc}"


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
            multi_male_inhibit = "((2boys, 3boys, multiple boys, multiple males, group sex, threesome, gangbang:1.35))"
            if multi_male_inhibit not in neg:
                neg = f"{neg}, {multi_male_inhibit}"

        if ctx.custom_neg and ctx.custom_neg.strip():
            neg = f"{neg}, {ctx.custom_neg.strip()}"

        # 포즈별 커스텀 네거티브 주입 (204번 발표 포즈 손 왜곡 방지 등)
        if getattr(ctx.pose, "negative_add", None) and ctx.pose.negative_add.strip():
            neg = f"{neg}, {ctx.pose.negative_add.strip()}"

        if "(photorealistic, realistic, 3d" not in neg:
            char_mult_guard = "" if ctx.is_two_person else "(multiple characters, character sheet, concept art, reference sheet, mannequin:1.3), "
            neg = f"(photorealistic, realistic, 3d, render, cgi:1.25), {char_mult_guard}{neg}"

        ctx.negative_prompt = neg


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

        # [패치 0-1] 상시 공통 결함 방어
        neg = (
            f"{neg}, "
            f"(text:1.4), (speech bubble:1.4), (dialogue:1.4), (dialogue box:1.4), (subtitles:1.4), (comic panel:1.4), (sound effects:1.4), (watermark:1.3), (signature:1.3), "
            f"(mask:1.4), (white mask:1.4), (face mask:1.4), (noh mask:1.4), (porcelain mask:1.4), (paper mask:1.4), (theatrical mask:1.4), (blindfold:1.4), (covered eyes:1.35), "
            f"(empty eyes:1.35), (blank eyes:1.35), (pupil-less:1.35), (white eyes:1.35), (eyeless:1.4), "
            f"(extra hands:1.4), (extra arms:1.4), (multiple hands:1.4), (multiple arms:1.4), (fused hands:1.4), (too many fingers:1.4), (missing fingers:1.35), (poorly drawn hands:1.35), (mutated hands:1.35)"
        )

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

        # [패치 C] 오토코노코 성기 분기
        char_gender_str = (ctx.char.gender or getattr(ctx.char, "default_mode", "") or "female").lower()
        ctx.is_otokonoko = char_gender_str == "otokonoko" or bool(ctx.char.sdxl_positive and "otokonoko" in ctx.char.sdxl_positive.lower())
        if ctx.is_otokonoko and ctx.nude:
            neg = f"{neg}, (pussy:1.35), (vagina:1.35), (female genitalia:1.35), (cameltoe:1.35), (cleavage:1.2), (large breasts:1.3), (breasts:1.2)"
            if "penis" not in ctx.positive_prompt.lower():
                ctx.positive_prompt = f"{ctx.positive_prompt}, (penis:1.2), (small erect penis:1.15), (testicles:1.15), male genitalia"

        ctx.negative_prompt = neg


class TwoPersonMobMutator(PromptMutator):
    """5단계: 2인 인터랙티브 씬 모브 BREAK 주입, 다인(갱뱅/3P) vs 단일 모브 분기, 시선 차단."""

    def mutate(self, ctx: PromptContext) -> None:
        pose_tag = ctx.pose_tag
        neg = ctx.negative_prompt
        pos = ctx.positive_prompt

        ctx.is_offscreen_partner = any(kw in pose_tag.lower() for kw in ("off-screen", "offscreen", "completely off-screen"))
        ctx.is_aftermath = any(kw in pose_tag.lower() for kw in ("aftermath", "aftersex"))

        has_interactive_keywords = any(kw in pose_tag.lower() for kw in (
            "partner", "faceless male", "missionary",
            "doggystyle", "cowgirl", "straddling", "penetration", "paizuri",
            "fellatio", "titfuck", "groping", "grabbed from behind", "hugging from behind",
            "shower sex", "standing sex", "anal sex", "vaginal penetration", "anal penetration",
            "alley sex", "covert sex"
        ))

        is_daily_or_pov = (not has_interactive_keywords) and (
            ctx.pose.section in ("genit_actions", "emotions", "actions", "spy_actions", "wuxia_actions")
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
            neg = re.sub(r",?\s*\bmale\b(?!\s+(?:face|partner|body|head|eyes|clothes|hair))", "", neg, flags=re.IGNORECASE)

            is_multi_partner = any(
                kw in pose_tag.lower()
                for kw in ("2boys", "3boys", "multiple boys", "gangbang", "threesome", "foursome", "group sex", "bukkake", "surrounded", "harem")
            )

            multi_male_guard = (
                "" if is_multi_partner
                else "(2boys:1.6), (multiple boys:1.6), (two men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate male:1.5), (two male partners:1.5), (second man:1.5), (multiple partners:1.5), "
            )
            limb_guard = "(extra hands:1.45), (multiple hands:1.45), (extra arms:1.45), (multiple arms:1.45), (three hands:1.45), (four hands:1.45), (duplicate hands:1.45), (duplicate arms:1.45), (extra limbs:1.4), (fused hands:1.4), (poorly drawn hands:1.4), "
            neg = f"{neg}, (severed head:1.4), (decapitation:1.4), (headless:1.4), (floating head:1.4), (disembodied head:1.4), (multiple heads:1.35), (two heads:1.35), (2girls:1.35), (multiple girls:1.35), (extra girl:1.35), (two girls:1.35), (duplicate:1.35), (reaction face:1.35), (inset:1.35), {multi_male_guard}{limb_guard}(extra head:1.35), own hand on face, own hand on chin, resting chin on hand, holding own chin, touching own face, touching own chin, hand on own face, hand on own chin, gloves, orange skin, (pitch black shadow on body:1.25), (burnt skin:1.25)"

            if ctx.is_offscreen_partner:
                neg = f"{neg}, ((male body, male torso, male lower body, male legs, pants, trousers, black pants, jeans, lap, sitting between legs, legs of partner, 1boy:1.35))"
            else:
                pos = re.sub(r",\s*solo\b", "", pos, flags=re.IGNORECASE)
                male_face_suppression = "(detailed male face:1.4), (detailed eyes on male:1.35), (handsome male:1.4), (attractive male face:1.3), (expressive male face:1.3), (male portrait:1.3), (bishi:1.3), (male eyelashes:1.3), male hair, male bangs, male haircut"

                is_non_sexual_support = any(kw in pose_tag.lower() for kw in ("non-sexual", "channeling qi", "transferring internal energy", "hands resting on back", "palms on upper back"))
                if is_non_sexual_support:
                    mob_positive = "BREAK (faceless male partner:1.15), (obscured face:1.15), (head out of frame:1.15), (from behind:1.15), sitting behind her, hands gently resting on her upper back, traditional oriental martial robes, non-sexual, serene healing"
                    mob_negative = f"{male_face_suppression}, (naked male:1.5), (shirtless:1.4), (bare chest:1.4), (penis:1.5), (sexual:1.5), (groping:1.5), (grabbing breasts:1.5), (kissing:1.5), (2boys:1.5), (multiple boys:1.5), (cross-section:1.5)"
                elif is_multi_partner:
                    neg = re.sub(r",?\s*\b(2boys|multiple boys|multiple males|two men|extra male|group|threesome|group sex)\b(:[0-9\.]+)?", "", neg, flags=re.IGNORECASE)
                    if ctx.nude:
                        mob_positive = "BREAK (multiple faceless males:1.15), (group of faceless men surrounding:1.15), (obscured male faces:1.15), (shadow over male eyes:1.1), (from behind:1.1), (naked males:1.15), (bottomless males:1.15), muscular builds"
                        mob_negative = f"{male_face_suppression}, male clothes, male shirt, pants, trousers, jeans, shorts, underwear"
                    else:
                        mob_positive = "BREAK (multiple faceless males:1.15), (group of faceless men surrounding:1.15), (obscured male faces:1.15), (shadow over male eyes:1.1), (from behind:1.1), (solid black pants:1.2), muscular builds"
                        mob_negative = f"{male_face_suppression}, male clothes, male shirt, male t-shirt, male jacket, male suit, (naked male:1.2), (bottomless:1.2), (male underwear:1.2), jeans, blue pants"
                else:
                    is_head_hug_scene = any(
                        kw in pose_tag.lower()
                        for kw in (
                            "head on chest", "burying face", "face buried", "holding head",
                            "hugging head", "patting head", "kissing head", "hair from behind",
                            "back of male", "back of head"
                        )
                    )
                    is_rear_scene = (
                        any(kw in pose_tag.lower() for kw in ("back hug", "doggystyle", "sumata", "rear", "prone", "grabbed from behind", "hugging from behind"))
                        or ("behind" in pose_tag.lower() and not any(f in pose_tag.lower() for f in ("head from behind", "hair from behind", "face buried", "cleavage", "buried between breasts", "nestled in cleavage")))
                    )
                    rear_direction = "(from behind:1.15), " if is_rear_scene else ""

                    if is_head_hug_scene:
                        # 이미 포즈 자체에 남성의 밀착 위치/뒤통수가 완전히 정의되어 있으므로 추가 모브 BREAK 블록을 주입하지 않음 (남성 분신 2명 방지)
                        mob_positive = ""
                        mob_negative = "(detailed male face:1.4), (detailed eyes on male:1.35), (handsome male:1.4), (attractive male face:1.3), (expressive male face:1.3), (male portrait:1.3), (bishi:1.3), (male eyelashes:1.3), (standing male:1.5), (tall male:1.5), (standing beside:1.5), (standing partner:1.5), (2boys:1.8), (3boys:1.8), (multiple boys:1.8), (multiple males:1.8), (two men:1.8), (extra male:1.8), (second male:1.8), (duplicate male:1.8), (group:1.8), (threesome:1.8)"
                    else:
                        head_cue = "(male head out of frame:1.15), "
                        head_suppression = male_face_suppression
                        lower_body = "(bottomless male:1.15), muscular build" if ctx.nude else "(solid black pants:1.2), muscular build"

                        if ctx.nude:
                            mob_positive = f"BREAK (single faceless male partner:1.15), (obscured male face:1.15), {head_cue}(shadow over male eyes:1.1), {rear_direction}(naked male:1.15), {lower_body}"
                            mob_negative = f"{head_suppression}, male clothes, male shirt, pants, trousers, jeans, shorts, underwear, (2boys:1.6), (multiple boys:1.6), (multiple males:1.6), (two men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6), (second male:1.6), (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45)"
                        else:
                            mob_positive = f"BREAK (single faceless male partner:1.15), (obscured male face:1.15), {head_cue}(shadow over male eyes:1.1), {rear_direction}(shirtless male:1.1), (bare shoulders:1.1), {lower_body}"
                            mob_negative = f"{head_suppression}, male clothes, male shirt, male t-shirt, male jacket, male suit, (naked male:1.2), (bottomless:1.2), (male underwear:1.2), jeans, blue pants, (2boys:1.6), (multiple boys:1.6), (multiple males:1.6), (two men:1.6), (extra male:1.6), (group:1.5), (threesome:1.5), (duplicate body:1.5), (duplicate male:1.6), (second male:1.6), (extra hands:1.45), (multiple hands:1.45), (extra arms:1.45)"

                if mob_positive:
                    pos = f"{pos} {mob_positive}"
                neg = f"{neg}, {mob_negative}"

            if any(kw in pose_tag.lower() for kw in ("looking at partner", "look at partner", "eye contact with partner", "facing partner", "towards partner")):
                neg = f"{neg}, looking at viewer, looking straight at camera"
            if any(kw in pose_tag.lower() for kw in ("looking down", "head tilted down", "downcast eyes", "head down")):
                neg = f"{neg}, looking at viewer, looking straight at camera"

        if ctx.is_aftermath or ctx.is_solo_scene:
            neg = f"{neg}, ((1boy, 2boys, male, masculine, partner, faceless male, multiple characters, extra face:1.35))"

        ctx.positive_prompt = pos
        ctx.negative_prompt = neg


class SanitizerMutator(PromptMutator):
    """6단계: 가중치 안전 클램핑(clamp_sdxl_weights) 및 공백/쉼표/BREAK 구조 정규화."""

    def mutate(self, ctx: PromptContext) -> None:
        pos = clamp_sdxl_weights(ctx.positive_prompt, max_weight=1.15)
        neg = clamp_sdxl_weights(ctx.negative_prompt, max_weight=1.25)

        pos = re.sub(r"\s*,\s*", ", ", pos).strip()
        pos = re.sub(r",?\s*BREAK\s*,?", " BREAK ", pos).strip()
        neg = re.sub(r"\s*,\s*", ", ", neg).strip()

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
            SanitizerMutator(),
        ]

    def execute(self, ctx: PromptContext) -> Tuple[str, str, bool]:
        for mutator in self.mutators:
            mutator.mutate(ctx)
        return ctx.positive_prompt, ctx.negative_prompt, ctx.nude


default_sdxl_pipeline = SDXLPromptPipeline()
