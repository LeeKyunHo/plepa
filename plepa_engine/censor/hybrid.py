"""
plepa_engine.censor.hybrid
Phase P2 Semantic-Guided Hybrid Gating 및 Residual Span 2-Way(Hand-Split / Union Span) 복원 모듈.
"""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image

from ._runtime import HAS_IMGUTILS, facade_get
from .constants import _normalize_censor_targets
from .detection import _detect_target_candidates
from .geometry import _box_iomin, _box_iou, _has_hand_between_boxes, get_skin_mask
from .hybrid_gates import (
    _apply_case_a_rescue,
    _is_valid_prior_match,
    _passes_case_a_rescue,
    _primary_rank,
    _should_reject_lower_secondary,
)
from .models import _infer_custom_censor_seg_items, _render_seg_items_mask, get_custom_censor_seg_model


def _merged_span(segs_rng: List[Tuple[int, int]]) -> int:
    """1차원 구간 리스트를 병합해 전체 덮임 길이를 반환합니다."""
    valid = sorted((a, b) for a, b in segs_rng if b > a)
    if not valid:
        return 0
    total_len = 0
    cur_a, cur_b = valid[0]
    for na, nb in valid[1:]:
        if na <= cur_b:
            cur_b = max(cur_b, nb)
        else:
            total_len += cur_b - cur_a
            cur_a, cur_b = na, nb
    return total_len + (cur_b - cur_a)


def _detect_hands_boxes(img_rgb: Image.Image) -> List[Tuple[int, int, int, int]]:
    """`imgutils.detect.detect_hands`로 전경 손 BBox 목록을 안전하게 추출합니다."""
    hands: List[Tuple[int, int, int, int]] = []
    if not facade_get("HAS_IMGUTILS", HAS_IMGUTILS):
        return hands
    try:
        from imgutils.detect import detect_hands
        for h_it in detect_hands(img_rgb, conf_threshold=0.45):
            hb = h_it[0] if isinstance(h_it, (tuple, list)) and len(h_it) >= 3 else h_it
            if isinstance(hb, (tuple, list)) and len(hb) >= 4:
                hands.append((int(hb[0]), int(hb[1]), int(hb[2]), int(hb[3])))
    except Exception:
        pass
    return hands


