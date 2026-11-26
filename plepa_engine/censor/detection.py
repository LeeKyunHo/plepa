"""
plepa_engine.censor.detection
다중 스케일 체위별 ROI 스캔, IoU/IoMin 병합, 하단 경계 오탐 필터링 및 detect_genitals 모듈.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image

from ._runtime import HAS_IMGUTILS, _compute_scale_factor, _scale_int, _split_rgb_and_alpha, detect_censors, facade_get, logger
from .constants import _normalize_censor_targets
from .geometry import _box_iomin, _box_iou, get_skin_mask
from .policy import get_pose_category


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


def _filter_bottom_edge_false_positives(
    candidates: Sequence[Tuple[Tuple[int, int, int, int], str, float]],
    img_w: int,
    img_h: int,
    img_rgb_np: Optional[np.ndarray] = None,
    skin_mask_np: Optional[np.ndarray] = None,
) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
    """
    상단에 고신뢰 주 성기 박스가 존재할 때, 이미지 최하단 경계 근처(y2 >= 0.88*H) 또는 수직 분리 영역에서
    발생하는 저신뢰(score < 0.35), 극단적 평판 조각(Sliver), 고밝기 체액/저피부 오탐 박스를 제거합니다.
    """
    if len(candidates) <= 1 or img_w <= 0 or img_h <= 0:
        return list(candidates)

    penis_indices = [i for i, item in enumerate(candidates) if str(item[1]).lower().strip() == "penis"]
    if len(penis_indices) <= 1:
        return list(candidates)

    filtered: List[Tuple[Tuple[int, int, int, int], str, float]] = []
    for idx, (box, lbl, score) in enumerate(candidates):
        lbl_clean = str(lbl).lower().strip()
        if lbl_clean != "penis":
            filtered.append((box, lbl, score))
            continue

        x1, y1, x2, y2 = box
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        area = bw * bh
        cy = (y1 + y2) * 0.5
        aspect = float(bw) / float(bh)

        # 자기 자신보다 위쪽에 위치한 고신뢰(>= 0.50) 주 후보 목록 확인
        upper_anchors = [
            candidates[j]
            for j in penis_indices
            if j != idx
            and float(candidates[j][2]) >= 0.50
            and ((candidates[j][0][1] + candidates[j][0][3]) * 0.5) < cy
        ]
        if not upper_anchors:
            filtered.append((box, lbl, score))
            continue

        top_box, _, _ = max(upper_anchors, key=lambda it: float(it[2]))
        top_h = max(1, top_box[3] - top_box[1])
        top_area = max(1, (top_box[2] - top_box[0]) * top_h)

        near_bottom = y2 >= int(img_h * 0.88)
        vert_isolated = y1 >= (top_box[3] - max(0, int(top_h * 0.08)))
        drop = False

        if near_bottom or vert_isolated:
            # 1) 2차 ROI 줌인 등에서 발생한 저신뢰(< 0.35) 하단/분리 오탐 기각
            if float(score) < 0.35:
                drop = True
            # 2) 최하단 경계(y2 >= 0.94*H)에 걸친 소형·평판 조각(Sliver) 기각
            elif y2 >= int(img_h * 0.94) and area < int(top_area * 0.14):
                if aspect >= 2.0 or bh < int(img_h * 0.06) or float(score) < 0.65:
                    drop = True
            # 3) 최하단 저피부/백색 체액 얼룩 오탐 기각 (단독 고신뢰 백광 타겟은 상단 앵커 미해당으로 보존)
            elif near_bottom and img_rgb_np is not None and img_rgb_np.size > 0:
                roi_rgb = img_rgb_np[max(0, y1) : min(img_h, y2), max(0, x1) : min(img_w, x2)]
                if roi_rgb.size > 0:
                    bright_ratio = float((roi_rgb.min(axis=2) >= 222).mean())
                    skin_ratio = 1.0
                    if skin_mask_np is not None and skin_mask_np.size > 0:
                        roi_sk = skin_mask_np[max(0, y1) : min(img_h, y2), max(0, x1) : min(img_w, x2)]
                        skin_ratio = float(np.count_nonzero(roi_sk)) / float(max(1, roi_sk.size))
                    if bright_ratio >= 0.28 or (y2 >= int(img_h * 0.92) and skin_ratio < 0.25):
                        drop = True

        if not drop:
            filtered.append((box, lbl, score))

    return filtered if filtered else list(candidates)


def _append_merged_candidate(
    detected: List[Tuple[Tuple[int, int, int, int], str, float]],
    box_coords: Tuple[int, int, int, int],
    lbl: str,
    score: float,
    *,
    img_w: int,
    img_h: int,
    min_box_px: int,
    min_y2_ratio: float,
    eff_pose_cat: Optional[str],
    normalized_targets: set[str],
    min_candidate_score: float,
    skin_check_np: np.ndarray,
) -> None:
    """개별 검출 박스에 크기·위치·피부톤·타겟 게이트를 적용해 병합/추가합니다."""
    lbl_low = str(lbl).lower().strip()
    x1, y1, x2, y2 = box_coords
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img_w, x2), min(img_h, y2)
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)
    if bw < min_box_px or bh < min_box_px or y2 < img_h * min_y2_ratio:
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
    for idx, (existing_box, existing_lbl, existing_score) in enumerate(detected):
        if _box_iou(cand, existing_box) > 0.45 or _box_iomin(cand, existing_box) >= 0.65:
            merged = (
                min(cand[0], existing_box[0]),
                min(cand[1], existing_box[1]),
                max(cand[2], existing_box[2]),
                max(cand[3], existing_box[3]),
            )
            detected[idx] = (
                merged,
                lbl_low if "penis" not in (lbl_low, existing_lbl) else "penis",
                max(score, float(existing_score)),
            )
            return
    detected.append((cand, lbl_low, score))


def _merge_overlapping_candidates(
    detected_boxes_with_labels: List[Tuple[Tuple[int, int, int, int], str, float]],
) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
    """포함(IoMin >= 0.65) 및 겹침(IoU > 0.45) 잔여 조각 박스를 수렴할 때까지 병합합니다."""
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
    if not facade_get("HAS_IMGUTILS", HAS_IMGUTILS):
        return []

    detect_fn = facade_get("detect_censors", detect_censors)
    cat_fn = facade_get("get_pose_category", get_pose_category)
    skin_fn = facade_get("get_skin_mask", get_skin_mask)
    filter_fp_fn = facade_get("_filter_bottom_edge_false_positives", _filter_bottom_edge_false_positives)

    eff_pose_cat = pose_cat if pose_cat is not None else (
        cat_fn(pose_code, roster=roster) if pose_code is not None else None
    )
    normalized_targets = _normalize_censor_targets(targets)
    include_lower_junction = "pussy" in normalized_targets
    eff_conf = max(0.05, float(min_confidence))
    roi_conf_floor = min(eff_conf, 0.17)
    min_candidate_score = min(eff_conf, roi_conf_floor)

    img_w, img_h = img_rgb.size
    scale = _compute_scale_factor(img_w, img_h)
    min_box_px = _scale_int(12, scale, minimum=8)
    img_rgb_np = np.array(img_rgb)
    skin_check_np = skin_np if skin_np is not None else skin_fn(img_rgb_np)

    detected: List[Tuple[Tuple[int, int, int, int], str, float]] = []
    is_upper_close = eff_pose_cat in ("fellatio", "paizuri", "piledriver")
    min_y2_ratio = 0.04 if eff_pose_cat == "piledriver" else (0.10 if is_upper_close else 0.24)
    gate_kw = dict(
        img_w=img_w, img_h=img_h, min_box_px=min_box_px, min_y2_ratio=min_y2_ratio,
        eff_pose_cat=eff_pose_cat, normalized_targets=normalized_targets,
        min_candidate_score=min_candidate_score, skin_check_np=skin_check_np,
    )

    try:
        # [1단계] 전체 이미지 스캔
        for box, label, score in detect_fn(img_rgb, conf_threshold=max(0.05, eff_conf * 0.85)):
            lbl_l = str(label).lower().strip()
            if (lbl_l in normalized_targets and score >= eff_conf) or (
                include_lower_junction and lbl_l == "pussy" and score >= max(0.18, eff_conf)
            ):
                _append_merged_candidate(detected, tuple(int(v) for v in box), lbl_l, float(score), **gate_kw)

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
            for box, label, score in detect_fn(up_img, conf_threshold=min(0.13, roi_conf_floor)):
                lbl_l = str(label).lower().strip()
                if (lbl_l in normalized_targets and score >= roi_conf_floor) or (
                    include_lower_junction and lbl_l == "pussy" and score >= pussy_roi_thresh
                ):
                    bx1, by1, bx2, by2 = [int(v / 1.6) for v in box]
                    _append_merged_candidate(detected, (bx1 + cx1, by1 + cy1, bx2 + cx1, by2 + cy1), lbl_l, float(score), **gate_kw)
    except Exception as e:
        logger.warning(f"[Censor] 감지 모델 추론 예외: {e}")

    # 3단계: 포함/겹침 잔여 조각 박스 수렴 병합 + 하단 경계 오탐 필터
    detected = _merge_overlapping_candidates(detected)
    return filter_fp_fn(detected, img_w=img_w, img_h=img_h, img_rgb_np=img_rgb_np, skin_mask_np=skin_check_np)


def detect_genitals(
    image: Union[Path, str, Image.Image],
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.22,
    pose_code: Optional[Union[str, int]] = None,
    roster: Optional[str] = None,
    **kwargs: Any,
) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
    """이미지에서 검열 대상 부위(성기 등)를 다중 스케일 ROI 포함 정밀 감지하여 [(box, label, score), ...] 형태로 반환합니다."""
    if not facade_get("HAS_IMGUTILS", HAS_IMGUTILS):
        return []
    try:
        src_img = _load_pil_image(image)
        img_rgb, _ = _split_rgb_and_alpha(src_img)
        detect_cand_fn = facade_get("_detect_target_candidates", _detect_target_candidates)
        return detect_cand_fn(
            img_rgb,
            targets=targets,
            min_confidence=min_confidence,
            pose_code=pose_code,
            roster=roster,
        )
    except Exception as e:
        logger.warning(f"[Censor] detect_genitals 감지 예외: {e}")
        return []
