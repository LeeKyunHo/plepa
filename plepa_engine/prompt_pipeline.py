"""
plepa_engine.prompt_pipeline
SDXL 프롬프트 조합을 위한 Pipeline Mutator(미들웨어) 호환 퍼사드.
상세 구현은 `plepa_engine.pipeline` 서브패키지에 모듈별로 분리되어 있습니다.
"""

from __future__ import annotations

import logging
import os
import re

from plepa_engine.pipeline import (
    _COMPOSITION_ANTI_DRIFT_RULES,
    _H_SCENE_MOOD_LIGHTING_TAGS,
    _H_SCENE_WET_SKIN_TAGS,
    _INTERACTIVE_POSE_KEYWORDS,
    _MOB_EYELESS_BANGS_NEG,
    _MOB_SHADOW_EYES_POS,
    _MOB_TIER_SPECS,
    _OUTDOOR_DAYLIGHT_HINTS,
    _PARTNER_POS_SPECS,
    _PROTECTED_CONTROL_TAGS,
    _STEAMY_H_NEG_UNLOCK_PATTERN,
    _STYLE_NEGATIVE_BALANCED_GUARD,
    _STYLE_NEGATIVE_GUARD,
    _STYLE_POSITIVE_BALANCED_TAGS,
    _STYLE_POSITIVE_GUARD_TAGS,
    CompositionAntiDriftMutator,
    DefectDefenseMutator,
    NegativeBaseMutator,
    PoseTagPreparationMutator,
    PositiveAssemblyMutator,
    PromptContext,
    PromptMutator,
    SanitizerMutator,
    SDXLPromptPipeline,
    TwoPersonMobMutator,
    _apply_gaze_direction_negatives,
    _assemble_positive_prompt,
    _build_common_interactive_negative_guard,
    _inject_partner_pos_inline,
    _inject_signature_accessories,
    _inject_style_positive_guard,
    _inject_wet_skin_tags,
    _is_face_hair_accessory,
    _is_outdoor_daylight_pose,
    _resolve_mob_tier,
    _select_active_signature_accessories,
    _strip_accessory_negative_conflicts,
    _strip_tags_preserving_parens,
    default_sdxl_pipeline,
    find_tag_conflicts,
    harmonize_character_expression,
    normalize_tag,
    remove_conflicting_tags_from_negative,
    split_tags,
)
from plepa_engine.pipeline.sanitizer import logger

__all__ = [
    "PromptContext",
    "PromptMutator",
    "PoseTagPreparationMutator",
    "PositiveAssemblyMutator",
    "NegativeBaseMutator",
    "DefectDefenseMutator",
    "TwoPersonMobMutator",
    "CompositionAntiDriftMutator",
    "SanitizerMutator",
    "SDXLPromptPipeline",
    "default_sdxl_pipeline",
    "harmonize_character_expression",
    "normalize_tag",
    "split_tags",
    "find_tag_conflicts",
    "remove_conflicting_tags_from_negative",
]
