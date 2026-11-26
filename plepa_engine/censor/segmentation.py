"""
plepa_engine.censor.segmentation
YOLO prior 확장 중심축 회랑 계산 및 SAM 2.1 시맨틱 Positive/Negative 프롬프트 추출 모듈.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .geometry import _scale_int


def _compute_prior_extension_corridor(
    prior_bin: np.ndarray,
    target_box: Tuple[int, int, int, int],
) -> Optional[np.ndarray]:
    """
    YOLO prior 마스크보다 target_box가 한쪽(또는 양쪽) 끝단으로 크게 확장된 경우(Branch B Union Span),
    prior 주축(PCA 1주성분)을 따라 미커버 잔여 구간으로 이어지는 중심축 회랑(Corridor) 마스크를 생성합니다.
    """
    h, w = prior_bin.shape[:2]
    ex1, ey1, ex2, ey2 = target_box
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    prior_in_box = prior_bin[ey1:ey2, ex1:ex2]
    pys_b, pxs_b = np.nonzero(prior_in_box)
    if len(pxs_b) < 16:
        return None

    px1, px2 = ex1 + int(pxs_b.min()), ex1 + int(pxs_b.max()) + 1
    py1, py2 = ey1 + int(pys_b.min()), ey1 + int(pys_b.max()) + 1
    gap_thresh = max(24, int(round(min(ebw, ebh) * 0.14)))
    gap_top, gap_bot = py1 - ey1, ey2 - py2
    gap_left, gap_right = px1 - ex1, ex2 - px2
    if max(gap_top, gap_bot, gap_left, gap_right) < gap_thresh:
        return None

    uncovered_rect = np.zeros((h, w), dtype=np.uint8)
    if gap_bot >= gap_thresh:
        uncovered_rect[py2:ey2, ex1:ex2] = 255
    if gap_top >= gap_thresh:
        uncovered_rect[ey1:py1, ex1:ex2] = 255
    if gap_left >= gap_thresh:
        uncovered_rect[ey1:ey2, ex1:px1] = 255
    if gap_right >= gap_thresh:
        uncovered_rect[ey1:ey2, px2:ex2] = 255

    gx = pxs_b.astype(np.float64) + float(ex1)
    gy = pys_b.astype(np.float64) + float(ey1)
    pcx, pcy = float(gx.mean()), float(gy.mean())
    pts_centered = np.column_stack((gx - pcx, gy - pcy))
    cov = np.cov(pts_centered, rowvar=False) if len(pts_centered) >= 4 else np.eye(2)
    eigvals, eigvecs = np.linalg.eigh(cov)
    major_idx = int(np.argmax(eigvals))
    minor_idx = 1 - major_idx
    eig_ratio = float(eigvals[major_idx]) / max(1e-6, float(eigvals[minor_idx]))
    if eig_ratio >= 1.25:
        vx, vy = float(eigvecs[0, major_idx]), float(eigvecs[1, major_idx])
    elif max(gap_top, gap_bot) >= max(gap_left, gap_right):
        vx, vy = 0.0, 1.0
    else:
        vx, vy = 1.0, 0.0
    norm_len = math.hypot(vx, vy) or 1.0
    vx, vy = vx / norm_len, vy / norm_len

    along_proj = pts_centered[:, 0] * vx + pts_centered[:, 1] * vy
    perp_proj = np.abs(pts_centered[:, 0] * (-vy) + pts_centered[:, 1] * vx)
    half_w = max(18, int(round(float(np.percentile(perp_proj, 95)) * 1.25)))

    corners = ((ex1, ey1), (ex2, ey1), (ex1, ey2), (ex2, ey2))
    box_projs = [(cx - pcx) * vx + (cy - pcy) * vy for cx, cy in corners]
    box_lo, box_hi = min(box_projs), max(box_projs)
    p_min, p_max = float(along_proj.min()), float(along_proj.max())
    p_lo, p_hi = float(np.percentile(along_proj, 8)), float(np.percentile(along_proj, 92))

    corridor = np.zeros((h, w), dtype=np.uint8)
    drew = False
    if (box_hi - p_max) >= gap_thresh * 0.70:
        pt1 = (int(round(pcx + vx * p_hi)), int(round(pcy + vy * p_hi)))
        pt2 = (int(round(pcx + vx * box_hi)), int(round(pcy + vy * box_hi)))
        cv2.line(corridor, pt1, pt2, 255, thickness=max(16, half_w * 2))
        drew = True
    if (p_min - box_lo) >= gap_thresh * 0.70:
        pt1 = (int(round(pcx + vx * p_lo)), int(round(pcy + vy * p_lo)))
        pt2 = (int(round(pcx + vx * box_lo)), int(round(pcy + vy * box_lo)))
        cv2.line(corridor, pt1, pt2, 255, thickness=max(16, half_w * 2))
        drew = True

    if not drew:
        return None

    box_mask = np.zeros((h, w), dtype=np.uint8)
    box_mask[ey1:ey2, ex1:ex2] = 255
    corridor = cv2.bitwise_and(corridor, box_mask)
    corridor = cv2.bitwise_and(corridor, uncovered_rect)
    return corridor if np.count_nonzero(corridor) >= 16 else None


def _build_prior_envelope(
    prior_bin: np.ndarray,
    ex1: int,
    ey1: int,
    ex2: int,
    ey2: int,
    scale: float,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """Prior 마스크의 ~15% 팽창 Envelope 가드와 확장 중심축 회랑을 결합 생성합니다."""
    h, w = prior_bin.shape[:2]
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    rx = max(_scale_int(8, scale, minimum=6), int(round(ebw * 0.15)))
    ry = max(_scale_int(8, scale, minimum=6), int(round(ebh * 0.15)))
    env_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, rx * 2 + 1), max(3, ry * 2 + 1)))
    envelope_mask = (cv2.dilate(prior_bin * 255, env_kernel, iterations=1) > 0).astype(np.uint8) * 255

    ext_corridor = _compute_prior_extension_corridor(prior_bin, (ex1, ey1, ex2, ey2))
    if ext_corridor is not None:
        ext_pad = cv2.dilate(ext_corridor, env_kernel, iterations=1)
        box_clip = np.zeros((h, w), dtype=np.uint8)
        box_clip[max(0, ey1 - 6):min(h, ey2 + 6), max(0, ex1 - 6):min(w, ex2 + 6)] = 255
        envelope_mask = cv2.bitwise_or(envelope_mask, cv2.bitwise_and(ext_pad, box_clip))
    return envelope_mask, ext_corridor


def _collect_prior_ridge_points(
    prior_bin: np.ndarray,
    ex1: int,
    ey1: int,
    ex2: int,
    ey2: int,
    hand_boxes: Sequence[Tuple[int, int, int, int]],
) -> List[List[int]]:
    """손 BBox를 제외한 YOLO prior의 `cv2.distanceTransform` 최대 코어 및 주축 능선 포인트를 수집합니다."""
    h, w = prior_bin.shape[:2]
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    valid_fg = prior_bin.copy()
    for hx1, hy1, hx2, hy2 in hand_boxes:
        ix1, iy1, ix2, iy2 = max(0, int(hx1)), max(0, int(hy1)), min(w, int(hx2)), min(h, int(hy2))
        if ix2 > ix1 and iy2 > iy1:
            valid_fg[iy1:iy2, ix1:ix2] = 0
    if np.count_nonzero(valid_fg) < 16:
        valid_fg = prior_bin.copy()

    def _in_hands(px: int, py: int) -> bool:
        return any(hx1 <= px <= hx2 and hy1 <= py <= hy2 for hx1, hy1, hx2, hy2 in hand_boxes)

    pos_pts: List[List[int]] = []
    if np.count_nonzero(valid_fg) == 0:
        return pos_pts

    dist = cv2.distanceTransform(valid_fg, cv2.DIST_L2, 5)
    max_dist = float(dist.max())
    min_sep = max(12.0, max(ebw, ebh) * 0.22)

    def _try_add(sub_dist: np.ndarray, x_off: int, y_off: int, min_val: float) -> None:
        if sub_dist.size == 0 or float(sub_dist.max()) < min_val:
            return
        ly, lx = np.unravel_index(int(np.argmax(sub_dist)), sub_dist.shape)
        cand = [int(lx + x_off), int(ly + y_off)]
        if _in_hands(cand[0], cand[1]):
            return
        if any(math.hypot(cand[0] - p[0], cand[1] - p[1]) < min_sep for p in pos_pts):
            return
        pos_pts.append(cand)

    _try_add(dist[ey1:ey2, ex1:ex2], ex1, ey1, 0.0)
    ys_fg, xs_fg = np.nonzero(valid_fg[ey1:ey2, ex1:ex2])
    if len(xs_fg) >= 24 and max_dist > 0.0:
        ridge_thresh = max(1.5, max_dist * 0.38)
        x_span = int(xs_fg.max() - xs_fg.min() + 1)
        y_span = int(ys_fg.max() - ys_fg.min() + 1)
        if y_span >= x_span:
            y_a = ey1 + int(ys_fg.min() + y_span * 0.42)
            y_b = ey1 + int(ys_fg.min() + y_span * 0.58)
            _try_add(dist[ey1:y_a, ex1:ex2], ex1, ey1, ridge_thresh)
            _try_add(dist[y_b:ey2, ex1:ex2], ex1, y_b, ridge_thresh)
        else:
            x_a = ex1 + int(xs_fg.min() + x_span * 0.42)
            x_b = ex1 + int(xs_fg.min() + x_span * 0.58)
            _try_add(dist[ey1:ey2, ex1:x_a], ex1, ey1, ridge_thresh)
            _try_add(dist[ey1:ey2, x_b:ex2], x_b, ey1, ridge_thresh)
    return pos_pts[:3]


def _collect_ext_and_quadrant_negatives(
    prior_bin: np.ndarray,
    ext_corridor: Optional[np.ndarray],
    ex1: int,
    ey1: int,
    ex2: int,
    ey2: int,
    context_box: Optional[Tuple[int, int, int, int]],
    skin_bool: np.ndarray,
    hand_boxes: Sequence[Tuple[int, int, int, int]],
    scale: float,
) -> Tuple[List[List[int]], List[List[int]]]:
    """Branch B 확장 기저부 보조 Positive 1점 및 주변 피부 사분면 Negative(최대 4점)를 추출합니다."""
    h, w = prior_bin.shape[:2]
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    neg_rx = max(_scale_int(6, scale, minimum=4), int(round(ebw * 0.08)))
    neg_ry = max(_scale_int(6, scale, minimum=4), int(round(ebh * 0.08)))
    neg_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (neg_rx * 2 + 1, neg_ry * 2 + 1))
    dilated_prior = cv2.dilate(prior_bin * 255, neg_kernel, iterations=1) > 0

    aux_pos_pts: List[List[int]] = []
    if ext_corridor is not None:
        ext_mask = (ext_corridor > 0) & (~dilated_prior)
        if np.count_nonzero(ext_mask) == 0:
            ext_mask = ext_corridor > 0
        for hx1, hy1, hx2, hy2 in hand_boxes:
            ext_mask[max(0, int(hy1)):min(h, int(hy2)), max(0, int(hx1)):min(w, int(hx2))] = False
        ext_skin = ext_mask & skin_bool
        eys, exs = np.where(ext_skin if np.count_nonzero(ext_skin) >= 12 else ext_mask)
        if len(exs) > 0:
            med_e = int(len(exs) // 2)
            cand_ext = [int(exs[med_e]), int(eys[med_e])]
            if not any(hx1 <= cand_ext[0] <= hx2 and hy1 <= cand_ext[1] <= hy2 for hx1, hy1, hx2, hy2 in hand_boxes):
                aux_pos_pts.append(cand_ext)

    cx1, cy1, cx2, cy2 = [int(v) for v in (context_box if context_box is not None else (ex1, ey1, ex2, ey2))]
    cx1, cy1 = max(0, min(ex1, cx1)), max(0, min(ey1, cy1))
    cx2, cy2 = min(w, max(ex2, cx2)), min(h, max(ey2, cy2))

    neg_pts: List[List[int]] = []
    if cx2 > cx1 + 4 and cy2 > cy1 + 4:
        protected_neg_zone = dilated_prior.copy()
        if ext_corridor is not None:
            protected_neg_zone |= (ext_corridor > 0)
        outer_skin = skin_bool[cy1:cy2, cx1:cx2] & (~protected_neg_zone[cy1:cy2, cx1:cx2])
        cw_ctx, ch_ctx = cx2 - cx1, cy2 - cy1
        mx, my = max(1, cw_ctx // 2), max(1, ch_ctx // 2)
        for qx1, qy1, qx2, qy2 in ((0, 0, mx, my), (mx, 0, cw_ctx, my), (0, my, mx, ch_ctx), (mx, my, cw_ctx, ch_ctx)):
            qys, qxs = np.where(outer_skin[qy1:qy2, qx1:qx2])
            if len(qxs) >= 12:
                med_idx = int(len(qxs) // 2)
                neg_pts.append([int(cx1 + qx1 + qxs[med_idx]), int(cy1 + qy1 + qys[med_idx])])
    return aux_pos_pts[:1], neg_pts[:4]


def _extract_semantic_sam_prompts(
    yolo_prior_mask: np.ndarray,
    target_box: Tuple[int, int, int, int],
    context_box: Optional[Tuple[int, int, int, int]],
    skin_bool: np.ndarray,
    hand_boxes: Sequence[Tuple[int, int, int, int]],
    scale: float,
) -> Tuple[List[List[int]], List[List[int]], np.ndarray]:
    """
    YOLO-seg 폴리곤 마스크(yolo_prior_mask)를 기반으로 SAM 2.1용 시맨틱 프롬프트를 산출합니다.
    - Positive(1): 손 영역을 제외한 prior 마스크의 cv2.distanceTransform 최대 코어 및 주축 능선 코어(최대 3점)
                   + Branch B 확장 기저부가 존재할 경우 중심축 확장 구간의 보조 Positive 1점 추가
    - Negative(0): context_box(또는 target_box) 내 피부 중 prior·확장 축 회랑 바깥의 주변 피부 사분면 대표 좌표(최대 4점)
    - envelope_mask: 타겟 박스 크기의 ~15% 반경으로 팽창시킨 Semantic Envelope 가드 (+ 확장 축 코어 허용)
    """
    h, w = yolo_prior_mask.shape[:2]
    prior_bin = (yolo_prior_mask > 0).astype(np.uint8)
    ex1, ey1, ex2, ey2 = [int(v) for v in target_box]
    ex1, ey1 = max(0, ex1), max(0, ey1)
    ex2, ey2 = min(w, ex2), min(h, ey2)

    envelope_mask, ext_corridor = _build_prior_envelope(prior_bin, ex1, ey1, ex2, ey2, scale)
    pos_pts = _collect_prior_ridge_points(prior_bin, ex1, ey1, ex2, ey2, hand_boxes)
    aux_pos_pts, neg_pts = _collect_ext_and_quadrant_negatives(
        prior_bin, ext_corridor, ex1, ey1, ex2, ey2, context_box, skin_bool, hand_boxes, scale
    )
    return pos_pts + aux_pos_pts, neg_pts, envelope_mask
