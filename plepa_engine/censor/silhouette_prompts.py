"""
plepa_engine.censor.silhouette_prompts
YOLO prior 유무에 따른 SAM 박스별 Positive/Negative 포인트 샘플링 및 손 분할 Sub-BBox 판정 모듈.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ._runtime import facade_get
from .protection import _compute_mutually_exclusive_prompts
from .segmentation import _extract_semantic_sam_prompts


def _extract_heuristic_sam_prompts(
    roi_hsv: np.ndarray,
    roi_skin: np.ndarray,
    eff_skin_bool: np.ndarray,
    box: Tuple[int, int, int, int],
    box_hand_boxes: Sequence[Tuple[int, int, int, int]],
    detected_face_boxes: Sequence[Tuple[int, int, int, int]],
    asym_thresh: float,
    img_w: int,
    img_h: int,
) -> Tuple[List[List[int]], List[List[int]], np.ndarray]:
    """YOLO prior 미존재 시 ROI 상·하단 피부 색상 분포 및 손·턱 위치를 바탕으로 SAM 프롬프트를 산출합니다."""
    ex1, ey1, ex2, ey2 = box
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    pos_pts: List[List[int]] = []
    neg_pts: List[List[int]] = []
    void_corner_mask = np.zeros((img_h, img_w), dtype=np.uint8)

    mid_y_l = int(ebh * 0.50)
    mid_x_l = int(ebw * 0.50)
    left_bot_hsv = roi_hsv[mid_y_l:, :mid_x_l]
    right_bot_hsv = roi_hsv[mid_y_l:, mid_x_l:]

    top_skin = roi_skin[int(ebh * 0.12):int(ebh * 0.48), :]
    top_h_med = (
        float(np.median(roi_hsv[int(ebh * 0.12):int(ebh * 0.48), :, 0][top_skin]))
        if np.count_nonzero(top_skin) >= 20
        else 11.0
    )

    def _side_target_score(sub_hsv: np.ndarray, sub_sk: np.ndarray) -> float:
        if sub_hsv.size == 0:
            return 0.0
        h_d = np.minimum(
            np.abs(sub_hsv[:, :, 0].astype(np.float32) - top_h_med),
            180.0 - np.abs(sub_hsv[:, :, 0].astype(np.float32) - top_h_med),
        )
        valid = sub_sk & (h_d <= 9.5)
        return float(np.count_nonzero(valid)) / float(max(1, sub_sk.size))

    l_score = _side_target_score(left_bot_hsv, roi_skin[mid_y_l:, :mid_x_l])
    r_score = _side_target_score(right_bot_hsv, roi_skin[mid_y_l:, mid_x_l:])

    # 반대쪽 비타겟 허공 코너는 실제 피부 비율이 뚜렷이 낮을 때(<0.22)만 제한적 감산
    if l_score > r_score * asym_thresh:
        cand_bot = [int(ex1 + ebw * 0.24), int(ey1 + ebh * 0.72)]
        neg_pts.append([int(ex1 + ebw * 0.76), int(ey1 + ebh * 0.78)])
        if r_score < 0.22:
            cv2.rectangle(void_corner_mask, (int(ex1 + ebw * 0.48), int(ey1 + ebh * 0.50)), (ex2, ey2), 255, -1)
    elif r_score > l_score * asym_thresh:
        cand_bot = [int(ex1 + ebw * 0.76), int(ey1 + ebh * 0.72)]
        neg_pts.append([int(ex1 + ebw * 0.24), int(ey1 + ebh * 0.78)])
        if l_score < 0.22:
            cv2.rectangle(void_corner_mask, (ex1, int(ey1 + ebh * 0.50)), (int(ex1 + ebw * 0.52), ey2), 255, -1)
    else:
        cand_bot = [int((ex1 + ex2) / 2), int(ey1 + ebh * 0.68)]

    def _in_hands(px: int, py: int) -> bool:
        return any(hx1 <= px <= hx2 and hy1 <= py <= hy2 for hx1, hy1, hx2, hy2 in box_hand_boxes)

    if box_hand_boxes:
        unocc_pts, hand_neg_pts = _compute_mutually_exclusive_prompts(box, box_hand_boxes, eff_skin_bool)
        for hpt in hand_neg_pts:
            if hpt not in neg_pts:
                neg_pts.append(hpt)
        for upt in unocc_pts:
            if not _in_hands(upt[0], upt[1]) and upt not in pos_pts:
                pos_pts.append(upt)
        if not _in_hands(cand_bot[0], cand_bot[1]) and cand_bot not in pos_pts:
            pos_pts.append(cand_bot)
    else:
        top_ys, top_xs = np.where(top_skin)
        if len(top_xs) >= 10:
            pos_pts.append([ex1 + int(np.median(top_xs)), ey1 + int(ebh * 0.12) + int(np.median(top_ys))])
        else:
            pos_pts.append([int((ex1 + ex2) / 2), int(ey1 + ebh * 0.30)])
        pos_pts.append(cand_bot)

    # YOLO 미탐 DeepGHS 단독 박스에 인접한 뺨/턱(타겟 바깥쪽)이 겹치면 안전 네거티브 추가
    tcx = (ex1 + ex2) * 0.5
    for fx1_i, fy1_i, fx2_i, fy2_i in detected_face_boxes:
        fw_f, fh_f = max(1, fx2_i - fx1_i), max(1, fy2_i - fy1_i)
        fcx_f = (fx1_i + fx2_i) * 0.5
        far_x = int(fx2_i - fw_f * 0.25) if fcx_f >= tcx else int(fx1_i + fw_f * 0.25)
        jaw_pt = [far_x, int(fy1_i + fh_f * 0.58)]
        if not (ex1 <= jaw_pt[0] <= ex2 and ey1 <= jaw_pt[1] <= ey2) and jaw_pt not in neg_pts:
            neg_pts.append(jaw_pt)

    return pos_pts, neg_pts, void_corner_mask


def _prepare_box_sam_prompts(
    img_np: np.ndarray,
    eff_skin_np: np.ndarray,
    box: Tuple[int, int, int, int],
    item_prior_mask: Optional[np.ndarray],
    item_context_box: Optional[Tuple[int, int, int, int]],
    face_neg_pts: Sequence[List[int]],
    detected_face_boxes: Sequence[Tuple[int, int, int, int]],
    box_hand_boxes: Sequence[Tuple[int, int, int, int]],
    asym_thresh: float,
    scale: float,
) -> Tuple[List[List[int]], List[List[int]], Optional[np.ndarray], np.ndarray]:
    """단일 타겟 BBox용 SAM Positive/Negative 포인트 및 Semantic Envelope·Void 코너 가드를 준비합니다."""
    ex1, ey1, ex2, ey2 = box
    ebh = max(1, ey2 - ey1)
    h, w = img_np.shape[:2]
    roi_rgb = img_np[ey1:ey2, ex1:ex2]
    roi_hsv = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2HSV)
    eff_skin_bool = eff_skin_np > 0
    roi_skin = eff_skin_bool[ey1:ey2, ex1:ex2]

    pos_pts: List[List[int]] = []
    local_neg_pts: List[List[int]] = list(face_neg_pts)
    envelope_mask: Optional[np.ndarray] = None
    void_corner_mask = np.zeros((h, w), dtype=np.uint8)

    if item_prior_mask is not None:
        sem_fn = facade_get("_extract_semantic_sam_prompts", _extract_semantic_sam_prompts)
        sem_pos, sem_neg, envelope_mask = sem_fn(
            item_prior_mask, box, item_context_box, eff_skin_bool, box_hand_boxes, scale
        )
        pos_pts.extend(sem_pos)
        for npt in sem_neg:
            if npt not in local_neg_pts:
                local_neg_pts.append(npt)
        if box_hand_boxes:
            _, hand_neg_pts = _compute_mutually_exclusive_prompts(box, box_hand_boxes, eff_skin_bool)
            for hpt in hand_neg_pts:
                if hpt not in local_neg_pts:
                    local_neg_pts.append(hpt)
        if not pos_pts:
            pys, pxs = np.nonzero(item_prior_mask[ey1:ey2, ex1:ex2])
            if len(pxs) > 0:
                pos_pts.append([ex1 + int(np.median(pxs)), ey1 + int(np.median(pys))])
    else:
        h_pos, h_neg, void_corner_mask = _extract_heuristic_sam_prompts(
            roi_hsv, roi_skin, eff_skin_bool, box, box_hand_boxes, detected_face_boxes, asym_thresh, w, h
        )
        pos_pts.extend(h_pos)
        for npt in h_neg:
            if npt not in local_neg_pts:
                local_neg_pts.append(npt)

    if not pos_pts:
        pos_pts.append([int((ex1 + ex2) / 2), int(ey1 + ebh * 0.22)])

    return pos_pts, local_neg_pts, envelope_mask, void_corner_mask


def _compute_hand_split_sub_boxes(
    box: Tuple[int, int, int, int],
    pos_pts: Sequence[List[int]],
    box_hand_boxes: Sequence[Tuple[int, int, int, int]],
) -> Tuple[bool, int, int, List[List[int]], List[List[int]], Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    """손 가로질림 시 상·하단 Sub-BBox 분할 여부와 각 영역 경계를 계산합니다."""
    ex1, ey1, ex2, ey2 = box
    ebw = max(1, ex2 - ex1)
    min_hy1 = min(hb[1] for hb in box_hand_boxes) if box_hand_boxes else ey1
    max_hy2 = max(hb[3] for hb in box_hand_boxes) if box_hand_boxes else ey2
    hand_span_x = (
        max(min(ex2, hx2) - max(ex1, hx1) for hx1, _, hx2, _ in box_hand_boxes)
        if box_hand_boxes
        else 0
    )
    hand_mid_y = int((min_hy1 + max_hy2) * 0.5)
    upper_pts = [pt for pt in pos_pts if pt[1] < min_hy1] if box_hand_boxes else []
    lower_pts = [pt for pt in pos_pts if pt[1] > max_hy2] if box_hand_boxes else []
    split_active = bool(
        box_hand_boxes and upper_pts and lower_pts and hand_span_x >= max(12, int(ebw * 0.35))
    )

    if split_active:
        hand_band = max(0, max_hy2 - min_hy1)
        band_pad = min(hand_band // 2, max(6, int(hand_band * 0.15)))
        upper_y2 = min(ey2, max(ey1 + 16, min(max_hy2, hand_mid_y + band_pad)))
        lower_y1 = max(ey1, min(ey2 - 16, max(min_hy1, hand_mid_y - band_pad)))
        return split_active, min_hy1, max_hy2, upper_pts, lower_pts, (ex1, ey1, ex2, upper_y2), (ex1, lower_y1, ex2, ey2)
    return False, min_hy1, max_hy2, upper_pts, lower_pts, box, box
