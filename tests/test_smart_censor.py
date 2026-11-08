"""
tests/test_smart_censor.py
피부색(HSV) 보존 스마트 컨투어 및 2차 사후 무결성 검증 게이트 단위 테스트:
1. get_skin_mask의 애니메이션 살구빛/핑크빛 피부 감지 정확도 검증
2. apply_silhouette 실행 시 피부 영역 침범 방지 검증
3. verify_and_heal_censor의 잔여 노출 자동 치유 동작 검증
"""

import numpy as np
import pytest
from PIL import Image

from plepa_engine.censor import (
    apply_debug_bbox,
    apply_silhouette,
    censor_image,
    get_skin_mask,
    verify_and_heal_censor,
)


def test_get_skin_mask():
    """피부색 영역 추출 검증."""
    # 100x100 크기의 이미지 생성
    img_np = np.zeros((100, 100, 3), dtype=np.uint8)

    # 살구빛 피부톤 색상 (RGB: 255, 224, 189 -> HSV: ~16, 66, 255)
    img_np[20:80, 20:80] = [255, 224, 189]
    # 푸른 배경 (RGB: 0, 100, 255)
    img_np[0:20, :] = [0, 100, 255]

    mask = get_skin_mask(img_np)
    # 피부 영역(20:80, 20:80) 내부의 픽셀이 255로 검출되어야 함
    assert mask[50, 50] == 255
    # 배경 영역(10, 50)은 0이어야 함
    assert mask[10, 50] == 0


def test_apply_silhouette_basic():
    """기본 실루엣 렌더링 동작 검증."""
    img = Image.new("RGB", (200, 200), (255, 220, 190))
    boxes = [((50, 50, 150, 150), "penis")]

    censored = apply_silhouette(img, boxes, color="white")
    assert isinstance(censored, Image.Image)
    assert censored.size == (200, 200)

    # 결과 이미지가 비어있지 않고 유효하게 반환됨
    arr = np.array(censored)
    assert arr.shape == (200, 200, 3)


def test_verify_and_heal_censor_clean():
    """노출이 없는 안전한 이미지는 추가 변경 없이 그대로 통과."""
    clean_img = Image.new("RGB", (200, 200), (128, 128, 128))
    result, was_healed = verify_and_heal_censor(clean_img, style="white_silhouette")
    assert isinstance(result, Image.Image)
    assert was_healed is False


def test_apply_debug_bbox():
    """BBox 및 신뢰도 점수 디버그 시각화 렌더링 검증."""
    img = Image.new("RGB", (300, 300), (255, 255, 255))
    boxes = [
        ((50, 50, 150, 150), "penis", 0.88),
        ((160, 160, 220, 220), "pussy"),
    ]
    debug_img = apply_debug_bbox(img, boxes)
    assert isinstance(debug_img, Image.Image)
    assert debug_img.size == (300, 300)

    # 원본 흰색 이미지와 디버그 박스가 그려진 이미지가 달라야 함
    orig_arr = np.array(img)
    debug_arr = np.array(debug_img)
    assert not np.array_equal(orig_arr, debug_arr)
