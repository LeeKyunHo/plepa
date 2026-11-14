"""
plepa_engine.censor
2D 애니메이션 일러스트 전용 자동 성기 검열(Censorship) 모듈.
- 남성기+고환 외곽선 블랙 실루엣 (Black Silhouette via MobileSAM)
- 와이드 솔리드 캡슐 바 (Wide Solid Bar)
- 슬림 사선 블랙 바 (Thin Black Bar)
- 그림자 음영 박스 (Shadow Box)
- 격자 모자이크 (Pixelated Mosaic)
"""

from __future__ import annotations

import gc
import logging
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import uuid

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

try:
    from imgutils.detect import detect_censors
    HAS_IMGUTILS = True
except ImportError:
    HAS_IMGUTILS = False

# MobileSAM 및 커스텀 YOLO-seg 모델 싱글톤 (Lazy Load, Thread-Safe)
_SAM_MODEL = None
_SAM_MODEL_LOCK = threading.Lock()
_CENSOR_SEG_MODEL = None
_CENSOR_SEG_LOCK = threading.Lock()
_BASE_RESOLUTION = 832.0


def _compute_scale_factor(width: int, height: int) -> float:
    """기준 해상도(832px) 대비 현재 이미지 비율 스케일 팩터를 계산합니다."""
    return max(0.5, float(min(max(1, width), max(1, height))) / _BASE_RESOLUTION)


def _scale_int(base: int, scale: float, minimum: int = 1) -> int:
    """스케일 팩터를 반영한 정수 픽셀 값을 반환합니다."""
    return max(minimum, int(round(base * scale)))


def _odd_kernel(base: int, scale: float, minimum: int = 3) -> int:
    """OpenCV 커널/블러용 홀수 정수 크기를 반환합니다."""
    val = max(minimum, int(round(base * scale)))
    return val if (val % 2 == 1) else (val + 1)