def _resolve_matched_prior_cluster(
    cand_segs: Sequence[Tuple[int, Tuple[Tuple[int, int, int, int], str, float, np.ndarray]]],
    d_box: Tuple[int, int, int, int],
    d_lbl: str,
    d_score: float,
    img_w: int,
    img_h: int,
    get_hands_fn: Callable[[], List[Tuple[int, int, int, int]]],
    final_boxes: List[Tuple[Tuple[int, int, int, int], str, float]],
    final_priors: List[Optional[np.ndarray]],
    final_contexts: List[Optional[Tuple[int, int, int, int]]],
) -> None:
    """매칭된 YOLO-seg 클러스터의 덮임 비율을 평가해 직결 유지 / 분기 A(Hand-Split) / 분기 B(Union Span)를 결정합니다."""
    dx1, dy1, dx2, dy2 = [int(v) for v in d_box]
    dghs_w, dghs_h = max(1, dx2 - dx1), max(1, dy2 - dy1)

    cov_y = _merged_span([(max(dy1, it[0][1]), min(dy2, it[0][3])) for _, it in cand_segs])
    cov_y_ratio = float(cov_y) / float(dghs_h)
    min_sx1 = min(int(it[0][0]) for _, it in cand_segs)
    min_sy1 = min(int(it[0][1]) for _, it in cand_segs)
    max_sx2 = max(int(it[0][2]) for _, it in cand_segs)
    max_sy2 = max(int(it[0][3]) for _, it in cand_segs)
    top_res, bot_res = max(0, min_sy1 - dy1), max(0, dy2 - max_sy2)
    y_res_thresh = max(75, int(round(dghs_h * 0.35)))

    cov_x = _merged_span([(max(dx1, it[0][0]), min(dx2, it[0][2])) for _, it in cand_segs])
    cov_x_ratio = float(cov_x) / float(dghs_w)
    x_res_thresh = max(75, int(round(dghs_w * 0.35)))
    lat_res = max(max(0, min_sx1 - dx1), max(0, dx2 - max_sx2))

    is_under_covered = (
        cov_y_ratio < 0.62
        or top_res >= y_res_thresh
        or bot_res >= y_res_thresh
        or (dghs_w >= dghs_h * 0.70 and (cov_x_ratio < 0.62 or lat_res >= x_res_thresh))
    )

    if not is_under_covered:
        for _, it in cand_segs:
            s_box, s_lbl, s_score, _ = it
            final_boxes.append((s_box, str(s_lbl), max(float(s_score), float(d_score))))
            final_priors.append(_render_seg_items_mask(img_w, img_h, [it]))
            final_contexts.append(d_box)
        return

    hands_list = get_hands_fn()
    yolo_union = (min_sx1, min_sy1, max_sx2, max_sy2)

    def _find_crossing_hand(sub_box: Tuple[int, int, int, int]) -> Optional[Tuple[int, int, int, int]]:
        return next((hb for hb in hands_list if _has_hand_between_boxes(yolo_union, sub_box, [hb])), None)

    bot_cand = (dx1, max_sy2, dx2, dy2) if bot_res >= max(50, int(round(dghs_h * 0.25))) else None
    top_cand = (dx1, dy1, dx2, min_sy1) if top_res >= max(50, int(round(dghs_h * 0.25))) else None
    cross_bot = _find_crossing_hand(bot_cand) if bot_cand is not None else None
    cross_top = _find_crossing_hand(top_cand) if top_cand is not None else None

    if cross_bot is not None or cross_top is not None:
        left_uncov, right_uncov = max(0, min_sx1 - dx1), max(0, dx2 - max_sx2)
        res_x1, res_x2 = dx1, dx2
        if left_uncov >= max(45, right_uncov * 2):
            res_x2 = min(dx2, min_sx1 + max(38, int(round(left_uncov * 0.33))))
        elif right_uncov >= max(45, left_uncov * 2):
            res_x1 = max(dx1, max_sx2 - max(38, int(round(right_uncov * 0.33))))

        for _, it in cand_segs:
            s_box, s_lbl, s_score, _ = it
            final_boxes.append((s_box, str(s_lbl), max(float(s_score), float(d_score))))
            final_priors.append(_render_seg_items_mask(img_w, img_h, [it]))
            final_contexts.append(d_box)
        if cross_bot is not None and bot_cand is not None:
            res_y1 = max(max_sy2, int(cross_bot[1]))
            if res_y1 >= dy2 - 24:
                res_y1 = max_sy2
            if dy2 - res_y1 >= 24 and res_x2 - res_x1 >= 24:
                final_boxes.append(((res_x1, res_y1, res_x2, dy2), str(d_lbl), float(d_score)))
                final_priors.append(None)
                final_contexts.append(None)
        if cross_top is not None and top_cand is not None:
            res_y2 = min(min_sy1, int(cross_top[3]))
            if res_y2 <= dy1 + 24:
                res_y2 = min_sy1
            if res_y2 - dy1 >= 24 and res_x2 - res_x1 >= 24:
                final_boxes.append(((res_x1, dy1, res_x2, res_y2), str(d_lbl), float(d_score)))
                final_priors.append(None)
                final_contexts.append(None)
    else:
        union_box = (max(0, min(dx1, min_sx1)), max(0, min(dy1, min_sy1)), min(img_w, max(dx2, max_sx2)), min(img_h, max(dy2, max_sy2)))
        merged_prior = _render_seg_items_mask(img_w, img_h, [it for _, it in cand_segs])
        merged_score = max([float(d_score)] + [float(it[2]) for _, it in cand_segs])
        final_boxes.append((union_box, str(d_lbl), merged_score))
        final_priors.append(merged_prior)
        final_contexts.append(d_box)


