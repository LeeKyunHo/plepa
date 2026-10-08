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
    description: str = ""


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
    sdxl_nude_positive: Optional[str] = None
    sdxl_negative: Optional[str] = None
    ref_weight: float = 0.7
    profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    active_profile: Optional[str] = None
    default_mode: Optional[str] = None
    file_path: Optional[Path] = None

    def apply_profile(self, profile_name: Optional[str]) -> None:
        """지정된 프로필명에 맞추어 외형, 의상, 긍정/부정 태그 등을 동적으로 오버라이드합니다."""
        if not profile_name or profile_name.strip() in ("", "default"):
            return
        
        target = profile_name.strip()
        if target not in self.profiles:
            avail = list(self.profiles.keys())
            avail_msg = f" (사용 가능: {', '.join(avail)})" if avail else " (등록된 프로필 없음)"
            raise ValueError(f"캐릭터 '{self.prefix}'({self.name})에 '{target}' 프로필이 존재하지 않습니다.{avail_msg}")
        
        prof = self.profiles[target]
        # 1. 의상 및 외형 오버라이드
        if "outfit" in prof:
            self.appearance.outfit = str(prof["outfit"]).strip()
        if "face_and_hair" in prof:
            self.appearance.face_and_hair = str(prof["face_and_hair"]).strip()
        if "physique" in prof:
            self.appearance.physique = str(prof["physique"]).strip()
        
        # 2. SDXL 프롬프트 오버라이드
        pos_override = prof.get("sdxl_positive") or prof.get("positive")
        if pos_override:
            self.sdxl_positive = str(pos_override).strip()
        neg_override = prof.get("sdxl_negative") or prof.get("negative")
        if neg_override:
            self.sdxl_negative = str(neg_override).strip()
            
        # 3. LoRA / 가중치 오버라이드
        if "ref_weight" in prof:
            self.ref_weight = float(prof["ref_weight"])
        if "lora" in prof and isinstance(prof["lora"], dict):
            if "name" in prof["lora"]:
                self.lora.name = prof["lora"]["name"]
            if "weight" in prof["lora"]:
                self.lora.weight = float(prof["lora"]["weight"])

        self.active_profile = target

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
        sdxl_nude_pos = data.get("sdxl_nude_positive")
        sdxl_neg = data.get("sdxl_negative") or data.get("negative")
        ref_weight = float(data.get("ref_weight", 0.7))
        profiles_raw = data.get("profiles") or data.get("_profiles") or {}
        default_mode = data.get("default_mode")

        return cls(
            prefix=data.get("prefix", "unknown"),
            name=data.get("name", "Unknown"),
            gender=data.get("gender", "female"),
            appearance=appearance,
            lora=lora,
            style_keywords=data.get("style_keywords", "masterpiece quality, 8k resolution"),
            sdxl_positive=sdxl_pos,
            sdxl_nude_positive=sdxl_nude_pos,
            sdxl_negative=sdxl_neg,
            ref_weight=ref_weight,
            profiles=dict(profiles_raw) if isinstance(profiles_raw, dict) else {},
            default_mode=default_mode,
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
