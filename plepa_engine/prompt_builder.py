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
    if getattr(entry, "required_outfit", None) == "nude":
        return True
    if entry.section in ("h_scenes", "scenes_otokonoko"):
        return True
    # 착의 포즈(20~39 / 020~039) 중 나체 씬 명시적 포함 항목
    try:
        if int(entry.code) in (30, 38, 39):
            return True
    except (ValueError, TypeError):
        pass
    return False


DEFAULT_THEME_OUTFITS = {
    "swimsuit": "micro bikini, halterneck bikini top, side-tie bikini bottom",
    "bunny": "black glossy bunny suit, fishnet pantyhose, bunny ears, white collar, bow tie",
    "maid": "classic maid outfit, black maid dress, white frilled apron, maid headdress, white thighhighs",
    "bdsm": "black leather strap harness, black choker, leather arm bands",
    "combat": "tactical battle attire, torn clothes, fingerless gloves, combat boots",
    "gym": "bloomers, gym uniform, white t-shirt",
    "school": "school uniform, sailor collar, pleated skirt",
    "underwear": "white lace bra, matching white lace panties",
    "wedding": "pure white bridal wedding gown, sheer bridal veil, floral lace bridal bodice, white opera gloves",
}


def resolve_pose_outfit_slot(pose: PoseEntry) -> str:
    """포즈의 요구 의상 슬롯('default', 'nude', 'swimsuit', 'bunny', 'maid' 등)을 판별."""
    if getattr(pose, "required_outfit", None):
        return pose.required_outfit.lower().strip()

    code = str(pose.code).upper().strip()
    sec = str(pose.section).lower().strip()
    label = str(getattr(pose, "label", "")).lower().strip()

    if is_nude_pose(pose):
        return "nude"
    if code.startswith("D") or sec == "swimsuit" or "수영" in label:
        return "swimsuit"
    if code.startswith("F") or sec == "bunny" or "바니" in label:
        return "bunny"
    if code.startswith("G") or sec == "maid" or "메이드" in label:
        return "maid"
    if code.startswith("E") or sec == "bdsm":
        return "bdsm"
    if code.startswith("I") or sec == "combat" or "전투" in label:
        return "combat"
    if "속옷" in label:
        return "underwear"
    if "웨딩" in label:
        return "wedding"

    return "default"


def get_character_outfit_prompt(char: CharacterConfig, slot: str) -> str:
    """캐릭터 맞춤 또는 공용 테마 의상 프롬프트를 조회."""
    slot = slot.lower().strip()
    if slot in ("", "nude"):
        return ""
    # 1. 캐릭터 고유 의상 슬롯 확인
    if hasattr(char, "get_outfit"):
        custom = char.get_outfit(slot)
        if custom:
            return custom
    elif hasattr(char, "outfits") and isinstance(char.outfits, dict):
        if slot in char.outfits and char.outfits[slot].strip():
            return char.outfits[slot].strip()

    # 2. 공용 테마 기본 의상 폴백
    return DEFAULT_THEME_OUTFITS.get(slot, "")


def _is_no_background(bg_prompt: str) -> bool:
    """해당 배경 프롬프트가 단색/무배경 스튜디오인지 판별."""
    if not bg_prompt:
        return False
    p = bg_prompt.strip().lower()
    if p in ("none", "no_bg", "nobg", "white_bg", "empty", "solid_white"):
        return True
    if "white background" in p and "simple background" in p:
        return True
    if "completely solid pure white background" in p or "clean minimalist studio backdrop" in p:
        return True
    return False


# ── 레거시 FLUX 프롬프트 빌더 (plepa_engine.legacy.flux_prompt_builder로 분리 격리됨) ──
from plepa_engine.legacy.flux_prompt_builder import assemble_flux_prompt


_OUTFIT_KEYWORDS = frozenset({
    "dress", "skirt", "bodycon", "knit", "high-neck", "turtleneck", "sleeves", "sleeved",
    "cutout", "shirt", "blouse", "pants", "jeans", "trousers", "slacks", "jacket", "coat", "sweater", "cardigan",
    "blazer", "vest", "waistcoat", "overcoat", "outerwear", "miniskirt", "mini-skirt",
    "uniform", "suit", "collar", "cuffs", "tie", "necktie", "bowtie", "necklace", "pendant", "choker",
    "bracelet", "gloves", "socks", "stockings", "pantyhose", "shoes", "boots", "heels",
    "bra", "panties", "underwear", "swimwear", "bikini", "swimsuit", "leotard", "one-piece",
    "apron", "shorts", "robe", "robes", "hanfu", "kimono", "hoodie", "top", "camisole", "bracers", "scabbard",
    "underboob", "underbust", "corset", "bodice", "bustier", "strap", "straps", "suspender", "garter", "garters",
    "belt", "buckle", "sash", "shawl", "fabric", "slit", "wrap", "wristwatch", "watch",
    "neckline", "scoop", "plunging", "v-neck", "halter-neck", "halterneck", "off-shoulder", "strapless", "backless",
    "slipping", "clinging", "contouring", "leather", "denim", "lace", "silk", "satin", "velvet", "cashmere",
    "headband", "headdress", "maid", "pinafore", "capelet", "cape", "petticoat", "brooch", "cross",
    "bandage", "bandages", "lanyard", "badge", "holster", "syringe", "holder", "folder", "bolero",
    "bunny", "suspenders", "tights", "qipao", "cheongsam", "bodysuit", "fishnet", "fishnets", "stiletto"
})

_HAIR_KEYWORDS = (
    "hair", "ponytail", "bun", "bangs", "strands", "sidelocks",
    "twintails", "braid", "updo", "ahoge", "curls"
)

DEFAULT_SDXL_QUALITY_TAGS = "masterpiece, best quality, highly detailed, soft lighting, delicate anime coloring, soft shaded skin, finely detailed beautiful eyes"

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


def clamp_sdxl_weights(prompt_text: str, max_weight: float = 1.40) -> str:
    """
    Illustrious-XL / SDXL CLIP 인코더 최적화:
    1. 지정된 max_weight를 초과하는 과도한 가중치를 안전 한계치로 클램핑하여 색상 과포화 방지.
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
    checkpoint_name: Optional[str] = None,
) -> Tuple[str, str, bool]:
    """
    SDXL(Unholy Nova AI / Danbooru 포맷) 전용 긍정/부정 프롬프트를 조립합니다.
    내부적으로 SDXLPromptPipeline(미들웨어 체인)을 통해 단계별 변환을 수행합니다.
    - 반환값: (positive_prompt, negative_prompt, is_nude)
    """
    from plepa_engine.prompt_pipeline import PromptContext, default_sdxl_pipeline

    ctx = PromptContext(
        char=char,
        pose=pose,
        bg_prompt=bg_prompt,
        custom_pos=custom_pos,
        custom_neg=custom_neg,
        checkpoint_name=checkpoint_name,
    )
    return default_sdxl_pipeline.execute(ctx)



