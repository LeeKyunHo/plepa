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


def test_min_confidence_and_backlit_skin_exemption(monkeypatch):
    """하향 조정된 min_confidence(0.18) 보존 및 고신뢰(>=0.50) 역광 박스 Skin Gate 면제 검증."""
    import plepa_engine.censor as censor

    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)

    # 1. 피부색 이미지에 score=0.19 후보 -> min_confidence=0.18이면 통과해야 함
    skin_img = Image.new("RGB", (500, 500), (245, 200, 180))
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda im, conf_threshold=0.16: [((180, 220, 280, 360), "penis", 0.19)] if im.size == (500, 500) else [],
    )
    out_low, cnt_low = censor_image(skin_img, min_confidence=0.18, style="bar")
    assert cnt_low == 1
    assert out_low.size == (500, 500)

    # 2. 어두운 역광 이미지(피부율 0%)라도 score=0.85면 Skin Density Gate를 통과해야 함
    dark_img = Image.new("RGB", (500, 500), (20, 20, 25))
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda im, conf_threshold=0.16: [((180, 220, 280, 360), "penis", 0.85)] if im.size == (500, 500) else [],
    )
    _, cnt_dark = censor_image(dark_img, min_confidence=0.20, style="bar")
    assert cnt_dark == 1


def test_detect_genitals_pose_code_and_rois(monkeypatch):
    """detect_genitals의 pose_code/다중 ROI 지원 계약 검증."""
    import plepa_engine.censor as censor

    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)
    seen_sizes = []

    def fake_detect(im, conf_threshold=0.16):
        seen_sizes.append(im.size)
        if im.size == (500, 500):
            return [((200, 240, 280, 360), "penis", 0.82)]
        return []

    monkeypatch.setattr(censor, "detect_censors", fake_detect)
    skin_img = Image.new("RGB", (500, 500), (245, 200, 180))
    res = censor.detect_genitals(skin_img, pose_code="088", min_confidence=0.20)
    assert len(res) == 1
    assert res[0][1] == "penis"
    # 전체 스캔 + 포즈 맞춤형 ROI 크롭 스캔이 호출되었는지 확인
    assert len(seen_sizes) >= 2


def test_all_styles_and_verify_heal_respects_style(monkeypatch):
    """6종 스타일 렌더링(Shadow 소프트 페더링 포함) 및 verify_and_heal_censor 스타일 존중 검증."""
    import plepa_engine.censor as censor

    base = Image.new("RGB", (400, 400), (245, 200, 180))
    boxes = [((120, 140, 260, 280), "penis", 0.90)]

    for st in ("white_silhouette", "black_silhouette", "bar", "slim_bar", "shadow", "mosaic"):
        rendered = censor._render_censored_style(base, boxes, style=st)
        assert rendered.size == (400, 400)
        assert not np.array_equal(np.array(rendered), np.array(base))

    # shadow 스타일은 직사각형 외곽 코너(121, 141)가 하드 덮어쓰기되지 않고 원본에 가까워야 함
    shadow_img = censor.apply_shadow_silhouette(base, [boxes[0][0]])
    corner_px = shadow_img.getpixel((121, 141))
    center_px = shadow_img.getpixel((190, 210))
    assert corner_px[0] > center_px[0] + 50

    # verify_and_heal_censor(style="bar")가 블랙 실루엣이 아닌 와이드 솔리드 바(#000000)로 보정하는지 검증
    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda im, conf_threshold=0.32: [((150, 160, 230, 240), "penis", 0.88)],
    )
    healed, was_healed = verify_and_heal_censor(base, style="bar")
    assert was_healed is True
    assert healed.getpixel((190, 200)) == (0, 0, 0)


def test_rgba_preservation_and_scale_helpers(tmp_path, monkeypatch):
    """RGBA 알파 채널 무손실 보존 및 4K 스케일 팩터/모자이크 ROI 크롭 검증."""
    import plepa_engine.censor as censor

    rgba = Image.new("RGBA", (300, 300), (245, 200, 180, 255))
    alpha = Image.new("L", (300, 300), 255)
    alpha.putpixel((10, 10), 42)
    rgba.putalpha(alpha)

    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda im, conf_threshold=0.16: [((100, 140, 200, 240), "penis", 0.90)] if im.size == (300, 300) else [],
    )
    out_rgba, cnt = censor_image(rgba, style="bar")
    assert cnt == 1
    assert out_rgba.mode == "RGBA"
    assert out_rgba.getchannel("A").getpixel((10, 10)) == 42

    src_png = tmp_path / "test_088_missionary.png"
    dst_png = tmp_path / "test_088_missionary_censored.png"
    rgba.save(src_png, "PNG")
    saved = censor.censor_file(src_png, dst_png, style="mosaic")
    assert saved == dst_png and dst_png.exists()
    with Image.open(dst_png) as reopened:
        assert reopened.mode == "RGBA"
        assert reopened.getchannel("A").getpixel((10, 10)) == 42

    assert censor._compute_scale_factor(3328, 4864) == pytest.approx(4.0)


def test_unload_censor_models_and_sam_lock(monkeypatch):
    """unload_censor_models() 싱글톤 해제 및 SAM ROI 크롭/실루엣 보존 검증."""
    import plepa_engine.censor as censor

    censor._SAM_MODEL = object()
    censor.unload_censor_models()
    assert censor._SAM_MODEL is None

    # get_sam_model이 None을 반환해도 타원 폴백으로 정상 동작해야 함
    monkeypatch.setattr(censor, "get_sam_model", lambda: None)
    img = Image.new("RGB", (300, 300), (245, 200, 180))
    out = apply_silhouette(img, [((100, 120, 180, 220), "penis", 0.9)], color="black")
    assert out.size == (300, 300)
    assert np.mean(np.array(out)[150:190, 120:160]) < 100

