"""
plepa_engine.censor.mask_refinement
SAM 누수·네모 과팽창 분류, 라운드·코어 가드 생성 및 실루엣 알파 블렌딩 마감 모듈.
"""

from __future__ import annotations

from typing import Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from ._runtime import facade_get
from .geometry import (
    _bbox_fallback_geometry,
    _estimate_penis_axis_and_base,
    _odd_kernel,
    _restore_alpha,
    _scale_int,
)
from .lineart import _snap_to_outer_lineart


def _build_rounded_box_guard(
    w: int,
    h: int,
    ex1: int,
    ey1: int,
    ex2: int,
    ey2: int,
    scale: float,
    radius_ratio: float = 0.30,
) -> np.ndarray:
    """SAM 마스크 누수(Leakage) 시 허벅지/배경 코너 번짐을 막는 보수적 라운드 사각 가드를 생성합니다."""
    guard = np.zeros((h, w), dtype=np.uint8)
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    rad = max(_scale_int(4, scale, 3), int(min(ebw, ebh) * radius_ratio))
    sub_c = np.zeros((ebh, ebw), dtype=np.uint8)
    if ebw > rad * 2 and ebh > rad * 2:
        cv2.rectangle(sub_c, (rad, 0), (ebw - rad, ebh), 255, -1)
        cv2.rectangle(sub_c, (0, rad), (ebw, ebh - rad), 255, -1)
        cv2.circle(sub_c, (rad, rad), rad, 255, -1)
        cv2.circle(sub_c, (ebw - rad, rad), rad, 255, -1)
        cv2.circle(sub_c, (rad, ebh - rad), rad, 255, -1)
        cv2.circle(sub_c, (ebw - rad, ebh - rad), rad, 255, -1)
    else:
        cv2.ellipse(sub_c, (ebw // 2, ebh // 2), (ebw // 2, ebh // 2), 0, 0, 360, 255, -1)
    guard[ey1:ey2, ex1:ex2] = sub_c
    return guard


def _classify_sam_mask_leak(
    raw_m: np.ndarray,
    ex1: int,
    ey1: int,
    ex2: int,
    ey2: int,
    rx1: int,
    ry1: int,
    rx2: int,
    ry2: int,
    box_fill_thresh: float = 0.52,
) -> Tuple[bool, bool]:
    """
    SAM 추론 마스크의 누수(Leakage) 및 BBox 내부 네모/덩어리 과팽창 여부를 분리 판정합니다.
    반환값: (global_leak, blocky_overexpansion)
    """
    in_box = raw_m[ey1:ey2, ex1:ex2] > 0
    in_count = int(np.count_nonzero(in_box))
    box_area = max(1, (ex2 - ex1) * (ey2 - ey1))
    box_fill = float(in_count) / float(box_area)
    total_fg = int(np.count_nonzero(raw_m))
    outside_ratio = float(max(0, total_fg - in_count)) / float(box_area)

    global_leak = False
    if box_fill >= 0.90 and outside_ratio >= 0.35:
        global_leak = True
    else:
        crop_slice = raw_m[ry1:ry2, rx1:rx2] > 0
        if crop_slice.size > 0 and outside_ratio >= 0.65:
            border_sides = sum(
                [
                    float(crop_slice[0, :].mean()) >= 0.35,
                    float(crop_slice[-1, :].mean()) >= 0.35,
                    float(crop_slice[:, 0].mean()) >= 0.35,
                    float(crop_slice[:, -1].mean()) >= 0.35,
                ]
            )
            if border_sides >= 2:
                global_leak = True

    blocky_leak = False
    if not global_leak and box_fill > float(box_fill_thresh) and in_count > 0:
        bw, bh = max(1, ex2 - ex1), max(1, ey2 - ey1)
        ys_in, xs_in = np.nonzero(in_box)
        mbw = int(xs_in.max() - xs_in.min() + 1)
        mbh = int(ys_in.max() - ys_in.min() + 1)
        rect_extent = float(in_count) / float(max(1, mbw * mbh))

        cw_c, ch_c = max(2, bw // 5), max(2, bh // 5)
        corner_fill = float(
            np.mean(
                [
                    float(in_box[:ch_c, :cw_c].mean()),
                    float(in_box[:ch_c, -cw_c:].mean()),
                    float(in_box[-ch_c:, :cw_c].mean()),
                    float(in_box[-ch_c:, -cw_c:].mean()),
                ]
            )
        )
        border_touches = sum(
            1
            for edge_mean in (
                float(in_box[0, :].mean()),
                float(in_box[-1, :].mean()),
                float(in_box[:, 0].mean()),
                float(in_box[:, -1].mean()),
            )
            if edge_mean >= 0.30
        )
        strict_single = float(box_fill_thresh) <= 0.45
        if (
            (rect_extent >= 0.86 and corner_fill >= 0.28)
            or (box_fill >= 0.62 and corner_fill >= 0.32)
            or (strict_single and border_touches >= 2 and corner_fill >= 0.20 and rect_extent >= 0.72)
        ):
            blocky_leak = True

    return global_leak, blocky_leak


def _is_sam_mask_leaky(
    raw_m: np.ndarray,
    ex1: int,
    ey1: int,
    ex2: int,
    ey2: int,
    rx1: int,
    ry1: int,
    rx2: int,
    ry2: int,
    box_fill_thresh: float = 0.52,
) -> bool:
    """SAM 추론 마스크가 외부 경계로 누수되었거나 BBox 내부 네모/덩어리로 과팽창했는지 판정합니다."""
    cls_fn = facade_get("_classify_sam_mask_leak", _classify_sam_mask_leak)
    global_leak, blocky_leak = cls_fn(
        raw_m, ex1, ey1, ex2, ey2, rx1, ry1, rx2, ry2, box_fill_thresh=box_fill_thresh
    )
    return global_leak or blocky_leak


def _build_oriented_core_guard(
    w: int,
    h: int,
    ex1: int,
    ey1: int,
    ex2: int,
    ey2: int,
    scale: float,
    img_np: Optional[np.ndarray] = None,
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    minor_ratio_cap: float = 0.36,
) -> np.ndarray:
    """과팽창 감지 시 성기 주축·낭심 추정 기반 타원형 코어 가드를 생성해 좌우 네모 군살을 제거합니다."""
    ebw, ebh = max(1, ex2 - ex1), max(1, ey2 - ey1)
    if img_np is not None:
        est_fn = facade_get("_estimate_penis_axis_and_base", _estimate_penis_axis_and_base)
        geom = est_fn(img_np, (ex1, ey1, ex2, ey2), skin_np=skin_np, pose_cat=pose_cat)
    else:
        geom = _bbox_fallback_geometry(ex1, ey1, ex2, ey2, pose_cat=pose_cat)

    guard = np.zeros((h, w), dtype=np.uint8)
    cx, cy = int(round(geom["center"][0])), int(round(geom["center"][1]))
    angle = float(geom["angle"])
    major_r = max(4, int(round(min(max(ebw, ebh) * 0.52, max(float(geom["major_len"]) * 0.55, max(ebw, ebh) * 0.44)))))
    minor_r = max(4, int(round(min(min(ebw, ebh) * float(minor_ratio_cap), max(float(geom["minor_len"]) * 0.54, min(ebw, ebh) * min(0.28, float(minor_ratio_cap)))))))
    cv2.ellipse(guard, (cx, cy), (major_r, minor_r), angle, 0, 360, 255, -1)

    bcx, bcy = int(round(geom["base_center"][0])), int(round(geom["base_center"][1]))
    brx = max(3, int(round(min(ebw * 0.38, float(geom["base_radii"][0])))))
    bry = max(3, int(round(min(ebh * 0.38, float(geom["base_radii"][1])))))
    cv2.ellipse(guard, (bcx, bcy), (brx, bry), angle, 0, 360, 255, -1)

    round_guard = _build_rounded_box_guard(w, h, ex1, ey1, ex2, ey2, scale, radius_ratio=0.30)
    clipped = cv2.bitwise_and(guard, round_guard)
    return clipped if np.count_nonzero(clipped) > 0 else round_guard


def _finalize_and_blend_silhouette(
    img_np: np.ndarray,
    alpha_ch: Optional[Image.Image],
    mask: np.ndarray,
    color: Union[str, Tuple[int, int, int]],
    scale: float,
    protection_mask: Optional[np.ndarray] = None,
    apply_lineart_snap: bool = True,
) -> Optional[Image.Image]:
    """실루엣 마스크 마감(중립 임계 스무딩 -> 외곽 선화 스냅 -> 보호 마스크 차감 -> 1px AA 블렌딩)을 통합 수행합니다."""
    if mask.size == 0 or np.count_nonzero(mask) == 0:
        return None

    kc = _odd_kernel(5, scale, minimum=3)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc, kc))
    closed = cv2.morphologyEx((mask > 0).astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel_close)

    ks = _odd_kernel(5, scale, minimum=3)
    smooth_blur = cv2.GaussianBlur(closed, (ks, ks), 1.0 * scale)
    _, smoothed = cv2.threshold(smooth_blur, 115, 255, cv2.THRESH_BINARY)

    if protection_mask is not None and np.count_nonzero(protection_mask) > 0:
        smoothed = cv2.bitwise_and(smoothed, cv2.bitwise_not(protection_mask))

    if apply_lineart_snap and np.count_nonzero(smoothed) > 0:
        snap_fn = facade_get("_snap_to_outer_lineart", _snap_to_outer_lineart)
        smoothed = snap_fn(smoothed, img_np, scale, protection_mask=protection_mask)

    if protection_mask is not None and np.count_nonzero(protection_mask) > 0:
        smoothed = cv2.bitwise_and(smoothed, cv2.bitwise_not(protection_mask))

    if np.count_nonzero(smoothed) == 0:
        return None

    kf = _odd_kernel(3, scale, minimum=3)
    blurred = cv2.GaussianBlur(smoothed, (kf, kf), 0.8 * scale)
    if isinstance(color, str):
        color_rgb = (255, 255, 255) if color.lower() in ("white", "whiteout", "white_silhouette") else (12, 12, 16)
    else:
        color_rgb = color

    alpha = (blurred.astype(np.float32) / 255.0)[:, :, np.newaxis]
    target_layer = np.full_like(img_np, color_rgb, dtype=np.float32)
    blended = (1.0 - alpha) * img_np.astype(np.float32) + alpha * target_layer
    blended = np.clip(blended, 0, 255).astype(np.uint8)
    return _restore_alpha(Image.fromarray(blended), alpha_ch)
