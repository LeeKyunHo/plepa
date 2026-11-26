"""
plepa_engine.censor.styles
망가 바(`manga_bar`), 망가 글로우(`manga_glow`), 디버그 BBox(`debug_bbox`) 및 통합 스타일 라우터 모듈.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

from ._runtime import facade_get
from .geometry import (
    _compute_scale_factor,
    _estimate_penis_axis_and_base,
    _normalize_censor_boxes,
    _odd_kernel,
    _restore_alpha,
    _rotated_rect_points,
    _scale_int,
    _split_rgb_and_alpha,
    get_skin_mask,
)
from .styles_basic import (
    apply_black_silhouette,
    apply_mosaic,
    apply_shadow_silhouette,
    apply_slim_black_bar,
    apply_white_silhouette,
    apply_wide_solid_bar,
)


def apply_manga_bar(
    img: Image.Image,
    boxes: Sequence[Any],
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
) -> Image.Image:
    """
    주축 회전 각도와 낭심(Base) 기하 구조를 따라 기둥 코어 바 및 낭심 크로스 바를 배치하는
    정통 망가식 검은 바(`manga_bar`) 검열을 렌더링합니다.
    """
    rgb_img, alpha_ch = _split_rgb_and_alpha(img)
    norm_boxes = _normalize_censor_boxes(boxes)
    if not norm_boxes:
        return _restore_alpha(rgb_img.copy(), alpha_ch)

    img_np = np.array(rgb_img, dtype=np.uint8)
    h_img, w_img = img_np.shape[:2]
    skin_fn = facade_get("get_skin_mask", get_skin_mask)
    est_fn = facade_get("_estimate_penis_axis_and_base", _estimate_penis_axis_and_base)
    skin_mask = skin_np if skin_np is not None else skin_fn(img_np)
    scale = _compute_scale_factor(w_img, h_img)
    min_bar_w = _scale_int(10, scale, minimum=5)

    mask = np.zeros((h_img, w_img), dtype=np.uint8)
    for (x1, y1, x2, y2) in norm_boxes:
        geom = est_fn(img_np, (x1, y1, x2, y2), skin_np=skin_mask, pose_cat=pose_cat)
        sx0, sy0 = geom["shaft_start"]
        sx1, sy1 = geom["shaft_end"]
        mid_shaft = ((sx0 + sx1) * 0.5, (sy0 + sy1) * 0.5)
        axis = geom["axis"]
        major_len = geom["major_len"]
        minor_len = geom["minor_len"]
        shaft_w = geom["shaft_width"]
        rx, ry = geom["base_radii"]

        box_mask = np.zeros((h_img, w_img), dtype=np.uint8)
        shaft_thick = max(float(min_bar_w), min(minor_len * 0.72, max(shaft_w * 0.85, minor_len * 0.42)))
        shaft_poly = _rotated_rect_points(mid_shaft, axis, major_len * 0.94, shaft_thick)
        cv2.fillConvexPoly(box_mask, shaft_poly, 255)

        base_len = max(float(min_bar_w) * 1.3, rx * 1.55)
        base_thick = max(float(min_bar_w) * 1.3, min(minor_len * 0.95, ry * 1.90))
        base_poly = _rotated_rect_points(geom["base_center"], axis, base_len, base_thick)
        cv2.fillConvexPoly(box_mask, base_poly, 255)

        pad = max(4, int(max(x2 - x1, y2 - y1) * 0.08))
        cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
        cx2, cy2 = min(w_img, x2 + pad), min(h_img, y2 + pad)
        mask[cy1:cy2, cx1:cx2] = np.maximum(mask[cy1:cy2, cx1:cx2], box_mask[cy1:cy2, cx1:cx2])

    out_np = img_np.copy()
    out_np[mask > 0] = (0, 0, 0)
    return _restore_alpha(Image.fromarray(out_np, mode="RGB"), alpha_ch)


def apply_manga_glow(
    img: Image.Image,
    boxes: Sequence[Any],
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
) -> Image.Image:
    """
    회전된 슬림 기둥 캡슐과 낭심 보호 타원을 결합한 뒤, 코어는 불투명 순백색(255)으로 유지하고
    외곽만 부드럽게 발광·페더링하는 정통 망가식 화이트 글로우(`manga_glow`) 검열을 적용합니다.
    """
    rgb_img, alpha_ch = _split_rgb_and_alpha(img)
    norm_boxes = _normalize_censor_boxes(boxes)
    if not norm_boxes:
        return _restore_alpha(rgb_img.copy(), alpha_ch)

    img_np = np.array(rgb_img, dtype=np.uint8)
    h_img, w_img = img_np.shape[:2]
    skin_fn = facade_get("get_skin_mask", get_skin_mask)
    est_fn = facade_get("_estimate_penis_axis_and_base", _estimate_penis_axis_and_base)
    skin_mask = skin_np if skin_np is not None else skin_fn(img_np)
    scale = _compute_scale_factor(w_img, h_img)
    min_cap_w = _scale_int(10, scale, minimum=5)
    fk = _odd_kernel(13, scale, minimum=5)

    alpha_total = np.zeros((h_img, w_img), dtype=np.float32)
    for (x1, y1, x2, y2) in norm_boxes:
        geom = est_fn(img_np, (x1, y1, x2, y2), skin_np=skin_mask, pose_cat=pose_cat)
        p0 = (int(round(geom["shaft_start"][0])), int(round(geom["shaft_start"][1])))
        p1 = (int(round(geom["shaft_end"][0])), int(round(geom["shaft_end"][1])))
        bc = (int(round(geom["base_center"][0])), int(round(geom["base_center"][1])))
        rx, ry = geom["base_radii"]
        minor_len = geom["minor_len"]
        shaft_w = geom["shaft_width"]
        angle = float(geom["angle"])

        outer_w = max(min_cap_w, int(round(min(minor_len * 0.72, max(shaft_w * 0.90, minor_len * 0.48)))))
        core_w = max(3, int(round(outer_w * 0.72)))

        outer_mask = np.zeros((h_img, w_img), dtype=np.uint8)
        cv2.line(outer_mask, p0, p1, 255, thickness=outer_w)
        cv2.ellipse(
            outer_mask,
            bc,
            (max(3, int(round(rx * 0.95))), max(3, int(round(ry * 0.95)))),
            angle,
            0,
            360,
            255,
            -1,
        )

        core_mask = np.zeros((h_img, w_img), dtype=np.uint8)
        cv2.line(core_mask, p0, p1, 255, thickness=core_w)
        cv2.ellipse(
            core_mask,
            bc,
            (max(2, int(round(rx * 0.74))), max(2, int(round(ry * 0.74)))),
            angle,
            0,
            360,
            255,
            -1,
        )

        sigma = max(1.8, min(float(x2 - x1), float(y2 - y1)) * 0.055)
        blurred = cv2.GaussianBlur(outer_mask, (fk, fk), sigma)
        box_alpha = np.maximum(blurred.astype(np.float32) / 255.0, (core_mask > 0).astype(np.float32))

        pad = max(6, int(max(x2 - x1, y2 - y1) * 0.14))
        cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
        cx2, cy2 = min(w_img, x2 + pad), min(h_img, y2 + pad)
        alpha_total[cy1:cy2, cx1:cx2] = np.maximum(alpha_total[cy1:cy2, cx1:cx2], box_alpha[cy1:cy2, cx1:cx2])

    alpha_3 = alpha_total[:, :, np.newaxis]
    blended = img_np.astype(np.float32) * (1.0 - alpha_3) + 255.0 * alpha_3
    out_np = np.clip(blended, 0, 255).astype(np.uint8)
    return _restore_alpha(Image.fromarray(out_np, mode="RGB"), alpha_ch)


def apply_debug_bbox(
    img: Image.Image,
    boxes_with_labels: Sequence[Any],
) -> Image.Image:
    """
    마스킹 대신 감지된 바운딩 박스(BBox), 라벨 및 신뢰도 점수를
    고대비 가시화 테두리(라임/시안)와 뱃지 텍스트로 그려주는 진단(QA) 시각화 함수.
    """
    out = img.copy()
    draw = ImageDraw.Draw(out)

    palette = {
        "penis": (0, 255, 64),        # 형광 라임 그린
        "pussy": (0, 229, 255),       # 형광 시안 블루
        "nipple_f": (255, 128, 192),  # 핑크
        "anchor": (255, 170, 0),      # 오렌지
    }
    fallback_color = (255, 235, 59)   # 밝은 노랑

    for item in boxes_with_labels:
        if len(item) >= 3:
            box, label, score = item[0], str(item[1]), float(item[2])
            caption = f"{label} {score:.2f}"
        else:
            box, label = item[0], str(item[1])
            caption = label

        x1, y1, x2, y2 = [int(v) for v in box]
        color = palette.get(label.lower(), fallback_color)

        for off in range(3):
            draw.rectangle([x1 - off, y1 - off, x2 + off, y2 + off], outline=color)

        badge_h = 16
        text_w = max(45, len(caption) * 7 + 8)
        bx2 = min(out.width, x1 + text_w)
        by1 = max(0, y1 - badge_h)
        draw.rectangle([x1, by1, bx2, y1], fill=(20, 20, 20))
        draw.text((x1 + 4, by1 + 2), caption, fill=color)

    return out


def _render_censored_style(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Any, ...]],
    style: str = "white_silhouette",
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    custom_seg_mask: Optional[np.ndarray] = None,
    fallback_boxes: Optional[Sequence[Tuple[Any, ...]]] = None,
    yolo_prior_masks: Optional[Sequence[Optional[np.ndarray]]] = None,
    context_boxes: Optional[Sequence[Optional[Tuple[int, int, int, int]]]] = None,
) -> Image.Image:
    """검열 스타일명(`style`)에 대응하는 렌더러로 일관되게 라우팅합니다."""
    detected_boxes = [item[0] for item in boxes_with_labels]
    style_clean = str(style or "white_silhouette").lower().strip()
    sil_kw = dict(
        skin_np=skin_np,
        pose_cat=pose_cat,
        custom_seg_mask=custom_seg_mask,
        fallback_boxes=fallback_boxes,
        yolo_prior_masks=yolo_prior_masks,
        context_boxes=context_boxes,
    )

    if style_clean in ("debug", "debug_bbox", "bbox", "bbox_debug"):
        return facade_get("apply_debug_bbox", apply_debug_bbox)(img, boxes_with_labels)
    if style_clean in ("white_silhouette", "white", "whiteout"):
        return facade_get("apply_white_silhouette", apply_white_silhouette)(img, boxes_with_labels, **sil_kw)
    if style_clean in ("black_silhouette", "silhouette_black", "black", "silhouette", "contour"):
        return facade_get("apply_black_silhouette", apply_black_silhouette)(img, boxes_with_labels, **sil_kw)
    if style_clean in ("manga_bar", "manga_black_bar", "haetae"):
        return facade_get("apply_manga_bar", apply_manga_bar)(img, detected_boxes, skin_np=skin_np, pose_cat=pose_cat)
    if style_clean in ("manga_glow", "manga_white", "glow_bar"):
        return facade_get("apply_manga_glow", apply_manga_glow)(img, detected_boxes, skin_np=skin_np, pose_cat=pose_cat)
    if style_clean in ("bar", "wide_bar", "solid_bar", "black_bar", "pill_bar"):
        return facade_get("apply_wide_solid_bar", apply_wide_solid_bar)(img, detected_boxes)
    if style_clean in ("slim_bar", "thin_bar"):
        return facade_get("apply_slim_black_bar", apply_slim_black_bar)(img, detected_boxes)
    if style_clean in ("shadow", "shadow_box", "shadow_silhouette"):
        return facade_get("apply_shadow_silhouette", apply_shadow_silhouette)(img, detected_boxes)
    if style_clean in ("mosaic", "pixel"):
        return facade_get("apply_mosaic", apply_mosaic)(img, detected_boxes)
    return facade_get("apply_white_silhouette", apply_white_silhouette)(img, boxes_with_labels, **sil_kw)
