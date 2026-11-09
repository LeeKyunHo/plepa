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
import shutil
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



def apply_silhouette(
    img: Image.Image,
    boxes_with_labels: Sequence[Tuple[Tuple[int, int, int, int], str]],
    color: Union[str, Tuple[int, int, int]] = "black",
) -> Image.Image:
    """
    네모난 박스가 아니라 타겟과 기저부의 실제 선화 외곽선(Contour)을 따라
    내부만 솔리드 컬러(블랙 #000000 또는 화이트 #FFFFFF)로 매끈하게 채우는 실루엣 검열을 렌더링합니다.
    - 다중 피부 포인트 프롬프트 + 얼굴 중심 네거티브 프롬프트 기반 MobileSAM 정밀 세그멘테이션.
    - 구강/측면 구도에서 입가 직각 파임이나 허공 타원 팽창을 원천 차단.
    """
    w, h = img.size
    img_np = np.array(img.convert("RGB"))
    final_mask = np.zeros((h, w), dtype=np.uint8)
    skin_np = get_skin_mask(img_np)

    sam = get_sam_model()

    # 0. 눈/이마(Upper Face 38%) 보호 마스크 및 얼굴 중심 네거티브 포인트 추출:
    #    - 입이나 뺨을 직각으로 파내지 않도록 오직 눈·이마(상단 38%)만 소프트 보호
    protection_mask = np.zeros((h, w), dtype=np.uint8)
    hands_mask = np.zeros((h, w), dtype=np.uint8)
    face_neg_pts: List[List[int]] = []
    try:
        from imgutils.detect import detect_faces, detect_hands
        detected_faces = detect_faces(img, conf_threshold=0.35)

        for (fx1, fy1, fx2, fy2), _, _ in detected_faces:
            fh = max(1, fy2 - fy1)
            safe_fy2 = int(fy1 + fh * 0.38)
            if safe_fy2 > fy1:
                cv2.rectangle(protection_mask, (int(fx1), int(fy1)), (int(fx2), safe_fy2), 255, -1)
            face_neg_pts.append([int((fx1 + fx2) / 2), int(fy1 + fh * 0.42)])

        if np.count_nonzero(protection_mask) > 0:
            protection_mask = cv2.GaussianBlur(protection_mask, (15, 15), 4.0)
            _, protection_mask = cv2.threshold(protection_mask, 128, 255, cv2.THRESH_BINARY)

        detected_hands = detect_hands(img, conf_threshold=0.55)
        for (hx1, hy1, hx2, hy2), _, _ in detected_hands:
            cv2.rectangle(hands_mask, (int(hx1), int(hy1)), (int(hx2), int(hy2)), 255, -1)
    except Exception as pe:
        logger.debug(f"[Censor] 보호 영역 검출 생략: {pe}")

    for item in boxes_with_labels:
        box, label = item[0], item[1]
        x1, y1, x2, y2 = box
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)

        is_penis = label == "penis"
        if is_penis:
            m_x = 0.06
            m_top = 0.04
            m_bot = 0.14 if bh > bw * 0.7 else 0.08
        else:
            m_x = 0.03
            m_top = 0.02
            m_bot = 0.08

        ex1 = max(0, int(x1 - bw * m_x))
        ey1 = max(0, int(y1 - bh * m_top))
        ex2 = min(w, int(x2 + bw * m_x))
        ey2 = min(h, int(y2 + bh * m_bot))

        ebw = max(1, ex2 - ex1)
        ebh = max(1, ey2 - ey1)
        sub_m = np.zeros((h, w), dtype=np.uint8)
        sam_succeeded = False

        if sam is not None:
            try:
                # 1) BBox 내부의 타겟 피부 영역과 비타겟(창문/책장/벽/어두운 허공) 영역을 분리합니다.
                #    - L자형 구강 구도에서 BBox는 [상단 수평 기둥 + 좌/우 한쪽의 수직 기저부]로 구성되며,
                #      반대쪽 하단 코너(턱 밑 공간)는 배경(창문, 벽, 어두운 그림자 등)입니다!
                #    - 기저부가 좌측에 있는지 우측에 있는지 판별하여, 턱 밑 반대쪽 하단 코너(Void Corner)에
                #      네거티브 프롬프트 포인트를 찍고 비타겟 허공을 부드럽게 감산합니다!
                roi_rgb = img_np[ey1:ey2, ex1:ex2]
                roi_hsv = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2HSV)
                roi_skin = skin_np[ey1:ey2, ex1:ex2] > 0

                # 상단(15~48%)과 하단 좌/우(52~95%)의 피부 및 컬러 분포 비교
                mid_y_l = int(ebh * 0.50)
                mid_x_l = int(ebw * 0.50)
                left_bot_hsv = roi_hsv[mid_y_l:, :mid_x_l]
                right_bot_hsv = roi_hsv[mid_y_l:, mid_x_l:]

                # 상단 기둥의 대표 Hue 추출 (0~180)
                top_skin = roi_skin[int(ebh * 0.12):int(ebh * 0.48), :]
                top_h_med = float(np.median(roi_hsv[int(ebh * 0.12):int(ebh * 0.48), :, 0][top_skin])) if np.count_nonzero(top_skin) >= 20 else 11.0

                def _side_target_score(sub_hsv: np.ndarray, sub_sk: np.ndarray) -> float:
                    if sub_hsv.size == 0:
                        return 0.0
                    # 상단 기둥과 Hue 차이가 9.5 이하이면서 피부 마스크에 속하는 픽셀 비율
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

                # 상단 기둥 중심 포인트
                top_ys, top_xs = np.where(top_skin)
                if len(top_xs) >= 10:
                    pos_pts.append([ex1 + int(np.median(top_xs)), ey1 + int(ebh * 0.12) + int(np.median(top_ys))])
                else:
                    pos_pts.append([int((ex1 + ex2) / 2), int(ey1 + ebh * 0.30)])

                # 하단 기저부 포인트 및 반대쪽 턱 밑 허공(Void Corner) 판정
                void_corner_mask = np.zeros((h, w), dtype=np.uint8)
                if l_score > r_score * 1.15:
                    # 기저부가 좌측(x1 쪽), 우하단(x2 쪽)은 턱 밑 허공!
                    pos_pts.append([int(ex1 + ebw * 0.24), int(ey1 + ebh * 0.72)])
                    local_neg_pts.append([int(ex1 + ebw * 0.76), int(ey1 + ebh * 0.78)])
                    cv2.rectangle(
                        void_corner_mask,
                        (int(ex1 + ebw * 0.44), int(ey1 + ebh * 0.48)),
                        (ex2, ey2),
                        255,
                        -1,
                    )
                elif r_score > l_score * 1.15:
                    # 기저부가 우측(x2 쪽), 좌하단(x1 쪽)은 턱 밑 허공!
                    pos_pts.append([int(ex1 + ebw * 0.76), int(ey1 + ebh * 0.72)])
                    local_neg_pts.append([int(ex1 + ebw * 0.24), int(ey1 + ebh * 0.78)])
                    cv2.rectangle(
                        void_corner_mask,
                        (ex1, int(ey1 + ebh * 0.48)),
                        (int(ex1 + ebw * 0.56), ey2),
                        255,
                        -1,
                    )
                else:
                    # 중앙 수직형(파이즈리, 정상 결합 등)
                    pos_pts.append([int((ex1 + ex2) / 2), int(ey1 + ebh * 0.68)])

                sam_union = np.zeros((h, w), dtype=np.uint8)
                crop_mask = np.zeros((h, w), dtype=np.uint8)
                crop_mask[ey1:ey2, ex1:ex2] = 255

                for pt in pos_pts:
                    try:
                        all_pts = [pt] + local_neg_pts
                        all_lbls = [1] + [0] * len(local_neg_pts)
                        results = sam(
                            img,
                            bboxes=[[ex1, ey1, ex2, ey2]],
                            points=[all_pts],
                            labels=[all_lbls],
                            verbose=False,
                        )
                    except Exception:
                        results = sam(img, bboxes=[[ex1, ey1, ex2, ey2]], verbose=False)

                    if results and results[0].masks is not None:
                        m_data = results[0].masks.data.cpu().numpy()
                        raw_m = (m_data[0] * 255).astype(np.uint8)
                        if raw_m.shape != (h, w):
                            raw_m = cv2.resize(raw_m, (w, h), interpolation=cv2.INTER_NEAREST)
                        raw_m = cv2.bitwise_and(raw_m, crop_mask)
                        if np.count_nonzero(raw_m) >= 60:
                            sam_union = np.maximum(sam_union, raw_m)

                # 턱 밑 허공 코너가 감지된 경우(L자형 구강 구도), 허공 사각 코너를 부드럽게 라운딩 차감하여
                # 타겟 기둥과 수직 기저부는 100% 솔리드로 덮으면서 턱 밑 네모난 창문/배경 박스만 깔끔히 덜어냅니다!
                if np.count_nonzero(void_corner_mask) > 0:
                    soft_void = cv2.GaussianBlur(void_corner_mask, (21, 21), 6.0)
                    _, soft_void_bin = cv2.threshold(soft_void, 140, 255, cv2.THRESH_BINARY)
                    sam_union = cv2.bitwise_and(sam_union, cv2.bitwise_not(soft_void_bin))

                contours, _ = cv2.findContours(sam_union, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    max_area = max(cv2.contourArea(c) for c in contours)
                    for c in contours:
                        if cv2.contourArea(c) >= max(80, max_area * 0.15):
                            # 외곽 컨투어 내부를 -1로 완전히 채워 내부 검은 점/구멍을 100% 원천 제거합니다!
                            cv2.drawContours(sub_m, [c], -1, 255, -1)
                    if np.count_nonzero(sub_m) >= (bw * bh * 0.12):
                        sam_succeeded = True
            except Exception as e:
                logger.warning(f"[Censor] MobileSAM fallback: {e}")

        # MobileSAM이 실패했거나 중앙형 소형 타겟(면적 2.5% 미만, L자형 제외)인 경우에만 솔리드 타원 캡슐로 보강
        if not sam_succeeded or ((ebw * ebh) < (w * h * 0.025) and np.count_nonzero(sub_m) < (ebw * ebh * 0.45)):
            bcx = int((ex1 + ex2) / 2)
            bcy = int((ey1 + ey2) / 2)
            erx = min(int(w * 0.16), max(6, int(ebw * 0.44)))
            ery = min(int(h * 0.20), max(6, int(ebh * 0.46)))
            cv2.ellipse(sub_m, (bcx, bcy), (erx, ery), 0, 0, 360, 255, -1)

        final_mask = np.maximum(final_mask, sub_m)

    if np.count_nonzero(final_mask) == 0:
        return img

    # 5. 모폴로지 팽창 + 닫힘 + 가우시안 스무딩으로 선화 내부 빈틈을 메우고 과장 없는 날렵한 외곽선 완성
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dilated = cv2.dilate(final_mask, kernel_dilate, iterations=1)

    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel_close)

    smooth_blur = cv2.GaussianBlur(closed, (7, 7), 1.8)
    _, smoothed = cv2.threshold(smooth_blur, 120, 255, cv2.THRESH_BINARY)

    # 얼굴 상단(눈/이마 38%) 보호 레이어 차감
    if np.count_nonzero(protection_mask) > 0:
        smoothed = cv2.bitwise_and(smoothed, cv2.bitwise_not(protection_mask))

    if np.count_nonzero(smoothed) == 0:
        return img

    # 6. 경계 블러 페더링 (소프트 안티앨리어싱으로 일러스트 선화와 자연스럽게 융합)
    blurred = cv2.GaussianBlur(smoothed, (5, 5), 1.2)

    # 색상 레이어 합성 (블랙 실루엣은 애니메이션 먹선 톤 (12, 12, 16) 적용)
    if isinstance(color, str):
        color_rgb = (255, 255, 255) if color.lower() in ("white", "whiteout", "white_silhouette") else (12, 12, 16)
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
    block_size: int = 16,
) -> Image.Image:
    """하단 기저부 42% 통합 확장 및 소프트 캡슐 페더링이 적용된 상업 표준 정밀 블러-모자이크."""
    w_img, h_img = img.size
    orig_np = np.array(img.convert('RGB'))
    blurred_pil = img.convert('RGB').filter(ImageFilter.GaussianBlur(radius=3))
    small_w = max(1, w_img // block_size)
    small_h = max(1, h_img // block_size)
    mosaic_full = blurred_pil.resize((small_w, small_h), Image.Resampling.BILINEAR).resize((w_img, h_img), Image.Resampling.NEAREST)
    mosaic_np = np.array(mosaic_full)
    mask = np.zeros((h_img, w_img), dtype=np.uint8)
    for (x1, y1, x2, y2) in boxes:
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        ex1 = max(0, int(x1 - bw * 0.04))
        ey1 = max(0, int(y1 - bh * 0.02))
        ex2 = min(w_img, int(x2 + bw * 0.04))
        ey2 = min(h_img, int(y2 + bh * (0.16 if bh > bw * 0.8 else 0.10)))
        cx = int((ex1 + ex2) / 2)
        cy = int((ey1 + ey2) / 2)
        rx = max(6, int((ex2 - ex1) * 0.48))
        ry = max(6, int((ey2 - ey1) * 0.48))
        cv2.ellipse(mask, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)
    if np.count_nonzero(mask) == 0:
        return img.copy()
    feathered = cv2.GaussianBlur(mask, (9, 9), 2.5)
    alpha = (feathered.astype(np.float32) / 255.0)[:, :, np.newaxis]
    blended = (1.0 - alpha) * orig_np.astype(np.float32) + alpha * mosaic_np.astype(np.float32)
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


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
    "doggystyle":  [0.35, 0.52, 0.65, 0.78],   # 후배위: 중앙 하단 결합부
    "cowgirl":     [0.34, 0.60, 0.66, 0.86],   # 기승위: 하단 기저부
    "fellatio":    [0.36, 0.38, 0.64, 0.60],   # 상반신·얼굴 밀착 구강: 중상단 입/접촉부
    "paizuri":     [0.34, 0.40, 0.66, 0.68],   # 상반신·바스트 밀착: 가슴 중심 결합부
    "piledriver":  [0.36, 0.08, 0.64, 0.38],   # 역전 파일드라이버: 상단 중앙 결합부
    "side":        [0.35, 0.55, 0.65, 0.82],   # 측와위: 측면 교차부
    "standing":    [0.34, 0.44, 0.66, 0.72],   # 입위(서서 하는 체위): 중앙 허리~골반 높이
    "shower":      [0.34, 0.48, 0.66, 0.76],   # 샤워실/수중 체위: 중앙 결합부
    "cunnilingus": [0.32, 0.52, 0.68, 0.82],   # 애무/커닐링구스/핑거링: 하단 중심부
    "handjob":     [0.34, 0.48, 0.66, 0.74],   # 대딸/핸드잡: 중하단 손 위치
    "footjob":     [0.34, 0.52, 0.66, 0.80],   # 풋잡: 하단 발 위치
    "spanking":    [0.34, 0.48, 0.66, 0.78],   # 스팽킹: 둔부/엉덩이 중심
    "default_h":   [0.34, 0.56, 0.66, 0.84],   # 기본 성인 결합 씬
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
NON_EXPOSURE_H_POSES: frozenset[str] = frozenset()


def is_pose_censor_required(
    pose_code: Union[str, int, None] = None,
    pose: Any = None,
    is_nude: bool = False,
    file_path: Union[str, Path, None] = None,
) -> bool:
    """
    2대 서브폴더 구조(01_normal, 02_h_scenes) 및 포즈 코드에 기반하여 해당 포즈/에셋이 검열 대상인지 엄격히 판정합니다:
    - 01_normal (000~059):
      * 000~019 (감정표현): 완전 착의 -> False (절대 면제)
      * 051~059 (일상 이벤트): 완전 착의 -> False (절대 면제)
      * 020~050 (범용 일상): DAILY_EXPOSURE_CODES(030,037,038,039,044,045)만 True, 나머지 False (절대 면제)
    - 02_h_scenes (060~209+):
      * 060~079 (로맨스/구강): 060,061(키스)은 False (절대 면제), 064~071(공용구강) 및 062,063은 True
      * 080~209 (범용/특색 H씬): NON_EXPOSURE_H_POSES(101,104,105,171,174,175)는 False, 나머지 True
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
        m = re.search(r"_(\d{3})(?:_|\.)", Path(file_path).name)
        if m:
            code_str = m.group(1)

    if not code_str:
        return False

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


_POSE_DB_CACHE: Optional[dict] = None


def _get_cached_pose_db() -> dict:
    """포즈 DB를 지연 로드하여 체위 카테고리 동적 추론에 활용합니다."""
    global _POSE_DB_CACHE
    if _POSE_DB_CACHE is None:
        try:
            from plepa_engine.services.pose_service import default_pose_service
            _POSE_DB_CACHE = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
        except Exception:
            _POSE_DB_CACHE = {}
    return _POSE_DB_CACHE


def get_pose_category(pose_code: Union[str, int]) -> Optional[str]:
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

    db = _get_cached_pose_db()
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
    pose_code: Union[str, int], img_width: int, img_height: int
) -> Optional[Tuple[int, int, int, int]]:
    """포즈 코드에 해당하는 안전 앵커 픽셀 바운딩 박스 (x1, y1, x2, y2)를 계산하여 반환합니다."""
    cat = get_pose_category(pose_code)
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


def censor_image(
    image: Union[Image.Image, Path, str],
    style: str = "white_silhouette",
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.16,
    pose_code: Optional[Union[str, int]] = None,
    enable_anchor_fallback: bool = False,
) -> Tuple[Image.Image, int]:
    """
    이미지 내 성기 및 결합 접점 부위를 다중 스케일(전체 + 하반신 줌인 ROI)로 정밀 감지하여 검열을 적용합니다.
    - 기본 스타일: 'white_silhouette' (매끈한 소프트 화이트 실루엣 - 젠잇 심의 규정 표준)
    - 기본 대상: 남성기+고환 ('penis') 및 성인 결합 씬의 하반신 삽입 접점 ('pussy', y2 >= 0.48*H)
    - 반환값: (검열된 PIL 이미지, 감지된 부위 개수)
    """
    # V3 오검열 원천 방어 가드: 비검열 대상(감정표현, 일상 스킨십, 착의 이벤트 등)은 즉시 원본 반환
    if pose_code is not None and not is_pose_censor_required(pose_code=pose_code, file_path=image if isinstance(image, (str, Path)) else None):
        return (Image.open(str(image)).convert("RGB") if isinstance(image, (str, Path)) else image.convert("RGB")), 0

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

    # 성인 결합 씬에서 'penis' 타겟 지정 시, 삽입 결합 접점('pussy'로 분류되는 하반신 접합부)도 함께 포착
    include_lower_junction = "penis" in normalized_targets
    eff_conf = min(min_confidence, 0.16)
    img_w, img_h = img.size

    detected_boxes_with_labels: List[Tuple[Any, ...]] = []

    skin_check_np = get_skin_mask(np.array(img))
    def _add_candidate(box_coords: Tuple[int, int, int, int], lbl: str, score: float = 1.0) -> None:
        x1, y1, x2, y2 = box_coords
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img_w, x2), min(img_h, y2)
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        if bw < 12 or bh < 12:
            return
        # 상단 배경/머리카락 오탐지 차단 (구강/상반신 클로즈업 및 역전 파일드라이버 씬은 상단 결합부까지 허용)
        pose_cat = get_pose_category(pose_code) if pose_code is not None else None
        is_upper_close = pose_cat in ("fellatio", "paizuri", "piledriver")
        min_y2_ratio = 0.04 if pose_cat == "piledriver" else (0.10 if is_upper_close else 0.24)
        if y2 < img_h * min_y2_ratio:
            return
        # 상단 얼굴/머리카락 침범 방지 (piledriver 제외: y1이 최상단 7% 이내이면 하향 조정)
        if pose_cat != "piledriver" and y1 < int(img_h * 0.07):
            y1 = max(y1, int(img_h * 0.07))
        # 배경/침대 시트 허공 박스 오탐지 원천 차단 (Skin Density Gate: 내부 피부톤 비율 18% 미만 시 즉시 폐기)
        roi_skin = skin_check_np[y1:y2, x1:x2]
        if roi_skin.size == 0 or (np.count_nonzero(roi_skin) / float(roi_skin.size)) < 0.18:
            return
        if lbl == "pussy":
            # 구강/파이즈리 단독 상반신 씬에서는 겨드랑이/쇄골 주름이 pussy로 오탐지되므로 원천 차단
            if pose_cat in ("fellatio", "paizuri"):
                return
            if pose_cat != "piledriver" and y2 < img_h * 0.48:
                return
            if bh > bw * 1.25 and bh > 60:
                safe_cut = int(bh * 0.22)
                y1 = min(y2 - 20, y1 + safe_cut)
        cand = (x1, y1, x2, y2)
        for idx, entry in enumerate(detected_boxes_with_labels):
            existing_box, existing_lbl = entry[0], entry[1]
            existing_score = float(entry[2]) if len(entry) >= 3 else 1.0
            if _box_iou(cand, existing_box) > 0.45:
                # 더 넓은 결합 영역으로 병합
                merged = (
                    min(cand[0], existing_box[0]),
                    min(cand[1], existing_box[1]),
                    max(cand[2], existing_box[2]),
                    max(cand[3], existing_box[3]),
                )
                detected_boxes_with_labels[idx] = (
                    merged,
                    "penis" if "penis" in (lbl, existing_lbl) else lbl,
                    max(score, existing_score),
                )
                return
        detected_boxes_with_labels.append((cand, lbl, score))

    if HAS_IMGUTILS:
        try:
            # [1단계] 전체 이미지 스캔
            results = detect_censors(img, conf_threshold=max(0.12, eff_conf * 0.85))
            for box, label, score in results:
                is_target = (label in normalized_targets and score >= eff_conf) or (
                    include_lower_junction and label == "pussy" and score >= max(0.18, eff_conf)
                )
                if is_target:
                    _add_candidate(tuple(int(v) for v in box), label, float(score))

            # [2단계] 다중 스케일 Zoom-In ROI 크롭 정밀 재스캔 (하반신 결합부 + 상반신 구강 클로즈업 + 상단 역전 결합부)
            roi_specs = [
                (0.14, 0.38, 0.86, 0.98),
                (0.20, 0.45, 0.80, 0.95),
                (0.12, 0.12, 0.88, 0.70),  # 상반신 / 구강 클로즈업 정밀 재스캔 ROI
                (0.18, 0.00, 0.82, 0.46),  # 상단 역전 자세(파일드라이버 등) 결합부 정밀 재스캔 ROI
            ]
            for rx0, ry0, rx1, ry1 in roi_specs:
                cx1, cy1 = int(img_w * rx0), int(img_h * ry0)
                cx2, cy2 = int(img_w * rx1), int(img_h * ry1)
                crop_img = img.crop((cx1, cy1, cx2, cy2))
                # 1.6배 Lanczos 업스케일 스캔으로 소형 타겟 검출률 극대화
                up_w, up_h = int(crop_img.width * 1.6), int(crop_img.height * 1.6)
                up_img = crop_img.resize((up_w, up_h), Image.Resampling.LANCZOS)
                crop_res = detect_censors(up_img, conf_threshold=0.13)
                for box, label, score in crop_res:
                    is_target = (label in normalized_targets and score >= 0.17) or (
                        include_lower_junction and label == "pussy" and score >= 0.20
                    )
                    if is_target:
                        bx1, by1, bx2, by2 = [int(v / 1.6) for v in box]
                        _add_candidate((bx1 + cx1, by1 + cy1, bx2 + cx1, by2 + cy1), label, float(score))
        except Exception as e:
            logger.warning(f"[Censor] 감지 모델 추론 예외: {e}")

    # 검열 미탐지 시 체위별 안전 앵커 폴백 점검 (기본 False: 신체 오검열 아티팩트 방지)
    if not detected_boxes_with_labels and pose_code is not None:
        cat = get_pose_category(pose_code)
        if cat:
            if enable_anchor_fallback:
                anchor_box = get_pose_anchor_box(pose_code, img.width, img.height)
                if anchor_box:
                    detected_boxes_with_labels.append((anchor_box, "anchor", 1.0))
                    logger.info(
                        f"[Censor] 포즈 {pose_code}: 성기 미탐지 ➔ 안전 앵커({cat}) 폴백 적용: {anchor_box}"
                    )
            else:
                logger.warning(
                    f"[WARN] [Censor] 포즈 {pose_code}: 성기 미탐지! 안전 앵커 영역({cat}) 폴백 점검 대상입니다."
                )

    if not detected_boxes_with_labels:
        return img, 0

    detected_boxes = [item[0] for item in detected_boxes_with_labels]
    style_clean = style.lower().strip()

    if style_clean in ("debug", "debug_bbox", "bbox", "bbox_debug"):
        censored = apply_debug_bbox(img, detected_boxes_with_labels)
        return censored, len(detected_boxes_with_labels)
    elif style_clean in ("white_silhouette", "white", "whiteout"):
        censored = apply_white_silhouette(img, detected_boxes_with_labels)
    elif style_clean in ("black_silhouette", "silhouette_black", "black", "silhouette", "contour"):
        censored = apply_black_silhouette(img, detected_boxes_with_labels)
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

    # 2차 사후 무결성 게이트: 미세 잔여 노출 자동 치유 (임계값 0.32로 과도한 2중 팽창 방지)
    censored, was_healed = verify_and_heal_censor(censored, style=style_clean, min_confidence=0.32)
    return censored, len(detected_boxes_with_labels)


def verify_and_heal_censor(
    censored_img: Image.Image,
    style: str = "white_silhouette",
    min_confidence: float = 0.32,
) -> Tuple[Image.Image, bool]:
    """
    검열이 완료된 이미지를 대상으로 성기 검출기를 다시 돌려 잔여 노출 여부를 2차 검증합니다.
    과도한 2중 팽창을 방지하기 위해 신뢰도 임계값 0.32 이상의 명백한 잔여 노출에만 2차 보정을 발동합니다.
    반환값: (최종 안전 이미지, 추가 보정 발생 여부)
    """
    if not HAS_IMGUTILS:
        return censored_img, False

    try:
        results = detect_censors(censored_img, conf_threshold=max(0.28, min_confidence))
        leaks = [((int(b[0]), int(b[1]), int(b[2]), int(b[3])), label) for b, label, score in results if label in ("penis", "pussy")]
        if not leaks:
            return censored_img, False

        logger.warning(
            f"[Censor Gate] 2차 사후 검증에서 명백한 잔여 노출 {len(leaks)}건 감지! 즉시 2차 안전 보정을 수행합니다."
        )
        if style.lower().strip() in ("mosaic", "pixel"):
            healed = apply_mosaic(censored_img, [b for b, _ in leaks])
        else:
            healed = apply_silhouette(censored_img, leaks, color=style)
        return healed, True
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
    if not is_pose_censor_required(pose_code=pose_code, file_path=src):
        return None

    if backup_dir:
        b_dir = Path(backup_dir)
        b_dir.mkdir(parents=True, exist_ok=True)
        b_path = b_dir / src.name
        if not b_path.exists():
            shutil.copy2(src, b_path)

    img = Image.open(src).convert("RGB")
    censored_img, count = censor_image(
        img,
        style=style,
        targets=targets,
        min_confidence=min_confidence,
        pose_code=pose_code,
        enable_anchor_fallback=enable_anchor_fallback,
    )

    if count == 0:
        return None

    if dst_path is None:
        target_dst = src.with_name(f"{src.stem}_censored{src.suffix}")
    else:
        target_dst = Path(dst_path)

    target_dst.parent.mkdir(parents=True, exist_ok=True)
    censored_img.save(target_dst, "WEBP", quality=quality)
    return target_dst


def detect_genitals(
    image: Union[Path, str, Image.Image],
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.22,
) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
    """이미지에서 검열 대상 부위(성기 등)를 감지하여 [(box, label, score), ...] 형태로 반환합니다."""
    if not HAS_IMGUTILS:
        return []
    try:
        if isinstance(image, (str, Path)):
            img = Image.open(str(image)).convert("RGB")
        else:
            img = image.convert("RGB")
        results = detect_censors(img, conf_threshold=max(0.18, min_confidence * 0.9))
        filtered = []
        normalized = set(t.lower() for t in targets)
        for box, label, score in results:
            if label.lower() in normalized and score >= min_confidence:
                filtered.append((box, label, score))
        return filtered
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

        # 2. V3 정밀 정규식: 하이브리드 파일명(prefix_000_label.webp) 및 코드 파일명(prefix_000.webp) 지원
        match = re.search(r"_(\d{3})(?:_|\.)", file_path.name)
        pose_code = int(match.group(1)) if match else None

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


