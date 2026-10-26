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
    2D 애니메이션 일러스트에서 여주인공의 밝은 피부 영역(살구빛/핑크빛)을 고정밀 HSV 필터로 추출합니다.
    - Hue: [0, 28] 또는 [165, 180] (자연스러운 붉은빛~살구빛 피부톤)
    - Saturation: [20, 160] (너무 무채색(흰색)이거나 너무 원색(의상)인 픽셀 제외)
    - Value: [125, 255] (어두운 음영/선화 제외한 밝은 피부 영역)
    """
    hsv = cv2.cvtColor(img_np, cv2.COLOR_RGB2HSV)
    lower1 = np.array([0, 20, 125], dtype=np.uint8)
    upper1 = np.array([28, 160, 255], dtype=np.uint8)
    mask1 = cv2.inRange(hsv, lower1, upper1)

    lower2 = np.array([165, 20, 125], dtype=np.uint8)
    upper2 = np.array([180, 160, 255], dtype=np.uint8)
    mask2 = cv2.inRange(hsv, lower2, upper2)

    return cv2.bitwise_or(mask1, mask2)



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
    skin_np = get_skin_mask(img_np)

    sam = get_sam_model()

    # 0. 눈/이마(Upper Face) 및 손(Hands) 보호 마스크 추출:
    #    - 얼굴(detect_faces) 상단 42%(눈·이마) 영역 보호
    #    - 손(detect_hands) 영역 감지 후 피부색 스마트 차감용으로 활용
    protection_mask = np.zeros((h, w), dtype=np.uint8)
    hands_mask = np.zeros((h, w), dtype=np.uint8)
    try:
        from imgutils.detect import detect_faces, detect_hands
        detected_faces = detect_faces(img, conf_threshold=0.35)

        for (fx1, fy1, fx2, fy2), _, _ in detected_faces:
            fh = max(1, fy2 - fy1)
            safe_fy2 = int(fy1 + fh * 0.42)
            if safe_fy2 > fy1:
                cv2.rectangle(protection_mask, (int(fx1), int(fy1)), (int(fx2), safe_fy2), 255, -1)

        detected_hands = detect_hands(img, conf_threshold=0.55)
        for (hx1, hy1, hx2, hy2), _, _ in detected_hands:
            cv2.rectangle(hands_mask, (int(hx1), int(hy1)), (int(hx2), int(hy2)), 255, -1)
    except Exception as pe:
        logger.debug(f"[Censor] 보호 영역 검출 생략: {pe}")

    for box, label in boxes_with_labels:
        x1, y1, x2, y2 = box
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)

        is_penis = label == "penis"
        if is_penis:
            # 슬림/타이트 마진:
            # 과도한 인공 마진으로 주변 피부/감상 영역이 가려지는 것을 막고,
            # AI 세그멘테이션이 실제 선화 경계선만 정확히 따도록 최소한의 마진만 적용
            m_x = 0.02
            m_top = 0.02
            m_bot = 0.08 if bh > bw * 1.2 else 0.03
            ex1 = max(0, int(x1 - bw * m_x))
            ey1 = max(0, int(y1 - bh * m_top))
            ex2 = min(w, int(x2 + bw * m_x))
            ey2 = min(h, int(y2 + bh * m_bot))
        else:
            m_x = 0.02
            m_top = 0.0
            m_bot = 0.03
            ex1 = max(0, int(x1 - bw * m_x))
            ey1 = max(0, y1)
            ex2 = min(w, int(x2 + bw * m_x))
            ey2 = min(h, int(y2 + bh * m_bot))

        expanded_bbox = [ex1, ey1, ex2, ey2]
        ebw = max(1, ex2 - ex1)
        ebh = max(1, ey2 - ey1)
        mask_obtained = False
        sub_m = np.zeros((h, w), dtype=np.uint8)

        # 1. MobileSAM 추론 (BBox + Point Prompting 중심점 가이드)
        if sam is not None:
            try:
                cx = int((ex1 + ex2) / 2)
                cy = int((ey1 + ey2) / 2)
                try:
                    results = sam(
                        img,
                        bboxes=[expanded_bbox],
                        points=[[[cx, cy]]],
                        labels=[[1]],
                        verbose=False
                    )
                except Exception:
                    results = sam(img, bboxes=[expanded_bbox], verbose=False)

                if results and results[0].masks is not None:
                    m_data = results[0].masks.data.cpu().numpy()
                    sub_m = (m_data[0] * 255).astype(np.uint8)
                    if sub_m.shape != (h, w):
                        sub_m = cv2.resize(sub_m, (w, h), interpolation=cv2.INTER_NEAREST)

                    # BBox 경계 외곽 엄격 제한 (타 부위 누수 차단)
                    crop_mask = np.zeros_like(sub_m)
                    crop_mask[ey1:ey2, ex1:ex2] = 255
                    sub_m = cv2.bitwise_and(sub_m, crop_mask)

                    # ── 스마트 피부색 차감 (손가락/허벅지 번짐 원천 방지) ──
                    # BBox 내부 중심 코어 영역(55%)은 대상 부위 본체이므로 온전히 보호하고,
                    # 손(detect_hands) 영역과 겹치거나 BBox 외곽부에 위치한 밝은 피부색 픽셀을 차감
                    core_mask = np.zeros((h, w), dtype=np.uint8)
                    c_pad_x = int(bw * 0.22)
                    c_pad_y = int(bh * 0.20)
                    core_x1 = min(w - 1, max(0, x1 + c_pad_x))
                    core_y1 = min(h - 1, max(0, y1 + c_pad_y))
                    core_x2 = max(core_x1 + 1, min(w, x2 - c_pad_x))
                    core_y2 = max(core_y1 + 1, min(h, y2 - c_pad_y))
                    cv2.rectangle(core_mask, (core_x1, core_y1), (core_x2, core_y2), 255, -1)

                    non_core = cv2.bitwise_not(core_mask)
                    # 손과 겹치는 피부는 100% 차감
                    hand_skin = cv2.bitwise_and(skin_np, hands_mask)
                    # 코어 바깥 BBox 외곽의 겹치는 피부 차감
                    outer_skin = cv2.bitwise_and(skin_np, non_core)
                    peel_mask = cv2.bitwise_or(hand_skin, outer_skin)
                    sub_m = cv2.bitwise_and(sub_m, cv2.bitwise_not(peel_mask))

                    # 노이즈 컨투어 정제: 미세 파편 제거
                    contours, _ = cv2.findContours(sub_m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        max_area = max(cv2.contourArea(c) for c in contours)
                        cleaned_sub_m = np.zeros_like(sub_m)
                        for c in contours:
                            c_area = cv2.contourArea(c)
                            if c_area >= 150 and c_area >= max_area * 0.05:
                                cv2.drawContours(cleaned_sub_m, [c], -1, 255, -1)
                        sub_m = cleaned_sub_m

                    if np.count_nonzero(sub_m) > 0:
                        mask_obtained = True
            except Exception as e:
                logger.warning(f"[Censor] MobileSAM 추론 실패, OpenCV 폴백: {e}")

        # 2. SAM 실패 시 OpenCV GrabCut 전경 마스크 폴백 (타원 강제 보강 배제)
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
                    sub_m[ey1:ey2, ex1:ex2] = np.maximum(sub_m[ey1:ey2, ex1:ex2], fg_mask)
                    if np.count_nonzero(sub_m) > 0:
                        mask_obtained = True
            except Exception:
                pass

        # 인공적인 타원 보강(Core Capsule)은 일러스트 감상미를 해치므로 완전 배제하고,
        # AI가 검출한 순수 실루엣만 렌더링합니다.
        final_mask = np.maximum(final_mask, sub_m)

    # 얼굴 상단(눈/이마) 보호 레이어 차감 (타겟 중심부가 훼손되지 않는 선에서만 보호)
    if np.count_nonzero(protection_mask) > 0:
        final_mask = cv2.bitwise_and(final_mask, cv2.bitwise_not(protection_mask))

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


# 체위별 안전 앵커 바운딩 박스 (정규화 좌표: [x0, y0, x1, y1])
POSE_SAFE_ANCHORS = {
    "missionary": [0.34, 0.58, 0.66, 0.84],   # 정상위/배위: 하단 중앙 영역
    "doggystyle": [0.35, 0.52, 0.65, 0.78],   # 후배위: 중앙 하단 결합부
    "cowgirl":    [0.34, 0.60, 0.66, 0.86],   # 기승위: 하단 기저부
    "fellatio":   [0.36, 0.38, 0.64, 0.60],   # 상반신·얼굴 밀착 구강: 중상단 입/접촉부
    "paizuri":    [0.34, 0.40, 0.66, 0.68],   # 상반신·바스트 밀착: 가슴 중심 결합부
    "side":       [0.35, 0.55, 0.65, 0.82],   # 측와위: 측면 교차부
    "default_h":  [0.34, 0.56, 0.66, 0.84],   # 기본 성인 결합 씬
}

# 100% 완전 착의 감정 표현 대역 (000~019)
EXEMPT_EMOTION_CODES = frozenset(f"{i:03d}" for i in range(0, 20))

# 100% 완전 착의 일상 이벤트 대역 (051~059)
EXEMPT_DAILY_EVENT_CODES = frozenset(f"{i:03d}" for i in range(51, 60))

# 일상 포즈(020~050) 중 명시적 탈의/노출 씬 (이 외의 모든 일상 포즈는 검열 면제)
DAILY_EXPOSURE_CODES = frozenset({
    "030",  # 전라스탠딩
    "037",  # 붓카케
    "038",  # 샤워뒤태
    "039",  # 샤워창밀착
    "044",  # 목욕중
    "045",  # 목욕들켜부끄러움
})

# 로맨스(060~079) 중 비노출/착의 씬 (성기 노출 없음)
ROMANCE_NON_EXPOSURE_CODES = frozenset({
    "060",  # 딥키스 (완전 착의 밀착 키스)
    "061",  # 알몸키스 (상체 밀착 키스)
})

# H씬(080~139, 150~209) 중 비노출 여운/포옹/대화 씬 (성기 노출 없음)
NON_EXPOSURE_H_POSES = frozenset({
    "101",  # 펠라사후
    "104",  # 입위강
    "105",  # 필로우토크
    "171",  # 펠라사후 (오토)
    "174",  # 입위강 (오토)
    "175",  # 필로우토크 (오토)
})


def is_pose_censor_required(
    pose_code: Union[str, int, None] = None,
    pose: Any = None,
    is_nude: bool = False,
    file_path: Union[str, Path, None] = None,
) -> bool:
    """
    V3 대역 체계 및 서브폴더 구조에 기반하여 해당 포즈/에셋이 검열 대상인지 엄격히 판정합니다:
    - 01_emotions (000~019): 완전 착의 감정표현 -> False (절대 면제)
    - 03_events (051~059): 완전 착의 일상 이벤트 -> False (절대 면제)
    - 02_daily (020~050): DAILY_EXPOSURE_CODES(030,037,038,039,044,045)만 True, 나머지 False (절대 면제)
    - 04_romance (060~079): 060,061(키스)은 False (절대 면제), 064~071(공용구강) 및 062,063은 True
    - 05_h_scenes, 06_special_h: NON_EXPOSURE_H_POSES(101,104,105,171,174,175)는 False, 나머지 True
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

    # 5. 로맨스(060~079): 064~071(공용 구강) 및 062, 063(함께씻기, 스푸닝)
    if 60 <= c_int <= 79:
        return c_int in (62, 63) or (64 <= c_int <= 71) or is_nude

    # 6. 성인 H씬 대역 (080~139 여성, 150~209 오토코노코)
    if (80 <= c_int <= 139) or (150 <= c_int <= 209):
        return True

    return False