def _resolve_hybrid_targets_with_priors(
    img_rgb: Image.Image,
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.16,
    pose_code: Optional[Union[str, int]] = None,
    roster: Optional[str] = None,
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    hand_boxes: Optional[Sequence[Tuple[int, int, int, int]]] = None,
) -> Tuple[
    List[Tuple[Tuple[int, int, int, int], str, float]],
    Optional[np.ndarray],
    Optional[List[Tuple[Tuple[int, int, int, int], str, float]]],
    Optional[List[Optional[np.ndarray]]],
    Optional[List[Optional[Tuple[int, int, int, int]]]],
]:
    """
    Phase P2 Semantic-Guided Hybrid Gating:
    - 초고신뢰(>=0.92) YOLO-seg 모의/극고신뢰 구간을 제외하고 0.85 장벽을 철폐.
    - YOLO-seg가 검출한 타겟(conf>=0.32 또는 IoMin>=0.20 & conf>=0.22)은 DeepGHS 통합 박스를
      YOLO의 타이트한 분리 박스로 대체하고, yolo_prior_mask + DeepGHS context_box를 SAM 2.1로 투영.
    - 손 BBox가 사이에 없는 인접 하단 2차 박스는 yolo_conf >= 0.58 미달 시 하단 접합/체액 오탐으로 기각.
    """
    custom_seg_model = facade_get("get_custom_censor_seg_model", get_custom_censor_seg_model)()
    detect_cand_fn = facade_get("_detect_target_candidates", _detect_target_candidates)
    if custom_seg_model is None:
        deep_cands = detect_cand_fn(
            img_rgb, targets=targets, min_confidence=min_confidence, pose_code=pose_code,
            roster=roster, skin_np=skin_np, pose_cat=pose_cat,
        )
        return deep_cands, None, None, None, None

    w, h = img_rgb.size
    eff_min_conf = float(min_confidence)
    norm_targets = _normalize_censor_targets(targets)
    skin_fn = facade_get("get_skin_mask", get_skin_mask)
    eff_skin = skin_np if skin_np is not None else skin_fn(np.array(img_rgb, dtype=np.uint8))

    infer_items_fn = facade_get("_infer_custom_censor_seg_items", _infer_custom_censor_seg_items)
    seg_items_all = infer_items_fn(img_rgb, custom_seg_model, min_confidence=eff_min_conf, skin_np=eff_skin)
    seg_items = [item for item in seg_items_all if item[1] in norm_targets and float(item[2]) >= eff_min_conf]

    # 극고신뢰(>=0.92) 직결 Fast Path (모조/고신뢰 단위 테스트 호환 유지, 0.85 장벽 제거)
    fast_path_conf = float(os.environ.get("PLEPA_YOLO_FASTPATH_CONF", "0.92"))
    if any(float(item[2]) >= fast_path_conf for item in seg_items):
        selected_seg = [item for item in seg_items if float(item[2]) >= 0.25]
        seg_mask = _render_seg_items_mask(w, h, selected_seg)
        return [(item[0], item[1], float(item[2])) for item in selected_seg], seg_mask, [], None, None

    deep_cands = detect_cand_fn(
        img_rgb, targets=targets, min_confidence=min_confidence, pose_code=pose_code,
        roster=roster, skin_np=eff_skin, pose_cat=pose_cat,
    )
    if not deep_cands:
        rescue_items = [it for it in seg_items if _passes_case_a_rescue(it, False, eff_skin, h)]
        if rescue_items:
            rescue_boxes = [(it[0], it[1], float(it[2])) for it in rescue_items]
            rescue_priors = [_render_seg_items_mask(w, h, [it]) for it in rescue_items]
            return rescue_boxes, None, list(rescue_boxes), rescue_priors, [None] * len(rescue_items)
        return [], None, None, None, None

    primary_cand = max(deep_cands, key=_primary_rank)
    primary_box, _, primary_score = primary_cand[0], primary_cand[1], float(primary_cand[2])
    primary_yc, primary_h = (primary_box[1] + primary_box[3]) * 0.5, max(1, primary_box[3] - primary_box[1])
    seg_confirmed_any = any(float(it[2]) >= 0.20 and ((it[0][1] + it[0][3]) * 0.5) >= (h * 0.14) for it in seg_items)

    cached_hands: Optional[List[Tuple[int, int, int, int]]] = list(hand_boxes) if hand_boxes is not None else None

    def _get_hands_lazy() -> List[Tuple[int, int, int, int]]:
        nonlocal cached_hands
        if cached_hands is None:
            cached_hands = _detect_hands_boxes(img_rgb)
        return cached_hands

    final_boxes: List[Tuple[Tuple[int, int, int, int], str, float]] = []
    final_priors: List[Optional[np.ndarray]] = []
    final_contexts: List[Optional[Tuple[int, int, int, int]]] = []
    consumed_seg_indices: set[int] = set()

    for d_box, d_lbl, d_score in deep_cands:
        matched_indexed = [(i, it) for i, it in enumerate(seg_items) if _box_iou(d_box, it[0]) >= 0.15 or _box_iomin(d_box, it[0]) >= 0.25]
        max_matched_yolo = max((float(it[2]) for _, it in matched_indexed), default=0.0)
        if _should_reject_lower_secondary(
            d_box=d_box, d_score=float(d_score), primary_box=primary_box, primary_score=primary_score,
            primary_yc=primary_yc, primary_h=primary_h, deep_cands=deep_cands, seg_items=seg_items,
            seg_confirmed_any=seg_confirmed_any, max_matched_yolo=max_matched_yolo,
            eff_skin=eff_skin, img_w=w, img_h=h, get_hands_fn=_get_hands_lazy,
        ):
            continue

        d_area = max(1, (int(d_box[2]) - int(d_box[0])) * (int(d_box[3]) - int(d_box[1])))
        cand_segs: List[Tuple[int, Any]] = []
        for idx, it in matched_indexed:
            if idx in consumed_seg_indices or not _is_valid_prior_match(d_box, d_area, it):
                continue
            if any(_box_iou(it[0], fb[0]) >= 0.45 for fb in final_boxes) or any(_box_iou(it[0], p[0]) >= 0.45 for _, p in cand_segs):
                continue
            cand_segs.append((idx, it))

        if cand_segs:
            for idx, _ in cand_segs:
                consumed_seg_indices.add(idx)
            _resolve_matched_prior_cluster(
                cand_segs, d_box, d_lbl, float(d_score), w, h, _get_hands_lazy, final_boxes, final_priors, final_contexts
            )
        else:
            final_boxes.append((d_box, str(d_lbl), float(d_score)))
            final_priors.append(None)
            final_contexts.append(None)

    _apply_case_a_rescue(
        seg_items, consumed_seg_indices, final_boxes, final_priors, final_contexts, eff_skin, w, h, _get_hands_lazy
    )
    return final_boxes, None, list(final_boxes), final_priors, final_contexts


def _resolve_hybrid_targets_and_mask(
    img_rgb: Image.Image,
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.16,
    pose_code: Optional[Union[str, int]] = None,
    roster: Optional[str] = None,
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
) -> Tuple[
    List[Tuple[Tuple[int, int, int, int], str, float]],
    Optional[np.ndarray],
    Optional[List[Tuple[Tuple[int, int, int, int], str, float]]],
]:
    """기존 3-튜플 시그니처 호환용 래퍼."""
    resolve_fn = facade_get("_resolve_hybrid_targets_with_priors", _resolve_hybrid_targets_with_priors)
    final_boxes, seg_mask, fallback_boxes, _, _ = resolve_fn(
        img_rgb,
        targets=targets,
        min_confidence=min_confidence,
        pose_code=pose_code,
        roster=roster,
        skin_np=skin_np,
        pose_cat=pose_cat,
    )
    return final_boxes, seg_mask, fallback_boxes
