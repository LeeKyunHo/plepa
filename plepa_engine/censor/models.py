"""
plepa_engine.censor.models
SAM 2.1 / MobileSAM 및 전용 YOLO-seg 모델의 스레드 안전 싱글톤 로더·추론·언로드 모듈.
"""

from __future__ import annotations

import gc
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

from ._runtime import facade_get, facade_set, logger
from .geometry import _box_iomin, _box_iou, get_skin_mask

# MobileSAM 및 커스텀 YOLO-seg 모델 싱글톤 (Lazy Load, Thread-Safe)
_SAM_MODEL: Any = None
_SAM_MODEL_LOCK = threading.Lock()
_CENSOR_SEG_MODEL: Any = None
_CENSOR_SEG_LOCK = threading.Lock()


def _extract_sam_mask_data(results: Any) -> Optional[np.ndarray]:
    """SAM/SAM2 추론 결과에서 마스크 numpy 배열을 안전하게 추출합니다 (빈 텐서·테스트 모의 객체 겸용)."""
    if not results or getattr(results[0], "masks", None) is None:
        return None
    raw_data = getattr(results[0].masks, "data", None)
    if raw_data is None:
        return None
    arr = raw_data.cpu().numpy() if hasattr(raw_data, "cpu") else np.asarray(raw_data)
    if arr is None or len(arr) == 0:
        return None
    return arr


def get_sam_model():
    """SAM 2.1(sam2.1_s.pt) 우선 및 MobileSAM 폴백 세그멘테이션 모델을 스레드 안전하게 싱글톤 로드합니다."""
    global _SAM_MODEL
    cur = facade_get("_SAM_MODEL", _SAM_MODEL)
    if cur is not None:
        return cur if cur is not False else None

    sam_lock = facade_get("_SAM_MODEL_LOCK", _SAM_MODEL_LOCK)
    with sam_lock:
        cur = facade_get("_SAM_MODEL", _SAM_MODEL)
        if cur is None:
            from plepa_engine.config import ROOT_DIR

            req_name = os.environ.get("PLEPA_SAM_MODEL", "sam2.1_s.pt").strip() or "sam2.1_s.pt"
            candidates: List[str] = [req_name]
            if req_name != "mobile_sam.pt":
                candidates.append("mobile_sam.pt")

            loaded = None
            for idx, cand in enumerate(candidates):
                try:
                    from ultralytics import SAM

                    cand_path = ROOT_DIR / cand
                    sam_path = str(cand_path) if cand_path.is_file() else cand
                    loaded = SAM(sam_path)
                    logger.info(f"[Censor] SAM 세그멘테이션 모델 로드 완료 ({sam_path})")
                    break
                except Exception as e:
                    next_hint = f" -> 폴백({candidates[idx + 1]}) 시도" if idx + 1 < len(candidates) else ""
                    logger.warning(f"[Censor] SAM({cand}) 로드 실패: {e}{next_hint}")

            if loaded is not None:
                _SAM_MODEL = loaded
            else:
                logger.warning("[Censor] 사용 가능한 SAM 모델이 없어 OpenCV 폴백 모드로 동작합니다.")
                _SAM_MODEL = False
            facade_set("_SAM_MODEL", _SAM_MODEL)
    cur = facade_get("_SAM_MODEL", _SAM_MODEL)
    return cur if cur is not False else None