def _split_rgb_and_alpha(img: Image.Image) -> Tuple[Image.Image, Optional[Image.Image]]:
    """RGB 변환과 함께 알파 채널(RGBA/LA/투명 P)을 안전하게 분리 보존합니다."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        return rgba.convert("RGB"), alpha
    if img.mode == "RGB":
        return img, None
    return img.convert("RGB"), None


def _restore_alpha(rgb_img: Image.Image, alpha: Optional[Image.Image]) -> Image.Image:
    """분리된 알파 채널이 있는 경우 RGBA 이미지로 복원합니다."""
    if alpha is None:
        return rgb_img
    rgba = rgb_img.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba


def get_sam_model():
    """MobileSAM 세그멘테이션 모델을 스레드 안전하게 싱글톤 로드합니다."""
    global _SAM_MODEL
    if _SAM_MODEL is not None:
        return _SAM_MODEL if _SAM_MODEL is not False else None

    with _SAM_MODEL_LOCK:
        if _SAM_MODEL is None:
            try:
                from plepa_engine.config import ROOT_DIR
                from ultralytics import SAM

                candidate_pt = ROOT_DIR / "mobile_sam.pt"
                sam_path = str(candidate_pt) if candidate_pt.exists() else "mobile_sam.pt"
                _SAM_MODEL = SAM(sam_path)
                logger.info(f"[Censor] MobileSAM 모델 로드 완료 ({sam_path})")
            except Exception as e:
                logger.warning(f"[Censor] MobileSAM 로드 실패, OpenCV 폴백 모드로 동작합니다: {e}")
                _SAM_MODEL = False
    return _SAM_MODEL if _SAM_MODEL is not False else None


def get_custom_censor_seg_model():
    """전용 YOLO-seg 검열 가중치(`PLEPA_CENSOR_SEG_MODEL` 또는 `models/censor_seg.pt`)를 싱글톤 로드합니다."""
    global _CENSOR_SEG_MODEL
    env_override = os.environ.get("PLEPA_CENSOR_SEG_MODEL", "").strip()
    if _CENSOR_SEG_MODEL is not None and not env_override:
        return _CENSOR_SEG_MODEL if _CENSOR_SEG_MODEL is not False else None

    with _CENSOR_SEG_LOCK:
        from plepa_engine.config import ROOT_DIR

        model_path = Path(env_override) if env_override else (ROOT_DIR / "models" / "censor_seg.pt")
        if not model_path.exists() or not model_path.is_file():
            return None

        if _CENSOR_SEG_MODEL is None or _CENSOR_SEG_MODEL is False or env_override:
            try:
                from ultralytics import YOLO

                _CENSOR_SEG_MODEL = YOLO(str(model_path))
                logger.info(f"[Censor] 전용 YOLO-seg 모델 로드 완료 ({model_path})")
            except Exception as e:
                logger.warning(f"[Censor] 전용 YOLO-seg 로드 실패, MobileSAM 모드로 폴백합니다: {e}")
                _CENSOR_SEG_MODEL = False
    return _CENSOR_SEG_MODEL if _CENSOR_SEG_MODEL is not False else None


def _infer_custom_censor_seg(
    img_rgb: Image.Image,
    seg_model: Any,
    min_confidence: float = 0.16,
) -> Tuple[List[Tuple[Tuple[int, int, int, int], str, float]], Optional[np.ndarray]]:
    """전용 YOLO-seg 모델로 성기 BBox 목록과 `cv2.fillPoly` 기반 이진 세그멘테이션 마스크를 추출합니다."""
    if seg_model is None:
        return [], None

    w, h = img_rgb.size
    mask = np.zeros((h, w), dtype=np.uint8)
    boxes_out: List[Tuple[Tuple[int, int, int, int], str, float]] = []

    try:
        with _CENSOR_SEG_LOCK:
            results = seg_model(img_rgb, conf=float(min_confidence), verbose=False)
        if not results:
            return [], None

        res0 = results[0]
        res_masks = getattr(res0, "masks", None)
        res_boxes = getattr(res0, "boxes", None)
        names = getattr(res0, "names", None) or {}
        polys = getattr(res_masks, "xy", None) if res_masks is not None else None
        if polys is None or len(polys) == 0:
            return [], None

        xyxy_arr = None
        conf_arr = None
        cls_arr = None
        if res_boxes is not None:
            if getattr(res_boxes, "xyxy", None) is not None:
                xyxy_arr = res_boxes.xyxy.cpu().numpy() if hasattr(res_boxes.xyxy, "cpu") else np.asarray(res_boxes.xyxy)
            if getattr(res_boxes, "conf", None) is not None:
                conf_arr = res_boxes.conf.cpu().numpy() if hasattr(res_boxes.conf, "cpu") else np.asarray(res_boxes.conf)
            if getattr(res_boxes, "cls", None) is not None:
                cls_arr = res_boxes.cls.cpu().numpy() if hasattr(res_boxes.cls, "cpu") else np.asarray(res_boxes.cls)

        for idx, poly in enumerate(polys):
            poly_pts = np.round(np.asarray(poly, dtype=np.float32)).astype(np.int32)
            if poly_pts.ndim != 2 or len(poly_pts) < 3:
                continue
            cv2.fillPoly(mask, [poly_pts], 255)

            if xyxy_arr is not None and idx < len(xyxy_arr):
                b = xyxy_arr[idx]
                box = (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
            else:
                xs, ys = poly_pts[:, 0], poly_pts[:, 1]
                box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

            score = float(conf_arr[idx]) if (conf_arr is not None and idx < len(conf_arr)) else 0.90
            cls_id = int(cls_arr[idx]) if (cls_arr is not None and idx < len(cls_arr)) else 0
            raw_name = names.get(cls_id, "penis") if isinstance(names, dict) else "penis"
            label = "penis" if str(raw_name).lower() in ("genital", "penis", "0", "") else str(raw_name).lower()
            boxes_out.append((box, label, score))

        if np.count_nonzero(mask) == 0 or not boxes_out:
            return [], None
        return boxes_out, mask
    except Exception as e:
        logger.warning(f"[Censor] 전용 YOLO-seg 추론 예외, 기본 파이프라인으로 폴백합니다: {e}")
        return [], None


def unload_censor_models() -> None:
    """로드된 MobileSAM 및 전용 YOLO-seg 싱글톤과 GPU VRAM 캐시를 안전하게 해제합니다."""
    global _SAM_MODEL, _CENSOR_SEG_MODEL
    with _SAM_MODEL_LOCK:
        _SAM_MODEL = None
    with _CENSOR_SEG_LOCK:
        _CENSOR_SEG_MODEL = None
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

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

    geom = _estimate_penis_axis_and_base(roi_rgb, (0, 0, rw, rh), skin_np=roi_skin, pose_cat=pose_cat)
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

    skin_bool = (
        skin_np > 0
        if skin_np is not None
        else (get_skin_mask(np.array(rgb_img)) > 0)
    )

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

        hbw, hbh = max(1, hx2 - hx1), max(1, hy2 - hy1)
        single_hand_m = np.zeros((h, w), dtype=np.uint8)
        sam_ok = False

        # 양방향 앵커 수집: 손 Positive(중심+손등 외측) & 성기 노출부 Negative(손 BBox 바깥)
        hand_pos_global: List[List[int]] = [[int((hx1 + hx2) / 2), int((hy1 + hy2) / 2)]]
        mean_gx = sum((gb[0] + gb[2]) / 2.0 for gb in intersecting) / float(len(intersecting))
        outer_pt = _extract_hand_outer_skin_point(skin_bool, (hx1, hy1, hx2, hy2), mean_gx)
        if outer_pt is not None and outer_pt != hand_pos_global[0]:
            hand_pos_global.append(outer_pt)

        genital_neg_global: List[List[int]] = []
        for gbox in intersecting:
            unocc_pts, _ = _compute_mutually_exclusive_prompts(gbox, [(hx1, hy1, hx2, hy2)], skin_bool)
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

                local_pos = [
                    [px - rx1, py - ry1]
                    for px, py in hand_pos_global
                    if rx1 <= px < rx2 and ry1 <= py < ry2
                ]
                if not local_pos:
                    local_pos = [[int((hx1 + hx2) / 2) - rx1, int((hy1 + hy2) / 2) - ry1]]
                local_neg = [
                    [px - rx1, py - ry1]
                    for px, py in genital_neg_global
                    if rx1 <= px < rx2 and ry1 <= py < ry2
                ]

                all_pts = local_pos + local_neg
                all_lbls = [1] * len(local_pos) + [0] * len(local_neg)

                with _SAM_MODEL_LOCK:
                    try:
                        results = sam(
                            crop_pil,
                            bboxes=[local_hbox],
                            points=[all_pts],
                            labels=[all_lbls],
                            verbose=False,
                        )
                    except Exception:
                        results = sam(crop_pil, bboxes=[local_hbox], verbose=False)

                if results and results[0].masks is not None:
                    m_data = results[0].masks.data.cpu().numpy()
                    crop_m = (m_data[0] * 255).astype(np.uint8)
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
            erx = max(2, int(hbw * 0.38))
            ery = max(2, int(hbh * 0.38))
            cv2.ellipse(single_hand_m, (hcx, hcy), (erx, ery), 0, 0, 360, 255, -1)

        # 해상도 비례 경계 소프트 페더링 후 손 BBox 내부로 위상 클리핑 유지
        kh = _odd_kernel(7, scale, minimum=5)
        smooth_hand = cv2.GaussianBlur(single_hand_m, (kh, kh), 1.6 * scale)
        _, smooth_hand = cv2.threshold(smooth_hand, 115, 255, cv2.THRESH_BINARY)
        bbox_bounded = np.zeros((h, w), dtype=np.uint8)
        bbox_bounded[hy1:hy2, hx1:hx2] = smooth_hand[hy1:hy2, hx1:hx2]

        hand_mask = np.maximum(hand_mask, bbox_bounded)

    return hand_mask


def apply_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Any, ...]],
    color: Union[str, Tuple[int, int, int]] = "black",
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    custom_seg_mask: Optional[np.ndarray] = None,
) -> Image.Image:
    """
    네모난 박스가 아니라 타겟과 기저부의 실제 선화 외곽선(Contour)을 따라
    내부만 솔리드 컬러(블랙 #000000 또는 화이트 #FFFFFF)로 매끈하게 채우는 실루엣 검열을 렌더링합니다.
    - 전용 YOLO-seg 가중치(`models/censor_seg.pt`)가 활성화된 경우 폴리곤 마스크(`cv2.fillPoly`)를 우선 사용합니다.
    - 미존재/미탐지 시 ADR-86 기준선(내측 8% 수축 + 전경 손 실루엣 하드 차감 + MobileSAM ROI 크롭)으로 폴백합니다.
    """
    rgb_img, alpha_ch = _split_rgb_and_alpha(img)
    w, h = rgb_img.size
    scale = _compute_scale_factor(w, h)
    img_np = np.array(rgb_img)

    # 0. 눈/이마(Upper Face 38%) 보호 마스크 및 얼굴 중심 네거티브 포인트 추출:
    #    - 입이나 뺨을 직각으로 파내지 않도록 오직 눈·이마(상단 38%)만 소프트 보호
    protection_mask = np.zeros((h, w), dtype=np.uint8)
    face_neg_pts: List[List[int]] = []
    try:
        from imgutils.detect import detect_faces
        detected_faces = detect_faces(rgb_img, conf_threshold=0.35)

        for (fx1, fy1, fx2, fy2), _, _ in detected_faces:
            fh = max(1, fy2 - fy1)
            safe_fy2 = int(fy1 + fh * 0.38)
            if safe_fy2 > fy1:
                cv2.rectangle(protection_mask, (int(fx1), int(fy1)), (int(fx2), safe_fy2), 255, -1)
            face_neg_pts.append([int((fx1 + fx2) / 2), int(fy1 + fh * 0.42)])

        if np.count_nonzero(protection_mask) > 0:
            pk = _odd_kernel(15, scale)
            protection_mask = cv2.GaussianBlur(protection_mask, (pk, pk), 4.0 * scale)
            _, protection_mask = cv2.threshold(protection_mask, 128, 255, cv2.THRESH_BINARY)
    except Exception as pe:
        logger.debug(f"[Censor] 보호 영역 검출 생략: {pe}")

    # 손 가려짐(Occlusion) 전경 박스 검출 (conf >= 0.45, detect_faces와 독립 격리)
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

    genital_boxes_raw: List[Tuple[int, int, int, int]] = [
        (int(it[0][0]), int(it[0][1]), int(it[0][2]), int(it[0][3]))
        for it in boxes_with_labels
        if it and isinstance(it[0], (tuple, list)) and len(it[0]) >= 4
    ]

    eff_skin_np = skin_np if skin_np is not None else get_skin_mask(img_np)

    # 전용 YOLO-seg 마스크 직접 렌더링 경로 (전달된 마스크 또는 활성화된 모델 추론)
    active_seg_mask = custom_seg_mask
    if active_seg_mask is None and boxes_with_labels:
        seg_model = get_custom_censor_seg_model()
        if seg_model is not None:
            _, active_seg_mask = _infer_custom_censor_seg(rgb_img, seg_model)

    if active_seg_mask is not None and np.count_nonzero(active_seg_mask) > 0:
        # YOLO-seg 경로에서는 get_sam_model() 호출 없이 보수적 손 보호 마스크만 병합
        if detected_hand_boxes and genital_boxes_raw:
            seg_hand_mask = _extract_hand_occlusion_mask(
                rgb_img,
                None,
                detected_hand_boxes,
                genital_boxes_raw,
                scale,
                skin_np=eff_skin_np,
            )
            if np.count_nonzero(seg_hand_mask) > 0:
                protection_mask = np.maximum(protection_mask, seg_hand_mask)

        seg_bin = (active_seg_mask > 0).astype(np.uint8) * 255
        if seg_bin.shape != (h, w):
            seg_bin = cv2.resize(seg_bin, (w, h), interpolation=cv2.INTER_NEAREST)

        kc_seg = _odd_kernel(5, scale, minimum=3)
        k_close_seg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc_seg, kc_seg))
        seg_bin = cv2.morphologyEx(seg_bin, cv2.MORPH_CLOSE, k_close_seg)

        if np.count_nonzero(protection_mask) > 0:
            seg_bin = cv2.bitwise_and(seg_bin, cv2.bitwise_not(protection_mask))

        if np.count_nonzero(seg_bin) == 0:
            return img

        kf_seg = _odd_kernel(5, scale, minimum=3)
        blurred_seg = cv2.GaussianBlur(seg_bin, (kf_seg, kf_seg), 1.2 * scale)
        if isinstance(color, str):
            color_rgb = (255, 255, 255) if color.lower() in ("white", "whiteout", "white_silhouette") else (12, 12, 16)
        else:
            color_rgb = color

        alpha = (blurred_seg.astype(np.float32) / 255.0)[:, :, np.newaxis]
        target_layer = np.full_like(img_np, color_rgb, dtype=np.float32)
        blended = (1.0 - alpha) * img_np.astype(np.float32) + alpha * target_layer
        blended = np.clip(blended, 0, 255).astype(np.uint8)
        return _restore_alpha(Image.fromarray(blended), alpha_ch)

    final_mask = np.zeros((h, w), dtype=np.uint8)
    sam = get_sam_model()
    hand_occ_mask = _extract_hand_occlusion_mask(
        rgb_img,
        sam,
        detected_hand_boxes,
        genital_boxes_raw,
        scale,
        skin_np=eff_skin_np,
    )
    if np.count_nonzero(hand_occ_mask) > 0:
        protection_mask = np.maximum(protection_mask, hand_occ_mask)
    asym_thresh = 1.15 if pose_cat in ("fellatio", "paizuri") else 1.35

    for item in boxes_with_labels:
        box = item[0]
        x1, y1, x2, y2 = box
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)

        # ADR-86 기준선: BBox 내측 8% 수축으로 주변 허벅지·손가락 여백 침범 방어
        inset_x = int(bw * 0.08)
        inset_y = int(bh * 0.08)
        ex1 = max(0, x1 + inset_x)
        ey1 = max(0, y1 + inset_y)
        ex2 = min(w, x2 - inset_x)
        ey2 = min(h, y2 - inset_y)
        if ex2 <= ex1 or ey2 <= ey1:
            ex1, ey1, ex2, ey2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)

        ebw = max(1, ex2 - ex1)
        ebh = max(1, ey2 - ey1)
        sub_m = np.zeros((h, w), dtype=np.uint8)
        sam_succeeded = False

        if sam is not None:
            try:
                # 1) BBox 내부의 타겟 피부 영역과 비타겟(창문/책장/벽/어두운 허공) 영역을 분리합니다.
                roi_rgb = img_np[ey1:ey2, ex1:ex2]
                roi_hsv = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2HSV)
                roi_skin = eff_skin_np[ey1:ey2, ex1:ex2] > 0

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

                pos_pts: List[List[int]] = []
                local_neg_pts: List[List[int]] = list(face_neg_pts)
                box_hand_boxes: List[Tuple[int, int, int, int]] = [
                    (hx1, hy1, hx2, hy2)
                    for hx1, hy1, hx2, hy2 in detected_hand_boxes
                    if max(x1, hx1) < min(x2, hx2) and max(y1, hy1) < min(y2, hy2)
                ]

                def _is_in_hand_boxes(px: int, py: int) -> bool:
                    return any(hx1 <= px <= hx2 and hy1 <= py <= hy2 for hx1, hy1, hx2, hy2 in box_hand_boxes)

                # 하단 기저부 포인트 및 반대쪽 턱 밑 허공(Void Corner) 보수적 판정
                void_corner_mask = np.zeros((h, w), dtype=np.uint8)
                if l_score > r_score * asym_thresh:
                    cand_bot = [int(ex1 + ebw * 0.24), int(ey1 + ebh * 0.72)]
                    local_neg_pts.append([int(ex1 + ebw * 0.76), int(ey1 + ebh * 0.78)])
                    cv2.rectangle(
                        void_corner_mask,
                        (int(ex1 + ebw * 0.44), int(ey1 + ebh * 0.48)),
                        (ex2, ey2),
                        255,
                        -1,
                    )
                elif r_score > l_score * asym_thresh:
                    cand_bot = [int(ex1 + ebw * 0.76), int(ey1 + ebh * 0.72)]
                    local_neg_pts.append([int(ex1 + ebw * 0.24), int(ey1 + ebh * 0.78)])
                    cv2.rectangle(
                        void_corner_mask,
                        (ex1, int(ey1 + ebh * 0.48)),
                        (int(ex1 + ebw * 0.56), ey2),
                        255,
                        -1,
                    )
                else:
                    cand_bot = [int((ex1 + ex2) / 2), int(ey1 + ebh * 0.68)]

                if box_hand_boxes:
                    unocc_pts, hand_neg_pts = _compute_mutually_exclusive_prompts(
                        (ex1, ey1, ex2, ey2),
                        box_hand_boxes,
                        eff_skin_np > 0,
                    )
                    for hpt in hand_neg_pts:
                        if hpt not in local_neg_pts:
                            local_neg_pts.append(hpt)
                    for upt in unocc_pts:
                        if not _is_in_hand_boxes(upt[0], upt[1]) and upt not in pos_pts:
                            pos_pts.append(upt)
                    if not _is_in_hand_boxes(cand_bot[0], cand_bot[1]) and cand_bot not in pos_pts:
                        pos_pts.append(cand_bot)
                else:
                    top_ys, top_xs = np.where(top_skin)
                    if len(top_xs) >= 10:
                        pos_pts.append([ex1 + int(np.median(top_xs)), ey1 + int(ebh * 0.12) + int(np.median(top_ys))])
                    else:
                        pos_pts.append([int((ex1 + ex2) / 2), int(ey1 + ebh * 0.30)])
                    pos_pts.append(cand_bot)

                if not pos_pts:
                    pos_pts.append([int((ex1 + ex2) / 2), int(ey1 + ebh * 0.22)])

                sam_union = np.zeros((h, w), dtype=np.uint8)
                crop_mask = np.zeros((h, w), dtype=np.uint8)
                rad = max(_scale_int(4, scale, 3), int(min(ebw, ebh) * 0.40))
                sub_c = np.zeros((ebh, ebw), dtype=np.uint8)
                if ebw > rad * 2 and ebh > rad * 2:
                    cv2.rectangle(sub_c, (rad, 0), (ebw - rad, ebh), 255, -1)
                    cv2.rectangle(sub_c, (0, rad), (ebw, ebh - rad), 255, -1)
                    cv2.circle(sub_c, (rad, rad), rad, 255, -1)
                    cv2.circle(sub_c, (ebw - rad, rad), rad, 255, -1)
                    cv2.circle(sub_c, (rad, ebh - rad), rad, 255, -1)
                    cv2.circle(sub_c, (ebw - rad, ebh - rad), rad, 255, -1)
                else:
                    cv2.ellipse(sub_c, (int(ebw / 2), int(ebh / 2)), (int(ebw / 2), int(ebh / 2)), 0, 0, 360, 255, -1)
                crop_mask[ey1:ey2, ex1:ex2] = sub_c

                # VRAM 절감 및 고해상도 정밀도 향상을 위한 ROI Padded Crop 기반 SAM 추론
                pad_x = max(_scale_int(64, scale, 32), int(bw * 0.45))
                pad_y = max(_scale_int(64, scale, 32), int(bh * 0.45))
                rx1 = max(0, ex1 - pad_x)
                ry1 = max(0, ey1 - pad_y)
                rx2 = min(w, ex2 + pad_x)
                ry2 = min(h, ey2 + pad_y)
                cw, ch = max(1, rx2 - rx1), max(1, ry2 - ry1)
                crop_pil = rgb_img.crop((rx1, ry1, rx2, ry2))
                local_bbox = [ex1 - rx1, ey1 - ry1, ex2 - rx1, ey2 - ry1]
                neg_in_crop = [
                    [px - rx1, py - ry1]
                    for px, py in local_neg_pts
                    if rx1 <= px < rx2 and ry1 <= py < ry2
                ]
                min_raw_pixels = _scale_int(60, scale * scale, minimum=25)

                for pt in pos_pts:
                    local_pt = [pt[0] - rx1, pt[1] - ry1]
                    all_pts = [local_pt] + neg_in_crop
                    all_lbls = [1] + [0] * len(neg_in_crop)
                    with _SAM_MODEL_LOCK:
                        try:
                            results = sam(
                                crop_pil,
                                bboxes=[local_bbox],
                                points=[all_pts],
                                labels=[all_lbls],
                                verbose=False,
                            )
                        except Exception:
                            results = sam(crop_pil, bboxes=[local_bbox], verbose=False)

                    if results and results[0].masks is not None:
                        m_data = results[0].masks.data.cpu().numpy()
                        crop_m = (m_data[0] * 255).astype(np.uint8)
                        if crop_m.shape != (ch, cw):
                            crop_m = cv2.resize(crop_m, (cw, ch), interpolation=cv2.INTER_NEAREST)
                        raw_m = np.zeros((h, w), dtype=np.uint8)
                        raw_m[ry1:ry2, rx1:rx2] = crop_m
                        raw_m = cv2.bitwise_and(raw_m, crop_mask)
                        if np.count_nonzero(raw_m) >= min_raw_pixels:
                            sam_union = np.maximum(sam_union, raw_m)

                # 턱 밑 허공 코너가 감지된 경우 부드러운 알파 감산으로 코너 배경만 덜어냄
                if np.count_nonzero(void_corner_mask) > 0:
                    vk = _odd_kernel(21, scale)
                    soft_void = cv2.GaussianBlur(void_corner_mask, (vk, vk), 6.0 * scale)
                    void_weight = 1.0 - (soft_void.astype(np.float32) / 255.0)
                    sam_union = np.clip(sam_union.astype(np.float32) * void_weight, 0, 255).astype(np.uint8)
                    _, sam_union = cv2.threshold(sam_union, 127, 255, cv2.THRESH_BINARY)

                # BBox 내부 엄격 클리핑 + ADR-86 기준선(3x3 침식) + 전경 손 실루엣 선차감
                sam_union = cv2.bitwise_and(sam_union, crop_mask)
                ke = _odd_kernel(3, scale, minimum=3)
                k_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ke, ke))
                sam_union = cv2.erode(sam_union, k_erode, iterations=1)
                if np.count_nonzero(hand_occ_mask) > 0:
                    sam_union = cv2.bitwise_and(sam_union, cv2.bitwise_not(hand_occ_mask))

                # connectedComponentsWithStats로 내부 구멍(손가락/배경 파임)을 메우지 않고 보존
                num_labels, labels_im, stats, _ = cv2.connectedComponentsWithStats(sam_union, connectivity=8)
                if num_labels > 1:
                    areas = stats[1:, cv2.CC_STAT_AREA]
                    max_area = float(areas.max())
                    min_cnt_area = max(_scale_int(60, scale * scale, minimum=25), max_area * 0.15)
                    for lbl_idx in range(1, num_labels):
                        if stats[lbl_idx, cv2.CC_STAT_AREA] >= min_cnt_area:
                            sub_m[labels_im == lbl_idx] = 255
                    if np.count_nonzero(sub_m) >= (bw * bh * 0.06):
                        sam_succeeded = True
            except Exception as e:
                logger.warning(f"[Censor] MobileSAM fallback: {e}")

        # MobileSAM이 실패한 경우에만 ADR-86 슬림 타원 캡슐로 폴백
        if not sam_succeeded:
            bcx = int((ex1 + ex2) / 2)
            bcy = int((ey1 + ey2) / 2)
            erx = min(int(w * 0.12), max(_scale_int(4, scale, 3), int(ebw * 0.40)))
            ery = min(int(h * 0.16), max(_scale_int(4, scale, 3), int(ebh * 0.46)))
            cv2.ellipse(sub_m, (bcx, bcy), (erx, ery), 0, 0, 360, 255, -1)

        final_mask = np.maximum(final_mask, sub_m)

    if np.count_nonzero(final_mask) == 0:
        return img

    # 5. ADR-86 기준선: 3x3 미세 침식 + 5x5 모폴로지 닫힘 + 경계 스무딩
    ke_f = _odd_kernel(3, scale, minimum=3)
    kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ke_f, ke_f))
    eroded = cv2.erode(final_mask, kernel_erode, iterations=1)

    kc = _odd_kernel(5, scale, minimum=3)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc, kc))
    closed = cv2.morphologyEx(eroded, cv2.MORPH_CLOSE, kernel_close)

    ks = _odd_kernel(5, scale, minimum=3)
    smooth_blur = cv2.GaussianBlur(closed, (ks, ks), 1.2 * scale)
    _, smoothed = cv2.threshold(smooth_blur, 140, 255, cv2.THRESH_BINARY)

    # 얼굴 상단(눈/이마 38%) + 전경 손(Hand) 실루엣 보호 레이어 차감
    if np.count_nonzero(protection_mask) > 0:
        smoothed = cv2.bitwise_and(smoothed, cv2.bitwise_not(protection_mask))

    if np.count_nonzero(smoothed) == 0:
        return img

    # 6. ADR-86 소프트 에지 페더링 (9x9, sigma 2.5*scale)
    kf = _odd_kernel(9, scale, minimum=5)
    blurred = cv2.GaussianBlur(smoothed, (kf, kf), 2.5 * scale)

    # 색상 레이어 합성 (블랙 실루엣은 애니메이션 먹선 톤 (12, 12, 16) 적용)
    if isinstance(color, str):
        color_rgb = (255, 255, 255) if color.lower() in ("white", "whiteout", "white_silhouette") else (12, 12, 16)
    else:
        color_rgb = color

    alpha = (blurred.astype(np.float32) / 255.0)[:, :, np.newaxis]
    target_layer = np.full_like(img_np, color_rgb, dtype=np.float32)
    blended = (1.0 - alpha) * img_np.astype(np.float32) + alpha * target_layer
    blended = np.clip(blended, 0, 255).astype(np.uint8)

    return _restore_alpha(Image.fromarray(blended), alpha_ch)


def apply_black_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Any, ...]],
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    custom_seg_mask: Optional[np.ndarray] = None,
) -> Image.Image:
    """블랙 실루엣(#000000) 검열 래퍼 함수."""
    return apply_silhouette(
        img,
        boxes_with_labels,
        color="black",
        skin_np=skin_np,
        pose_cat=pose_cat,
        custom_seg_mask=custom_seg_mask,
    )


def apply_white_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Any, ...]],
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    custom_seg_mask: Optional[np.ndarray] = None,
) -> Image.Image:
    """화이트 실루엣(#FFFFFF) 검열 래퍼 함수."""
    return apply_silhouette(
        img,
        boxes_with_labels,
        color="white",
        skin_np=skin_np,
        pose_cat=pose_cat,
        custom_seg_mask=custom_seg_mask,
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


def _normalize_censor_boxes(boxes: Sequence[Any]) -> List[Tuple[int, int, int, int]]:
    """단순 4-튜플 BBox 또는 `(bbox, label, conf)` 시퀀스를 `(x1, y1, x2, y2)` 리스트로 정규화합니다."""
    normalized: List[Tuple[int, int, int, int]] = []
    for item in boxes:
        raw = item[0] if isinstance(item, (list, tuple)) and item and isinstance(item[0], (list, tuple)) else item
        normalized.append((int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3])))
    return normalized


