"""
plepa_engine.services.schemas
Pydantic v2 기반 엄격한 데이터 유효성 검증 스키마 정의.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PoseFlags(BaseModel):
    """포즈 특성 명시적 메타데이터 (키워드 추측 휴리스틱 종식용)."""
    model_config = ConfigDict(extra="ignore")

    nude: Optional[bool] = Field(default=None, description="탈의/나체 여부 (True면 의상 스트리핑 및 nude 주입)")
    scene_type: Optional[Literal["solo", "interactive", "offscreen", "aftermath"]] = Field(
        default=None,
        description="씬 연출 유형 (solo: 단독, interactive: 모브/파트너 상호작용, offscreen: 화면 밖 파트너, aftermath: 사정 후/절정 잔여)"
    )
    wet: Optional[bool] = Field(default=None, description="물기/수증기 젖은 효과 유무")
    disabled: Optional[bool] = Field(default=False, description="소프트 삭제 여부 (True면 생성 목록에서 제외)")


class PoseItemSchema(BaseModel):
    """포즈 1개 항목 스키마."""
    model_config = ConfigDict(extra="allow")

    label: str = Field(min_length=1, max_length=20, description="포즈 간략 명칭 (권장 6글자 이하)")
    description: Optional[str] = Field(default="", description="포즈 한글 상세 설명")
    prompt: str = Field(min_length=1, description="엔진별 프롬프트 (FLUX 자연어 또는 SDXL 태그)")
    flags: Optional[PoseFlags] = Field(default=None, description="포즈 메타데이터 플래그")

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("포즈 라벨은 공백일 수 없습니다.")
        return s


class PoseDatabaseSchema(BaseModel):
    """포즈 데이터베이스 전체 스키마 (emotions, poses, h_scenes, scenes_otokonoko)."""
    model_config = ConfigDict(extra="allow")

    schema_info: Optional[Dict[str, Any]] = Field(default=None, alias="_schema")
    emotions: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    poses: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    h_scenes: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    scenes_otokonoko: Dict[str, PoseItemSchema] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def handle_schema_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "_schema" in data and "schema_info" not in data:
            data = dict(data)
            data["schema_info"] = data["_schema"]
        return data


class CharacterAppearanceSchema(BaseModel):
    """캐릭터 외형 묘사."""
    model_config = ConfigDict(extra="allow")

    face_and_hair: str = Field(default="", description="얼굴, 눈동자, 머리 스타일/색상")
    physique: str = Field(default="", description="체형, 체격, 가슴 크기 등 신체 묘사")
    outfit: str = Field(default="", description="기본 착용 의상")


class LoraSchema(BaseModel):
    """LoRA 모델 설정."""
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = Field(default=None, description="LoRA 파일명 (확장자 포함)")
    weight: float = Field(default=0.8, ge=0.0, le=2.0, description="LoRA 적용 강도")


class CharacterSchema(BaseModel):
    """캐릭터 정의 스키마."""
    model_config = ConfigDict(extra="allow")

    prefix: str = Field(min_length=2, max_length=32, description="고유 식별자 영문 약칭 (예: ykn, bjh)")
    name: str = Field(min_length=1, description="캐릭터 표시 이름 (한글 또는 영문)")
    gender: str = Field(default="female", description="성별 (female, male, otokonoko 등)")
    appearance: CharacterAppearanceSchema = Field(default_factory=CharacterAppearanceSchema)
    lora: LoraSchema = Field(default_factory=LoraSchema)
    style_keywords: str = Field(
        default="masterpiece quality, ultra-detailed anime digital art, 8k resolution",
        description="화질 및 스타일 공통 키워드"
    )
    sdxl_positive: Optional[str] = Field(default=None, description="SDXL 전용 추가 긍정 태그")
    sdxl_negative: Optional[str] = Field(default=None, description="SDXL 전용 추가 부정 태그")
    ref_weight: float = Field(default=0.7, ge=0.0, le=1.0, description="IP-Adapter 참조 이미지 가중치")
    profiles: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="의상/프로필별 오버라이드 맵")
    is_adult: bool = Field(default=True, description="성인 캐릭터 여부 (가드레일 검증용)")

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v: str) -> str:
        s = v.strip().lower()
        if not re.match(r"^[a-z0-9_]+$", s):
            raise ValueError(f"식별자(prefix)는 영문 소문자, 숫자, 밑줄(_)만 사용할 수 있습니다: '{s}'")
        return s

    @model_validator(mode="before")
    @classmethod
    def normalize_character_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # positive / negative 별칭 정규화
        if "positive" in d and "sdxl_positive" not in d:
            d["sdxl_positive"] = d.get("positive")
        if "negative" in d and "sdxl_negative" not in d:
            d["sdxl_negative"] = d.get("negative")
        # _profiles 별칭 정규화
        if "_profiles" in d and "profiles" not in d:
            d["profiles"] = d.get("_profiles")
        return d


class BackgroundPresetSchema(BaseModel):
    """단일 배경 프리셋."""
    key: str = Field(min_length=1, description="배경 프리셋 키 (예: default, bedroom, shower)")
    prompt: str = Field(description="배경 프롬프트 내용")


class PoseSetSchema(BaseModel):
    """이름 붙인 포즈 묶음 (배치 생성 즐겨찾기용)."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, description="포즈 세트 고유 ID (예: shower_pack, h_full)")
    name: str = Field(min_length=1, description="포즈 세트 표시 이름 (예: 샤워 3종 세트)")
    description: Optional[str] = Field(default="", description="설명")
    codes: List[str] = Field(default_factory=list, description="포즈 코드 목록 (예: ['038', '039', '057'])")
