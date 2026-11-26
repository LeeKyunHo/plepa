"""
plepa_engine.pipeline.mob_helpers
2인 인터랙티브/모브 제어용 공통 네거티브 빌더, 시선 방향 억제, 인라인 파트너 주입 헬퍼 모듈.
"""

from __future__ import annotations

from typing import Optional

from plepa_engine.pipeline.constants import _PARTNER_POS_SPECS
from plepa_engine.pipeline.context import PromptContext


def _build_common_interactive_negative_guard(ctx: PromptContext, is_multi_partner: bool = False) -> str:
    """2인 이상 인터랙티브 씬 공통 다인·사지·두부 왜곡 억제 네거티브 블록을 생성합니다."""
    if is_multi_partner:
        multi_male_guard = ""
    elif ctx.is_otokonoko:
        multi_male_guard = (
            "(3boys:1.6), (multiple boys:1.6), (three men:1.6), (extra male:1.6), "
            "(group:1.5), (threesome:1.5), (duplicate male:1.5), (two male partners:1.5), (multiple partners:1.5), "
        )
    else:
        multi_male_guard = (
            "(2boys:1.6), (multiple boys:1.6), (two men:1.6), (extra male:1.6), "
            "(group:1.5), (threesome:1.5), (duplicate male:1.5), (two male partners:1.5), (second man:1.5), (multiple partners:1.5), "
        )
    limb_guard = (
        "(extra hands:1.45), (multiple hands:1.45), (extra arms:1.45), (multiple arms:1.45), "
        "(three hands:1.45), (four hands:1.45), (duplicate hands:1.45), (duplicate arms:1.45), "
        "(extra limbs:1.4), (fused hands:1.4), (poorly drawn hands:1.4), "
    )
    return (
        f"(severed head:1.4), (decapitation:1.4), (headless:1.4), (floating head:1.4), (disembodied head:1.4), "
        f"(multiple heads:1.35), (two heads:1.35), (2girls:1.35), (multiple girls:1.35), (extra girl:1.35), "
        f"(two girls:1.35), (duplicate:1.35), (reaction face:1.35), (inset:1.35), "
        f"{multi_male_guard}{limb_guard}(extra head:1.35), own hand on face, own hand on chin, "
        f"resting chin on hand, holding own chin, touching own face, touching own chin, "
        f"hand on own face, hand on own chin, gloves, orange skin, "
        f"(pitch black shadow on body:1.25), (burnt skin:1.25)"
    )


def _apply_gaze_direction_negatives(pose_tag: str, neg: str) -> str:
    """파트너 응시 또는 시선 하향 포즈에서 카메라 직시 드리프트를 억제합니다."""
    pose_low = pose_tag.lower()
    if any(kw in pose_low for kw in ("looking at partner", "look at partner", "eye contact with partner", "facing partner", "towards partner")):
        neg = f"{neg}, looking at viewer, looking straight at camera"
    if any(kw in pose_low for kw in ("looking down", "head tilted down", "downcast eyes", "head down")):
        neg = f"{neg}, looking at viewer, looking straight at camera"
    return neg


def _inject_partner_pos_inline(pos: str, partner_pos: Optional[str], pose_tag: str = "") -> str:
    """2인 구도 시 범용 BREAK 대신 첫 청크 후미(BREAK 앞)에 방향성 파트너 엣지 크롭 태그를 인라인 주입한다."""
    pose_low = (pose_tag or "").lower()
    if partner_pos == "side_kiss" and any(kw in pose_low for kw in ("kiss", "french kiss")):
        tags = (
            "over-the-shoulder angle from behind dark-haired male partner, "
            "cropped dark-haired male jaw and lips at extreme frame edge, "
            "male upper face turned away in deep shadow, male eyes out of frame, partner arms around waist"
        )
    else:
        tags = _PARTNER_POS_SPECS.get(partner_pos or "", "partner head out of frame, cropped male shoulders at frame edge")
    if not tags:
        return pos
    if " BREAK " in pos:
        head, tail = pos.split(" BREAK ", 1)
        return f"{head}, {tags} BREAK {tail}"
    return f"{pos}, {tags}"
