"""
plepa_engine.pipeline.context
SDXL 프롬프트 조립 파이프라인 컨텍스트(PromptContext), Mutator 기반 클래스 및 Tier 판별기.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.pipeline.constants import _INTERACTIVE_POSE_KEYWORDS, _MOB_TIER_SPECS
from plepa_engine.prompt_builder import _is_no_background, resolve_pose_outfit_slot


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
