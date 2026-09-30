"""
plepa_engine.prompt_builder
플럭스 T5-XXL 인코더에 최적화된 영문 서술형 자연어 프롬프트 조합 모듈.
"""

from __future__ import annotations

import re
from typing import Tuple
from plepa_engine.models import CharacterConfig, PoseEntry


def is_nude_pose(entry: PoseEntry) -> bool:
    """해당 포즈가 탈의/나체 상태를 요구하는지 판별."""
    if entry.section in ("h_scenes", "scenes_otokonoko"):
        return True
    # 착의 포즈(20~39) 중 나체 씬 명시적 포함 항목
    if entry.code in ("30", "38", "39"):
        return True
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
    "underboob", "underbust", "corset", "bodice", "bustier", "straps", "suspender", "garter"
})

_HAIR_KEYWORDS = (
    "hair", "ponytail", "bun", "bangs", "strands", "sidelocks",
    "twintails", "braid", "updo", "ahoge", "curls"
)

DEFAULT_SDXL_NEGATIVE = (
    "worst quality, low quality, bad anatomy, bad proportions, bad hands, extra fingers, missing fingers, "
    "mutated hands, extra limbs, deformed, jpeg artifacts, watermark, signature, text, 1boy, male, "
    "photorealistic, realistic, 3d, render, flat color, thick lineart, comic, panel layout, border, monochrome, greyscale"
)


def strip_sdxl_outfit_tags(prompt_text: str) -> str:
    """
    SDXL 캐릭터 프롬프트에서 헤어/체형/얼굴 태그는 보존하고 의상 및 착용 액세서리 태그를 제거.
    완전 탈의(H-씬)에서 의상 파편이 잔류하는 현상을 방지.
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
            if not is_outfit and any(kw in clean for kw in ("through dress", "contouring dress", "through clothes", "underboob", "underbust")):
                is_outfit = True

            if not is_outfit:
                cleaned_tags.append(t)
        chunks.append(", ".join(cleaned_tags))

    return " BREAK ".join(chunks)


def clamp_sdxl_weights(prompt_text: str, max_weight: float = 1.15) -> str:
    """
    ComfyUI 순정 CLIP 인코더에서 가중치 과다 곱셈으로 인한 색상 폭주(Color Burn / 네온 형광 현상)를
    방지하기 위해 1.15를 초과하는 과도한 가중치를 안전 한계치로 자동 클램핑합니다.
    """
    def _clamp_match(m: re.Match) -> str:
        w = float(m.group(1))
        return f":{min(w, max_weight):.2f}"

    return re.sub(r":([0-9]+\.[0-9]+)", _clamp_match, prompt_text)


def assemble_sdxl_prompt(
    char: CharacterConfig,
    pose: PoseEntry,
    bg_prompt: str = "",
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
        if nude:
            base_pos = strip_sdxl_outfit_tags(base_pos)
            base_pos = f"{base_pos}, nude, completely nude"

        if " BREAK " in base_pos:
            quality_part, char_part = base_pos.split(" BREAK ", 1)
            first_chunk = f"{quality_part.strip()}, {pose_tag}" if pose_tag else quality_part.strip()
            positive_prompt = f"{first_chunk} BREAK {char_part.strip()}"
        else:
            positive_prompt = f"{base_pos}, {pose_tag}" if pose_tag else base_pos.strip()
    else:
        # 폴백: 캐릭터 외형 기반
        gender_tag = "1boy, male" if char.gender.lower() == "male" else "1girl"
        char_desc = f"{char.appearance.face_and_hair}, {char.appearance.physique}".strip(", ")
        if not nude and char.appearance.outfit:
            char_desc += f", {char.appearance.outfit}"
        elif nude:
            char_desc += ", nude, completely nude"

        quality_tags = "masterpiece, best quality, newest, absurdres, aesthetic illustration"
        first_chunk = f"{quality_tags}, {pose_tag}" if pose_tag else quality_tags.strip()
        positive_prompt = f"{first_chunk} BREAK {gender_tag}, solo, {char_desc}"

    # 3. 부정 프롬프트 조립
    negative_prompt = char.sdxl_negative.strip() if char.sdxl_negative else DEFAULT_SDXL_NEGATIVE

    # 4. ComfyUI 색상 왜곡 방지용 가중치 안전 클램핑 (1.15 한계치)
    positive_prompt = clamp_sdxl_weights(positive_prompt, max_weight=1.15)
    negative_prompt = clamp_sdxl_weights(negative_prompt, max_weight=1.15)

    # 연속 콤마 및 공백 정리
    positive_prompt = re.sub(r"\s*,\s*", ", ", positive_prompt).strip()
    negative_prompt = re.sub(r"\s*,\s*", ", ", negative_prompt).strip()

    return positive_prompt, negative_prompt, nude


