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

import logging
import math
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

try:
    from imgutils.detect import detect_censors
    HAS_IMGUTILS = True
except ImportError:
    HAS_IMGUTILS = False

# MobileSAM 모델 싱글톤 (Lazy Load)
_SAM_MODEL = None


def get_sam_model():
    """MobileSAM 세그멘테이션 모델을 싱글톤으로 로드합니다."""
    global _SAM_MODEL
    if _SAM_MODEL is None:
        try:
            from ultralytics import SAM
            _SAM_MODEL = SAM("mobile_sam.pt")
            logger.info("[Censor] MobileSAM 모델 로드 완료 (mobile_sam.pt)")
        except Exception as e:
            logger.warning(f"[Censor] MobileSAM 로드 실패, OpenCV 폴백 모드로 동작합니다: {e}")
            _SAM_MODEL = False
    return _SAM_MODEL if _SAM_MODEL is not False else None


def apply_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Tuple[int, int, int, int], str]],
    color: Union[str, Tuple[int, int, int]] = "black",
) -> Image.Image:
    """
    네모난 박스가 아니라 남성기 전체와 고환의 실제 선화 외곽선(Contour)을 따라
    내부만 솔리드 컬러(블랙 #000000 또는 화이트 #FFFFFF)로 매끈하게 채우는 실루엣 검열을 렌더링합니다.
    - MobileSAM BBox Prompting으로 픽셀 단위 마스크 추출.
    - 펠라/오랄 구도에서 여주인공 팔/어깨 피부 침범을 원천 차단하는 적응형 마진 및 고립 노이즈 컨투어 정제.
    - 타원 커널 모폴로지 클로징 및 가우시안 안티앨리어싱으로 계단 현상 없는 유려한 곡선 완성.
    """
    w, h = img.size
    img_np = np.array(img.convert("RGB"))
    final_mask = np.zeros((h, w), dtype=np.uint8)

    sam = get_sam_model()

    for box, label in boxes_with_labels:
        x1, y1, x2, y2 = box
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)

        is_penis = label == "penis"
        if is_penis:
            # 적응형 마진: 가로형(bw >= bh)은 오랄/펠라 등 여주인공 신체 밀착 구도이므로 하단 확장 억제(0.04),
            # 세로형(bh > bw * 1.3)일 때만 고환 영역을 고려하여 하단 10% 확장
            m_x = 0.05
            m_top = 0.04
            m_bot = 0.10 if bh > bw * 1.3 else 0.04
            ex1 = max(0, int(x1 - bw * m_x))
            ey1 = max(0, int(y1 - bh * m_top))
            ex2 = min(w, int(x2 + bw * m_x))
            ey2 = min(h, int(y2 + bh * m_bot))
        else:
            ex1 = max(0, int(x1 - bw * 0.05))
            ey1 = max(0, int(y1 - bh * 0.05))
            ex2 = min(w, int(x2 + bw * 0.05))
            ey2 = min(h, int(y2 + bh * 0.05))

        expanded_bbox = [ex1, ey1, ex2, ey2]
        mask_obtained = False

        # 1. MobileSAM 추론 시도
        if sam is not None:
            try:
                results = sam(img, bboxes=[expanded_bbox], verbose=False)
                if results and results[0].masks is not None:
                    m_data = results[0].masks.data.cpu().numpy()
                    sub_m = (m_data[0] * 255).astype(np.uint8)
                    if sub_m.shape != (h, w):
                        sub_m = cv2.resize(sub_m, (w, h), interpolation=cv2.INTER_NEAREST)

                    # BBox 범위 외곽 엄격 제한 (경계 밖 누수 차단)
                    crop_mask = np.zeros_like(sub_m)
                    crop_mask[ey1:ey2, ex1:ex2] = 255
                    sub_m = cv2.bitwise_and(sub_m, crop_mask)

                    # 노이즈 컨투어 정제: 면적 300px 미만 또는 주 컨투어 대비 5% 미만인 고립된 파편(팔/어깨 침범 원인) 완전 제거
                    contours, _ = cv2.findContours(sub_m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        max_area = max(cv2.contourArea(c) for c in contours)
                        cleaned_sub_m = np.zeros_like(sub_m)
                        for c in contours:
                            c_area = cv2.contourArea(c)
                            if c_area >= 300 and c_area >= max_area * 0.05:
                                cv2.drawContours(cleaned_sub_m, [c], -1, 255, -1)
                        sub_m = cleaned_sub_m

                    if np.count_nonzero(sub_m) > 0:
                        final_mask = np.maximum(final_mask, sub_m)
                        mask_obtained = True
            except Exception as e:
                logger.warning(f"[Censor] MobileSAM 추론 실패, OpenCV 폴백: {e}")

        # 2. SAM 실패 시 OpenCV GrabCut / 엣지 기반 전경 마스크 폴백
        if not mask_obtained:
            try:
                roi = img_np[ey1:ey2, ex1:ex2]
                if roi.size > 0:
                    bgd_model = np.zeros((1, 65), np.float64)
                    fgd_model = np.zeros((1, 65), np.float64)
                    rect = (2, 2, max(1, ex2 - ex1 - 4), max(1, ey2 - ey1 - 4))
                    grab_mask = np.zeros(roi.shape[:2], np.uint8)
                    cv2.grabCut(roi, grab_mask, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
                    fg_mask = np.where((grab_mask == 2) | (grab_mask == 0), 0, 255).astype(np.uint8)
                    final_mask[ey1:ey2, ex1:ex2] = np.maximum(final_mask[ey1:ey2, ex1:ex2], fg_mask)
                    mask_obtained = True
            except Exception:
                pass

        # 3. 최후 폴백: 둥근 직사각형
        if not mask_obtained:
            cv2.rectangle(final_mask, (ex1, ey1), (ex2, ey2), 255, -1)

    if np.count_nonzero(final_mask) == 0:
        return img

    # 마스크 클로징 및 스무딩 (자연스러운 외곽선 곡선화)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    closed = cv2.morphologyEx(final_mask, cv2.MORPH_CLOSE, kernel_close)

    # 테두리 가우시안 블러 (미세 안티앨리어싱)
    blurred = cv2.GaussianBlur(closed, (3, 3), 1.0)

    # 색상 레이어 합성
    if isinstance(color, str):
        color_rgb = (255, 255, 255) if color.lower() in ("white", "whiteout", "white_silhouette") else (0, 0, 0)
    else:
        color_rgb = color

    alpha = (blurred.astype(np.float32) / 255.0)[:, :, np.newaxis]
    target_layer = np.full_like(img_np, color_rgb, dtype=np.float32)
    blended = (1.0 - alpha) * img_np.astype(np.float32) + alpha * target_layer
    blended = np.clip(blended, 0, 255).astype(np.uint8)

    return Image.fromarray(blended)


def apply_black_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Tuple[int, int, int, int], str]],
) -> Image.Image:
    """블랙 실루엣(#000000) 검열 래퍼 함수."""
    return apply_silhouette(img, boxes_with_labels, color="black")


