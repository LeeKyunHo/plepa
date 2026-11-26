"""
plepa_engine.censor._runtime
검열 서브패키지 공용 로거, 선택적 탐지기 임포트, Facade 바인딩 및 이미지/커널 기본 유틸리티.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("plepa_engine.censor")

try:
    from imgutils.detect import detect_censors
    HAS_IMGUTILS = True
except ImportError:
    detect_censors = None  # type: ignore[assignment]
    HAS_IMGUTILS = False

_BASE_RESOLUTION = 832.0


def facade_get(name: str, default: Any = None) -> Any:
    """`plepa_engine.censor` 파사드 모듈에 패치된 심볼이 있으면 우선 반환합니다."""
    pkg = sys.modules.get("plepa_engine.censor")
    if pkg is not None and name in pkg.__dict__:
        return pkg.__dict__[name]
    return default


def facade_set(name: str, value: Any) -> None:
    """`plepa_engine.censor` 파사드 모듈 속성이 존재할 때 상태를 동기화합니다."""
    pkg = sys.modules.get("plepa_engine.censor")
    if pkg is not None:
        pkg.__dict__[name] = value


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
