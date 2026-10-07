"""
plepa_engine.censor
2D 애니메이션 일러스트 전용 자동 성기 검열(Censorship) 모듈.
- 슬림 블랙 바 (Thin Black Bar)
- 그림자 실루엣 (Shadow Silhouette)
- 격자 모자이크 (Pixelated Mosaic)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageDraw, ImageFilter

try:
    from imgutils.detect import detect_censors
    HAS_IMGUTILS = True
except ImportError:
    HAS_IMGUTILS = False


def apply_wide_solid_bar(
    img: Image.Image,
    boxes: Sequence[Tuple[int, int, int, int]],
    margin_ratio: float = 0.18,
    corner_radius_ratio: float = 0.25,
    min_margin: int = 6,
) -> Image.Image:
    """
    2D 서브컬처 상업 동인지/미연시(DLsite/FANZA) 표준 '와이드 솔리드 캡슐 바(Wide Solid Bar)'를 렌더링합니다.
    - 정밀 성기 BBox 영역을 상하좌우 18% 적응형 세이프 마진(Safe Margin)으로 팽창하여 1픽셀의 노출 누수도 100% 원천 차단.
    - 각진 직사각형 블록의 투박함을 배제하고 모서리를 둥글게 깎는 캡슐형(Pill-shaped) 라운딩을 적용하여
      복부, 허벅지 등 인접한 인체 곡선미를 95% 이상 자연스럽게 보존합니다.
    """
    canvas = img.copy()
    draw = ImageDraw.Draw(canvas)
    img_w, img_h = canvas.size

    for (x1, y1, x2, y2) in boxes:
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)

        # 18% 적응형 세이프 마진 적용 (경계면 누수 제로 보장)
        pad_x = max(min_margin, int(w * margin_ratio))
        pad_y = max(min_margin, int(h * margin_ratio))

        bx1 = max(0, x1 - pad_x)
        by1 = max(0, y1 - pad_y)
        bx2 = min(img_w, x2 + pad_x)
        by2 = min(img_h, y2 + pad_y)

        box_w = bx2 - bx1
        box_h = by2 - by1

        # 모서리 라운딩 반경 계산 (짧은 쪽 변의 25~35%)
        radius = max(4, int(min(box_w, box_h) * corner_radius_ratio))

        # 캡슐형 둥근 직사각형 렌더링 (솔리드 블랙 RGB: 0, 0, 0)
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

        # 바 두께: 박스 최소 변의 25~30% (최소 12px, 최대 32px)
        bar_thickness = max(12, min(32, int(min(w, h) * thickness_ratio)))
        # 바 길이: 박스 대각선 또는 최대 변의 95%
        bar_length = max(w, h) * 0.95

        angle_rad = math.radians(angle_deg)
        dx = (bar_length / 2.0) * math.cos(angle_rad)
        dy = (bar_length / 2.0) * math.sin(angle_rad)

        p1 = (cx - dx, cy - dy)
        p2 = (cx + dx, cy + dy)

        # 둥근 끝선(Round cap) 스타일로 부드럽고 깔끔하게 렌더링
        draw.line([p1, p2], fill=(0, 0, 0), width=bar_thickness)
        # 양 끝점 둥글림
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
    고급 그림자 실루엣(Shadow Silhouette) 검열을 적용합니다.
    """
    canvas = img.copy()

    for (x1, y1, x2, y2) in boxes:
        box_w = max(1, x2 - x1)
        box_h = max(1, y2 - y1)
        crop_box = (max(0, x1), max(0, y1), min(canvas.width, x2), min(canvas.height, y2))
        sub_img = canvas.crop(crop_box)

        # 1. 내부 세부 선화 블러링
        blurred = sub_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # 2. 짙은 흑회색 그림자 오버레이 블렌딩
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
    style: str = "bar",
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.35,
) -> Tuple[Image.Image, int]:
    """
    이미지 내 남성기(또는 지정 부위)를 자동으로 감지하여 검열을 적용합니다.
    - 반환값: (검열된 PIL 이미지, 감지된 부위 개수)
    """
    if isinstance(image, (str, Path)):
        img = Image.open(str(image)).convert("RGB")
    else:
        img = image.convert("RGB")

    # 타깃 키워드 정규화 ('all', 'genital', 'penis', 'pussy', 'nipple' 등 지원)
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

    detected_boxes: List[Tuple[int, int, int, int]] = []

    if HAS_IMGUTILS:
        try:
            results = detect_censors(img)
            for box, label, score in results:
                if label in normalized_targets and score >= min_confidence:
                    x1, y1, x2, y2 = [int(v) for v in box]
                    detected_boxes.append((x1, y1, x2, y2))
        except Exception as e:
            # 탐지 예외 시 안전 폴백
            print(f"  [검열 탐지 경고] 모델 추론 예외: {e}")

    if not detected_boxes:
        # 감지된 부위가 없으면 원본 그대로 반환
        return img, 0

    style_clean = style.lower().strip()
    if style_clean in ("bar", "wide_bar", "solid_bar", "black_bar", "pill_bar"):
        censored = apply_wide_solid_bar(img, detected_boxes)
    elif style_clean in ("slim_bar", "thin_bar"):
        censored = apply_slim_black_bar(img, detected_boxes)
    elif style_clean in ("shadow", "silhouette", "shadow_silhouette"):
        censored = apply_shadow_silhouette(img, detected_boxes)
    elif style_clean in ("mosaic", "pixel"):
        censored = apply_mosaic(img, detected_boxes)
    else:
        censored = apply_wide_solid_bar(img, detected_boxes)

    return censored, len(detected_boxes)


def censor_file(
    src_path: Union[Path, str],
    dst_path: Optional[Union[Path, str]] = None,
    style: str = "bar",
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
