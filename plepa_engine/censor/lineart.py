"""
plepa_engine.censor.lineart
2D 일러스트 먹선/윤곽선 장벽(Barrier) 추출, 시드 스냅, 선화 구획 클램핑 및 외곽 스냅 모듈.
"""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from ._runtime import facade_get
from .geometry import _estimate_penis_axis_and_base, _odd_kernel, _scale_int


def _extract_lineart_barrier(roi_rgb: np.ndarray, scale: float) -> np.ndarray:
    """
    2D 일러스트 ROI에서 검은 먹선/윤곽선(Line-Art) 마스크를 추출하고,
    미세한 1~2px 끊김을 폐합해 허벅지/배경 번짐을 막는 선화 장벽(Barrier)을 생성합니다.
    """
    if roi_rgb.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    gray = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2GRAY)
    blur_k = _odd_kernel(3, scale, minimum=3)
    blurred = cv2.GaussianBlur(gray, (blur_k, blur_k), 0.8)

    block_sz = _odd_kernel(11, scale, minimum=7)
    adap = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_sz,
        7,
    )
    canny = cv2.Canny(blurred, 55, 145)
    raw_barrier = cv2.bitwise_or(adap, canny)
    if np.count_nonzero(raw_barrier) == 0:
        return raw_barrier

    close_sz = _odd_kernel(3, scale, minimum=3)
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (close_sz, close_sz))
    return cv2.morphologyEx(raw_barrier, cv2.MORPH_CLOSE, k_close, iterations=1)


def _snap_seed_to_fillable(fillable: np.ndarray, px: int, py: int, max_radius: int = 8) -> Optional[Tuple[int, int]]:
    """시드 좌표가 선화 위 등에 걸린 경우 반경 내에서 유효 `fillable > 0` 픽셀로 스냅합니다."""
    rh, rw = fillable.shape[:2]
    if rh == 0 or rw == 0:
        return None
    px = max(0, min(rw - 1, int(px)))
    py = max(0, min(rh - 1, int(py)))
    if fillable[py, px] > 0:
        return px, py

    for r in range(1, max_radius + 1):
        y0, y1 = max(0, py - r), min(rh, py + r + 1)
        x0, x1 = max(0, px - r), min(rw, px + r + 1)
        ys, xs = np.nonzero(fillable[y0:y1, x0:x1] > 0)
        if len(xs) > 0:
            d2 = (xs + x0 - px) ** 2 + (ys + y0 - py) ** 2
            best = int(np.argmin(d2))
            return int(xs[best] + x0), int(ys[best] + y0)
    return None


def _label_border_touch_ratio(labels: np.ndarray, label_id: int) -> float:
    """연결 성분 `label_id`가 ROI 외곽 1px 둘레를 차지하는 비율(0.0~1.0)을 반환합니다."""
    rh, rw = labels.shape[:2]
    if rh < 2 or rw < 2:
        return 1.0
    perim = np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])
    return float(np.count_nonzero(perim == label_id)) / float(max(1, perim.size))