def get_custom_censor_seg_model():
    """전용 YOLO-seg 검열 가중치(`PLEPA_CENSOR_SEG_MODEL` 또는 `models/censor_seg.pt`)를 싱글톤 로드합니다."""
    global _CENSOR_SEG_MODEL
    env_override = os.environ.get("PLEPA_CENSOR_SEG_MODEL", "").strip()
    cur = facade_get("_CENSOR_SEG_MODEL", _CENSOR_SEG_MODEL)
    if cur is not None and not env_override:
        return cur if cur is not False else None

    seg_lock = facade_get("_CENSOR_SEG_LOCK", _CENSOR_SEG_LOCK)
    with seg_lock:
        from plepa_engine.config import ROOT_DIR

        model_path = Path(env_override) if env_override else (ROOT_DIR / "models" / "censor_seg.pt")
        if not model_path.exists() or not model_path.is_file():
            return None

        cur = facade_get("_CENSOR_SEG_MODEL", _CENSOR_SEG_MODEL)
        if cur is None or cur is False or env_override:
            try:
                from ultralytics import YOLO

                _CENSOR_SEG_MODEL = YOLO(str(model_path))
                logger.info(f"[Censor] 전용 YOLO-seg 모델 로드 완료 ({model_path})")
            except Exception as e:
                logger.warning(f"[Censor] 전용 YOLO-seg 로드 실패, MobileSAM 모드로 폴백합니다: {e}")
                _CENSOR_SEG_MODEL = False
            facade_set("_CENSOR_SEG_MODEL", _CENSOR_SEG_MODEL)
    cur = facade_get("_CENSOR_SEG_MODEL", _CENSOR_SEG_MODEL)
    return cur if cur is not False else None