def _to_rgb_ndarray(img_or_np: Union[Image.Image, np.ndarray]) -> np.ndarray:
    """PIL Image 또는 NumPy 배열을 RGB uint8 `(H, W, 3)` 배열로 변환합니다."""
    if isinstance(img_or_np, np.ndarray):
        if img_or_np.ndim == 2:
            return cv2.cvtColor(img_or_np, cv2.COLOR_GRAY2RGB)
        if img_or_np.shape[2] == 4:
            return img_or_np[:, :, :3]
        return img_or_np
    return np.array(img_or_np.convert("RGB"), dtype=np.uint8)


def _extract_roi_foreground_mask(roi_rgb: np.ndarray, roi_skin: Optional[np.ndarray]) -> np.ndarray:
    """ROI 내부의 피부 또는 배경 대비 전경 픽셀 마스크(`bool`)를 추출합니다."""
    rh, rw = roi_rgb.shape[:2]
    area = max(1, rh * rw)
    min_px = max(16, int(area * 0.03))

    skin_bool = (roi_skin > 0) if roi_skin is not None else (get_skin_mask(roi_rgb) > 0)
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
    skin_mask = skin_np if skin_np is not None else get_skin_mask(img_np)
    scale = _compute_scale_factor(w_img, h_img)
    min_bar_w = _scale_int(10, scale, minimum=5)

    mask = np.zeros((h_img, w_img), dtype=np.uint8)
    for (x1, y1, x2, y2) in norm_boxes:
        geom = _estimate_penis_axis_and_base(img_np, (x1, y1, x2, y2), skin_np=skin_mask, pose_cat=pose_cat)
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
    skin_mask = skin_np if skin_np is not None else get_skin_mask(img_np)
    scale = _compute_scale_factor(w_img, h_img)
    min_cap_w = _scale_int(10, scale, minimum=5)
    fk = _odd_kernel(13, scale, minimum=5)

    alpha_total = np.zeros((h_img, w_img), dtype=np.float32)
    for (x1, y1, x2, y2) in norm_boxes:
        geom = _estimate_penis_axis_and_base(img_np, (x1, y1, x2, y2), skin_np=skin_mask, pose_cat=pose_cat)
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


