"""
plepa_engine.censor.silhouette
외곽선 실루엣 검열(`apply_silhouette`) 메인 오케스트레이터 모듈.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from ._runtime import facade_get
from .geometry import _compute_scale_factor, _split_rgb_and_alpha, get_skin_mask
from .mask_refinement import _finalize_and_blend_silhouette
from .models import _infer_custom_censor_seg, get_custom_censor_seg_model, get_sam_model
from .protection import _extract_face_and_hand_boxes, _extract_hand_occlusion_mask
from .silhouette_sam import _segment_target_box_with_sam


def apply_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Any, ...]],
    color: Union[str, Tuple[int, int, int]] = "black",
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    custom_seg_mask: Optional[np.ndarray] = None,
    fallback_boxes: Optional[Sequence[Tuple[Any, ...]]] = None,
    yolo_prior_masks: Optional[Sequence[Optional[np.ndarray]]] = None,
    context_boxes: Optional[Sequence[Optional[Tuple[int, int, int, int]]]] = None,
) -> Image.Image:
    """
    네모난 박스가 아니라 타겟과 기저부의 실제 선화 외곽선(Contour)을 따라
    내부만 솔리드 컬러(블랙 #000000 또는 화이트 #FFFFFF)로 매끈하게 채우는 실루엣 검열을 렌더링합니다.
    - Phase P0: 4중 수축(8% 인셋, 0.40 코너 절단, 중복 erode, 140 클리핑) 해체 + Line-Art Outer Snap 적용.
    - Phase P0.5: 손 가로질림 상·하단 Sub-BBox 분할 디코딩 + 영역별 독립 컴포넌트 보존 + 내부 네모 과팽창 억제.
    - Phase P2: Semantic-Guided SAM (YOLO distanceTransform 코어 Positive + 외곽 피부 Negative + Envelope 가드) + SAM 2.1 적용.
    """
    rgb_img, alpha_ch = _split_rgb_and_alpha(img)
    w, h = rgb_img.size
    scale = _compute_scale_factor(w, h)
    img_np = np.array(rgb_img)

    protection_mask, face_neg_pts, detected_face_boxes, detected_hand_boxes = _extract_face_and_hand_boxes(
        rgb_img, scale
    )
    genital_boxes_raw: List[Tuple[int, int, int, int]] = [
        (int(it[0][0]), int(it[0][1]), int(it[0][2]), int(it[0][3]))
        for it in boxes_with_labels
        if it and isinstance(it[0], (tuple, list)) and len(it[0]) >= 4
    ]

    skin_fn = facade_get("get_skin_mask", get_skin_mask)
    eff_skin_np = skin_np if skin_np is not None else skin_fn(img_np)

    # 전용 YOLO-seg 마스크 직접 렌더링 경로 (+ 필요 시 미커버 fallback_boxes 하이브리드 병합)
    active_seg_mask = custom_seg_mask
    if active_seg_mask is None and boxes_with_labels and fallback_boxes is None:
        seg_model = facade_get("get_custom_censor_seg_model", get_custom_censor_seg_model)()
        if seg_model is not None:
            _, active_seg_mask = facade_get("_infer_custom_censor_seg", _infer_custom_censor_seg)(rgb_img, seg_model)

    has_active_seg = active_seg_mask is not None and np.count_nonzero(active_seg_mask) > 0
    if fallback_boxes is not None:
        sam_target_boxes = list(fallback_boxes)
    elif has_active_seg:
        sam_target_boxes = []
    else:
        sam_target_boxes = list(boxes_with_labels)

    final_mask = np.zeros((h, w), dtype=np.uint8)
    if has_active_seg:
        seg_bin = (active_seg_mask > 0).astype(np.uint8) * 255
        if seg_bin.shape != (h, w):
            seg_bin = cv2.resize(seg_bin, (w, h), interpolation=cv2.INTER_NEAREST)
        final_mask = np.maximum(final_mask, seg_bin)

    has_intersecting_hand = any(
        max(gx1, hx1) < min(ex2_i, hx2) and max(ey1_i, hy1) < min(ey2_i, hy2)
        for (gx1, ey1_i, ex2_i, ey2_i) in genital_boxes_raw
        for (hx1, hy1, hx2, hy2) in detected_hand_boxes
    )
    need_sam_for_boxes = len(sam_target_boxes) > 0
    sam = facade_get("get_sam_model", get_sam_model)() if (need_sam_for_boxes or has_intersecting_hand) else None

    if detected_hand_boxes and genital_boxes_raw:
        hand_occ_fn = facade_get("_extract_hand_occlusion_mask", _extract_hand_occlusion_mask)
        hand_occ_mask = hand_occ_fn(
            rgb_img, sam, detected_hand_boxes, genital_boxes_raw, scale, skin_np=eff_skin_np
        )
        if np.count_nonzero(hand_occ_mask) > 0:
            protection_mask = np.maximum(protection_mask, hand_occ_mask)
    else:
        hand_occ_mask = np.zeros((h, w), dtype=np.uint8)

    asym_thresh = 1.15 if pose_cat in ("fellatio", "paizuri") else 1.35

    for item_idx, item in enumerate(sam_target_boxes):
        x1, y1, x2, y2 = item[0]
        ex1, ey1 = max(0, int(x1)), max(0, int(y1))
        ex2, ey2 = min(w, int(x2)), min(h, int(y2))
        if ex2 <= ex1 or ey2 <= ey1:
            continue

        item_prior_raw = yolo_prior_masks[item_idx] if (yolo_prior_masks is not None and item_idx < len(yolo_prior_masks)) else None
        item_context_box = context_boxes[item_idx] if (context_boxes is not None and item_idx < len(context_boxes)) else None
        item_prior_mask: Optional[np.ndarray] = None
        if item_prior_raw is not None:
            prior_u8 = (np.asarray(item_prior_raw) > 0).astype(np.uint8) * 255
            if prior_u8.shape != (h, w):
                prior_u8 = cv2.resize(prior_u8, (w, h), interpolation=cv2.INTER_NEAREST)
            if np.count_nonzero(prior_u8) >= 16:
                item_prior_mask = prior_u8

        sub_m = _segment_target_box_with_sam(
            rgb_img=rgb_img,
            img_np=img_np,
            eff_skin_np=eff_skin_np,
            sam=sam,
            box=(ex1, ey1, ex2, ey2),
            item_prior_mask=item_prior_mask,
            item_context_box=item_context_box,
            face_neg_pts=face_neg_pts,
            detected_face_boxes=detected_face_boxes,
            detected_hand_boxes=detected_hand_boxes,
            hand_occ_mask=hand_occ_mask,
            asym_thresh=asym_thresh,
            scale=scale,
            pose_cat=pose_cat,
        )
        final_mask = np.maximum(final_mask, sub_m)

    blend_fn = facade_get("_finalize_and_blend_silhouette", _finalize_and_blend_silhouette)
    blended_out = blend_fn(
        img_np, alpha_ch, final_mask, color=color, scale=scale, protection_mask=protection_mask, apply_lineart_snap=True
    )
    return blended_out if blended_out is not None else img
