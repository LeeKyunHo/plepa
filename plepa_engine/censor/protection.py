"""
plepa_engine.censor.protection
얼굴 상단(눈/이마 38%) 및 전경 손 가려짐(Hand Occlusion) 보호 마스크 추출 모듈.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

from ._runtime import facade_get, logger
from .geometry import _odd_kernel, _scale_int, get_skin_mask
from .models import _SAM_MODEL_LOCK, _extract_sam_mask_data


def _extract_hand_outer_skin_point(
    skin_mask_bool: np.ndarray,
    hbox: Tuple[int, int, int, int],
    genital_center_x: float,
) -> Optional[List[int]]:
    """손 BBox 내 성기 중심축에서 먼 손등/손목 외측 절반 구간의 대표 피부 좌표를 추출합니다."""
    img_h, img_w = skin_mask_bool.shape[:2]
    hx1 = max(0, int(hbox[0]))
    hy1 = max(0, int(hbox[1]))
    hx2 = min(img_w, int(hbox[2]))
    hy2 = min(img_h, int(hbox[3]))
    if hx2 <= hx1 or hy2 <= hy1:
        return None
    hx_mid = int((hx1 + hx2) / 2)
    hy_mid = int((hy1 + hy2) / 2)
    if hx_mid >= genital_center_x:
        ox1, ox2 = hx_mid, hx2
        fallback_x = int(hx1 + (hx2 - hx1) * 0.75)
    else:
        ox1, ox2 = hx1, hx_mid
        fallback_x = int(hx1 + (hx2 - hx1) * 0.25)

    if ox2 > ox1:
        ys, xs = np.where(skin_mask_bool[hy1:hy2, ox1:ox2])
        if len(xs) >= 12:
            return [ox1 + int(np.median(xs)), hy1 + int(np.median(ys))]
    return [min(img_w - 1, max(0, fallback_x)), min(img_h - 1, max(0, hy_mid))]


def _compute_mutually_exclusive_prompts(
    gbox: Tuple[int, int, int, int],
    hand_boxes: Sequence[Tuple[int, int, int, int]],
    skin_mask_bool: np.ndarray,
) -> Tuple[List[List[int]], List[List[int]]]:
    """
    성기 BBox와 교차하는 손 BBox 목록 간의 상호 배타적 앵커 포인트를 계산합니다.
    - unoccluded_pts: 손 BBox 바깥쪽 비가려짐 영역(상단 귀두 / 하단 기둥·낭심 / 측면)의 성기 코어 포인트
    - hand_anchor_pts: 교차 손 BBox 중심 및 성기 중심축 외측(손등/손목) 피부 포인트
    """
    img_h, img_w = skin_mask_bool.shape[:2]
    ex1 = max(0, int(gbox[0]))
    ey1 = max(0, int(gbox[1]))
    ex2 = min(img_w, int(gbox[2]))
    ey2 = min(img_h, int(gbox[3]))
    if ex2 <= ex1 or ey2 <= ey1:
        return [], []

    ebw = max(1, ex2 - ex1)
    ebh = max(1, ey2 - ey1)
    gx_mid = (ex1 + ex2) / 2.0

    intersecting = [
        (max(0, int(hx1)), max(0, int(hy1)), min(img_w, int(hx2)), min(img_h, int(hy2)))
        for hx1, hy1, hx2, hy2 in hand_boxes
        if max(ex1, hx1) < min(ex2, hx2) and max(ey1, hy1) < min(ey2, hy2)
    ]
    if not intersecting:
        return [], []

    def _in_hands(px: int, py: int) -> bool:
        return any(hx1 <= px <= hx2 and hy1 <= py <= hy2 for hx1, hy1, hx2, hy2 in intersecting)

    safe_roi_skin = skin_mask_bool[ey1:ey2, ex1:ex2].copy()
    hand_anchor_pts: List[List[int]] = []
    for hx1, hy1, hx2, hy2 in intersecting:
        center_pt = [int((hx1 + hx2) / 2), int((hy1 + hy2) / 2)]
        hand_anchor_pts.append(center_pt)
        outer_pt = _extract_hand_outer_skin_point(skin_mask_bool, (hx1, hy1, hx2, hy2), gx_mid)
        if outer_pt is not None and outer_pt != center_pt:
            hand_anchor_pts.append(outer_pt)

        # 경계 +1px까지 포함해 safe_roi_skin에서 마스킹 아웃
        shx1 = max(0, hx1 - ex1)
        shy1 = max(0, hy1 - ey1)
        shx2 = min(ebw, hx2 - ex1 + 1)
        shy2 = min(ebh, hy2 - ey1 + 1)
        if shx2 > shx1 and shy2 > shy1:
            safe_roi_skin[shy1:shy2, shx1:shx2] = False

    min_hy1 = min(hb[1] for hb in intersecting)
    max_hy2 = max(hb[3] for hb in intersecting)
    unoccluded_pts: List[List[int]] = []

    # 1) 상단 노출 코어 (손 위로 노출된 귀두 영역)
    if min_hy1 > ey1 + 6:
        top_cut = min(ebh, max(1, min_hy1 - ey1))
    else:
        top_cut = max(1, int(ebh * 0.48))
    tys, txs = np.where(safe_roi_skin[:top_cut, :])
    if len(txs) >= 8:
        pt_top = [ex1 + int(np.median(txs)), ey1 + int(np.median(tys))]
        if not _in_hands(pt_top[0], pt_top[1]):
            unoccluded_pts.append(pt_top)
    elif min_hy1 > ey1 + 6:
        pt_top = [int(gx_mid), int((ey1 + min(ey2, min_hy1)) / 2)]
        if not _in_hands(pt_top[0], pt_top[1]):
            unoccluded_pts.append(pt_top)

    # 2) 하단 노출 코어 (손 아래로 노출된 기둥/낭심 영역)
    if ey2 > max_hy2 + 6:
        bot_start = min(ebh - 1, max(0, max_hy2 - ey1 + 1))
        bys, bxs = np.where(safe_roi_skin[bot_start:, :])
        if len(bxs) >= 8:
            pt_bot = [ex1 + int(np.median(bxs)), ey1 + bot_start + int(np.median(bys))]
            if not _in_hands(pt_bot[0], pt_bot[1]):
                unoccluded_pts.append(pt_bot)
        else:
            pt_bot = [int(gx_mid), int((max(ey1, max_hy2) + ey2) / 2)]
            if not _in_hands(pt_bot[0], pt_bot[1]):
                unoccluded_pts.append(pt_bot)

    # 3) 좌/우 비가려짐 노출 코어 (상·하가 손에 모두 걸쳐진 경우)
    if not unoccluded_pts:
        sys_all, sxs_all = np.where(safe_roi_skin)
        if len(sxs_all) >= 8:
            pt_side = [ex1 + int(np.median(sxs_all)), ey1 + int(np.median(sys_all))]
            if not _in_hands(pt_side[0], pt_side[1]):
                unoccluded_pts.append(pt_side)

    if not unoccluded_pts:
        cand_above = [int(gx_mid), max(0, min_hy1 - 4)]
        cand_below = [int(gx_mid), min(img_h - 1, max_hy2 + 4)]
        if min_hy1 > ey1 and not _in_hands(cand_above[0], cand_above[1]):
            unoccluded_pts.append(cand_above)
        elif ey2 > max_hy2 and not _in_hands(cand_below[0], cand_below[1]):
            unoccluded_pts.append(cand_below)

    return unoccluded_pts, hand_anchor_pts


def _decode_single_hand_mask(
    rgb_img: Image.Image,
    sam: Any,
    hand_box: Tuple[int, int, int, int],
    intersecting: Sequence[Tuple[int, int, int, int]],
    skin_bool: np.ndarray,
    scale: float,
    w: int,
    h: int,
) -> np.ndarray:
    """단일 교차 손 BBox에 대해 양방향 앵커 SAM 디코딩(미가용 시 내측 타원 폴백)과 칼선 스무딩을 수행합니다."""
    hx1, hy1, hx2, hy2 = hand_box
    hbw, hbh = max(1, hx2 - hx1), max(1, hy2 - hy1)
    single_hand_m = np.zeros((h, w), dtype=np.uint8)
    sam_ok = False
    sam_lock = facade_get("_SAM_MODEL_LOCK", _SAM_MODEL_LOCK)

    # 양방향 앵커 수집: 손 Positive(중심+손등 외측) & 성기 노출부 Negative(손 BBox 바깥)
    hand_pos_global: List[List[int]] = [[int((hx1 + hx2) / 2), int((hy1 + hy2) / 2)]]
    mean_gx = sum((gb[0] + gb[2]) / 2.0 for gb in intersecting) / float(len(intersecting))
    outer_pt = _extract_hand_outer_skin_point(skin_bool, hand_box, mean_gx)
    if outer_pt is not None and outer_pt != hand_pos_global[0]:
        hand_pos_global.append(outer_pt)

    genital_neg_global: List[List[int]] = []
    for gbox in intersecting:
        unocc_pts, _ = _compute_mutually_exclusive_prompts(gbox, [hand_box], skin_bool)
        for pt in unocc_pts:
            if not (hx1 <= pt[0] <= hx2 and hy1 <= pt[1] <= hy2) and pt not in genital_neg_global:
                genital_neg_global.append(pt)

    if sam is not None:
        try:
            pad = max(_scale_int(32, scale, minimum=16), int(max(hbw, hbh) * 0.25))
            rx1 = max(0, min([hx1] + [gb[0] for gb in intersecting]) - pad)
            ry1 = max(0, min([hy1] + [gb[1] for gb in intersecting]) - pad)
            rx2 = min(w, max([hx2] + [gb[2] for gb in intersecting]) + pad)
            ry2 = min(h, max([hy2] + [gb[3] for gb in intersecting]) + pad)
            cw, ch = max(1, rx2 - rx1), max(1, ry2 - ry1)
            crop_pil = rgb_img.crop((rx1, ry1, rx2, ry2))
            local_hbox = [hx1 - rx1, hy1 - ry1, hx2 - rx1, hy2 - ry1]

            local_pos = [[px - rx1, py - ry1] for px, py in hand_pos_global if rx1 <= px < rx2 and ry1 <= py < ry2]
            if not local_pos:
                local_pos = [[int((hx1 + hx2) / 2) - rx1, int((hy1 + hy2) / 2) - ry1]]
            local_neg = [[px - rx1, py - ry1] for px, py in genital_neg_global if rx1 <= px < rx2 and ry1 <= py < ry2]
            all_pts = local_pos + local_neg
            all_lbls = [1] * len(local_pos) + [0] * len(local_neg)

            with sam_lock:
                try:
                    results = sam(
                        crop_pil, bboxes=[local_hbox], points=[all_pts], labels=[all_lbls], verbose=False
                    )
                except Exception:
                    results = sam(crop_pil, bboxes=[local_hbox], verbose=False)

            m_data = _extract_sam_mask_data(results)
            if m_data is not None:
                crop_m = (m_data[0].astype(np.float32) * 255.0).clip(0, 255).astype(np.uint8)
                if crop_m.shape != (ch, cw):
                    crop_m = cv2.resize(crop_m, (cw, ch), interpolation=cv2.INTER_NEAREST)
                raw_m = np.zeros((h, w), dtype=np.uint8)
                raw_m[ry1:ry2, rx1:rx2] = crop_m
                clipped = np.zeros((h, w), dtype=np.uint8)
                clipped[hy1:hy2, hx1:hx2] = raw_m[hy1:hy2, hx1:hx2]
                if np.count_nonzero(clipped) > 0:
                    single_hand_m = clipped
                    sam_ok = True
        except Exception as he:
            logger.debug(f"[Censor] 손 전경 마스크 추출 폴백: {he}")

    if not sam_ok:
        # SAM 미가용 또는 빈 마스크 반환 시 손 BBox 내측 보수 타원 마스크로 폴백
        hcx, hcy = int((hx1 + hx2) / 2), int((hy1 + hy2) / 2)
        erx, ery = max(2, int(hbw * 0.38)), max(2, int(hbh * 0.38))
        cv2.ellipse(single_hand_m, (hcx, hcy), (erx, ery), 0, 0, 360, 255, -1)

    # 해상도 비례 1~1.5px 칼선 스무딩 후 손 BBox 내부로 위상 클리핑 유지
    kh = _odd_kernel(3, scale, minimum=3)
    smooth_hand = cv2.GaussianBlur(single_hand_m, (kh, kh), 0.8 * scale)
    _, smooth_hand = cv2.threshold(smooth_hand, 115, 255, cv2.THRESH_BINARY)
    bbox_bounded = np.zeros((h, w), dtype=np.uint8)
    bbox_bounded[hy1:hy2, hx1:hx2] = smooth_hand[hy1:hy2, hx1:hx2]
    return bbox_bounded


def _extract_hand_occlusion_mask(
    rgb_img: Image.Image,
    sam: Any,
    hand_boxes: Sequence[Tuple[int, int, int, int]],
    genital_boxes: Sequence[Tuple[int, int, int, int]],
    scale: float,
    skin_np: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    인위적인 고정 면적 비율 컷 없이 양방향 앵커와 기하학적 위상 경계만으로 전경 손(Hand) 실루엣을 분리합니다.
    - Positive(1): 손 중심 + 성기 중심축 외측(손등/손목) 피부 포인트
    - Negative(0): 손 BBox 바깥쪽 비가려짐 성기 코어 포인트(상단 귀두 / 하단 기저부)
    - 추출된 손 마스크는 손 BBox 내부로만 엄격히 국한되며 경계 소프트 페더링을 적용합니다.
    """
    w, h = rgb_img.size
    hand_mask = np.zeros((h, w), dtype=np.uint8)
    if not hand_boxes or not genital_boxes:
        return hand_mask

    skin_fn = facade_get("get_skin_mask", get_skin_mask)
    skin_bool = skin_np > 0 if skin_np is not None else (skin_fn(np.array(rgb_img)) > 0)

    for raw_hx1, raw_hy1, raw_hx2, raw_hy2 in hand_boxes:
        hx1 = max(0, int(raw_hx1))
        hy1 = max(0, int(raw_hy1))
        hx2 = min(w, int(raw_hx2))
        hy2 = min(h, int(raw_hy2))
        if hx2 <= hx1 or hy2 <= hy1:
            continue

        intersecting = [
            (max(0, int(gx1)), max(0, int(gy1)), min(w, int(gx2)), min(h, int(gy2)))
            for (gx1, gy1, gx2, gy2) in genital_boxes
            if max(gx1, hx1) < min(gx2, hx2) and max(gy1, hy1) < min(gy2, hy2)
        ]
        if not intersecting:
            continue

        bbox_bounded = _decode_single_hand_mask(
            rgb_img, sam, (hx1, hy1, hx2, hy2), intersecting, skin_bool, scale, w, h
        )
        hand_mask = np.maximum(hand_mask, bbox_bounded)

    return hand_mask


