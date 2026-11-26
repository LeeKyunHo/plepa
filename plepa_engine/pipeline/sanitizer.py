"""
plepa_engine.pipeline.sanitizer
5.5단계(CompositionAntiDriftMutator), 6단계(SanitizerMutator) 및 7단계 SDXLPromptPipeline 오케스트레이터.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from plepa_engine.pipeline.assembly import PositiveAssemblyMutator
from plepa_engine.pipeline.constants import (
    _COMPOSITION_ANTI_DRIFT_RULES,
    _STEAMY_H_NEG_UNLOCK_PATTERN,
)
from plepa_engine.pipeline.context import PromptContext, PromptMutator
from plepa_engine.pipeline.defense import DefectDefenseMutator
from plepa_engine.pipeline.mob import TwoPersonMobMutator
from plepa_engine.pipeline.negative_base import NegativeBaseMutator
from plepa_engine.pipeline.pose_prep import PoseTagPreparationMutator
from plepa_engine.pipeline.tags import (
    _strip_tags_preserving_parens,
    remove_conflicting_tags_from_negative,
)
from plepa_engine.prompt_builder import clamp_sdxl_weights

logger = logging.getLogger(__name__)


class CompositionAntiDriftMutator(PromptMutator):
    """5.5단계: 샷 사이즈별 반대 구도 이탈 방지 네거티브를 자동 주입합니다."""

    def mutate(self, ctx: PromptContext) -> None:
        pose_low = (ctx.pose_tag or "").lower()
        if not pose_low:
            return
        for shot_kws, anti_neg in _COMPOSITION_ANTI_DRIFT_RULES:
            if "full body" in shot_kws and "portrait" in pose_low:
                continue
            if any(kw in pose_low for kw in shot_kws):
                ctx.negative_prompt = f"{ctx.negative_prompt}, {anti_neg}" if ctx.negative_prompt else anti_neg
                break


class SanitizerMutator(PromptMutator):
    """6단계: 사용자/포즈 커스텀 네거티브 보호 주입, 가중치 안전 클램핑(clamp_sdxl_weights), 태그 충돌 정제 및 BREAK 정규화."""

    def mutate(self, ctx: PromptContext) -> None:
        # 0. 모브 정규식(TwoPersonMobMutator) 종료 후 포즈별/사용자 커스텀 네거티브 안전 결합
        if getattr(ctx.pose, "negative_add", None) and ctx.pose.negative_add.strip():
            ctx.negative_prompt = f"{ctx.negative_prompt}, {ctx.pose.negative_add.strip()}"
        if ctx.custom_neg and ctx.custom_neg.strip():
            ctx.negative_prompt = f"{ctx.negative_prompt}, {ctx.custom_neg.strip()}"

        if ctx.is_steamy_h_scene:
            ctx.negative_prompt = _strip_tags_preserving_parens(
                ctx.negative_prompt,
                _STEAMY_H_NEG_UNLOCK_PATTERN,
            )

        # 1. 긍정/부정 태그 충돌 감지 및 네거티브에서 자동 제거
        # 남성 모브 전용 BREAK 블록(레거시 및 Tier 2/3)의 태그가 여주인공 본체 네거티브를 지우지 않도록 모브 블록 제외 후 검사
        pos_without_mob = re.sub(
            r"\bBREAK\s*\((?:(?:single|multiple)\s+)?faceless(?:\s+shadowed)?\s+male.*$|\bBREAK\s*\(pov\s+crotch.*$|\bBREAK\s*\(tall\s+dark-haired\s+male\s+mob.*$",
            "",
            ctx.positive_prompt,
            flags=re.IGNORECASE,
        )
        cleaned_neg, conflicts = remove_conflicting_tags_from_negative(pos_without_mob, ctx.negative_prompt)
        if conflicts:
            logger.warning(f"[WARN] 프롬프트 태그 충돌 감지: {conflicts} -> 네거티브에서 자동 제거되었습니다.")
            ctx.negative_prompt = cleaned_neg

        # 2. 가중치 클램핑
        pos = clamp_sdxl_weights(ctx.positive_prompt, max_weight=1.15)
        neg = clamp_sdxl_weights(ctx.negative_prompt, max_weight=1.25)

        pos = re.sub(r"\(\s*,\s*", "(", pos)
        pos = re.sub(r"\s*,\s*", ", ", pos).strip().strip(",")
        pos = re.sub(r",?\s*BREAK\s*,?", " BREAK ", pos).strip()
        neg = re.sub(r"\(\s*,\s*", "(", neg)
        neg = re.sub(r",\s*,+", ", ", neg)
        neg = re.sub(r"\s*,\s*", ", ", neg).strip().strip(",")

        ctx.positive_prompt = pos
        ctx.negative_prompt = neg


class SDXLPromptPipeline:
    """SDXL 프롬프트 조합 미들웨어 파이프라인 관리자."""

    def __init__(self, mutators: Optional[List[PromptMutator]] = None) -> None:
        self.mutators = mutators if mutators is not None else [
            PoseTagPreparationMutator(),
            PositiveAssemblyMutator(),
            NegativeBaseMutator(),
            DefectDefenseMutator(),
            TwoPersonMobMutator(),
            CompositionAntiDriftMutator(),
            SanitizerMutator(),
        ]

    def execute(self, ctx: PromptContext) -> Tuple[str, str, bool]:
        for mutator in self.mutators:
            mutator.mutate(ctx)
        return ctx.positive_prompt, ctx.negative_prompt, ctx.nude


default_sdxl_pipeline = SDXLPromptPipeline()