def _infer_custom_censor_seg_items(
    img_rgb: Image.Image,
    seg_model: Any,
    min_confidence: float = 0.16,
    skin_np: Optional[np.ndarray] = None,
) -> List[Tuple[Tuple[int, int, int, int], str, float, np.ndarray]]:
    """전용 YOLO-seg 모델로 (bbox, label, score, poly_pts) 항목 리스트를 추출합니다."""
    if seg_model is None:
        return []

    w, h = img_rgb.size
    items_out: List[Tuple[Tuple[int, int, int, int], str, float, np.ndarray]] = []
    seg_lock = facade_get("_CENSOR_SEG_LOCK", _CENSOR_SEG_LOCK)
    skin_fn = facade_get("get_skin_mask", get_skin_mask)

    try:
        infer_kwargs: Dict[str, Any] = {
            "conf": float(min_confidence),
            "verbose": False,
        }
        if hasattr(seg_model, "overrides"):
            infer_kwargs["imgsz"] = 1024
            infer_kwargs["retina_masks"] = True
        with seg_lock:
            results = seg_model(img_rgb, **infer_kwargs)
        if not results:
            return []

        res0 = results[0]
        res_masks = getattr(res0, "masks", None)
        res_boxes = getattr(res0, "boxes", None)
        names = getattr(res0, "names", None) or {}
        polys = getattr(res_masks, "xy", None) if res_masks is not None else None
        if polys is None or len(polys) == 0:
            return []

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

        skin_np_seg: Optional[np.ndarray] = skin_np
        min_box_px = max(8, int(round(min(w, h) * 0.01)))
        max_poly_area = float(w * h) * 0.25

        for idx, poly in enumerate(polys):
            poly_pts = np.round(np.asarray(poly, dtype=np.float32)).astype(np.int32)
            if poly_pts.ndim != 2 or len(poly_pts) < 3:
                continue

            if xyxy_arr is not None and idx < len(xyxy_arr):
                b = xyxy_arr[idx]
                box = (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
            else:
                xs, ys = poly_pts[:, 0], poly_pts[:, 1]
                box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

            bx1 = max(0, min(w - 1, box[0]))
            by1 = max(0, min(h - 1, box[1]))
            bx2 = max(bx1 + 1, min(w, box[2]))
            by2 = max(by1 + 1, min(h, box[3]))
            if (bx2 - bx1) < min_box_px or (by2 - by1) < min_box_px:
                continue
            if by2 < h * 0.10:
                continue

            score = float(conf_arr[idx]) if (conf_arr is not None and idx < len(conf_arr)) else 0.90
            yc = (by1 + by2) * 0.5
            if yc < h * 0.14 and score < 0.35:
                continue

            poly_area = abs(float(cv2.contourArea(poly_pts)))
            if poly_area < float(min_box_px * min_box_px) or poly_area > max_poly_area:
                continue

            if score < 0.40:
                if skin_np_seg is None:
                    skin_np_seg = skin_fn(np.array(img_rgb, dtype=np.uint8))
                roi_sk = skin_np_seg[by1:by2, bx1:bx2]
                if roi_sk.size == 0 or (np.count_nonzero(roi_sk) / float(roi_sk.size)) < 0.12:
                    continue

            cls_id = int(cls_arr[idx]) if (cls_arr is not None and idx < len(cls_arr)) else 0
            raw_name = names.get(cls_id, "penis") if isinstance(names, dict) else "penis"
            label = "penis" if str(raw_name).lower() in ("genital", "penis", "0", "") else str(raw_name).lower()
            items_out.append(((bx1, by1, bx2, by2), label, score, poly_pts))

        # 동일 타겟 내 중첩/부분 조각 박스 병합 억제 (_box_iomin / _box_iou)
        items_out.sort(key=lambda it: float(it[2]), reverse=True)
        merged_items: List[Tuple[Tuple[int, int, int, int], str, float, np.ndarray]] = []
        for cand in items_out:
            c_box, c_lbl, _, _ = cand
            if any(
                m_lbl == c_lbl and (_box_iou(c_box, m_box) >= 0.35 or _box_iomin(c_box, m_box) >= 0.55)
                for m_box, m_lbl, _, _ in merged_items
            ):
                continue
            merged_items.append(cand)

        return merged_items
    except Exception as e:
        logger.warning(f"[Censor] 전용 YOLO-seg 추론 예외, 기본 파이프라인으로 폴백합니다: {e}")
        return []


def _render_seg_items_mask(
    width: int,
    height: int,
    seg_items: Sequence[Tuple[Tuple[int, int, int, int], str, float, np.ndarray]],
) -> Optional[np.ndarray]:
    """선택된 YOLO-seg 항목들의 폴리곤을 단일 이진 마스크(`0/255`)로 래스터화합니다."""
    if not seg_items:
        return None
    mask = np.zeros((height, width), dtype=np.uint8)
    for _, _, _, poly_pts in seg_items:
        cv2.fillPoly(mask, [poly_pts], 255)
    return mask if np.count_nonzero(mask) > 0 else None


def _infer_custom_censor_seg(
    img_rgb: Image.Image,
    seg_model: Any,
    min_confidence: float = 0.16,
) -> Tuple[List[Tuple[Tuple[int, int, int, int], str, float]], Optional[np.ndarray]]:
    """전용 YOLO-seg 모델로 성기 BBox 목록과 `cv2.fillPoly` 기반 이진 세그멘테이션 마스크를 추출합니다."""
    infer_fn = facade_get("_infer_custom_censor_seg_items", _infer_custom_censor_seg_items)
    render_fn = facade_get("_render_seg_items_mask", _render_seg_items_mask)
    items = infer_fn(img_rgb, seg_model, min_confidence=min_confidence)
    if not items:
        return [], None
    w, h = img_rgb.size
    mask = render_fn(w, h, items)
    if mask is None:
        return [], None
    boxes_out = [(box, label, score) for box, label, score, _ in items]
    return boxes_out, mask


def unload_censor_models() -> None:
    """로드된 MobileSAM 및 전용 YOLO-seg 싱글톤과 GPU VRAM 캐시를 안전하게 해제합니다."""
    global _SAM_MODEL, _CENSOR_SEG_MODEL
    sam_lock = facade_get("_SAM_MODEL_LOCK", _SAM_MODEL_LOCK)
    seg_lock = facade_get("_CENSOR_SEG_LOCK", _CENSOR_SEG_LOCK)
    with sam_lock:
        _SAM_MODEL = None
        facade_set("_SAM_MODEL", None)
    with seg_lock:
        _CENSOR_SEG_MODEL = None
        facade_set("_CENSOR_SEG_MODEL", None)
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