def _render_censored_style(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Any, ...]],
    style: str = "white_silhouette",
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
    custom_seg_mask: Optional[np.ndarray] = None,
) -> Image.Image:
    """검열 스타일명(`style`)에 대응하는 렌더러로 일관되게 라우팅합니다."""
    detected_boxes = [item[0] for item in boxes_with_labels]
    style_clean = str(style or "white_silhouette").lower().strip()

    if style_clean in ("debug", "debug_bbox", "bbox", "bbox_debug"):
        return apply_debug_bbox(img, boxes_with_labels)
    if style_clean in ("white_silhouette", "white", "whiteout"):
        return apply_white_silhouette(
            img,
            boxes_with_labels,
            skin_np=skin_np,
            pose_cat=pose_cat,
            custom_seg_mask=custom_seg_mask,
        )
    if style_clean in ("black_silhouette", "silhouette_black", "black", "silhouette", "contour"):
        return apply_black_silhouette(
            img,
            boxes_with_labels,
            skin_np=skin_np,
            pose_cat=pose_cat,
            custom_seg_mask=custom_seg_mask,
        )
    if style_clean in ("manga_bar", "manga_black_bar", "haetae"):
        return apply_manga_bar(img, detected_boxes, skin_np=skin_np, pose_cat=pose_cat)
    if style_clean in ("manga_glow", "manga_white", "glow_bar"):
        return apply_manga_glow(img, detected_boxes, skin_np=skin_np, pose_cat=pose_cat)
    if style_clean in ("bar", "wide_bar", "solid_bar", "black_bar", "pill_bar"):
        return apply_wide_solid_bar(img, detected_boxes)
    if style_clean in ("slim_bar", "thin_bar"):
        return apply_slim_black_bar(img, detected_boxes)
    if style_clean in ("shadow", "shadow_box", "shadow_silhouette"):
        return apply_shadow_silhouette(img, detected_boxes)
    if style_clean in ("mosaic", "pixel"):
        return apply_mosaic(img, detected_boxes)
    return apply_white_silhouette(
        img,
        boxes_with_labels,
        skin_np=skin_np,
        pose_cat=pose_cat,
        custom_seg_mask=custom_seg_mask,
    )


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

        # 가시성을 위한 3px 두께 직사각형 테두리
        for off in range(3):
            draw.rectangle([x1 - off, y1 - off, x2 + off, y2 + off], outline=color)

        # 상단 캡션 뱃지 배경 (검은 반투명 효과용 솔리드 블랙)
        badge_h = 16
        text_w = max(45, len(caption) * 7 + 8)
        bx2 = min(out.width, x1 + text_w)
        by1 = max(0, y1 - badge_h)
        draw.rectangle([x1, by1, bx2, y1], fill=(20, 20, 20))
        draw.text((x1 + 4, by1 + 2), caption, fill=color)

    return out


