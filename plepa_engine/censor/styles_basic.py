"""
plepa_engine.censor.styles_basic
블랙/화이트 실루엣 래퍼, 와이드 솔리드 바, 슬림 블랙 바, 그림자 음영 및 모자이크 스타일 렌더러.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ._runtime import facade_get
from .geometry import _compute_scale_factor, _odd_kernel, _restore_alpha, _scale_int, _split_rgb_and_alpha
from .silhouette import apply_silhouette


def apply_black_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Any, ...]],
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    custom_seg_mask: Optional[np.ndarray] = None,
    fallback_boxes: Optional[Sequence[Tuple[Any, ...]]] = None,
    yolo_prior_masks: Optional[Sequence[Optional[np.ndarray]]] = None,
    context_boxes: Optional[Sequence[Optional[Tuple[int, int, int, int]]]] = None,
) -> Image.Image:
    """블랙 실루엣(#000000) 검열 래퍼 함수."""
    sil_fn = facade_get("apply_silhouette", apply_silhouette)
    return sil_fn(
        img,
        boxes_with_labels,
        color="black",
        skin_np=skin_np,
        pose_cat=pose_cat,
        custom_seg_mask=custom_seg_mask,
        fallback_boxes=fallback_boxes,
        yolo_prior_masks=yolo_prior_masks,
        context_boxes=context_boxes,
    )


def apply_white_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Any, ...]],
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    custom_seg_mask: Optional[np.ndarray] = None,
    fallback_boxes: Optional[Sequence[Tuple[Any, ...]]] = None,
    yolo_prior_masks: Optional[Sequence[Optional[np.ndarray]]] = None,
    context_boxes: Optional[Sequence[Optional[Tuple[int, int, int, int]]]] = None,
) -> Image.Image:
    """화이트 실루엣(#FFFFFF) 검열 래퍼 함수."""
    sil_fn = facade_get("apply_silhouette", apply_silhouette)
    return sil_fn(
        img,
        boxes_with_labels,
        color="white",
        skin_np=skin_np,
        pose_cat=pose_cat,
        custom_seg_mask=custom_seg_mask,
        fallback_boxes=fallback_boxes,
        yolo_prior_masks=yolo_prior_masks,
        context_boxes=context_boxes,
    )


def apply_wide_solid_bar(
    img: Image.Image,
    boxes: Sequence[Tuple[int, int, int, int]],
    margin_ratio: float = 0.18,
    corner_radius_ratio: float = 0.25,
    min_margin: int = 6,
) -> Image.Image:
    """
    2D 서브컬처 상업 동인지/미연시(DLsite/FANZA) 표준 '와이드 솔리드 캡슐 바(Wide Solid Bar)'를 렌더링합니다.
    - 정밀 성기 BBox 영역을 상하좌우 18% 적응형 세이프 마진(Safe Margin)으로 팽창.
    - 모서리를 둥글게 깎는 캡슐형(Pill-shaped) 라운딩 적용.
    """
    rgb_img, alpha_ch = _split_rgb_and_alpha(img)
    canvas = rgb_img.copy()
    draw = ImageDraw.Draw(canvas)
    img_w, img_h = canvas.size
    scale = _compute_scale_factor(img_w, img_h)
    scaled_min_margin = _scale_int(min_margin, scale, minimum=2)
    min_radius = _scale_int(4, scale, minimum=2)

    for (x1, y1, x2, y2) in boxes:
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)

        pad_x = max(scaled_min_margin, int(w * margin_ratio))
        pad_y = max(scaled_min_margin, int(h * margin_ratio))

        bx1 = max(0, x1 - pad_x)
        by1 = max(0, y1 - pad_y)
        bx2 = min(img_w, x2 + pad_x)
        by2 = min(img_h, y2 + pad_y)

        box_w = max(1, bx2 - bx1)
        box_h = max(1, by2 - by1)

        radius = max(min_radius, int(min(box_w, box_h) * corner_radius_ratio))
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=radius, fill=(0, 0, 0))

    return _restore_alpha(canvas, alpha_ch)


def apply_slim_black_bar(
    img: Image.Image,
    boxes: Sequence[Tuple[int, int, int, int]],
    angle_deg: float = 25.0,
    thickness_ratio: float = 0.28,
) -> Image.Image:
    """
    2D 서브컬처 미니멀 슬림 블랙 바(Thin Black Bar)를 렌더링합니다.
    - 남성기 중심을 통과하는 사선(기본 25도) 얇은 검은색 띠를 얹습니다.
    """
    rgb_img, alpha_ch = _split_rgb_and_alpha(img)
    canvas = rgb_img.copy()
    draw = ImageDraw.Draw(canvas)
    scale = _compute_scale_factor(*canvas.size)
    min_thickness = _scale_int(12, scale, minimum=4)
    max_thickness = _scale_int(32, scale, minimum=12)

    for (x1, y1, x2, y2) in boxes:
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        bar_thickness = max(min_thickness, min(max_thickness, int(min(w, h) * thickness_ratio)))
        bar_length = max(w, h) * 0.95

        angle_rad = math.radians(angle_deg)
        dx = (bar_length / 2.0) * math.cos(angle_rad)
        dy = (bar_length / 2.0) * math.sin(angle_rad)

        p1 = (cx - dx, cy - dy)
        p2 = (cx + dx, cy + dy)

        draw.line([p1, p2], fill=(0, 0, 0), width=bar_thickness)
        r = bar_thickness / 2.0
        draw.ellipse([p1[0] - r, p1[1] - r, p1[0] + r, p1[1] + r], fill=(0, 0, 0))
        draw.ellipse([p2[0] - r, p2[1] - r, p2[0] + r, p2[1] + r], fill=(0, 0, 0))

    return _restore_alpha(canvas, alpha_ch)