def apply_white_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Tuple[int, int, int, int], str]],
) -> Image.Image:
    """화이트 실루엣(#FFFFFF) 검열 래퍼 함수."""
    return apply_silhouette(img, boxes_with_labels, color="white")


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
    canvas = img.copy()
    draw = ImageDraw.Draw(canvas)
    img_w, img_h = canvas.size

    for (x1, y1, x2, y2) in boxes:
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)

        pad_x = max(min_margin, int(w * margin_ratio))
        pad_y = max(min_margin, int(h * margin_ratio))

        bx1 = max(0, x1 - pad_x)
        by1 = max(0, y1 - pad_y)
        bx2 = min(img_w, x2 + pad_x)
        by2 = min(img_h, y2 + pad_y)

        box_w = bx2 - bx1
        box_h = by2 - by1

        radius = max(4, int(min(box_w, box_h) * corner_radius_ratio))
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=radius, fill=(0, 0, 0))

    return canvas


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
    canvas = img.copy()
    draw = ImageDraw.Draw(canvas)

    for (x1, y1, x2, y2) in boxes:
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        bar_thickness = max(12, min(32, int(min(w, h) * thickness_ratio)))
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

    return canvas


def apply_shadow_silhouette(
    img: Image.Image,
    boxes: Sequence[Tuple[int, int, int, int]],
    shadow_opacity: float = 0.85,
    blur_radius: int = 14,
) -> Image.Image:
    """
    형태 윤곽선과 굴곡(실루엣)은 은은하게 유지하되, 내부 선화 디테일만 짙은 그림자 톤으로 덮는
    고급 그림자 음영(Shadow Box) 검열을 적용합니다.
    """
    canvas = img.copy()

    for (x1, y1, x2, y2) in boxes:
        crop_box = (max(0, x1), max(0, y1), min(canvas.width, x2), min(canvas.height, y2))
        sub_img = canvas.crop(crop_box)

        blurred = sub_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        shadow = Image.new("RGB", blurred.size, color=(18, 18, 18))
        blended = Image.blend(blurred, shadow, alpha=shadow_opacity)

        canvas.paste(blended, crop_box)

    return canvas