# 체위별 안전 앵커 바운딩 박스 (정규화 좌표: [x0, y0, x1, y1])
POSE_SAFE_ANCHORS = {
    "missionary":  [0.34, 0.58, 0.66, 0.84],   # 정상위/배위: 하단 중앙 영역
    "doggystyle":  [0.40, 0.60, 0.60, 0.74],   # 후배위: 결합 중심 슬림 앵커
    "cowgirl":     [0.34, 0.60, 0.66, 0.86],   # 기승위: 하단 기저부
    "fellatio":    [0.36, 0.38, 0.64, 0.60],   # 상반신·얼굴 밀착 구강: 중상단 입/접촉부
    "paizuri":     [0.34, 0.40, 0.66, 0.68],   # 상반신·바스트 밀착: 가슴 중심 결합부
    "piledriver":  [0.36, 0.08, 0.64, 0.38],   # 역전 파일드라이버: 상단 중앙 결합부
    "side":        [0.35, 0.55, 0.65, 0.82],   # 측와위: 측면 교차부
    "standing":    [0.34, 0.44, 0.66, 0.72],   # 입위(서서 하는 체위): 중앙 허리~골반 높이
    "shower":      [0.34, 0.48, 0.66, 0.76],   # 샤워실/수중 체위: 중앙 결합부
    "cunnilingus": [0.45, 0.65, 0.55, 0.75],   # 애무: 미사용 (검열 면제)
    "handjob":     [0.34, 0.48, 0.66, 0.74],   # 대딸/핸드잡: 중하단 손 위치
    "footjob":     [0.34, 0.52, 0.66, 0.80],   # 풋잡: 하단 발 위치
    "spanking":    [0.34, 0.48, 0.66, 0.78],   # 스팽킹: 둔부/엉덩이 중심
    "default_h":   [0.34, 0.56, 0.66, 0.84],   # 기본 성인 결합 씬
}

# 다중 표본(N>=9) 실측 벤치마크 기반 포즈별 고유 정밀 앵커 좌표 (x0, y0, x1, y1)
# 범용 카테고리 앵커보다 최우선 적용되어 미탐지 폴백 시에도 정확한 실제 결합 부위에 마스킹 안착
POSE_EXACT_ANCHORS: Dict[str, List[float]] = {
    # 088 후배위약: 좌측 측면 배면 결합 (N=9 실측 평균 X=0.14, Y=0.73 기반 정밀 바운딩)
    "067": [0.10, 0.20, 0.40, 0.65],  # 067 딥스로트: 좌측 구강 결합 (N=9 실측 X=0.25, Y=0.35)
    "072": [0.35, 0.55, 0.65, 0.90],  # 072 파이즈리: 정면 바스트 중앙 결합 (N=9 실측 X=0.50, Y=0.68)
    "088": [0.04, 0.66, 0.26, 0.88],
    "116": [0.38, 0.10, 0.66, 0.45],  # 116 파일드라이버: 상단 반전 결합 (N=9 실측 X=0.53, Y=0.25)
    "186": [0.38, 0.10, 0.66, 0.45],  # 186 오토코노코 파일드라이버 (+70)
    "158": [0.04, 0.66, 0.26, 0.88],  # 오토코노코 대칭 (+70)
}

# 100% 완전 착의 감정 표현 대역 (000~019)
EXEMPT_EMOTION_CODES = frozenset(f"{i:03d}" for i in range(0, 20))

# 100% 완전 착의 일상 이벤트 대역 (051~059)
EXEMPT_DAILY_EVENT_CODES = frozenset(f"{i:03d}" for i in range(51, 60))

# 일상 포즈(020~050) 중 남성 관련 노출 씬 (사용자 정책: 여성 단독 노출 씬 030,038,039,044,045는 검열 면제)
DAILY_EXPOSURE_CODES = frozenset({
    "037",  # 붓카케 (파트너 사정 흔적)
})

# 로맨스(060~079) 중 비노출/착의 씬 (성기 노출 없음)
ROMANCE_NON_EXPOSURE_CODES = frozenset({
    "060",  # 딥키스 (완전 착의 밀착 키스)
    "061",  # 알몸키스 (상체 밀착 키스)
})

# H씬(080~139, 150~209)은 모델 생성 편차로 인한 우발적 노출까지 100% 포착하기 위해 면제 없이 전수 YOLO 스캔 수행
# 남성 결합 부위가 일체 등장하지 않는 포즈 대역 (애무, 커닐링구스, 착의 전희, 사후 여운 등)
# 사용자 정책: 여성 신체 부위는 검열 대상에서 완전 제외하므로, 남성 결합 대상이 없는 포즈는 검열 원천 면제
NON_EXPOSURE_H_POSES: frozenset[str] = frozenset({
    "081",  # 대면좌위 (파트너 등 뒤 뷰 -> 결합 부위 가려짐/비노출)
    "082",  # 대면좌위절정 (클로즈업 비노출)
    "083",  # 누워절정여운 (여성 솔로 사후 여운 -> 남성 없음)
    "084",  # 엎드려절정여운 (여성 솔로 사후 여운 -> 남성 없음)
    "101",  # 펠라사후 (사후 여운)
    "109",  # 커닐링구스 (여성 대상 구강 애무 -> 남성 결합 부위 없음)
    "110",  # 보지애무약 (손가락 애무 -> 남성 결합 부위 없음)
    "111",  # 보지애무강 (손가락 애무 -> 남성 결합 부위 없음)
    "112",  # 착의섹스 전 (치마 걷기/전희 -> 결합 전 비노출)
    "114",  # 착의섹스 후 (사후 여운)
    "115",  # 필로우토크 (사후 대화)
    "123",  # 전라유혹 (여성 단독 포즈)
    # 오토코노코 대칭 (+70)
    "151",  # 대면좌위 (<-081)
    "152",  # 대면좌위절정 (<-082)
    "153",  # 침대사후 (<-083)
    "154",  # 후방사후 (<-084)
    "171",  # 펠라사후
    "179",  # 구강애무받기 (<-109)
    "180",  # 후방애무약 (<-110)
    "181",  # 후방애무강 (<-111)
    "182",  # 착의섹스 전 (<-112)
    "184",  # 착의섹스 후 (<-114)
    "185",  # 필로우토크 (<-115)
    "193",  # 배복종자세 (<-123)
})


def is_pose_censor_required(
    pose_code: Union[str, int, None] = None,
    pose: Any = None,
    is_nude: bool = False,
    file_path: Union[str, Path, None] = None,
    roster: Optional[str] = None,
) -> bool:
    """
    2대 서브폴더 구조(01_normal, 02_h_scenes) 및 포즈 코드에 기반하여 해당 포즈/에셋이 검열 대상인지 엄격히 판정합니다:
    - 01_normal (000~059):
      * 000~019 (감정표현): 완전 착의 -> False (절대 면제)
      * 051~059 (일상 이벤트): 완전 착의 -> False (절대 면제)
      * 020~050 (범용 일상): DAILY_EXPOSURE_CODES({"037"})만 True, 나머지(여성 단독 노출 포함) False
    - 02_h_scenes (060~209+):
      * 060~079 (로맨스/구강): 060,061(키스)은 False (절대 면제), 062~079는 True
      * 080~209 (범용/특색 H씬): NON_EXPOSURE_H_POSES(081~084, 101, 109~112, 114, 115, 123 등 및 오토코노코 대칭)는 False, 나머지 True
    """
    # 1. 파일 경로 기반 서브폴더 1차 검사 (01_emotions, 03_events는 무조건 면제)
    if file_path is not None:
        p_str = str(file_path).replace("\\", "/")
        if "/01_emotions/" in p_str or "/03_events/" in p_str:
            return False

    # 2. 포즈 객체 및 코드 추출
    code_str = None
    if pose_code is not None:
        try:
            code_str = str(int(str(pose_code).strip())).zfill(3)
        except (ValueError, TypeError):
            code_str = str(pose_code).strip()
    elif pose is not None and hasattr(pose, "code"):
        try:
            code_str = str(int(str(pose.code).strip())).zfill(3)
        except (ValueError, TypeError):
            code_str = str(pose.code).strip()
    elif file_path is not None:
        m = re.search(r"_([A-Za-z]\d{2,3}|\d{3})(?:_|\.)", Path(file_path).name)
        if m:
            code_str = m.group(1).upper()

    if not code_str:
        return False

    # 알파벳 코드(N01 등) 중 explicit 성인 접두사 판별
    if len(code_str) >= 2 and code_str[0] == "N" and code_str[1:].isdigit():
        return True

    # 3. 비노출 면제 대역 판정
    if code_str in EXEMPT_EMOTION_CODES:
        return False
    if code_str in EXEMPT_DAILY_EVENT_CODES:
        return False
    if code_str in ROMANCE_NON_EXPOSURE_CODES:
        return False
    if code_str in NON_EXPOSURE_H_POSES:
        return False

    try:
        c_int = int(code_str)
    except ValueError:
        return False

    # 4. 일상 포즈(020~050): 명시적 탈의 씬 또는 is_nude일 때만 검열
    if 20 <= c_int <= 50:
        return code_str in DAILY_EXPOSURE_CODES or is_nude

    # 5. 로맨스(060~079): 064~079(공용 구강/바스트/핸드잡/풋잡/스마타) 및 062, 063(함께씻기, 스푸닝)
    if 60 <= c_int <= 79:
        return c_int in (62, 63) or (64 <= c_int <= 79) or is_nude

    # 6. 성인 H씬 대역 (080~139 여성, 150~209 오토코노코)
    if (80 <= c_int <= 139) or (150 <= c_int <= 209):
        return True

    return False