def apply_shadow_silhouette(
    img: Image.Image,
    boxes: Sequence[Tuple[int, int, int, int]],
    shadow_opacity: float = 0.85,
    blur_radius: int = 14,
) -> Image.Image:
    """
    형태 윤곽선과 굴곡(실루엣)은 은은하게 유지하되, 내부 선화 디테일만 짙은 그림자 톤으로 덮는
    소프트 페더링 그림자 음영(Shadow Box) 검열을 적용합니다.
    """
    rgb_img, alpha_ch = _split_rgb_and_alpha(img)
    canvas = rgb_img.copy()
    scale = _compute_scale_factor(*canvas.size)
    eff_blur = max(2, int(round(blur_radius * scale)))
    fk = _odd_kernel(13, scale)

    for (x1, y1, x2, y2) in boxes:
        crop_box = (max(0, x1), max(0, y1), min(canvas.width, x2), min(canvas.height, y2))
        cw = crop_box[2] - crop_box[0]
        ch = crop_box[3] - crop_box[1]
        if cw <= 0 or ch <= 0:
            continue
        sub_img = canvas.crop(crop_box)

        blurred = sub_img.filter(ImageFilter.GaussianBlur(radius=eff_blur))
        shadow = Image.new("RGB", blurred.size, color=(18, 18, 18))
        blended = Image.blend(blurred, shadow, alpha=shadow_opacity)

        mask_np = np.zeros((ch, cw), dtype=np.uint8)
        rx = max(2, int(cw * 0.44))
        ry = max(2, int(ch * 0.44))
        cv2.ellipse(mask_np, (cw // 2, ch // 2), (rx, ry), 0, 0, 360, 255, -1)
        feathered_mask = cv2.GaussianBlur(mask_np, (fk, fk), 3.5 * scale)
        canvas.paste(blended, crop_box, Image.fromarray(feathered_mask, mode="L"))

    return _restore_alpha(canvas, alpha_ch)


def apply_mosaic(
    img: Image.Image,
    boxes: Sequence[Tuple[int, int, int, int]],
    block_size: int = 16,
) -> Image.Image:
    """하단 기저부 통합 확장 및 ROI 국소 픽셀화·소프트 캡슐 페더링이 적용된 정밀 블러-모자이크."""
    rgb_img, alpha_ch = _split_rgb_and_alpha(img)
    w_img, h_img = rgb_img.size
    scale = _compute_scale_factor(w_img, h_img)
    eff_block = _scale_int(block_size, scale, minimum=4)
    eff_pre_blur = max(1.0, 3.0 * scale)
    fk = _odd_kernel(9, scale)

    mask = np.zeros((h_img, w_img), dtype=np.uint8)
    ux1, uy1, ux2, uy2 = w_img, h_img, 0, 0
    for (x1, y1, x2, y2) in boxes:
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        ex1 = max(0, int(x1 - bw * 0.04))
        ey1 = max(0, int(y1 - bh * 0.02))
        ex2 = min(w_img, int(x2 + bw * 0.04))
        ey2 = min(h_img, int(y2 + bh * (0.16 if bh > bw * 0.8 else 0.10)))
        if ex2 <= ex1 or ey2 <= ey1:
            continue
        cx = int((ex1 + ex2) / 2)
        cy = int((ey1 + ey2) / 2)
        rx = max(_scale_int(6, scale, 4), int((ex2 - ex1) * 0.48))
        ry = max(_scale_int(6, scale, 4), int((ey2 - ey1) * 0.48))
        cv2.ellipse(mask, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)
        ux1, uy1 = min(ux1, ex1), min(uy1, ey1)
        ux2, uy2 = max(ux2, ex2), max(uy2, ey2)

    if np.count_nonzero(mask) == 0 or ux2 <= ux1 or uy2 <= uy1:
        return img.copy()

    ux1 = max(0, ux1 - fk)
    uy1 = max(0, uy1 - fk)
    ux2 = min(w_img, ux2 + fk)
    uy2 = min(h_img, uy2 + fk)

    orig_crop = rgb_img.crop((ux1, uy1, ux2, uy2))
    cw, ch = orig_crop.size
    blurred_crop = orig_crop.filter(ImageFilter.GaussianBlur(radius=eff_pre_blur))
    small_w = max(1, cw // eff_block)
    small_h = max(1, ch // eff_block)
    mosaic_crop = blurred_crop.resize((small_w, small_h), Image.Resampling.BILINEAR).resize(
        (cw, ch), Image.Resampling.NEAREST
    )

    feathered = cv2.GaussianBlur(mask[uy1:uy2, ux1:ux2], (fk, fk), 2.5 * scale)
    alpha = (feathered.astype(np.float32) / 255.0)[:, :, np.newaxis]
    blended_np = (1.0 - alpha) * np.array(orig_crop, dtype=np.float32) + alpha * np.array(mosaic_crop, dtype=np.float32)
    blended_crop = Image.fromarray(np.clip(blended_np, 0, 255).astype(np.uint8))

    out = rgb_img.copy()
    out.paste(blended_crop, (ux1, uy1))
    return _restore_alpha(out, alpha_ch)