def apply_mosaic(
    img: Image.Image,
    boxes: Sequence[Tuple[int, int, int, int]],
    block_size: int = 14,
) -> Image.Image:
    """
    클래식 격자 모자이크(Pixelated Mosaic)를 적용합니다.
    """
    canvas = img.copy()

    for (x1, y1, x2, y2) in boxes:
        crop_box = (max(0, x1), max(0, y1), min(canvas.width, x2), min(canvas.height, y2))
        sub_img = canvas.crop(crop_box)
        w, h = sub_img.size
        small_w = max(1, w // block_size)
        small_h = max(1, h // block_size)

        pixelated = sub_img.resize((small_w, small_h), Image.Resampling.BILINEAR).resize(
            (w, h), Image.Resampling.NEAREST
        )
        canvas.paste(pixelated, crop_box)

    return canvas


def censor_image(
    image: Union[Image.Image, Path, str],
    style: str = "silhouette",
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.35,
) -> Tuple[Image.Image, int]:
    """
    이미지 내 남성기(또는 지정 부위)를 자동으로 감지하여 검열을 적용합니다.
    - 기본 스타일: 'silhouette' (남성기+고환 외곽선 정밀 블랙 실루엣)
    - 반환값: (검열된 PIL 이미지, 감지된 부위 개수)
    """
    if isinstance(image, (str, Path)):
        img = Image.open(str(image)).convert("RGB")
    else:
        img = image.convert("RGB")

    normalized_targets = set()
    for t in targets:
        t_clean = str(t).strip().lower()
        if t_clean in ("all", "both"):
            normalized_targets.update(["penis", "pussy", "nipple_f"])
        elif t_clean in ("genital", "genitals", "sex"):
            normalized_targets.update(["penis", "pussy"])
        elif t_clean in ("pussy", "vagina", "vulva"):
            normalized_targets.add("pussy")
        elif t_clean in ("penis", "cock", "dick"):
            normalized_targets.add("penis")
        elif t_clean in ("nipple", "nipples", "nipple_f"):
            normalized_targets.add("nipple_f")
        else:
            normalized_targets.add(t_clean)

    detected_boxes_with_labels: List[Tuple[Tuple[int, int, int, int], str]] = []

    if HAS_IMGUTILS:
        try:
            results = detect_censors(img)
            for box, label, score in results:
                if label in normalized_targets and score >= min_confidence:
                    x1, y1, x2, y2 = [int(v) for v in box]
                    detected_boxes_with_labels.append(((x1, y1, x2, y2), label))
        except Exception as e:
            logger.warning(f"[Censor] 감지 모델 추론 예외: {e}")

    if not detected_boxes_with_labels:
        return img, 0

    detected_boxes = [box for box, _ in detected_boxes_with_labels]
    style_clean = style.lower().strip()

    if style_clean in ("white_silhouette", "white", "whiteout"):
        censored = apply_white_silhouette(img, detected_boxes_with_labels)
    elif style_clean in ("black_silhouette", "silhouette_black", "black"):
        censored = apply_black_silhouette(img, detected_boxes_with_labels)
    elif style_clean in ("silhouette", "contour"):
        # 기본 실루엣: 화이트 실루엣
        censored = apply_white_silhouette(img, detected_boxes_with_labels)
    elif style_clean in ("bar", "wide_bar", "solid_bar", "black_bar", "pill_bar"):
        censored = apply_wide_solid_bar(img, detected_boxes)
    elif style_clean in ("slim_bar", "thin_bar"):
        censored = apply_slim_black_bar(img, detected_boxes)
    elif style_clean in ("shadow", "shadow_box", "shadow_silhouette"):
        censored = apply_shadow_silhouette(img, detected_boxes)
    elif style_clean in ("mosaic", "pixel"):
        censored = apply_mosaic(img, detected_boxes)
    else:
        censored = apply_white_silhouette(img, detected_boxes_with_labels)

    return censored, len(detected_boxes_with_labels)


def censor_file(
    src_path: Union[Path, str],
    dst_path: Optional[Union[Path, str]] = None,
    style: str = "white_silhouette",
    targets: Sequence[str] = ("penis",),
    quality: int = 95,
) -> Optional[Path]:
    """
    파일 경로를 입력받아 검열본을 생성하고 저장합니다.
    - dst_path 미지정 시 'stem_censored.webp'로 자동 저장.
    - 감지된 검열 대상이 없는 경우 검열본을 생성하지 않고 None 반환.
    """
    src = Path(src_path)
    if not src.exists():
        return None

    img = Image.open(src).convert("RGB")
    censored_img, count = censor_image(img, style=style, targets=targets)

    if count == 0:
        return None

    if dst_path is None:
        target_dst = src.with_name(f"{src.stem}_censored{src.suffix}")
    else:
        target_dst = Path(dst_path)

    target_dst.parent.mkdir(parents=True, exist_ok=True)
    censored_img.save(target_dst, "WEBP", quality=quality)
    return target_dst