_POSE_DB_CACHE: Dict[str, dict] = {}
_POSE_DB_CACHE_LOCK = threading.Lock()


def _normalize_censor_targets(targets: Sequence[str] = ("penis",)) -> set[str]:
    """검열 대상 라벨 시퀀스를 정규화된 소문자 집합으로 변환합니다 ('all' 지원)."""
    raw = {str(t).strip().lower() for t in (targets or ()) if str(t).strip()}
    if not raw:
        return {"penis"}
    if "all" in raw:
        return {"penis", "pussy"}
    return raw


def _get_cached_pose_db(roster: Optional[str] = None) -> dict:
    """로스터별 포즈 DB를 스레드 안전하게 지연 로드하여 체위 카테고리 동적 추론에 활용합니다."""
    from plepa_engine.config import DEFAULT_ROSTER

    eff_roster = (roster or DEFAULT_ROSTER).strip() or DEFAULT_ROSTER
    with _POSE_DB_CACHE_LOCK:
        cached = _POSE_DB_CACHE.get(eff_roster)
    if cached is not None:
        return cached

    try:
        from plepa_engine.services.pose_service import default_pose_service
        loaded = default_pose_service.load_pose_db(engine="sdxl", roster=eff_roster)
    except Exception:
        loaded = {}

    with _POSE_DB_CACHE_LOCK:
        _POSE_DB_CACHE.setdefault(eff_roster, loaded)
        return _POSE_DB_CACHE[eff_roster]


def get_pose_category(pose_code: Union[str, int], roster: Optional[str] = None) -> Optional[str]:
    """
    포즈 DB의 프롬프트 및 라벨 메타데이터를 기반으로 체위 카테고리를 동적으로 판정합니다.
    포즈 DB가 수정되면 별도 하드코딩 수정 없이 자동으로 연동됩니다.
    """
    code_str = str(pose_code).zfill(3)
    if code_str in NON_EXPOSURE_H_POSES:
        return None

    try:
        code_int = int(code_str)
    except ValueError:
        return None

    if not ((64 <= code_int <= 79) or (80 <= code_int <= 139) or (150 <= code_int <= 209)):
        return None

    db = _get_cached_pose_db(roster=roster)
    entry = db.get(code_str)
    if entry is not None:
        label = (entry.label or "").lower()
        prompt = (entry.prompt or "").lower()
        combined = f"{label} {prompt}"

        # 0. 역전 파일드라이버 (상단 결합 구도: 116, 186 등)
        if any(kw in combined for kw in ("piledriver", "upside-down", "inverted position", "파일드라이버")):
            return "piledriver"

        # 1. 바스트 밀착 단독 (구강 복합이 아닌 순수 바스트 밀착)
        if ("paizuri" in combined or "titfuck" in combined or "파이즈리" in label or "가슴사정" in label) and "fellatio" not in combined and "펠라" not in label:
            return "paizuri"

        # 2. 상반신 구강/손 밀착
        if any(kw in combined for kw in ("fellatio", "blowjob", "deepthroat", "licking shaft", "licking penis", "펠라", "딥스로트", "남근핥기", "수유대딸", "가슴애무대딸")):
            return "fellatio"

        # 3. 후배위/배면
        if any(kw in combined for kw in ("doggystyle", "sex from behind", "anal doggystyle", "후배위", "교배프레스", "뒷스마타", "빈강의실")):
            return "doggystyle"

        # 4. 기승위/상위
        if any(kw in combined for kw in ("cowgirl", "straddling", "riding partner", "기승위", "보건실")):
            return "cowgirl"

        # 5. 측와위
        if any(kw in combined for kw in ("side by side sex", "측위", "들박")):
            return "side"

        # 6. 입위(서서 하는 체위)
        if any(kw in combined for kw in ("standing sex", "입위", "들박")):
            return "standing"

        # 7. 샤워실/수중 체위
        if any(kw in combined for kw in ("shower sex", "샤워", "욕실")):
            return "shower"

        # 8. 애무/커닐링구스/핑거링
        if any(kw in combined for kw in ("cunnilingus", "fingering", "보지애무", "구강애무", "후방애무", "커닐링구스")):
            return "cunnilingus"

        # 9. 핸드잡/대딸
        if any(kw in combined for kw in ("handjob", "대딸", "핸드잡", "백허그대딸")):
            return "handjob"

        # 10. 풋잡
        if any(kw in combined for kw in ("footjob", "풋잡")):
            return "footjob"

        # 11. 스팽킹
        if any(kw in combined for kw in ("spanking", "스팽킹")):
            return "spanking"

        # 12. 정상위/배위/누운 자세
        if any(kw in combined for kw in ("missionary", "정상위", "대면좌위", "삽입조르기", "웨딩섹스", "알몸섹스절정", "m자개각", "밀착절정")):
            return "missionary"

    return "default_h"


