"""
plepa_engine.censor.silhouette_sam
단일 타겟 BBox의 SAM ROI 크롭 추론, 누수·과팽창 가드 적용, 손 분할 컴포넌트 선택 및 폴백 모듈.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

from ._runtime import facade_get, logger
from .geometry import _odd_kernel, _scale_int
from .mask_refinement import _build_oriented_core_guard, _build_rounded_box_guard, _classify_sam_mask_leak
from .models import _SAM_MODEL_LOCK, _extract_sam_mask_data
from .silhouette_prompts import _compute_hand_split_sub_boxes, _prepare_box_sam_prompts


def _decode_single_sam_point(
    *,
    sam: Any,
    crop_pil: Image.Image,
    crop_rect: Tuple[int, int, int, int],
    full_shape: Tuple[int, int],
    pt: List[int],
    target_box: Tuple[int, int, int, int],
    outer_box: Tuple[int, int, int, int],
    neg_in_crop: Sequence[List[int]],
    scale: float,
    margin: int,
    min_raw_pixels: int,
    has_yolo_prior: bool,
    item_prior_mask: Optional[np.ndarray],
    prior_area: int,
    envelope_mask: Optional[np.ndarray],
    split_active: bool,
    img_np: np.ndarray,
    eff_skin_np: np.ndarray,
    pose_cat: Optional[str],
    box_fill_thresh: float,
    core_minor_cap: float,
    guards_cache: Dict[str, Any],
) -> Optional[np.ndarray]:
    """단일 Positive 포인트에 대해 SAM 추론 후 누수·네모 과팽창·Envelope 가드를 적용합니다."""
    h, w = full_shape
    rx1, ry1, rx2, ry2 = crop_rect
    cw, ch = max(1, rx2 - rx1), max(1, ry2 - ry1)
    sx1, sy1, sx2, sy2 = target_box
    ex1, ey1, ex2, ey2 = outer_box

    local_bbox = [sx1 - rx1, sy1 - ry1, sx2 - rx1, sy2 - ry1]
    all_pts = [[pt[0] - rx1, pt[1] - ry1]] + list(neg_in_crop)
    all_lbls = [1] + [0] * len(neg_in_crop)
    sam_lock = facade_get("_SAM_MODEL_LOCK", _SAM_MODEL_LOCK)
    with sam_lock:
        try:
            results = sam(crop_pil, bboxes=[local_bbox], points=[all_pts], labels=[all_lbls], verbose=False)
        except Exception:
            results = sam(crop_pil, bboxes=[local_bbox], verbose=False)

    m_data = _extract_sam_mask_data(results)
    if m_data is None:
        return None

    crop_m = (m_data[0].astype(np.float32) * 255.0).clip(0, 255).astype(np.uint8)
    if crop_m.shape != (ch, cw):
        crop_m = cv2.resize(crop_m, (cw, ch), interpolation=cv2.INTER_NEAREST)
    raw_m = np.zeros((h, w), dtype=np.uint8)
    raw_m[ry1:ry2, rx1:rx2] = crop_m

    zone_rect_guards: Dict[Tuple[int, int, int, int], np.ndarray] = guards_cache["zone_rect_guards"]
    if target_box not in zone_rect_guards:
        zg = np.zeros((h, w), dtype=np.uint8)
        zg[max(0, sy1 - margin) : min(h, sy2 + margin), max(0, sx1 - margin) : min(w, sx2 + margin)] = 255
        zone_rect_guards[target_box] = zg
    sub_rect_guard = zone_rect_guards[target_box]

    cls_fn = facade_get("_classify_sam_mask_leak", _classify_sam_mask_leak)
    global_leak, blocky_leak = cls_fn(raw_m, sx1, sy1, sx2, sy2, rx1, ry1, rx2, ry2, box_fill_thresh=box_fill_thresh)
    if has_yolo_prior and item_prior_mask is not None and envelope_mask is not None:
        clamped_env = cv2.bitwise_and(raw_m, envelope_mask)
        if global_leak or blocky_leak or np.count_nonzero(clamped_env) < max(min_raw_pixels, int(prior_area * 0.25)):
            raw_m = cv2.bitwise_and(item_prior_mask, sub_rect_guard)
        else:
            raw_m = clamped_env
    elif global_leak:
        if guards_cache["outer_round_guard"] is None:
            guards_cache["outer_round_guard"] = _build_rounded_box_guard(w, h, ex1, ey1, ex2, ey2, scale, radius_ratio=0.30)
        org = guards_cache["outer_round_guard"]
        guard_mask = cv2.bitwise_and(sub_rect_guard, org) if split_active else org
        raw_m = cv2.bitwise_and(raw_m, guard_mask)
    elif blocky_leak:
        zone_core_guards: Dict[Tuple[int, int, int, int], np.ndarray] = guards_cache["zone_core_guards"]
        if target_box not in zone_core_guards:
            zone_core_guards[target_box] = _build_oriented_core_guard(
                w, h, sx1, sy1, sx2, sy2, scale,
                img_np=img_np, skin_np=eff_skin_np, pose_cat=pose_cat, minor_ratio_cap=core_minor_cap,
            )
        raw_m = cv2.bitwise_and(raw_m, zone_core_guards[target_box])
    else:
        raw_m = cv2.bitwise_and(raw_m, sub_rect_guard)

    return raw_m if np.count_nonzero(raw_m) >= min_raw_pixels else None


def _select_sam_components(
    sam_union: np.ndarray,
    full_shape: Tuple[int, int],
    box_shape: Tuple[int, int],
    scale: float,
    has_yolo_prior: bool,
    prior_area: int,
    split_active: bool,
    min_hy1: int,
    max_hy2: int,
    upper_pts: Sequence[List[int]],
    lower_pts: Sequence[List[int]],
) -> Tuple[np.ndarray, bool]:
    """`connectedComponentsWithStats`로 노이즈를 제거하고 손 분할 시 상·하단 독립 컴포넌트를 보존합니다."""
    h, w = full_shape
    ebw, ebh = box_shape
    sub_m = np.zeros((h, w), dtype=np.uint8)
    num_labels, labels_im, stats, centroids = cv2.connectedComponentsWithStats(sam_union, connectivity=8)
    if num_labels <= 1:
        return sub_m, False

    areas = stats[1:, cv2.CC_STAT_AREA]
    max_area = float(areas.max())
    base_noise = _scale_int(60, scale * scale, minimum=25)
    min_noise_area = max(64, base_noise) if split_active else base_noise
    min_cnt_area = max(min_noise_area, max_area * 0.15)
    keep_labels = {i for i in range(1, num_labels) if stats[i, cv2.CC_STAT_AREA] >= min_cnt_area}

    if split_active:
        for zone_pts, zone_fn in ((upper_pts, lambda cy: cy < max_hy2), (lower_pts, lambda cy: cy >= min_hy1)):
            best_lbl: Optional[int] = None
            best_score = -1.0
            for pt_z in zone_pts:
                patch = labels_im[max(0, pt_z[1] - 4):min(h, pt_z[1] + 5), max(0, pt_z[0] - 4):min(w, pt_z[0] + 5)]
                for lbl_hit in np.unique(patch):
                    if lbl_hit <= 0:
                        continue
                    area_val = float(stats[int(lbl_hit), cv2.CC_STAT_AREA])
                    if area_val >= min_noise_area and area_val > best_score:
                        best_score, best_lbl = area_val, int(lbl_hit)
            if best_lbl is None:
                best_dist, ref_pt = float("inf"), zone_pts[0]
                for lbl_idx in range(1, num_labels):
                    area_val = float(stats[lbl_idx, cv2.CC_STAT_AREA])
                    if area_val < min_noise_area:
                        continue
                    cx_c, cy_c = float(centroids[lbl_idx][0]), float(centroids[lbl_idx][1])
                    if not zone_fn(cy_c):
                        continue
                    dist = math.hypot(cx_c - ref_pt[0], cy_c - ref_pt[1])
                    if dist < best_dist:
                        best_dist, best_lbl = dist, lbl_idx
            if best_lbl is not None:
                keep_labels.add(best_lbl)

    for lbl_idx in sorted(keep_labels):
        sub_m[labels_im == lbl_idx] = 255
    min_accept_px = max(_scale_int(40, scale * scale, 16), int(prior_area * 0.25)) if has_yolo_prior else (ebw * ebh * 0.06)
    return sub_m, bool(np.count_nonzero(sub_m) >= min_accept_px)


def _fallback_box_mask(
    full_shape: Tuple[int, int],
    box: Tuple[int, int, int, int],
    scale: float,
    item_prior_mask: Optional[np.ndarray],
    hand_occ_mask: np.ndarray,
) -> np.ndarray:
    """SAM 실패 시 `item_prior_mask` 우선 폴백, 없으면 보수적 타원 캡슐 마스크를 반환합니다."""
    h, w = full_shape
    ex1, ey1, ex2, ey2 = box
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    sub_m = np.zeros((h, w), dtype=np.uint8)
    if item_prior_mask is not None:
        sub_m[ey1:ey2, ex1:ex2] = item_prior_mask[ey1:ey2, ex1:ex2]
        if np.count_nonzero(hand_occ_mask) > 0:
            sub_m = cv2.bitwise_and(sub_m, cv2.bitwise_not(hand_occ_mask))
    else:
        bcx, bcy = int((ex1 + ex2) / 2), int((ey1 + ey2) / 2)
        erx = min(int(w * 0.12), max(_scale_int(4, scale, 3), int(ebw * 0.42)))
        ery = min(int(h * 0.16), max(_scale_int(4, scale, 3), int(ebh * 0.48)))
        cv2.ellipse(sub_m, (bcx, bcy), (erx, ery), 0, 0, 360, 255, -1)
    return sub_m


def _segment_target_box_with_sam(
    *,
    rgb_img: Image.Image,
    img_np: np.ndarray,
    eff_skin_np: np.ndarray,
    sam: Any,
    box: Tuple[int, int, int, int],
    item_prior_mask: Optional[np.ndarray],
    item_context_box: Optional[Tuple[int, int, int, int]],
    face_neg_pts: Sequence[List[int]],
    detected_face_boxes: Sequence[Tuple[int, int, int, int]],
    detected_hand_boxes: Sequence[Tuple[int, int, int, int]],
    hand_occ_mask: np.ndarray,
    asym_thresh: float,
    scale: float,
    pose_cat: Optional[str],
) -> np.ndarray:
    """단일 성기 타겟 BBox를 SAM padded crop 추론 및 폴백을 통해 이진 마스크로 변환합니다."""
    h, w = img_np.shape[:2]
    ex1, ey1, ex2, ey2 = box
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    has_yolo_prior = item_prior_mask is not None
    prior_area = int(np.count_nonzero(item_prior_mask)) if has_yolo_prior else 0
    sub_m = np.zeros((h, w), dtype=np.uint8)
    sam_succeeded = False

    if sam is not None:
        try:
            box_hand_boxes = [
                (hx1, hy1, hx2, hy2)
                for hx1, hy1, hx2, hy2 in detected_hand_boxes
                if max(ex1, hx1) < min(ex2, hx2) and max(ey1, hy1) < min(ey2, hy2)
            ]
            pos_pts, local_neg_pts, envelope_mask, void_corner_mask = _prepare_box_sam_prompts(
                img_np, eff_skin_np, box, item_prior_mask, item_context_box,
                face_neg_pts, detected_face_boxes, box_hand_boxes, asym_thresh, scale,
            )
            split_active, min_hy1, max_hy2, upper_pts, lower_pts, upper_sub_bbox, lower_sub_bbox = (
                _compute_hand_split_sub_boxes(box, pos_pts, box_hand_boxes)
            )
            ctx_x1, ctx_y1, ctx_x2, ctx_y2 = [int(v) for v in item_context_box] if item_context_box is not None else [ex1, ey1, ex2, ey2]
            pad_x = max(_scale_int(64, scale, 32), int(ebw * 0.45))
            pad_y = max(_scale_int(64, scale, 32), int(ebh * 0.45))
            rx1, ry1 = max(0, min(ex1, ctx_x1) - pad_x), max(0, min(ey1, ctx_y1) - pad_y)
            rx2, ry2 = min(w, max(ex2, ctx_x2) + pad_x), min(h, max(ey2, ctx_y2) + pad_y)
            crop_pil = rgb_img.crop((rx1, ry1, rx2, ry2))
            neg_in_crop = [[px - rx1, py - ry1] for px, py in local_neg_pts if rx1 <= px < rx2 and ry1 <= py < ry2]
            min_raw_pixels = _scale_int(60, scale * scale, minimum=25)
            guards_cache: Dict[str, Any] = {"outer_round_guard": None, "zone_core_guards": {}, "zone_rect_guards": {}}
            sam_union = np.zeros((h, w), dtype=np.uint8)

            for pt in pos_pts:
                target_box = upper_sub_bbox if (split_active and pt[1] < min_hy1) else (lower_sub_bbox if (split_active and pt[1] > max_hy2) else box)
                decoded = _decode_single_sam_point(
                    sam=sam, crop_pil=crop_pil, crop_rect=(rx1, ry1, rx2, ry2), full_shape=(h, w),
                    pt=pt, target_box=target_box, outer_box=box, neg_in_crop=neg_in_crop, scale=scale,
                    margin=_scale_int(4, scale, minimum=2), min_raw_pixels=min_raw_pixels,
                    has_yolo_prior=has_yolo_prior, item_prior_mask=item_prior_mask, prior_area=prior_area,
                    envelope_mask=envelope_mask, split_active=split_active, img_np=img_np, eff_skin_np=eff_skin_np,
                    pose_cat=pose_cat, box_fill_thresh=0.52 if has_yolo_prior else 0.42,
                    core_minor_cap=0.36 if has_yolo_prior else 0.30, guards_cache=guards_cache,
                )
                if decoded is not None:
                    sam_union = np.maximum(sam_union, decoded)

            if np.count_nonzero(void_corner_mask) > 0:
                vk = _odd_kernel(21, scale)
                soft_void = cv2.GaussianBlur(void_corner_mask, (vk, vk), 6.0 * scale)
                void_weight = 1.0 - (soft_void.astype(np.float32) / 255.0)
                sam_union = np.clip(sam_union.astype(np.float32) * void_weight, 0, 255).astype(np.uint8)
                _, sam_union = cv2.threshold(sam_union, 127, 255, cv2.THRESH_BINARY)
            if np.count_nonzero(hand_occ_mask) > 0:
                sam_union = cv2.bitwise_and(sam_union, cv2.bitwise_not(hand_occ_mask))

            sub_m, sam_succeeded = _select_sam_components(
                sam_union, (h, w), (ebw, ebh), scale, has_yolo_prior, prior_area,
                split_active, min_hy1, max_hy2, upper_pts, lower_pts,
            )
        except Exception as e:
            logger.warning(f"[Censor] SAM 세그멘테이션 폴백: {e}")

    if not sam_succeeded:
        return _fallback_box_mask((h, w), box, scale, item_prior_mask if has_yolo_prior else None, hand_occ_mask)
    return sub_m
