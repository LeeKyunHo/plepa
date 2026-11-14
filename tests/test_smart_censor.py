"""
tests/test_smart_censor.py
피부색(HSV) 보존 스마트 컨투어 및 2차 사후 무결성 검증 게이트 단위 테스트:
1. get_skin_mask의 애니메이션 살구빛/핑크빛 피부 감지 정확도 검증
2. apply_silhouette 실행 시 피부 영역 침범 방지 검증
3. verify_and_heal_censor의 잔여 노출 자동 치유 동작 검증
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

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
    """8종 스타일 렌더링(Shadow/Manga 포함) 및 verify_and_heal_censor 스타일 존중 검증."""
    import plepa_engine.censor as censor

    base = Image.new("RGB", (400, 400), (245, 200, 180))
    boxes = [((120, 140, 260, 280), "penis", 0.90)]

    for st in ("white_silhouette", "black_silhouette", "manga_bar", "manga_glow", "bar", "slim_bar", "shadow", "mosaic"):
        rendered = censor._render_censored_style(base, boxes, style=st)
        assert rendered.size == (400, 400)
        assert not np.array_equal(np.array(rendered), np.array(base))

    # shadow 스타일은 직사각형 외곽 코너(121, 141)가 하드 덮어쓰기되지 않고 원본에 가까워야 함
    shadow_img = censor.apply_shadow_silhouette(base, [boxes[0][0]])
    corner_px = shadow_img.getpixel((121, 141))
    center_px = shadow_img.getpixel((190, 210))
    assert corner_px[0] > center_px[0] + 50

    # verify_and_heal_censor(style="bar" / "manga_bar" / "manga_glow") 스타일 존중 검증
    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda im, conf_threshold=0.32: [((150, 160, 230, 240), "penis", 0.88)],
    )
    healed, was_healed = verify_and_heal_censor(base, style="bar")
    assert was_healed is True
    assert healed.getpixel((190, 200)) == (0, 0, 0)

    healed_mb, was_healed_mb = verify_and_heal_censor(base, style="manga_bar")
    assert was_healed_mb is True
    assert healed_mb.getpixel((190, 200)) == (0, 0, 0)

    healed_mg, was_healed_mg = verify_and_heal_censor(base, style="manga_glow")
    assert was_healed_mg is True
    assert healed_mg.getpixel((190, 200)) == (255, 255, 255)


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


def _make_diagonal_target_image(bg_color=(255, 255, 255), fg_color=(240, 185, 165)):
    """45도 대각선 기둥 + 우하단 낭심 팽대부 합성 테스트 이미지를 생성합니다."""
    img = Image.new("RGB", (400, 400), bg_color)
    draw = ImageDraw.Draw(img)
    # 얇은 기둥: (125, 125) -> (230, 230)
    draw.line([(125, 125), (230, 230)], fill=fg_color, width=22)
    draw.ellipse([114, 114, 136, 136], fill=fg_color)
    # 넓은 낭심(Base): (225, 225) 주변 원형/타원형 팽대부 (폭 ~66px)
    draw.ellipse([192, 192, 258, 258], fill=fg_color)
    return img


def test_estimate_penis_axis_and_base_diagonal_and_oral():
    """대각선 주축 각도(PCA), 양 끝단 30% 폭 기반 낭심 위치 추정 및 구강 씬·폴백 동작을 검증합니다."""
    import plepa_engine.censor as censor

    img = _make_diagonal_target_image()
    img_np = np.array(img)
    bbox = (90, 90, 280, 280)

    geom = censor._estimate_penis_axis_and_base(img_np, bbox)
    assert geom["fallback"] is False
    # 45도(-135도) 대각선 주축 정렬 검증
    mod_angle = geom["angle"] % 180.0
    assert abs(mod_angle - 45.0) < 12.0

    # 낭심(Base)은 더 넓은 우하단 (225, 225) 쪽에 가까워야 함
    bx, by = geom["base_center"]
    dist_to_base = ((bx - 225.0) ** 2 + (by - 225.0) ** 2) ** 0.5
    dist_to_tip = ((bx - 125.0) ** 2 + (by - 125.0) ** 2) ** 0.5
    assert dist_to_base < dist_to_tip

    # 구강 씬(fellatio)에서는 얼굴/입에서 먼 하단 끝점을 Base로 고정
    geom_oral = censor._estimate_penis_axis_and_base(img_np, bbox, pose_cat="fellatio")
    assert geom_oral["base_center"][1] > 180.0

    # 배경과 동일한 평탄 이미지(픽셀 구분 불가)에서는 BBox 종횡비 폴백 작동
    flat_np = np.full((300, 300, 3), 245, dtype=np.uint8)
    geom_fb = censor._estimate_penis_axis_and_base(flat_np, (50, 100, 250, 180))
    assert geom_fb["fallback"] is True
    assert geom_fb["major_len"] > geom_fb["minor_len"]


def test_manga_bar_and_manga_glow_diagonal_masking():
    """manga_bar와 manga_glow가 대각선 기둥+낭심만 깔끔히 덮고 비대상 여백을 침범하지 않는지 검증합니다."""
    import plepa_engine.censor as censor

    bbox = (90, 90, 280, 280)
    boxes = [(bbox, "penis", 0.92)]

    # 1) manga_bar 검증: 흰 배경 위 대각선 피부 영역에 회전 바 적용
    img_bar = _make_diagonal_target_image(bg_color=(255, 255, 255), fg_color=(240, 185, 165))
    out_bar = censor._render_censored_style(img_bar, boxes, style="manga_bar")
    # 기둥 중심(170, 170) 및 낭심 중심(225, 225)은 순수 검은색 (0, 0, 0)
    assert out_bar.getpixel((170, 170)) == (0, 0, 0)
    assert out_bar.getpixel((225, 225)) == (0, 0, 0)
    # 대각선과 무관한 BBox 내부 반대편 여백 코너는 침범 없이 원본(255, 255, 255) 유지
    assert out_bar.getpixel((100, 265)) == (255, 255, 255)
    assert out_bar.getpixel((265, 100)) == (255, 255, 255)

    # 2) manga_glow 검증: 회색 배경 위 대각선 피부 영역에 화이트 글로우 적용
    img_glow = _make_diagonal_target_image(bg_color=(180, 180, 180), fg_color=(240, 185, 165))
    out_glow = censor._render_censored_style(img_glow, boxes, style="manga_glow")
    # 기둥 중심(170, 170) 및 낭심 중심(225, 225) 코어는 불투명 순백색 (255, 255, 255)
    assert out_glow.getpixel((170, 170)) == (255, 255, 255)
    assert out_glow.getpixel((225, 225)) == (255, 255, 255)
    # 먼 여백 코너는 원 배경색 유지
    assert out_glow.getpixel((100, 265)) == (180, 180, 180)
    assert out_glow.getpixel((265, 100)) == (180, 180, 180)


def test_adr86_restoration_and_hand_negative_points(monkeypatch):
    """ADR-86 내측 8% 수축 기준선 복원, 반실사 음영 비파편화, 겹친 손(detect_hands) 네거티브 포인트 주입을 검증합니다."""
    import imgutils.detect as img_detect
    import plepa_engine.censor as censor

    # 테스트 중 custom YOLO-seg가 개입하지 않도록 모델 미존재 상태로 격리
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: None)

    skin_color = (238, 188, 168)
    img = Image.new("RGB", (400, 400), skin_color)
    draw = ImageDraw.Draw(img)
    # 반실사 물광/음영 패턴을 중앙부에 그려도 C5 선화 장벽이 동작하지 않으므로 구멍 없이 덮여야 함
    draw.rectangle([185, 130, 215, 270], fill=(255, 250, 245), outline=(85, 45, 35), width=2)
    draw.line([(195, 140), (195, 260)], fill=(255, 255, 255), width=3)

    bbox = (140, 100, 260, 300)  # bw=120, bh=200 -> 8% inset => ex1=149, ey1=116, ex2=251, ey2=284
    captured_calls = []

    class _FakeMaskData:
        def __init__(self, arr):
            self._arr = arr

        def cpu(self):
            return self

        def numpy(self):
            return self._arr

    class _FakeRes:
        def __init__(self, w, h):
            self.masks = type("_M", (), {"data": _FakeMaskData(np.ones((1, h, w), dtype=np.float32))})()

    def _fake_sam(crop_pil, **kw):
        captured_calls.append(dict(kw))
        return [_FakeRes(crop_pil.width, crop_pil.height)]

    monkeypatch.setattr(censor, "get_sam_model", lambda: _fake_sam)
    monkeypatch.setattr(img_detect, "detect_faces", lambda *a, **kw: [])
    # 겹치는 손 BBox (중심 230, 200) + 겹치지 않는 원거리 손 BBox (중심 20, 20)
    monkeypatch.setattr(
        img_detect,
        "detect_hands",
        lambda *a, **kw: [
            ((200, 170, 260, 230), "hand", 0.92),
            ((10, 10, 30, 30), "hand", 0.98),
        ],
    )

    out = apply_silhouette(img, [(bbox, "penis", 0.94)], color="white")

    # 1) 중앙 물광/음영 영역이 C5 구멍 없이 순백색으로 매끈히 덮임
    assert out.getpixel((200, 200)) == (255, 255, 255)
    # 2) ADR-86 8% 내측 수축으로 BBox 최외곽 경계부(143, 200)는 허벅지 보호(원본 색 유지)
    assert out.getpixel((142, 200)) == skin_color
    assert out.getpixel((258, 200)) == skin_color
    # 3) SAM에 겹친 손 중심점(negative label=0)이 주입되었고, 원거리 손(20, 20)은 제외됨
    assert len(captured_calls) >= 1
    first_call = captured_calls[0]
    lb = first_call["bboxes"][0]
    pts = first_call["points"][0]
    lbls = first_call["labels"][0]
    assert lbls[0] == 1 and 0 in lbls
    # local_bbox = [ex1-rx1, ey1-ry1, ...], ex1=149 => rx1 = ex1 - lb[0]
    rx1 = 149 - lb[0]
    ry1 = 116 - lb[1]
    assert [230 - rx1, 200 - ry1] in pts
    neg_idx = pts.index([230 - rx1, 200 - ry1])
    assert lbls[neg_idx] == 0
    assert [20 - rx1, 20 - ry1] not in pts


def test_custom_yolo_seg_priority_and_train_dry_run(tmp_path, monkeypatch):
    """전용 YOLO-seg 모델 우선 폴리곤 추론·미탐지 시 폴백·원클릭 학습 스크립트를 검증합니다."""
    from pathlib import Path
    import sys
    import types
    import plepa_engine.censor as censor
    from scripts.train_censor_seg import main as train_main

    censor.unload_censor_models()
    dummy_weight = tmp_path / "models" / "censor_seg.pt"
    dummy_weight.parent.mkdir(parents=True, exist_ok=True)
    dummy_weight.write_bytes(b"dummy_weights")
    monkeypatch.setenv("PLEPA_CENSOR_SEG_MODEL", str(dummy_weight))

    # 삼각형 폴리곤 마스크를 반환하는 모조 YOLO-seg
    triangle_poly = np.array([[180.0, 140.0], [230.0, 260.0], [150.0, 260.0]], dtype=np.float32)
    seg_mode = {"empty": False}

    class _FakeSegModel:
        def __call__(self, img_rgb, conf=0.16, verbose=False):
            if seg_mode["empty"]:
                return [types.SimpleNamespace(masks=None, boxes=None, names={0: "penis"})]
            res_masks = types.SimpleNamespace(xy=[triangle_poly])
            res_boxes = types.SimpleNamespace(
                xyxy=np.array([[150.0, 140.0, 230.0, 260.0]], dtype=np.float32),
                conf=np.array([0.93], dtype=np.float32),
                cls=np.array([0], dtype=np.float32),
            )
            return [types.SimpleNamespace(masks=res_masks, boxes=res_boxes, names={0: "penis"})]

    fake_ultra = types.ModuleType("ultralytics")
    fake_ultra.YOLO = lambda path: _FakeSegModel()
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultra)

    # MobileSAM이나 기본 검출기가 절대 호출되지 않아야 함
    monkeypatch.setattr(censor, "get_sam_model", lambda: (_ for _ in ()).throw(AssertionError("SAM called")))
    fallback_called = {"count": 0}

    def _fake_fallback_detect(*args, **kwargs):
        fallback_called["count"] += 1
        return []

    monkeypatch.setattr(censor, "_detect_target_candidates", _fake_fallback_detect)

    try:
        base_img = Image.new("RGB", (400, 400), (220, 175, 155))
        out_img, count = censor.censor_image(base_img, style="white_silhouette")
        assert count == 1
        assert fallback_called["count"] == 0
        # 폴리곤 내부 픽셀(185, 220)은 순백색, 외부(80, 80)는 원본 유지
        assert out_img.getpixel((185, 220)) == (255, 255, 255)
        assert out_img.getpixel((80, 80)) == (220, 175, 155)

        # 전용 모델이 0건 탐지하면 기존 검출기 폴백 호출
        seg_mode["empty"] = True
        out_empty, count_empty = censor.censor_image(base_img, style="white_silhouette")
        assert count_empty == 0
        assert fallback_called["count"] == 1
    finally:
        censor.unload_censor_models()

    # train_censor_seg --dry-run 및 모조 학습/가중치 배포 검증
    gt_dir = tmp_path / "gt"
    proj_dir = tmp_path / "proj"
    orig_dir = proj_dir / "campus" / "assets" / "aya_origin" / "02_h_scenes"
    orig_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    orig = Image.new("RGB", (320, 320), (235, 190, 170))
    gt = orig.copy()
    ImageDraw.Draw(gt).rectangle([120, 100, 200, 220], fill=(255, 255, 255))
    orig.save(orig_dir / "aya_086_정상위강.webp", "WEBP")
    gt.save(gt_dir / "aya_086_정상위강.webp", "WEBP")

    ds_dir = tmp_path / "seg_ds"
    run_dir = tmp_path / "seg_runs"
    out_weights = tmp_path / "deployed" / "censor_seg.pt"

    assert train_main([
        "--gt-dir", str(gt_dir),
        "--projects-dir", str(proj_dir),
        "--dataset-dir", str(ds_dir),
        "--out-weights", str(out_weights),
        "--run-dir", str(run_dir),
        "--dry-run",
    ]) == 0

    class _FakeTrainYOLO:
        def __init__(self, model_name):
            self.model_name = model_name

        def train(self, **kwargs):
            weights_dir = Path(kwargs["project"]) / kwargs["name"] / "weights"
            weights_dir.mkdir(parents=True, exist_ok=True)
            (weights_dir / "best.pt").write_bytes(b"trained_best_weights")
            return types.SimpleNamespace(save_dir=str(Path(kwargs["project"]) / kwargs["name"]))

    fake_ultra.YOLO = _FakeTrainYOLO
    assert train_main([
        "--gt-dir", str(gt_dir),
        "--projects-dir", str(proj_dir),
        "--dataset-dir", str(ds_dir),
        "--out-weights", str(out_weights),
        "--run-dir", str(run_dir),
        "--epochs", "5",
    ]) == 0
    assert out_weights.is_file()
    assert out_weights.read_bytes() == b"trained_best_weights"


def test_extract_yolo_seg_polygons_from_diff(tmp_path):
    """원본·검열본 픽셀 차분 기반 YOLO-seg 폴리곤 추출 및 빈 ground_truth 안전 종료를 검증합니다."""
    from scripts.extract_censor_seg_dataset import build_yolo_seg_dataset, extract_yolo_seg_polygons_from_diff, main

    origin_img = Image.new("RGB", (400, 400), (235, 190, 170))
    censored_img = origin_img.copy()
    draw = ImageDraw.Draw(censored_img)
    draw.rounded_rectangle([150, 120, 250, 280], radius=18, fill=(255, 255, 255))

    mask, lines = extract_yolo_seg_polygons_from_diff(origin_img, censored_img, class_id=0, diff_thresh=18)
    assert mask.shape == (400, 400)
    assert mask[200, 200] == 255
    assert mask[20, 20] == 0
    assert len(lines) == 1

    tokens = lines[0].split()
    assert tokens[0] == "0"
    coords = [float(v) for v in tokens[1:]]
    assert len(coords) >= 6 and len(coords) % 2 == 0
    assert all(0.0 <= c <= 1.0 for c in coords)

    # 1) 비어 있는 ground_truth에서도 에러 없이 0 pairs processed 반환
    empty_gt = tmp_path / "empty_gt"
    empty_out = tmp_path / "empty_ds"
    assert main(["--gt-dir", str(empty_gt), "--projects-dir", str(tmp_path / "proj"), "--out-dir", str(empty_out)]) == 0
    assert (empty_out / "images").is_dir() and (empty_out / "labels").is_dir()

    # 2) 실제 매칭 쌍이 있을 때 images/ 및 labels/*.txt 생성 검증
    gt_dir = tmp_path / "gt"
    proj_dir = tmp_path / "projects"
    orig_dir = proj_dir / "campus" / "assets" / "aya_origin" / "02_h_scenes"
    orig_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    origin_img.save(orig_dir / "aya_086_정상위강.webp", "WEBP")
    censored_img.save(gt_dir / "aya_086_정상위강.webp", "WEBP")

    out_ds = tmp_path / "yolo_ds"
    stats = build_yolo_seg_dataset(gt_dir, proj_dir, out_ds)
    assert stats["processed"] == 1
    assert (out_ds / "images" / "aya_086_정상위강.webp").exists()
    assert (out_ds / "labels" / "aya_086_정상위강.txt").exists()
    assert (out_ds / "data.yaml").exists()