def _extract_face_and_hand_boxes(
    rgb_img: Image.Image,
    scale: float,
) -> Tuple[np.ndarray, List[List[int]], List[Tuple[int, int, int, int]], List[Tuple[int, int, int, int]]]:
    """눈/이마(상단 38%) 보호 마스크와 얼굴 네거티브 포인트 및 전경 손 BBox 목록을 추출합니다."""
    w, h = rgb_img.size
    protection_mask = np.zeros((h, w), dtype=np.uint8)
    face_neg_pts: List[List[int]] = []
    detected_face_boxes: List[Tuple[int, int, int, int]] = []
    try:
        from imgutils.detect import detect_faces
        detected_faces = detect_faces(rgb_img, conf_threshold=0.35)

        for (fx1, fy1, fx2, fy2), _, _ in detected_faces:
            fx1_i, fy1_i, fx2_i, fy2_i = int(fx1), int(fy1), int(fx2), int(fy2)
            detected_face_boxes.append((fx1_i, fy1_i, fx2_i, fy2_i))
            fh = max(1, fy2_i - fy1_i)
            safe_fy2 = int(fy1_i + fh * 0.38)
            if safe_fy2 > fy1_i:
                cv2.rectangle(protection_mask, (fx1_i, fy1_i), (fx2_i, safe_fy2), 255, -1)
            face_neg_pts.append([int((fx1_i + fx2_i) / 2), int(fy1_i + fh * 0.42)])

        if np.count_nonzero(protection_mask) > 0:
            pk = _odd_kernel(15, scale)
            protection_mask = cv2.GaussianBlur(protection_mask, (pk, pk), 4.0 * scale)
            _, protection_mask = cv2.threshold(protection_mask, 128, 255, cv2.THRESH_BINARY)
    except Exception as pe:
        logger.debug(f"[Censor] 보호 영역 검출 생략: {pe}")

    detected_hand_boxes: List[Tuple[int, int, int, int]] = []
    try:
        from imgutils.detect import detect_hands
        detected_hands = detect_hands(rgb_img, conf_threshold=0.45)
        for h_item in detected_hands:
            hbox = h_item[0] if isinstance(h_item, (tuple, list)) and len(h_item) >= 3 else h_item
            if isinstance(hbox, (tuple, list)) and len(hbox) >= 4:
                detected_hand_boxes.append((int(hbox[0]), int(hbox[1]), int(hbox[2]), int(hbox[3])))
    except Exception as he:
        logger.debug(f"[Censor] 손 영역 검출 생략: {he}")

    return protection_mask, face_neg_pts, detected_face_boxes, detected_hand_boxes
