"""
plepa_engine.prompt_builder
플럭스 T5-XXL 인코더에 최적화된 영문 서술형 자연어 프롬프트 조합 모듈.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from plepa_engine.models import CharacterConfig, PoseEntry


def is_nude_pose(entry: PoseEntry) -> bool:
    """해당 포즈가 탈의/나체 상태를 요구하는지 판별."""
    if entry.section in ("h_scenes", "scenes_otokonoko"):
        return True
    # 착의 포즈(20~39 / 020~039) 중 나체 씬 명시적 포함 항목
    try:
        if int(entry.code) in (30, 38, 39):
            return True
    except (ValueError, TypeError):
        pass
    return False


def assemble_flux_prompt(
    char: CharacterConfig,
    pose: PoseEntry,
    bg_prompt: str = "",
) -> Tuple[str, bool]:
    """
    캐릭터 설정과 포즈 DB의 항목을 결합하여 고품질 플럭스 자연어 프롬프트를 조립합니다.
    - 탈의/H-씬의 경우 캐릭터 평상시 의상 묘사를 원천 배제합니다.
    - emotions 씬의 경우 프로젝트 배경(bg_prompt)이 주어지면 기본 배경을 치환합니다.
    - 반환값: (최종 조립 프롬프트, 탈의여부 boolean)
    """
    nude = is_nude_pose(pose)
    sentences = []

    # 1. 포즈/구도 및 상황 서술 (선두 배치하여 구도 우선권 부여)
    pose_text = pose.prompt.strip()
    if bg_prompt and pose.section == "emotions":
        bg_clean = bg_prompt.strip().rstrip(".")
        pose_text = re.sub(
            r"Clean\s+(minimalist|minimalistic|soft)?\s*(indoor\s+)?background[,\.\s]*",
            f"Set in {bg_clean}, ",
            pose_text,
            flags=re.IGNORECASE,
        )

    if pose_text:
        if not pose_text.endswith("."):
            pose_text += "."
        sentences.append(pose_text)

    # 2. 인물 기본 외형 (헤어, 눈동자, 신체 특징)
    face_hair = char.appearance.face_and_hair.strip()
    physique = char.appearance.physique.strip()
    char_desc_parts = [p for p in (face_hair, physique) if p]
    if char_desc_parts:
        desc_text = f"The character features {', '.join(char_desc_parts)}."
        sentences.append(desc_text)

    # 3. 의상 묘사 (착의 상태일 때만 주입)
    if not nude:
        outfit = char.appearance.outfit.strip()
        if outfit:
            sentences.append(f"Dressed in {outfit}.")

    # 4. 화풍 및 렌더링 품질 키워드
    if char.style_keywords:
        style = char.style_keywords.strip()
        if not style.endswith("."):
            style += "."
        sentences.append(style)

    # 5. 캐릭터 전용 LoRA 트리거 (지정된 경우)
    if char.lora.name:
        sentences.append(f"<lora:{char.lora.name}:{char.lora.weight:.2f}>")

    final_prompt = " ".join(sentences)
    # 연속 공백 및 마침표 중복 정리
    final_prompt = re.sub(r"\s+", " ", final_prompt)
    final_prompt = re.sub(r"\.\s*\.", ".", final_prompt)

    return final_prompt.strip(), nude


_OUTFIT_KEYWORDS = frozenset({
    "dress", "skirt", "bodycon", "knit", "high-neck", "turtleneck", "sleeves", "sleeved",
    "cutout", "shirt", "blouse", "pants", "jeans", "trousers", "slacks", "jacket", "coat", "sweater", "cardigan",
    "uniform", "suit", "collar", "cuffs", "tie", "necktie", "bowtie", "necklace", "pendant", "choker",
    "bracelet", "gloves", "socks", "stockings", "pantyhose", "shoes", "boots", "heels",
    "bra", "panties", "underwear", "swimwear", "bikini", "swimsuit", "leotard", "one-piece",
    "apron", "shorts", "robe", "kimono", "hoodie", "top", "camisole",
    "underboob", "underbust", "corset", "bodice", "bustier", "strap", "straps", "suspender", "garter", "garters",
    "belt", "buckle", "sash", "shawl", "fabric", "slit", "wrap", "wristwatch", "watch",
    "neckline", "scoop", "plunging", "v-neck", "halter-neck", "halterneck", "off-shoulder", "strapless", "backless",
    "slipping", "clinging", "contouring", "leather", "denim", "lace", "silk", "satin", "velvet", "cashmere",
    "headband", "headdress", "maid", "pinafore", "capelet", "cape", "petticoat", "brooch", "cross"
})

_HAIR_KEYWORDS = (
    "hair", "ponytail", "bun", "bangs", "strands", "sidelocks",
    "twintails", "braid", "updo", "ahoge", "curls"
)

DEFAULT_SDXL_QUALITY_TAGS = "masterpiece, best quality, very aesthetic, absurdres, newest, glossy skin, delicate anime coloring"

# 언홀리(Unholy) 전용 베스트 프랙티스 네거티브 (2D 미소녀 작화 극대화, 실사/3D 및 다중 인물/마네킹 차단)
DEFAULT_SDXL_NEGATIVE = (
    "lowres, worst quality, bad quality, bad anatomy, bad proportions, bad hands, "
    "missing fingers, extra digits, deformed, jpeg artifacts, signature, watermark, "
    "username, artist name, blurry, ugly face, weird eyes, (photorealistic, realistic, 3d, render, cgi:1.25), "
    "(multiple characters, character sheet, concept art, reference sheet, mannequin:1.3), "
    "1boy, male, choker, necklace, multiple moles, freckles, dark circles, dark eyelids, heavy shadow on face, "
    "(hourglass:1.3), (cat ears, animal ears, wolf ears, fox ears, kemonomimi:1.3), (comic:1.2), (multiple views:1.2), (panel layout:1.2)"
)


def strip_sdxl_outfit_tags(prompt_text: str) -> str:
    """
    SDXL 캐릭터 프롬프트에서 헤어/체형/얼굴 태그는 보존하고 의상 및 착용 액세서리 태그를 제거.
    완전 탈의(H-씬)에서 의상 파편(벨트, 스트랩, 숄, 치마 슬릿 등)이 잔류하는 현상을 방지.
    """
    if not prompt_text:
        return ""

    chunks = []
    parts = prompt_text.split(" BREAK ")
    for part in parts:
        tags = [t.strip() for t in part.split(",") if t.strip()]
        cleaned_tags = []
        for t in tags:
            clean = t.lower().replace("(", "").replace(")", "").split(":")[0].strip()
            is_hair = any(h in clean for h in _HAIR_KEYWORDS)
            words = clean.split()
            is_outfit = not is_hair and any(w in _OUTFIT_KEYWORDS for w in words)
            if not is_outfit and any(kw in clean for kw in (
                "through dress", "contouring dress", "through clothes", "underboob", "underbust",
                "side slit", "thigh slit", "off shoulder", "off-shoulder", "over shoulder",
                "slipping off", "snug fabric", "clinging tightly", "waist fit", "snug fit",
                "cashmere shawl", "leather belt", "black strap", "white strap", "silk strap",
                "metallic strap", "thin strap", "open back", "bare shoulders", "no jewelry",
                "maid headband", "maid cap", "maid dress", "ruffled apron", "frilled apron",
                "lace choker", "ribbon choker", "cross pendant", "lace cuffs", "puffy sleeves",
                "sweetheart neckline", "scoop neckline", "high-neck", "corset bodice"
            )):
                is_outfit = True

            if not is_outfit:
                cleaned_tags.append(t)
        chunks.append(", ".join(cleaned_tags))

    return " BREAK ".join(chunks)


def clamp_sdxl_weights(prompt_text: str, max_weight: float = 1.15) -> str:
    """
    Illustrious-XL / SDXL CLIP 인코더 최적화:
    1. 1.15를 초과하는 과도한 가중치를 안전 한계치(1.15)로 클램핑하여 색상 과포화 방지.
    2. 다중 괄호((...)) 누적으로 인한 비정상 가중치 증폭을 단일화.
    """
    def _clamp_match(m: re.Match) -> str:
        w = float(m.group(1))
        return f":{min(w, max_weight):.2f}"

    text = re.sub(r":([0-9]+\.[0-9]+)", _clamp_match, prompt_text)
    # 2중 이상 연속 괄호 정규화
    text = re.sub(r"\({2,}", "(", text)
    text = re.sub(r"\){2,}", ")", text)
    return text


def assemble_sdxl_prompt(
    char: CharacterConfig,
    pose: PoseEntry,
    bg_prompt: str = "",
    custom_pos: Optional[str] = None,
    custom_neg: Optional[str] = None,
) -> Tuple[str, str, bool]:
    """
    SDXL(Unholy Nova AI / Danbooru 포맷) 전용 긍정/부정 프롬프트를 조립합니다.
    - 반환값: (positive_prompt, negative_prompt, is_nude)
    """
    nude = is_nude_pose(pose)

    # 1. 포즈 태그 정리
    pose_tag = pose.prompt.strip()
    if bg_prompt and pose.section == "emotions":
        if "clean background" in pose_tag.lower():
            pose_tag = re.sub(r"clean\s+background", bg_prompt.strip(), pose_tag, flags=re.IGNORECASE)
        else:
            pose_tag = f"{pose_tag}, {bg_prompt.strip()}"

    # 2. 긍정 프롬프트 조립
    if char.sdxl_positive:
        base_pos = char.sdxl_positive.strip()
        # 모래시계 오브젝트 및 실사화 오염 태그 강제 제거
        base_pos = re.sub(r",?\s*\(?hourglass\s*(shape)?(:[0-9\.]+)?\)?", "", base_pos, flags=re.IGNORECASE)
        base_pos = re.sub(r",?\s*(photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|wet skin|sweatdrop|sweat|volumetric lighting)", "", base_pos, flags=re.IGNORECASE)
        if nude:
            base_pos = strip_sdxl_outfit_tags(base_pos)
            base_pos = f"{base_pos}, nude, completely nude"

        if " BREAK " in base_pos:
            quality_part, char_part = base_pos.split(" BREAK ", 1)
            # 기존 실사/과노출 태그 정제
            quality_clean = re.sub(r",?\s*(HDR|high contrast|cartoon|photorealistic(:[0-9\.]+)?|depth of field|soft shaded skin(:[0-9\.]+)?|smooth skin(:[0-9\.]+)?|wet skin|sweatdrop|sweat|volumetric lighting)", "", quality_part, flags=re.IGNORECASE)
            # 2D 만화체 전용 은은한 광택 태그 주입
            for kw in ("glossy skin", "delicate anime coloring"):
                if kw.lower() not in quality_clean.lower():
                    quality_clean = f"{quality_clean}, {kw}"
            prefix_tags = f"{custom_pos.strip()}, {quality_clean.strip()}" if custom_pos and custom_pos.strip() else quality_clean.strip()
            first_chunk = f"{prefix_tags}, {pose_tag}" if pose_tag else prefix_tags
            positive_prompt = f"{first_chunk} BREAK {char_part.strip()}"
        else:
            prefix_tags = f"{custom_pos.strip()}, {base_pos}" if custom_pos and custom_pos.strip() else base_pos
            positive_prompt = f"{prefix_tags}, {pose_tag}" if pose_tag else prefix_tags
    else:
        # 폴백: 캐릭터 외형 기반
        char_gender_val = (char.gender or getattr(char, "default_mode", "") or "female").lower()
        gender_tag = "1boy, male" if char_gender_val in ("male", "otokonoko") else "1girl"
        char_desc = f"{char.appearance.face_and_hair}, {char.appearance.physique}".strip(", ")
        if not nude and char.appearance.outfit:
            char_desc += f", {char.appearance.outfit}"
        elif nude:
            char_desc += ", nude, completely nude"

        quality_tags = DEFAULT_SDXL_QUALITY_TAGS
        if custom_pos and custom_pos.strip():
            quality_tags = f"{custom_pos.strip()}, {quality_tags}"
        first_chunk = f"{quality_tags}, {pose_tag}" if pose_tag else quality_tags.strip()
        positive_prompt = f"{first_chunk} BREAK {gender_tag}, solo, {char_desc}"

    # 3. 부정 프롬프트 조립
    negative_prompt = char.sdxl_negative.strip() if char.sdxl_negative else DEFAULT_SDXL_NEGATIVE
    if custom_neg and custom_neg.strip():
        negative_prompt = f"{negative_prompt}, {custom_neg.strip()}"

    # 실사/3D 및 다중 인물/마네킹 차단 방어선 최전방 보장
    if "(photorealistic, realistic, 3d" not in negative_prompt:
        negative_prompt = f"(photorealistic, realistic, 3d, render, cgi:1.25), (multiple characters, character sheet, concept art, reference sheet, mannequin:1.3), {negative_prompt}"

    # [패치 A] 탈의(nude) 상태 시 의상/에이프런/소품 잔류 원천 차단
    if nude:
        negative_prompt = f"{negative_prompt}, (clothes:1.35), (dress:1.35), (maid dress:1.35), (apron:1.35), (frilled apron:1.35), (white apron:1.35), (headband:1.35), (headdress:1.35), (collar:1.3), (choker:1.3), (vest:1.3), (capelet:1.3), (petticoat:1.3), (gloves:1.3), (socks:1.3), (stockings:1.3), (thighhighs:1.3), (bra:1.3), (panties:1.3), (underwear:1.3)"

    # [패치 A-2] 침대 및 탈의 씬에서 불필요한 와인/음료/유리잔/병 오브젝트 생성 차단
    if nude or "on bed" in pose_tag.lower():
        negative_prompt = f"{negative_prompt}, (wine, wine glass, champagne, glass, bottle, cup, drink, beverage:1.3)"

    # [패치 B] 턱올리기(033) 파트너 손 중복 및 꼬임 차단
    if "chin lift" in pose_tag.lower():
        negative_prompt = f"{negative_prompt}, (extra hands:1.35), (two hands on chin:1.35), (multiple hands:1.35), (extra arms:1.35), (four hands:1.35), (three hands:1.35)"

    # [패치 C] 오토코노코 캐릭터 나체/H씬 여성기 렌더링 방지 및 남성기 보장
    char_gender_str = (char.gender or getattr(char, "default_mode", "") or "female").lower()
    is_otokonoko = char_gender_str == "otokonoko" or (char.sdxl_positive and "otokonoko" in char.sdxl_positive.lower())
    if is_otokonoko and nude:
        negative_prompt = f"{negative_prompt}, (pussy:1.35), (vagina:1.35), (female genitalia:1.35), (cameltoe:1.35), (cleavage:1.2), (large breasts:1.3), (breasts:1.2)"
        if "penis" not in positive_prompt.lower():
            positive_prompt = f"{positive_prompt}, (penis:1.2), (small erect penis:1.15), (testicles:1.15), male genitalia"

    # 4. 2인 상호작용/파트너 씬 판별 및 충돌 방지
    is_offscreen_partner = any(kw in pose_tag.lower() for kw in ("off-screen", "offscreen", "completely off-screen"))
    is_aftermath = any(kw in pose_tag.lower() for kw in ("aftermath", "aftersex"))
    
    # 명백한 2인 결합/상호작용 키워드 식별 (샤워섹스, 스탠딩섹스, 삽입, 파트너 등)
    has_interactive_keywords = any(kw in pose_tag.lower() for kw in (
        "partner", "faceless male", "hug", "kiss", "carry", "missionary",
        "doggystyle", "cowgirl", "straddling", "penetration", "paizuri",
        "fellatio", "titfuck", "groping", "grabbed from behind", "hugging from behind",
        "shower sex", "standing sex", "anal sex", "vaginal penetration", "anal penetration"
    ))

    # 순수 1인 솔로 씬 (046/146 개각유혹, 038/039 단독 샤워 등)
    # 단, 결합/상호작용 키워드가 있으면 절대로 솔로로 오분류되지 않음
    is_solo_scene = not has_interactive_keywords and (
        "solo focus" in pose_tag.lower()
        or "solo, " in pose_tag.lower()
        or ", solo" in pose_tag.lower()
        or "standing in shower" in pose_tag.lower()
        or "shower stall" in pose_tag.lower()
        or "spreading own legs" in pose_tag.lower()
    )

    is_interactive = (
        has_interactive_keywords or pose.section in ("h_scenes", "scenes_otokonoko")
    ) and not is_aftermath and not is_solo_scene

    if is_interactive:
        # 부정 프롬프트에서 남성 차단 태그(1boy, male) 제거하여 여성 얼굴 복제 방지
        negative_prompt = re.sub(r",?\s*\b(1boy|male)\b", "", negative_prompt, flags=re.IGNORECASE)
        # 파트너 위치에 여성 머리/얼굴이 중복 렌더링되거나 자기 손으로 턱/얼굴을 잡는 왜곡, 손 색상 오염/장갑 원천 차단
        negative_prompt = f"{negative_prompt}, (multiple heads:1.3), (two heads:1.3), (2girls:1.3), (duplicate:1.3), (2boys:1.35), (multiple males:1.35), (extra head:1.35), own hand on face, own hand on chin, resting chin on hand, holding own chin, touching own face, touching own chin, hand on own face, hand on own chin, gloves, (colored skin:1.2), orange skin"

        # 화면 밖(off-screen) 파트너 씬의 경우 남성 하반신/의상 화면 침범 원천 차단
        if is_offscreen_partner:
            negative_prompt = f"{negative_prompt}, ((male body, male torso, male lower body, male legs, pants, trousers, black pants, jeans, lap, sitting between legs, legs of partner, 1boy:1.35))"
        else:
            # 긍정 프롬프트에서 단독 강제 태그(solo) 제거하여 파트너와의 자연스러운 공존 보장
            positive_prompt = re.sub(r",\s*solo\b", "", positive_prompt, flags=re.IGNORECASE)

            # 모브 남성 파트너: BREAK를 통한 여주인공과 모브의 Attention 완전 격리 (이염 원천 차단)
            # 포즈의 착의/탈의 여부에 따른 하의(단색 블랙 팬츠 vs 완전 탈의) 정밀 분기
            if nude:
                # 탈의/성인 씬: 완전 탈의 모브
                mob_positive = "BREAK (faceless male:1.2), (bald male:1.2), (naked male:1.2), (shirtless male:1.15), (bottomless male:1.2), muscular build, featureless silhouette"
                mob_negative = "male clothes, male shirt, pants, trousers, jeans, shorts, underwear, male hair, male bangs, male haircut"
            else:
                # 착의 스킨십 씬: 상반신 탈의 + 단색 블랙 팬츠 고정 (하의 무작위성 방지)
                mob_positive = "BREAK (faceless male:1.2), (bald male:1.2), (shirtless male:1.15), (bare shoulders:1.1), (solid black pants:1.2), muscular build, featureless silhouette"
                mob_negative = "male clothes, male shirt, male t-shirt, male jacket, male suit, (naked male:1.2), (bottomless:1.2), (male underwear:1.2), jeans, blue pants, male hair, male bangs, male haircut"

            positive_prompt = f"{positive_prompt} {mob_positive}"
            negative_prompt = f"{negative_prompt}, {mob_negative}"

        # 파트너를 응시해야 하는 상호작용 포즈인 경우 정면/카메라 응시 차단
        if any(kw in pose_tag.lower() for kw in ("looking at partner", "look at partner", "eye contact with partner", "facing partner", "towards partner")):
            negative_prompt = f"{negative_prompt}, looking at viewer, looking straight at camera"
        # 고개를 숙이거나 아래를 바라보아야 하는 포즈인 경우 정면/카메라 응시 차단
        if any(kw in pose_tag.lower() for kw in ("looking down", "head tilted down", "downcast eyes", "head down")):
            negative_prompt = f"{negative_prompt}, looking at viewer, looking straight at camera"

    # 사후여운 및 솔로 유혹 씬인 경우 모브/남성 파트너 신체 생성 원천 차단
    if is_aftermath or is_solo_scene:
        negative_prompt = f"{negative_prompt}, ((1boy, 2boys, male, masculine, partner, faceless male, multiple characters, extra face:1.35))"

    # 5. ComfyUI 색상 왜곡 방지용 가중치 안전 클램핑 (1.15 한계치)
    positive_prompt = clamp_sdxl_weights(positive_prompt, max_weight=1.15)
    negative_prompt = clamp_sdxl_weights(negative_prompt, max_weight=1.15)

    # 연속 콤마 및 공백 정리
    positive_prompt = re.sub(r"\s*,\s*", ", ", positive_prompt).strip()
    positive_prompt = re.sub(r",?\s*BREAK\s*,?", " BREAK ", positive_prompt).strip()
    negative_prompt = re.sub(r"\s*,\s*", ", ", negative_prompt).strip()

    return positive_prompt, negative_prompt, nude


