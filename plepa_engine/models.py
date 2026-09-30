"""
plepa_engine.models
플에파 데이터 구조 및 타입 모델 정의.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PoseEntry:
    code: str
    section: str
    label: str
    prompt: str


@dataclass
class CharacterAppearance:
    face_and_hair: str
    physique: str
    outfit: str


@dataclass
class LoraConfig:
    name: Optional[str] = None
    weight: float = 0.8


@dataclass
class CharacterConfig:
    prefix: str
    name: str
    gender: str
    appearance: CharacterAppearance
    lora: LoraConfig = field(default_factory=LoraConfig)
    style_keywords: str = "masterpiece quality, ultra-detailed anime digital art, 8k resolution"
    sdxl_positive: Optional[str] = None
    sdxl_negative: Optional[str] = None
    ref_weight: float = 0.7
    file_path: Optional[Path] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], file_path: Optional[Path] = None) -> CharacterConfig:
        app_raw = data.get("appearance", {})
        appearance = CharacterAppearance(
            face_and_hair=app_raw.get("face_and_hair", ""),
            physique=app_raw.get("physique", ""),
            outfit=app_raw.get("outfit", "")
        )
        lora_raw = data.get("lora", {})
        lora = LoraConfig(
            name=lora_raw.get("name"),
            weight=float(lora_raw.get("weight", 0.8))
        )
        sdxl_pos = data.get("sdxl_positive") or data.get("positive")
        sdxl_neg = data.get("sdxl_negative") or data.get("negative")
        ref_weight = float(data.get("ref_weight", 0.7))

        return cls(
            prefix=data.get("prefix", "unknown"),
            name=data.get("name", "Unknown"),
            gender=data.get("gender", "female"),
            appearance=appearance,
            lora=lora,
            style_keywords=data.get("style_keywords", "masterpiece quality, 8k resolution"),
            sdxl_positive=sdxl_pos,
            sdxl_negative=sdxl_neg,
            ref_weight=ref_weight,
            file_path=file_path
        )


@dataclass
class GenerationTarget:
    code: str
    section: str
    label: str
    assembled_prompt: str
    is_nude: bool
    output_filename: str


@dataclass
class GenerationResult:
    target: GenerationTarget
    success: bool
    image_path: Optional[Path] = None
    duration_sec: float = 0.0
    error_message: Optional[str] = None
