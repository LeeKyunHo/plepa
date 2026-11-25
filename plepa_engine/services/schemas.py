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
    """포즈 1개 항목 스키마 (`PoseEntry` 도메인 모델과 단일 SSOT 필드 대칭)."""
    model_config = ConfigDict(extra="allow")

    label: str = Field(min_length=1, max_length=32, description="포즈 간략 명칭")
    description: str = Field(default="", description="포즈 한글 상세 설명")
    prompt: str = Field(default="", description="SDXL 기본 프롬프트")
    required_outfit: str = Field(default="", description="요구 의상 슬롯 (default/nude/wedding 등)")
    prompt_female: str = Field(default="", description="여성 캐릭터 전용 분기 프롬프트")
    prompt_otokonoko: str = Field(default="", description="오토코노코 전용 분기 프롬프트")
    target_gender: Optional[str] = Field(default=None, description="대상 성별 제한 (female/otokonoko)")
    allowed_rosters: Optional[List[str]] = Field(default=None, description="허용 로스터 목록")
    negative_add: str = Field(default="", description="포즈별 추가 네거티브 태그")
    status: str = Field(default="active", description="포즈 활성 상태 (active/deprecated)")
    canonical_code: Optional[str] = Field(default=None, description="deprecated 시 통합 기준 코드")
    mob_tier: Optional[Literal[0, 1, 2, 3]] = Field(
        default=None,
        description="2인 파트너/모브 노출 등급 (0=솔로 POV, 1=손·팔 크롭, 2=실루엣 밀착, 3=콤팩트 봉사)",
    )
    partner_pos: Optional[Literal["above", "below", "behind", "side_kiss", "offscreen", "carry", "bury_chest"]] = Field(
        default=None,
        description="2인 구도 시 파트너 상대 위치",
    )
    mob_shadow: bool = Field(default=False, description="상안부 그림자 음영 가드 활성화 여부")
    flags: Optional[PoseFlags] = Field(default=None, description="포즈 메타데이터 플래그")

    @model_validator(mode="before")
    @classmethod
    def normalize_pose_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if not d.get("prompt") and d.get("sdxl_prompt"):
            d["prompt"] = d.get("sdxl_prompt")
        for txt_key in ("description", "prompt", "required_outfit", "prompt_female", "prompt_otokonoko", "negative_add"):
            if d.get(txt_key) is None:
                d[txt_key] = ""
        if d.get("status") is None:
            d["status"] = "active"
        if d.get("mob_shadow") is None:
            d["mob_shadow"] = False
        return d

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("포즈 라벨은 공백일 수 없습니다.")
        return s

    def to_pose_entry(self, code: str, section: str) -> Any:
        """검증된 스키마를 도메인 불변 모델 `PoseEntry`로 변환합니다."""
        from plepa_engine.models import PoseEntry

        return PoseEntry.from_dict(code=code, section=section, data=self.model_dump())

    @classmethod
    def from_pose_entry(cls, entry: Any) -> PoseItemSchema:
        """도메인 `PoseEntry` 인스턴스로부터 `PoseItemSchema`를 생성합니다."""
        return cls.model_validate({
            "label": entry.label,
            "description": entry.description,
            "prompt": entry.prompt,
            "required_outfit": entry.required_outfit,
            "prompt_female": entry.prompt_female,
            "prompt_otokonoko": entry.prompt_otokonoko,
            "target_gender": entry.target_gender,
            "allowed_rosters": entry.allowed_rosters,
            "negative_add": entry.negative_add,
            "status": entry.status,
            "canonical_code": entry.canonical_code,
            "mob_tier": entry.mob_tier,
            "partner_pos": entry.partner_pos,
            "mob_shadow": entry.mob_shadow,
            "flags": entry.flags,
        })


class PoseDatabaseSchema(BaseModel):
    """포즈 데이터베이스 전체 스키마 (V3 전체 섹션 및 하위 호환 섹션)."""
    model_config = ConfigDict(extra="allow")

    schema_info: Optional[Dict[str, Any]] = Field(default=None, alias="_schema")
    emotions: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    daily: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    poses: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    romance: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    daily_events: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    h_scenes: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    special_h: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    special_female_h: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    scenes_otokonoko: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    special_otokonoko: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    special_otokonoko_h: Dict[str, PoseItemSchema] = Field(default_factory=dict)
    otokonoko: Dict[str, PoseItemSchema] = Field(default_factory=dict)

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
    name: str = Field(default="", description="캐릭터 표시 이름 (한글 또는 영문)")
    gender: str = Field(default="female", description="성별 (female, male, otokonoko 등)")
    appearance: CharacterAppearanceSchema = Field(default_factory=CharacterAppearanceSchema)
    lora: LoraSchema = Field(default_factory=LoraSchema)
    loras: List[LoraSchema] = Field(default_factory=list, description="추가 LoRA 체이닝 목록")
    style_keywords: str = Field(
        default="masterpiece quality, ultra-detailed anime digital art, 8k resolution",
        description="화질 및 스타일 공통 키워드"
    )
    sdxl_positive: Optional[str] = Field(default=None, description="SDXL 전용 추가 긍정 태그")
    sdxl_nude_positive: Optional[str] = Field(default=None, description="SDXL 탈의/누드 전용 긍정 태그")
    sdxl_negative: Optional[str] = Field(default=None, description="SDXL 전용 추가 부정 태그")
    ref_weight: float = Field(default=0.7, ge=0.0, le=1.0, description="IP-Adapter 참조 이미지 가중치")
    default_mode: Optional[str] = Field(default=None, description="기본 엔진 모드 (sdxl, flux, fast, quality 등)")
    outfits: Dict[str, str] = Field(default_factory=dict, description="테마 슬롯별 의상 프롬프트 맵")
    profiles: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="의상/프로필별 오버라이드 맵")
    pose_restrictions: Dict[str, List[str]] = Field(default_factory=dict, description="캐릭터별 허용/제외 포즈 제한 규칙")
    faction: Optional[str] = Field(default=None, description="소속 진영/세계관 메타데이터")
    is_adult: bool = Field(default=True, description="성인 캐릭터 여부 (가드레일 검증용)")
    signature_accessories: List[str] = Field(default_factory=list, description="캐릭터 고유 장신구·소품 고정 목록 (CLIP 75토큰 전단 우선 배치)")

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
        # name 누락 시 prefix로 자동 폴백
        if not d.get("name"):
            d["name"] = d.get("prefix", "unknown")
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