def get_pose_category(pose_code: Union[str, int]) -> Optional[str]:
    """
    V3 포즈 코드(060~079, 080~139, 150~209)에 따른 체위 카테고리를 반환합니다.
    비노출 씬이거나 일반 일상 포즈는 None을 반환합니다.
    """
    code_str = str(pose_code).zfill(3)
    if code_str in NON_EXPOSURE_H_POSES:
        return None

    try:
        code_int = int(code_str)
    except ValueError:
        return None

    # 바스트/가슴 밀착 씬 (095 여성, 165 오토 대칭)
    if code_str in ("095", "165"):
        return "paizuri"

    # 구강/클로즈업 씬 (064~071 공용, 086~087, 098~100, 102, 120, 126~127, 132 및 오토 대칭)
    fellatio_codes = {
        "064", "065", "066", "067", "068", "069", "070", "071",
        "086", "087", "098", "099", "100", "102", "120", "126", "127", "132",
        "156", "157", "169", "170", "172", "190", "196", "197", "202"
    }
    if code_str in fellatio_codes:
        return "fellatio"
    # 후배위/배면 씬
    if code_str in ("088", "089", "090", "118", "121", "154", "158", "159", "160", "188", "191"):
        return "doggystyle"
    # 기승위/승마 씬
    if code_str in ("091", "092", "093", "109", "114", "130", "161", "162", "163", "179", "184", "200"):
        return "cowgirl"
    # 측와위 씬
    if code_str in ("107", "108", "119", "168", "177", "178", "189"):
        return "side"
    # 정상위/배위/누운 자세
    if code_str in ("080", "081", "082", "083", "084", "085", "094", "096", "097", "131", "150", "151", "152", "153", "164", "166", "167", "201"):
        return "missionary"
    # 그 외 성인 H-씬 대역 (064~079 공용 H, 080~139 여캐 H/특색, 150~209 오토 H/특색)
    if (64 <= code_int <= 79) or (80 <= code_int <= 139) or (150 <= code_int <= 209):
        return "default_h"

    return None


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