def get_pose_anchor_box(
    pose_code: Union[str, int],
    img_width: int,
    img_height: int,
    roster: Optional[str] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """
    포즈 코드에 해당하는 안전 앵커 픽셀 바운딩 박스 (x1, y1, x2, y2)를 계산하여 반환합니다.
    1순위: N>=9 실측 벤치마크 기반 포즈 고유 앵커 (POSE_EXACT_ANCHORS)
    2순위: 체위 카테고리 범용 안전 앵커 (POSE_SAFE_ANCHORS)
    """
    code_key = str(pose_code).strip().zfill(3)

    # 1순위: 포즈별 실측 정밀 앵커
    if code_key in POSE_EXACT_ANCHORS:
        x0_pct, y0_pct, x1_pct, y1_pct = POSE_EXACT_ANCHORS[code_key]
        x1 = int(round(x0_pct * img_width))
        y1 = int(round(y0_pct * img_height))
        x2 = int(round(x1_pct * img_width))
        y2 = int(round(y1_pct * img_height))
        return (x1, y1, x2, y2)

    # 2순위: 카테고리 범용 앵커
    cat = get_pose_category(pose_code, roster=roster)
    if not cat or cat not in POSE_SAFE_ANCHORS:
        return None
    x0_pct, y0_pct, x1_pct, y1_pct = POSE_SAFE_ANCHORS[cat]
    x1 = int(round(x0_pct * img_width))
    y1 = int(round(y0_pct * img_height))
    x2 = int(round(x1_pct * img_width))
    y2 = int(round(y1_pct * img_height))
    return (x1, y1, x2, y2)


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


def _load_pil_image(image: Union[Image.Image, Path, str]) -> Image.Image:
    """파일 경로 또는 PIL 이미지를 컨텍스트 매니저로 안전하게 로드합니다."""
    if isinstance(image, (str, Path)):
        with Image.open(str(image)) as opened:
            return opened.copy()
    return image


def _get_roi_specs_for_pose(pose_cat: Optional[str]) -> List[Tuple[float, float, float, float]]:
    """체위 카테고리에 맞춰 2단계 Zoom-In ROI 스캔 영역을 최적화합니다."""
    if pose_cat == "piledriver":
        return [
            (0.18, 0.00, 0.82, 0.46),  # 상단 역전 자세(파일드라이버 등) 결합부
            (0.12, 0.12, 0.88, 0.70),  # 중앙-상단 보조 결합부
        ]
    if pose_cat in ("fellatio", "paizuri"):
        return [
            (0.12, 0.12, 0.88, 0.70),  # 상반신 / 구강 클로즈업
            (0.14, 0.38, 0.86, 0.98),  # 흉부-하단 결합 보조 ROI
        ]
    if pose_cat is not None:
        return [
            (0.14, 0.38, 0.86, 0.98),  # 하반신 결합부 표준 ROI
            (0.20, 0.45, 0.80, 0.95),  # 심층 중앙 줌인 ROI
        ]
    return [
        (0.14, 0.38, 0.86, 0.98),
        (0.20, 0.45, 0.80, 0.95),
        (0.12, 0.12, 0.88, 0.70),
        (0.18, 0.00, 0.82, 0.46),
    ]


def _detect_target_candidates(
    img_rgb: Image.Image,
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.16,
    pose_code: Optional[Union[str, int]] = None,
    roster: Optional[str] = None,
    skin_np: Optional[np.ndarray] = None,
    pose_cat: Optional[str] = None,
) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
    """전체 스캔 + 체위 맞춤형 다중 스케일 Zoom-In ROI 정밀 재스캔으로 성기 후보를 검출합니다."""
    if not HAS_IMGUTILS:
        return []

    eff_pose_cat = pose_cat if pose_cat is not None else (
        get_pose_category(pose_code, roster=roster) if pose_code is not None else None
    )
    normalized_targets = _normalize_censor_targets(targets)
    include_lower_junction = "pussy" in normalized_targets
    eff_conf = max(0.05, float(min_confidence))
    roi_conf_floor = min(eff_conf, 0.17)
    min_candidate_score = min(eff_conf, roi_conf_floor)

    img_w, img_h = img_rgb.size
    scale = _compute_scale_factor(img_w, img_h)
    min_box_px = _scale_int(12, scale, minimum=8)
    skin_check_np = skin_np if skin_np is not None else get_skin_mask(np.array(img_rgb))

    detected_boxes_with_labels: List[Tuple[Tuple[int, int, int, int], str, float]] = []
    is_upper_close = eff_pose_cat in ("fellatio", "paizuri", "piledriver")
    min_y2_ratio = 0.04 if eff_pose_cat == "piledriver" else (0.10 if is_upper_close else 0.24)

    def _add_candidate(box_coords: Tuple[int, int, int, int], lbl: str, score: float = 1.0) -> None:
        lbl_low = str(lbl).lower().strip()
        x1, y1, x2, y2 = box_coords
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img_w, x2), min(img_h, y2)
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        if bw < min_box_px or bh < min_box_px:
            return
        if y2 < img_h * min_y2_ratio:
            return
        if eff_pose_cat != "piledriver" and y1 < int(img_h * 0.07):
            y1 = max(y1, int(img_h * 0.07))
            if y2 <= y1:
                return
        # 고신뢰도(score >= 0.50) 박스는 역광·야경·체액 반사로 인한 저피부율 오기각을 면제
        if score < 0.50:
            roi_skin = skin_check_np[y1:y2, x1:x2]
            if roi_skin.size == 0 or (np.count_nonzero(roi_skin) / float(roi_skin.size)) < 0.18:
                return
        if lbl_low not in normalized_targets and lbl_low != "anchor":
            return
        if lbl_low == "pussy" and y2 < img_h * 0.45:
            return
        if score < min_candidate_score:
            return
        cand = (x1, y1, x2, y2)
        for idx, (existing_box, existing_lbl, existing_score) in enumerate(detected_boxes_with_labels):
            if _box_iou(cand, existing_box) > 0.45 or _box_iomin(cand, existing_box) >= 0.65:
                merged = (
                    min(cand[0], existing_box[0]),
                    min(cand[1], existing_box[1]),
                    max(cand[2], existing_box[2]),
                    max(cand[3], existing_box[3]),
                )
                detected_boxes_with_labels[idx] = (
                    merged,
                    lbl_low if "penis" not in (lbl_low, existing_lbl) else "penis",
                    max(score, float(existing_score)),
                )
                return
        detected_boxes_with_labels.append((cand, lbl_low, score))

    try:
        # [1단계] 전체 이미지 스캔
        results = detect_censors(img_rgb, conf_threshold=max(0.05, eff_conf * 0.85))
        for box, label, score in results:
            lbl_l = str(label).lower().strip()
            is_target = (lbl_l in normalized_targets and score >= eff_conf) or (
                include_lower_junction and lbl_l == "pussy" and score >= max(0.18, eff_conf)
            )
            if is_target:
                _add_candidate(tuple(int(v) for v in box), lbl_l, float(score))

        # [2단계] 체위 맞춤형 다중 스케일 Zoom-In ROI 크롭 정밀 재스캔
        pussy_roi_thresh = min(max(0.18, eff_conf), 0.20)
        for rx0, ry0, rx1, ry1 in _get_roi_specs_for_pose(eff_pose_cat):
            cx1, cy1 = int(img_w * rx0), int(img_h * ry0)
            cx2, cy2 = int(img_w * rx1), int(img_h * ry1)
            if cx2 <= cx1 or cy2 <= cy1:
                continue
            crop_img = img_rgb.crop((cx1, cy1, cx2, cy2))
            up_w, up_h = max(1, int(crop_img.width * 1.6)), max(1, int(crop_img.height * 1.6))
            up_img = crop_img.resize((up_w, up_h), Image.Resampling.LANCZOS)
            crop_res = detect_censors(up_img, conf_threshold=min(0.13, roi_conf_floor))
            for box, label, score in crop_res:
                lbl_l = str(label).lower().strip()
                is_target = (lbl_l in normalized_targets and score >= roi_conf_floor) or (
                    include_lower_junction and lbl_l == "pussy" and score >= pussy_roi_thresh
                )
                if is_target:
                    bx1, by1, bx2, by2 = [int(v / 1.6) for v in box]
                    _add_candidate((bx1 + cx1, by1 + cy1, bx2 + cx1, by2 + cy1), lbl_l, float(score))
    except Exception as e:
        logger.warning(f"[Censor] 감지 모델 추론 예외: {e}")

    # 3단계: 포함(IoMin >= 0.65) 및 겹침(IoU > 0.45) 잔여 조각 박스 수렴 병합
    changed = True
    while changed and len(detected_boxes_with_labels) > 1:
        changed = False
        merged_list: List[Tuple[Tuple[int, int, int, int], str, float]] = []
        for cand_box, cand_lbl, cand_score in detected_boxes_with_labels:
            merged_hit = False
            for idx, (ex_box, ex_lbl, ex_score) in enumerate(merged_list):
                if _box_iou(cand_box, ex_box) > 0.45 or _box_iomin(cand_box, ex_box) >= 0.65:
                    merged_box = (
                        min(cand_box[0], ex_box[0]),
                        min(cand_box[1], ex_box[1]),
                        max(cand_box[2], ex_box[2]),
                        max(cand_box[3], ex_box[3]),
                    )
                    merged_list[idx] = (
                        merged_box,
                        cand_lbl if "penis" not in (cand_lbl, ex_lbl) else "penis",
                        max(float(cand_score), float(ex_score)),
                    )
                    merged_hit = True
                    changed = True
                    break
            if not merged_hit:
                merged_list.append((cand_box, cand_lbl, float(cand_score)))
        detected_boxes_with_labels = merged_list

    return detected_boxes_with_labels


def _atomic_replace_with_retry(
    temp_dst: Path,
    target_dst: Path,
    retries: int = 5,
    delay: float = 0.08,
) -> None:
    """Windows 파일 락 일시 충돌 시 지수/선형 백오프로 os.replace를 재시도합니다."""
    last_err: Optional[OSError] = None
    for attempt in range(max(1, retries)):
        try:
            os.replace(temp_dst, target_dst)
            return
        except PermissionError as err:
            last_err = err
            if attempt + 1 < retries:
                time.sleep(delay * (attempt + 1))
        except OSError as err:
            last_err = err
            if attempt + 1 < retries:
                time.sleep(delay * (attempt + 1))
    if last_err is not None:
        raise last_err


def censor_image(
    image: Union[Image.Image, Path, str],
    style: str = "white_silhouette",
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.16,
    pose_code: Optional[Union[str, int]] = None,
    enable_anchor_fallback: bool = False,
    roster: Optional[str] = None,
) -> Tuple[Image.Image, int]:
    """
    이미지 내 성기 및 결합 접점 부위를 다중 스케일(전체 + 체위별 줌인 ROI)로 정밀 감지하여 검열을 적용합니다.
    - 기본 스타일: 'white_silhouette' (매끈한 소프트 화이트 실루엣 - 젠잇 심의 규정 표준)
    - 기본 대상: 남성기+고환 ('penis'), 옵션으로 'pussy'/'all' 등 targets 인수를 존중
    - RGBA 입력 시 알파 채널을 무손실 보존합니다.
    - 반환값: (검열된 PIL 이미지, 감지된 부위 개수)
    """
    src_img = _load_pil_image(image)
    img_rgb, alpha_ch = _split_rgb_and_alpha(src_img)

    # V3 오검열 원천 방어 가드: 비검열 대상(감정표현, 일상 스킨십, 착의 이벤트 등)은 즉시 원본 반환
    if pose_code is not None and not is_pose_censor_required(
        pose_code=pose_code,
        file_path=image if isinstance(image, (str, Path)) else None,
        roster=roster,
    ):
        return _restore_alpha(img_rgb, alpha_ch), 0

    pose_cat = get_pose_category(pose_code, roster=roster) if pose_code is not None else None
    skin_check_np = get_skin_mask(np.array(img_rgb))

    # 1순위: 전용 학습 YOLO-seg 가중치(models/censor_seg.pt) 존재 시 MobileSAM을 우회하여 폴리곤 마스크 직결
    custom_seg_model = get_custom_censor_seg_model()
    custom_seg_mask: Optional[np.ndarray] = None
    detected_boxes_with_labels: List[Tuple[Tuple[int, int, int, int], str, float]] = []

    if custom_seg_model is not None:
        seg_boxes, seg_mask = _infer_custom_censor_seg(
            img_rgb,
            custom_seg_model,
            min_confidence=min_confidence,
        )
        norm_targets = _normalize_censor_targets(targets)
        filtered_seg = [item for item in seg_boxes if item[1] in norm_targets]
        if filtered_seg and seg_mask is not None and np.count_nonzero(seg_mask) > 0:
            detected_boxes_with_labels = filtered_seg
            custom_seg_mask = seg_mask

    # 2순위: 전용 YOLO-seg 미존재 또는 0건 탐지 시 기존 detect_censors + ADR-86 MobileSAM 폴백
    if not detected_boxes_with_labels:
        detected_boxes_with_labels = _detect_target_candidates(
            img_rgb,
            targets=targets,
            min_confidence=min_confidence,
            pose_code=pose_code,
            roster=roster,
            skin_np=skin_check_np,
            pose_cat=pose_cat,
        )

    # 검열 미탐지 시 체위별 안전 앵커 폴백 점검 (기본 False: 신체 오검열 아티팩트 방지)
    if not detected_boxes_with_labels and pose_code is not None and pose_cat:
        if enable_anchor_fallback:
            anchor_box = get_pose_anchor_box(pose_code, img_rgb.width, img_rgb.height, roster=roster)
            if anchor_box:
                detected_boxes_with_labels.append((anchor_box, "anchor", 1.0))
                logger.info(
                    f"[Censor] 포즈 {pose_code}: 성기 미탐지 ➔ 안전 앵커({pose_cat}) 폴백 적용: {anchor_box}"
                )
        else:
            logger.warning(
                f"[WARN] [Censor] 포즈 {pose_code}: 성기 미탐지! 안전 앵커 영역({pose_cat}) 폴백 점검 대상입니다."
            )

    if not detected_boxes_with_labels:
        return _restore_alpha(img_rgb, alpha_ch), 0

    censored_rgb = _render_censored_style(
        img_rgb,
        detected_boxes_with_labels,
        style=style,
        skin_np=skin_check_np,
        pose_cat=pose_cat,
        custom_seg_mask=custom_seg_mask,
    )
    return _restore_alpha(censored_rgb, alpha_ch), len(detected_boxes_with_labels)


