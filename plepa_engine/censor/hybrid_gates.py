"""
plepa_engine.censor.hybrid_gates
Phase P2/P2.5 YOLO-seg & DeepGHS 합의 매칭, Case A 구제 및 Case B1/B2 하단 오탐 게이트 모듈.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from ._runtime import logger
from .geometry import _box_iomin, _box_iou, _has_hand_between_boxes
from .models import _render_seg_items_mask


def _primary_rank(cand: Tuple[Tuple[int, int, int, int], str, float]) -> Tuple[float, int]:
    """주 후보(Primary) 선정용 `(신뢰도, 박스 면적)` 순위 키를 반환합니다."""
    bx = cand[0]
    return (float(cand[2]), max(0, bx[2] - bx[0]) * max(0, bx[3] - bx[1]))


def _passes_case_a_rescue(
    item: Tuple[Tuple[int, int, int, int], str, float, np.ndarray],
    has_existing: bool,
    eff_skin: np.ndarray,
    img_h: int,
) -> bool:
    """Case A(DeepGHS 미탐 시 YOLO 구제 및 독립 타겟 구제) 통과 여부를 판정합니다."""
    s_box_c, _, s_score_c, _ = item
    min_r = 0.40 if has_existing else 0.19
    if float(s_score_c) < min_r:
        return False
    if not has_existing and 0.19 <= float(s_score_c) < 0.25:
        sx1, sy1, sx2, sy2 = [int(v) for v in s_box_c]
        s_area = max(0, sx2 - sx1) * max(0, sy2 - sy1)
        if s_area < 900:
            return False
        roi_sk = eff_skin[max(0, sy1):min(img_h, sy2), max(0, sx1):min(eff_skin.shape[1], sx2)]
        skin_ratio = float(np.count_nonzero(roi_sk)) / float(max(1, roi_sk.size))
        if skin_ratio < 0.12:
            return False
    return True


def _should_reject_lower_secondary(
    *,
    d_box: Tuple[int, int, int, int],
    d_score: float,
    primary_box: Tuple[int, int, int, int],
    primary_score: float,
    primary_yc: float,
    primary_h: int,
    deep_cands: Sequence[Tuple[Tuple[int, int, int, int], str, float]],
    seg_items: Sequence[Tuple[Tuple[int, int, int, int], str, float, np.ndarray]],
    seg_confirmed_any: bool,
    max_matched_yolo: float,
    eff_skin: np.ndarray,
    img_w: int,
    img_h: int,
    get_hands_fn: Callable[[], List[Tuple[int, int, int, int]]],
) -> bool:
    """Case B1(고립 하단 오탐 Dual Gate) 및 Case B2(손 미분할 인접 하단 Echo) 기각 여부를 판정합니다."""
    dx1, dy1, dx2, dy2 = [int(v) for v in d_box]
    d_yc = (dy1 + dy2) * 0.5
    y2_ratio = float(dy2) / float(max(1, img_h))
    is_isolated = len(deep_cands) >= 2 and d_box != primary_box and _box_iou(d_box, primary_box) == 0.0

    # Case B1: P1 기존 하단 고립 오탐 게이트
    if is_isolated and d_yc > (img_h * 0.68):
        roi_sk = eff_skin[max(0, dy1):min(img_h, dy2), max(0, dx1):min(img_w, dx2)]
        skin_ratio = float(np.count_nonzero(roi_sk)) / float(max(1, roi_sk.size))
        if (
            (seg_confirmed_any and (skin_ratio >= 0.35 or float(d_score) < 0.28))
            or (
                not seg_items
                and float(d_score) < 0.22
                and primary_score >= float(d_score) + 0.06
                and skin_ratio >= 0.35
            )
        ):
            logger.debug(
                f"[Censor] Dual Gate 하단 2차 오탐 기각: box={d_box}, score={d_score:.2f}, skin={skin_ratio:.2f}"
            )
            return True

    # Case B2 (P2): 상단 Primary 아래 인접 하단 2차 박스 중 손 분할이 아니고 YOLO 확신도 < 0.58인 체액/접합 Echo 기각
    is_adjacent_lower = (
        len(deep_cands) >= 2
        and d_box != primary_box
        and _box_iou(d_box, primary_box) < 0.25
        and d_yc > primary_yc + max(20.0, primary_h * 0.25)
        and (y2_ratio > 0.82 or dy1 >= primary_box[3] - max(24, int(primary_h * 0.25)))
    )
    if is_adjacent_lower:
        hands_list = get_hands_fn()
        if not _has_hand_between_boxes(primary_box, d_box, hands_list) and max_matched_yolo < 0.58:
            logger.debug(
                f"[Censor] P2 인접 하단 Echo 오탐 기각: box={d_box}, deep={d_score:.2f}, yolo={max_matched_yolo:.2f}"
            )
            return True
    return False


def _is_valid_prior_match(
    d_box: Tuple[int, int, int, int],
    d_area: int,
    it: Tuple[Tuple[int, int, int, int], str, float, np.ndarray],
) -> bool:
    """DeepGHS 박스와 YOLO-seg prior 항목 간의 유효 매칭 여부를 판정합니다 (경계 파편·외곽 이탈 배제)."""
    dx1, dy1, dx2, dy2 = [int(v) for v in d_box]
    s_bx, _, s_sc, _ = it
    sc = float(s_sc)
    if not (sc >= 0.32 or (sc >= 0.22 and _box_iomin(d_box, s_bx) >= 0.20)):
        return False
    sx1, sy1, sx2, sy2 = [int(v) for v in s_bx]
    s_area = max(1, (sx2 - sx1) * (sy2 - sy1))
    inter_area = max(0, min(dx2, sx2) - max(dx1, sx1)) * max(0, min(dy2, sy2) - max(dy1, sy1))
    if (float(inter_area) / float(d_area)) < 0.06 and sc < 0.55:
        return False
    s_cx, s_cy = (sx1 + sx2) * 0.5, (sy1 + sy2) * 0.5
    center_inside = (dx1 <= s_cx <= dx2) and (dy1 <= s_cy <= dy2)
    if not center_inside and (float(inter_area) / float(s_area)) < 0.55 and sc < 0.60:
        return False
    return True


def _apply_case_a_rescue(
    seg_items: Sequence[Tuple[Tuple[int, int, int, int], str, float, np.ndarray]],
    consumed_seg_indices: set[int],
    final_boxes: List[Tuple[Tuple[int, int, int, int], str, float]],
    final_priors: List[Optional[np.ndarray]],
    final_contexts: List[Optional[Tuple[int, int, int, int]]],
    eff_skin: np.ndarray,
    img_w: int,
    img_h: int,
    get_hands_fn: Callable[[], List[Tuple[int, int, int, int]]],
) -> None:
    """DeepGHS가 놓친 독립 타겟을 YOLO-seg 합의로 추가 구제합니다."""
    for idx, it in enumerate(seg_items):
        if idx in consumed_seg_indices:
            continue
        s_box, s_lbl, s_score, _ = it
        if not _passes_case_a_rescue(it, has_existing=bool(final_boxes), eff_skin=eff_skin, img_h=img_h):
            continue
        if any(_box_iou(s_box, f_box) >= 0.12 or _box_iomin(s_box, f_box) >= 0.22 for f_box, _, _ in final_boxes):
            continue
        if final_boxes:
            top_primary = max(final_boxes, key=_primary_rank)[0]
            tp_yc = (top_primary[1] + top_primary[3]) * 0.5
            s_yc = (s_box[1] + s_box[3]) * 0.5
            if float(s_yc) < (float(img_h) * 0.14) and float(s_score) < 0.65:
                continue
            s_y2r = float(s_box[3]) / float(max(1, img_h))
            if (
                s_yc > tp_yc + 20.0
                and s_y2r > 0.82
                and float(s_score) < 0.58
                and not _has_hand_between_boxes(top_primary, s_box, get_hands_fn())
            ):
                continue

        prior_mask = _render_seg_items_mask(img_w, img_h, [it])
        final_boxes.append((s_box, str(s_lbl), float(s_score)))
        final_priors.append(prior_mask)
        final_contexts.append(None)
