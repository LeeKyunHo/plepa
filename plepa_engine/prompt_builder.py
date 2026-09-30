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
