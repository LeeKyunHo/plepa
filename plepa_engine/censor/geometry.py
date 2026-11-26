"""
plepa_engine.censor.geometry
피부톤 마스크, BBox IoU/IoMin, 손 교차 판별 및 성기 주축·낭심 PCA 기하 추정 유틸리티.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from ._runtime import (
    _BASE_RESOLUTION,
    _compute_scale_factor,
    _normalize_censor_boxes,
    _odd_kernel,
    _restore_alpha,
    _scale_int,
    _split_rgb_and_alpha,
    _to_rgb_ndarray,
    facade_get,
)


def get_skin_mask(img_np: np.ndarray) -> np.ndarray:
    """
    2D 애니메이션 일러스트에서 밝은 피부 영역(살구빛/핑크빛)부터 구릿빛/태닝/음영 피부톤까지 고정밀 HSV 필터로 추출합니다.
    - Hue: [0, 32] 또는 [162, 180] (자연스러운 붉은빛~살구빛~구릿빛 피부톤)
    - Saturation: [15, 190] (무채색 흰색이나 고채도 원색 의상 픽셀 제외)
    - Value: [55, 255] (태닝 피부 및 짙은 음영 피부까지 포괄)
    """
    hsv = cv2.cvtColor(img_np, cv2.COLOR_RGB2HSV)
    lower1 = np.array([0, 15, 55], dtype=np.uint8)
    upper1 = np.array([32, 190, 255], dtype=np.uint8)
    mask1 = cv2.inRange(hsv, lower1, upper1)

    lower2 = np.array([162, 15, 55], dtype=np.uint8)
    upper2 = np.array([180, 190, 255], dtype=np.uint8)
    mask2 = cv2.inRange(hsv, lower2, upper2)

    return cv2.bitwise_or(mask1, mask2)


def _extract_roi_foreground_mask(roi_rgb: np.ndarray, roi_skin: Optional[np.ndarray]) -> np.ndarray:
    """ROI 내부의 피부 또는 배경 대비 전경 픽셀 마스크(`bool`)를 추출합니다."""
    rh, rw = roi_rgb.shape[:2]
    area = max(1, rh * rw)
    min_px = max(16, int(area * 0.03))

    skin_fn = facade_get("get_skin_mask", get_skin_mask)
    skin_bool = (roi_skin > 0) if roi_skin is not None else (skin_fn(roi_rgb) > 0)
    skin_count = int(np.count_nonzero(skin_bool))

    if min_px <= skin_count <= int(area * 0.80):
        return skin_bool

    border_samples = np.concatenate(
        [roi_rgb[0, :], roi_rgb[-1, :], roi_rgb[:, 0], roi_rgb[:, -1]],
        axis=0,
    ).astype(np.float32)
    border_bg = np.median(border_samples, axis=0)
    dist = np.linalg.norm(roi_rgb.astype(np.float32) - border_bg, axis=2)
    max_dist = float(dist.max()) if dist.size else 0.0
    if max_dist > 16.0:
        contrast_bool = dist > max(18.0, max_dist * 0.35)
        contrast_count = int(np.count_nonzero(contrast_bool))
        if min_px <= contrast_count <= int(area * 0.82):
            return contrast_bool

    if skin_count >= min_px:
        return skin_bool
    return np.zeros((rh, rw), dtype=bool)


def _bbox_fallback_geometry(
    x1: int, y1: int, x2: int, y2: int, pose_cat: Optional[str] = None
) -> Dict[str, Any]:
    """픽셀 부족 또는 등방성 ROI에 대한 BBox 종횡비 기반 기하 폴백을 생성합니다."""
    bw = max(1.0, float(x2 - x1))
    bh = max(1.0, float(y2 - y1))
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    if bw >= bh:
        ux, uy = 1.0, 0.0
        major_len = bw * 0.84
        minor_len = bh * 0.56
    else:
        ux, uy = 0.0, -1.0  # 아래(Base) -> 위(Tip)
        major_len = bh * 0.84
        minor_len = bw * 0.56

    if pose_cat and any(k in str(pose_cat).lower() for k in ("fellatio", "deepthroat", "oral", "blowjob", "irrumatio")):
        if abs(uy) < 0.25:
            ux, uy = 1.0, 0.0
        elif uy > 0:
            ux, uy = -ux, -uy

    half_len = major_len * 0.5
    base_t = -half_len * 0.65
    ry = max(4.0, minor_len * 0.425)
    rx = max(ry * 0.85, major_len * 0.20)
    return {
        "center": (cx, cy),
        "axis": (ux, uy),
        "angle": math.degrees(math.atan2(uy, ux)),
        "major_len": major_len,
        "minor_len": minor_len,
        "shaft_width": minor_len * 0.72,
        "shaft_start": (cx - ux * half_len, cy - uy * half_len),
        "shaft_end": (cx + ux * half_len, cy + uy * half_len),
        "base_center": (cx + ux * base_t, cy + uy * base_t),
        "base_radii": (rx, ry),
        "fallback": True,
    }


def _slice_cross_width(n_vals: np.ndarray, mask: np.ndarray, default_val: float) -> float:
    """주축 구간 슬라이스 내부의 수직 폭(`P98 - P2`)을 계산합니다."""
    if int(np.count_nonzero(mask)) < 4:
        return default_val
    vals = n_vals[mask]
    return max(2.0, float(np.percentile(vals, 98.0) - np.percentile(vals, 2.0)))


def _estimate_penis_axis_and_base(
    img_np_or_rgb: Union[Image.Image, np.ndarray],
    bbox: Tuple[int, int, int, int],
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
) -> Dict[str, Any]:
    """
    BBox 내부 전경 마스크의 PCA 주축(기울기 각도)과 양 끝단 단면 폭(30% 슬라이스)을 비교해
    기둥 방향과 낭심(Base Bulb) 위치·반경을 추정합니다.
    """
    img_np = _to_rgb_ndarray(img_np_or_rgb)
    h_img, w_img = img_np.shape[:2]
    x1 = max(0, min(w_img - 1, int(bbox[0])))
    y1 = max(0, min(h_img - 1, int(bbox[1])))
    x2 = max(x1 + 1, min(w_img, int(bbox[2])))
    y2 = max(y1 + 1, min(h_img, int(bbox[3])))

    roi_rgb = img_np[y1:y2, x1:x2]
    roi_skin = skin_np[y1:y2, x1:x2] if skin_np is not None else None
    fg_mask = _extract_roi_foreground_mask(roi_rgb, roi_skin)
    ys, xs = np.nonzero(fg_mask)
    roi_area = max(1, (x2 - x1) * (y2 - y1))

    if len(xs) < 16 or len(xs) > int(roi_area * 0.88):
        return _bbox_fallback_geometry(x1, y1, x2, y2, pose_cat=pose_cat)

    pts = np.column_stack([xs.astype(np.float64) + x1, ys.astype(np.float64) + y1])
    mean = pts.mean(axis=0)
    centered = pts - mean
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    lambda_minor = float(max(eigvals[0], 1e-6))
    lambda_major = float(max(eigvals[1], 1e-6))

    bw, bh = float(x2 - x1), float(y2 - y1)
    bbox_elongated = max(bw, bh) / max(1.0, min(bw, bh)) >= 1.35
    if (lambda_major / lambda_minor) < 1.25 and not bbox_elongated:
        return _bbox_fallback_geometry(x1, y1, x2, y2, pose_cat=pose_cat)

    u = eigvecs[:, 1].astype(np.float64)
    v = np.array([-u[1], u[0]], dtype=np.float64)
    t_vals = centered @ u
    n_vals = centered @ v

    t_min = float(np.percentile(t_vals, 1.0))
    t_max = float(np.percentile(t_vals, 99.0))
    span = max(6.0, t_max - t_min)

    neg_mask = t_vals <= (t_min + 0.30 * span)
    pos_mask = t_vals >= (t_max - 0.30 * span)
    mid_mask = (t_vals >= (t_min + 0.32 * span)) & (t_vals <= (t_max - 0.32 * span))

    fallback_w = max(4.0, float(np.percentile(n_vals, 95.0) - np.percentile(n_vals, 5.0)))
    width_neg = _slice_cross_width(n_vals, neg_mask, fallback_w)
    width_pos = _slice_cross_width(n_vals, pos_mask, fallback_w)
    shaft_width = _slice_cross_width(n_vals, mid_mask, min(width_neg, width_pos))

    # 양 끝단 중 더 넓은 쪽을 낭심(Base)으로 선택; 구강 씬에서는 입/얼굴에서 먼 쪽(하단 우선)을 우선 고정
    is_oral = bool(
        pose_cat
        and any(k in str(pose_cat).lower() for k in ("fellatio", "deepthroat", "oral", "blowjob", "irrumatio"))
    )
    end_neg_pt = mean + u * (t_min + 0.16 * span)
    end_pos_pt = mean + u * (t_max - 0.16 * span)
    if is_oral and abs(float(end_neg_pt[1] - end_pos_pt[1])) > 0.15 * span:
        base_is_pos = float(end_pos_pt[1]) >= float(end_neg_pt[1])
    else:
        base_is_pos = width_pos > width_neg

    if base_is_pos:
        u = -u
        t_min, t_max = -t_max, -t_min
        base_width = width_pos
    else:
        base_width = width_neg

    # Base는 항상 t_min 쪽에 위치 (u는 Base -> Tip 방향)
    ux, uy = float(u[0]), float(u[1])
    cx, cy = float(mean[0]), float(mean[1])
    overall_minor = max(shaft_width, base_width, fallback_w)
    overall_minor = min(overall_minor, max(bw, bh) * 0.95)

    base_t = t_min + 0.18 * span
    bx = cx + ux * base_t
    by = cy + uy * base_t

    ry = max(4.0, max(overall_minor * 0.85, base_width * 0.92) * 0.50)
    rx = max(ry * 0.82, span * 0.20)
    return {
        "center": (cx, cy),
        "axis": (ux, uy),
        "angle": math.degrees(math.atan2(uy, ux)),
        "major_len": span,
        "minor_len": overall_minor,
        "shaft_width": max(4.0, shaft_width),
        "shaft_start": (cx + ux * t_min, cy + uy * t_min),
        "shaft_end": (cx + ux * t_max, cy + uy * t_max),
        "base_center": (bx, by),
        "base_radii": (rx, ry),
        "fallback": False,
    }


def _rotated_rect_points(
    center: Tuple[float, float],
    axis: Tuple[float, float],
    length_along: float,
    thickness_perp: float,
) -> np.ndarray:
    """중심·방향벡터(`axis`)·길이·두께로부터 회전 직사각형 4꼭짓점(`int32`)을 계산합니다."""
    cx, cy = center
    ux, uy = axis
    vx, vy = -uy, ux
    hl = max(1.0, length_along * 0.5)
    ht = max(1.0, thickness_perp * 0.5)
    return np.array(
        [
            [cx - ux * hl - vx * ht, cy - uy * hl - vy * ht],
            [cx + ux * hl - vx * ht, cy + uy * hl - vy * ht],
            [cx + ux * hl + vx * ht, cy + uy * hl + vy * ht],
            [cx - ux * hl + vx * ht, cy - uy * hl + vy * ht],
        ],
        dtype=np.int32,
    )


def _box_iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    union = max(1, area_a + area_b - inter)
    return inter / float(union)


def _box_iomin(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    """두 BBox 중 작은 박스 면적 대비 교집합 비율(IoMin)을 계산해 포함 중복 여부를 판정합니다."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / float(min(area_a, area_b))