def _clamp_mask_by_lineart_and_base(
    sam_mask: np.ndarray,
    roi_rgb: np.ndarray,
    roi_skin: Optional[np.ndarray],
    scale: float,
    pose_cat: Optional[str] = None,
) -> np.ndarray:
    """
    2D 선화 장벽(`_extract_lineart_barrier`)과 기둥·낭심 전경 시드를 결합해
    선화 바깥(허벅지/사타구니/입술/손)으로 번진 마스크를 절단하고, 선화 위(1~2px)까지만 매끈히 채웁니다.
    """
    rh, rw = sam_mask.shape[:2]
    if rh == 0 or rw == 0 or np.count_nonzero(sam_mask) == 0:
        return sam_mask

    barrier = _extract_lineart_barrier(roi_rgb, scale)
    if np.count_nonzero(barrier) < 6:
        return sam_mask

    sam_bin = (sam_mask > 127).astype(np.uint8) * 255
    fillable = cv2.bitwise_and(sam_bin, cv2.bitwise_not(barrier))
    if np.count_nonzero(fillable) < max(16, int(rh * rw * 0.02)):
        return sam_mask

    est_fn = facade_get("_estimate_penis_axis_and_base", _estimate_penis_axis_and_base)
    geom = est_fn(roi_rgb, (0, 0, rw, rh), skin_np=roi_skin, pose_cat=pose_cat)
    num_labels, labels = cv2.connectedComponents((fillable > 0).astype(np.uint8), connectivity=4)
    if num_labels <= 1:
        return sam_mask

    # 기둥 중심(ROI 중앙 + PCA 중심) 및 낭심 중심(base_center)에서 유효 시드 컴포넌트 탐색
    cand_pts = [
        (int(round(geom["center"][0])), int(round(geom["center"][1]))),
        (rw // 2, rh // 2),
    ]
    center_label = 0
    for cpx, cpy in cand_pts:
        snapped = _snap_seed_to_fillable(fillable, cpx, cpy, max_radius=max(6, int(min(rw, rh) * 0.08)))
        if snapped is not None:
            lbl = int(labels[snapped[1], snapped[0]])
            if lbl > 0:
                center_label = lbl
                break

    if center_label == 0:
        return sam_mask

    # 중심 구획이 ROI 둘레 대부분(>60%)을 감싸는 외곽 배경인 경우는 선화 폐곡선이 없는 씬이므로 원 마스크 유지
    if _label_border_touch_ratio(labels, center_label) > 0.60:
        return sam_mask

    keep_mask = (labels == center_label).astype(np.uint8) * 255

    # 낭심(Base Bulb)이 별도 선화 구획으로 분리되어 있을 경우 외곽 배경이 아닐 때만 병합
    bx, by = int(round(geom["base_center"][0])), int(round(geom["base_center"][1]))
    base_snapped = _snap_seed_to_fillable(fillable, bx, by, max_radius=max(5, int(min(rw, rh) * 0.06)))
    if base_snapped is not None:
        base_lbl = int(labels[base_snapped[1], base_snapped[0]])
        if base_lbl > 0 and base_lbl != center_label and _label_border_touch_ratio(labels, base_lbl) < 0.42:
            keep_mask = cv2.bitwise_or(keep_mask, (labels == base_lbl).astype(np.uint8) * 255)

    # 장벽 추출로 비어 있던 검은 선화 두께(1~2px) 자체만 덮고, 선화 바깥 구획에는 넘치지 않게 제약
    dil_sz = _odd_kernel(3, scale, minimum=3)
    k_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dil_sz, dil_sz))
    dilated = cv2.dilate(keep_mask, k_dil, iterations=1)
    allowed_zone = cv2.bitwise_or(keep_mask, barrier)
    return cv2.bitwise_and(dilated, allowed_zone)


def _snap_to_outer_lineart(
    mask: np.ndarray,
    img_np: np.ndarray,
    scale: float,
    protection_mask: Optional[np.ndarray] = None,
    max_steps: Optional[int] = None,
) -> np.ndarray:
    """
    전경 마스크 바로 바깥쪽(해상도 비례 1~3px) 링 구간의 어두운 먹선/외곽 선화 픽셀을 흡수해
    피부 테두리 노출 없이 포토샵 작업본처럼 선화 외곽까지 밀착 스냅합니다.
    protection_mask 내부로는 단 1px도 확장하지 않습니다.
    """
    if mask.size == 0 or np.count_nonzero(mask) == 0 or img_np.size == 0:
        return mask

    steps = (
        max(1, int(max_steps))
        if max_steps is not None
        else min(3, max(1, _scale_int(2, scale, minimum=1)))
    )
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    k_ctx = _odd_kernel(7, scale, minimum=5)
    k_bh = _odd_kernel(9, scale, minimum=5)
    local_bright = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_ctx, k_ctx)))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_bh, k_bh)))

    # 평탄한 어두운 배경은 제외하고 주변 피부 대비 명도가 뚜렷이 낮은 얇은 윤곽선/어두운 테두리만 선별
    contrast = local_bright.astype(np.int16) - gray.astype(np.int16)
    dark_lineart = (blackhat >= 14) | ((gray <= 135) & (contrast >= 20))

    allowed = (protection_mask == 0) if (protection_mask is not None and protection_mask.shape == mask.shape) else np.ones_like(mask, dtype=bool)
    cur = (mask > 0).astype(np.uint8) * 255
    k_step = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))

    for _ in range(steps):
        ring = (cv2.dilate(cur, k_step, iterations=1) > 0) & (cur == 0)
        absorb = ring & dark_lineart & allowed
        if not np.any(absorb):
            break
        cur[absorb] = 255

    k_smooth_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cur = cv2.morphologyEx(cur, cv2.MORPH_CLOSE, k_smooth_close)
    if protection_mask is not None and protection_mask.shape == cur.shape:
        cur[protection_mask > 0] = 0
    return cur