def censor_image(
    image: Union[Image.Image, Path, str],
    style: str = "silhouette",
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.14,
    pose_code: Optional[Union[str, int]] = None,
    enable_anchor_fallback: bool = False,
) -> Tuple[Image.Image, int]:
    """
    이미지 내 성기 부위를 자동으로 감지하여 검열을 적용합니다.
    - 기본 스타일: 'white_silhouette' (외곽선 화이트 실루엣)
    - 기본 대상: 남성기+고환 ('penis') — 여주인공 신체/다리/복부 오검열 방지
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

    detected_boxes_with_labels: List[Tuple[Tuple[int, int, int, int], str]] = []

    if HAS_IMGUTILS:
        try:
            results = detect_censors(img, conf_threshold=max(0.08, min_confidence * 0.8))
            img_w, img_h = img.size
            for box, label, score in results:
                if label in normalized_targets and score >= min_confidence:
                    x1, y1, x2, y2 = [int(v) for v in box]
                    bw = max(1, x2 - x1)
                    bh = max(1, y2 - y1)

                    # ── 자궁문신(Womb Tattoo) 및 복부 오탐지 보호 필터 ──
                    if label == "pussy":
                        if y2 < img_h * 0.48 and bh < img_h * 0.15:
                            logger.info(f"[Censor] 하복부 자궁문신 오인식 박스 제외: ({x1},{y1},{x2},{y2})")
                            continue

                        if bh > bw * 1.25 and bh > 60:
                            safe_cut = int(bh * 0.25)
                            y1 = min(y2 - 20, y1 + safe_cut)

                    detected_boxes_with_labels.append(((x1, y1, x2, y2), label))
        except Exception as e:
            logger.warning(f"[Censor] 감지 모델 추론 예외: {e}")

    # 검열 미탐지 시 체위별 안전 앵커 폴백 점검
    if not detected_boxes_with_labels and pose_code is not None:
        cat = get_pose_category(pose_code)
        if cat:
            logger.warning(
                f"[WARN] [Censor] 포즈 {pose_code}: 성기 미탐지! 안전 앵커 영역({cat}) 폴백 점검 대상입니다."
            )
            if enable_anchor_fallback:
                w, h = img.size
                anchor_box = get_pose_anchor_box(pose_code, w, h)
                if anchor_box:
                    detected_boxes_with_labels.append((anchor_box, "safe_anchor"))
                    logger.info(f"[Censor] 포즈 {pose_code}: 안전 앵커 폴백 박스 적용 {anchor_box}")

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

    # 2차 사후 무결성 게이트: 미세 잔여 노출 자동 치유
    censored, was_healed = verify_and_heal_censor(censored, style=style_clean, min_confidence=min_confidence)
    return censored, len(detected_boxes_with_labels)




def verify_and_heal_censor(
    censored_img: Image.Image,
    style: str = "white_silhouette",
    min_confidence: float = 0.14,
) -> Tuple[Image.Image, bool]:
    """
    검열이 완료된 이미지를 대상으로 성기 검출기를 다시 돌려 잔여 노출 여부를 2차 검증합니다.
    미세 누출이 감지되면 10% 확장 마진으로 즉시 2차 실루엣을 덧칠하여 100% 무결성을 보장합니다.
    반환값: (최종 안전 이미지, 추가 보정 발생 여부)
    """
    if not HAS_IMGUTILS:
        return censored_img, False

    try:
        results = detect_censors(censored_img, conf_threshold=min_confidence)
        leaks = [((int(b[0]), int(b[1]), int(b[2]), int(b[3])), label) for b, label, score in results if label in ("penis", "pussy")]
        if not leaks:
            return censored_img, False

        logger.warning(
            f"[Censor Gate] 2차 사후 검증에서 미세 잔여 노출 {len(leaks)}건 감지! 즉시 2차 안전 덧칠 보정을 수행합니다."
        )
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
    min_confidence: float = 0.14,
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
    min_confidence: float = 0.14,
) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
    """이미지에서 검열 대상 부위(성기 등)를 감지하여 [(box, label, score), ...] 형태로 반환합니다."""
    if not HAS_IMGUTILS:
        return []
    try:
        if isinstance(image, (str, Path)):
            img = Image.open(str(image)).convert("RGB")
        else:
            img = image.convert("RGB")
        results = detect_censors(img, conf_threshold=max(0.08, min_confidence * 0.8))
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
    min_confidence: float = 0.14,
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