def _has_hand_between_boxes(
    box_a: Tuple[int, int, int, int],
    box_b: Tuple[int, int, int, int],
    hand_boxes: Sequence[Tuple[int, int, int, int]],
) -> bool:
    """두 타겟 후보 박스 사이의 수직 틈새/연결 구간을 손 BBox가 실제로 가로질러 양분하는지 판정합니다."""
    if not hand_boxes:
        return False

    ya = (box_a[1] + box_a[3]) * 0.5
    yb = (box_b[1] + box_b[3]) * 0.5
    upper, lower = (box_a, box_b) if ya <= yb else (box_b, box_a)
    ux1, uy1, ux2, uy2 = [int(v) for v in upper]
    lx1, ly1, lx2, ly2 = [int(v) for v in lower]

    upper_cy, lower_cy = (uy1 + uy2) * 0.5, (ly1 + ly2) * 0.5
    corr_x1, corr_x2 = min(ux1, lx1) - 12, max(ux2, lx2) + 12
    gap_top, gap_bot = min(uy2, ly1) - 16, max(uy2, ly1) + 16

    for hx1, hy1, hx2, hy2 in hand_boxes:
        if min(corr_x2, hx2) <= max(corr_x1, hx1):
            continue
        hy_mid = (hy1 + hy2) * 0.5
        if upper_cy < hy_mid < lower_cy and min(gap_bot, hy2) >= max(gap_top, hy1):
            return True
    return False