def verify_and_heal_censor(
    censored_img: Image.Image,
    style: str = "white_silhouette",
    min_confidence: float = 0.32,
    targets: Sequence[str] = ("penis",),
) -> Tuple[Image.Image, bool]:
    """
    검열이 완료된 이미지를 대상으로 성기 검출기를 다시 돌려 잔여 노출 여부를 2차 검증합니다.
    과도한 2중 팽창을 방지하기 위해 신뢰도 임계값 0.32 이상의 명백한 잔여 노출에만 2차 보정을 발동합니다.
    반환값: (최종 안전 이미지, 추가 보정 발생 여부)
    """
    if not HAS_IMGUTILS:
        return censored_img, False

    try:
        rgb_img, alpha_ch = _split_rgb_and_alpha(censored_img)
        target_labels = _normalize_censor_targets(targets)
        eff_min_conf = max(0.05, float(min_confidence))
        results = detect_censors(rgb_img, conf_threshold=eff_min_conf)
        leaks = [
            ((int(b[0]), int(b[1]), int(b[2]), int(b[3])), str(label).strip().lower())
            for b, label, score in results
            if str(label).strip().lower() in target_labels and float(score) >= eff_min_conf
        ]
        if not leaks:
            return censored_img, False

        logger.warning(
            f"[Censor Gate] 2차 사후 검증에서 명백한 잔여 노출 {len(leaks)}건 감지! 즉시 2차 안전 보정을 수행합니다."
        )
        healed_rgb = _render_censored_style(rgb_img, leaks, style=style)
        return _restore_alpha(healed_rgb, alpha_ch), True
    except Exception as e:
        logger.debug(f"[Censor Gate] 사후 검증 예외: {e}")
        return censored_img, False


def censor_file(
    src_path: Union[Path, str],
    dst_path: Optional[Union[Path, str]] = None,
    style: str = "white_silhouette",
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.16,
    quality: int = 95,
    pose_code: Optional[Union[str, int]] = None,
    enable_anchor_fallback: bool = False,
    backup_dir: Optional[Union[Path, str]] = None,
    roster: Optional[str] = None,
) -> Optional[Path]:
    """
    파일 경로를 입력받아 검열본을 생성하고 저장합니다.
    - dst_path 미지정 시 'stem_censored.webp'로 자동 저장.
    - backup_dir 지정 시 감지 성공 여부와 무관하게 원본 파일을 해당 폴더로 안전하게 선제 복사 백업.
    - 감지된 검열 대상이 없는 경우 검열본을 생성하지 않고 None 반환.
    """
    src = Path(src_path)
    if not src.exists():
        return None

    # V3 오검열 원천 방어 가드: 비검열 대역(01_emotions, 03_events, 착의 일상 등)은 100% 면제
    if not is_pose_censor_required(pose_code=pose_code, file_path=src, roster=roster):
        return None

    if backup_dir:
        b_dir = Path(backup_dir)
        b_dir.mkdir(parents=True, exist_ok=True)
        b_path = b_dir / src.name
        if not b_path.exists():
            shutil.copy2(src, b_path)

    with Image.open(src) as opened:
        img = opened.copy()
    censored_img, count = censor_image(
        img,
        style=style,
        targets=targets,
        min_confidence=min_confidence,
        pose_code=pose_code,
        enable_anchor_fallback=enable_anchor_fallback,
        roster=roster,
    )

    if count == 0:
        return None

    if dst_path is None:
        target_dst = src.with_name(f"{src.stem}_censored{src.suffix}")
    else:
        target_dst = Path(dst_path)

    target_dst.parent.mkdir(parents=True, exist_ok=True)
    ext_map = {".webp": "WEBP", ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
    save_fmt = ext_map.get(target_dst.suffix.lower(), "WEBP")
    if save_fmt == "JPEG" and censored_img.mode != "RGB":
        censored_img = censored_img.convert("RGB")
    temp_dst = target_dst.with_name(f".{target_dst.stem}_{uuid.uuid4().hex[:8]}.tmp{target_dst.suffix or '.webp'}")
    try:
        save_kwargs = {"quality": quality} if save_fmt in ("WEBP", "JPEG") else {"optimize": True}
        censored_img.save(temp_dst, save_fmt, **save_kwargs)
        _atomic_replace_with_retry(temp_dst, target_dst)
    finally:
        if temp_dst.exists():
            temp_dst.unlink(missing_ok=True)
    return target_dst


def detect_genitals(
    image: Union[Path, str, Image.Image],
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.22,
    pose_code: Optional[Union[str, int]] = None,
    roster: Optional[str] = None,
    **kwargs: Any,
) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
    """이미지에서 검열 대상 부위(성기 등)를 다중 스케일 ROI 포함 정밀 감지하여 [(box, label, score), ...] 형태로 반환합니다."""
    if not HAS_IMGUTILS:
        return []
    try:
        src_img = _load_pil_image(image)
        img_rgb, _ = _split_rgb_and_alpha(src_img)
        return _detect_target_candidates(
            img_rgb,
            targets=targets,
            min_confidence=min_confidence,
            pose_code=pose_code,
            roster=roster,
        )
    except Exception as e:
        logger.warning(f"[Censor] detect_genitals 감지 예외: {e}")
        return []


def run_batch_censor(
    folder_path: Union[Path, str],
    style: str = "white_silhouette",
    overwrite: bool = True,
    recursive: bool = True,
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.22,
    enable_anchor_fallback: bool = False,
) -> int:
    """폴더 내의 모든 일러스트 에셋을 스캔하여 일괄 검열을 수행합니다."""
    base_dir = Path(folder_path).resolve()
    if not base_dir.exists():
        logger.error(f"[오류] 대상 폴더를 찾을 수 없습니다: {base_dir}")
        return 0

    extensions = ["*.webp", "*.png", "*.jpg", "*.jpeg"]
    image_files: List[Path] = []
    for ext in extensions:
        if recursive:
            image_files.extend(base_dir.rglob(ext))
        else:
            image_files.extend(base_dir.glob(ext))

    target_files = [f for f in image_files if not f.stem.endswith("_censored")]
    total = len(target_files)
    processed_count = 0

    for idx, file_path in enumerate(target_files, 1):
        # 1. _origin 폴더 내부 파일은 원본이므로 배치 검열 대상에서 원천 제외
        if "_origin" in file_path.parts:
            continue

        # 2. V3 정밀 정규식: 하이브리드 파일명(prefix_000_label.webp), 영숫자 코드(prefix_N01_label.webp) 및 코드 파일명 지원
        match = re.search(r"_([A-Za-z]\d{2,3}|\d{3})(?:_|\.)", file_path.name)
        pose_code: Union[str, int, None] = None
        if match:
            raw_code = match.group(1)
            pose_code = int(raw_code) if raw_code.isdigit() else raw_code.upper()

        # 3. V3 대역 체계 기반 검열 대상 여부 엄격 판정: 비검열 대역은 100% 바이패스
        if not is_pose_censor_required(pose_code=pose_code, file_path=file_path):
            continue

        try:
            dst = file_path if overwrite else file_path.with_name(f"{file_path.stem}_censored{file_path.suffix}")
            saved = censor_file(
                src_path=file_path,
                dst_path=dst,
                style=style,
                targets=targets,
                min_confidence=min_confidence,
                pose_code=pose_code,
                enable_anchor_fallback=enable_anchor_fallback,
            )
            if saved is not None:
                processed_count += 1
        except Exception as e:
            logger.warning(f"[Censor] 배치 검열 실패: {file_path.name} ({e})")

    return processed_count


