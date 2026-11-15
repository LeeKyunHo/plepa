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
    """Phase P0 인셋 해제(0%), 누수 시 조건부 라운드 가드, 반실사 음영 비파편화 및 겹친 손 네거티브 포인트 주입을 검증합니다."""
    import imgutils.detect as img_detect
    import plepa_engine.censor as censor

    # 테스트 중 custom YOLO-seg가 개입하지 않도록 모델 미존재 상태로 격리
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: None)

    skin_color = (238, 188, 168)
    img = Image.new("RGB", (400, 400), skin_color)
    draw = ImageDraw.Draw(img)
    # 반실사 물광/음영 패턴을 중앙부에 그려도 파편화 없이 덮여야 함
    draw.rectangle([185, 130, 215, 270], fill=(255, 250, 245), outline=(85, 45, 35), width=2)
    draw.line([(195, 140), (195, 260)], fill=(255, 255, 255), width=3)

    bbox = (140, 100, 260, 300)  # Phase P0: 내측 8% 수축 없이 원본 BBox 그대로 사용 (ex1=140, ey1=100)
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
            # 전체 패딩 크롭을 1.0으로 채워 Leakage Guard 발동 상황도 동시 검증
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

    # 1) 손 바깥 비가려짐 코어 및 기존 8% 인셋으로 잘리던 좌측 BBox 내부 경계부(144, 200)가 순백색으로 덮임
    assert out.getpixel((200, 150)) == (255, 255, 255)
    assert out.getpixel((180, 200)) == (255, 255, 255)
    assert out.getpixel((144, 200)) == (255, 255, 255)
    # 2) SAM 전체 크롭 누수(Leakage) 상황에서는 조건부 라운드 가드로 최외곽 코너(142, 102)와 BBox 바깥 여백 보호
    assert out.getpixel((142, 102)) == skin_color
    assert out.getpixel((132, 200)) == skin_color
    # 3) 성기 SAM 호출에 겹친 손 중심점(negative label=0)이 주입되었고, 원거리 손(20, 20)은 제외됨
    genital_calls = [c for c in captured_calls if (c["bboxes"][0][2] - c["bboxes"][0][0]) >= 90]
    assert len(genital_calls) >= 1
    first_call = genital_calls[0]
    lb = first_call["bboxes"][0]
    pts = first_call["points"][0]
    lbls = first_call["labels"][0]
    assert lbls[0] == 1 and 0 in lbls
    # local_bbox = [ex1-rx1, ey1-ry1, ...], ex1=140, ey1=100 => rx1 = ex1 - lb[0]
    rx1 = 140 - lb[0]
    ry1 = 100 - lb[1]
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


def test_box_iomin_merges_contained_fragments(monkeypatch):
    """큰 성기 BBox 내부에 포함된 다중 스케일 조각 BBox들이 IoMin>=0.65 기준으로 1개로 병합되는지 검증합니다."""
    import plepa_engine.censor as censor

    img = Image.new("RGB", (900, 1300), (240, 196, 176))
    # 1단계 전체 스캔과 2단계 ROI 스캔이 순서·크기 다른 조각 박스들을 반환하는 상황 모사
    # 주의: _detect_target_candidates의 2단계 ROI는 좌표 / 1.6 + offset 으로 변환됨
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda pil_img, conf_threshold=0.1: (
            # 전체 이미지(900x1300): 작은 조각들이 먼저, 큰 전체 박스가 뒤에 오는 경우 포함
            [
                ((252, 458, 439, 771), "penis", 0.57),
                ((277, 456, 435, 558), "penis", 0.29),
                ((112, 445, 453, 1083), "penis", 0.84),
            ]
            if pil_img.size == (900, 1300)
            else []
        ),
    )

    cands = censor._detect_target_candidates(img, targets=("penis",), min_confidence=0.16)
    assert len(cands) == 1
    assert cands[0][0] == (112, 445, 453, 1083)
    assert abs(cands[0][2] - 0.84) < 1e-6


def test_mutually_exclusive_hand_occlusion_and_hole_preservation(monkeypatch):
    """손-성기 상호 배타적 앵커 분리, 고정 비율 컷 없는 동적 손 실루엣 보호 및 내부 구멍 보존을 검증합니다."""
    import imgutils.detect as img_detect
    import plepa_engine.censor as censor

    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: None)
    monkeypatch.setattr(img_detect, "detect_faces", lambda *a, **kw: [])

    skin_color = (238, 188, 168)
    img = Image.new("RGB", (400, 400), skin_color)
    gbox = (140, 80, 260, 320)  # ex1=149, ey1=99, ex2=251, ey2=301

    class _FakeMaskData:
        def __init__(self, arr):
            self._arr = arr

        def cpu(self):
            return self

        def numpy(self):
            return self._arr

    class _FakeRes:
        def __init__(self, mask_2d):
            self.masks = type("_M", (), {"data": _FakeMaskData(mask_2d[None, :, :].astype(np.float32))})()

    for label_case, hand_box in [
        ("small_overlap", (160, 180, 240, 220)),   # 높이 약 17% 겹침
        ("large_overlap", (145, 140, 255, 285)),   # 높이 약 60% 겹침 (고정 비율 컷 없이 모두 보호되어야 함)
    ]:
        hx1, hy1, hx2, hy2 = hand_box
        calls = []

        def _fake_sam(crop_pil, **kw):
            cw, ch = crop_pil.size
            calls.append({"size": (cw, ch), "kwargs": dict(kw)})
            lb = kw["bboxes"][0]
            # 손 SAM 호출인지, 성기 SAM 호출인지 BBox 폭/위치로 구분해 손가락/몸통 마스크 모사
            m = np.zeros((ch, cw), dtype=np.float32)
            # 호출 BBox 내부(성기 BBox라면 내부 90% 채우되 손 영역에는 구멍을 남기는 형태)
            m[max(0, lb[1]):min(ch, lb[3]), max(0, lb[0]):min(cw, lb[2])] = 1.0
            return [_FakeRes(m)]

        monkeypatch.setattr(censor, "get_sam_model", lambda _fn=_fake_sam: _fn)
        monkeypatch.setattr(img_detect, "detect_hands", lambda *a, _hb=hand_box, **kw: [(_hb, "hand", 0.91)])

        out = apply_silhouette(img, [(gbox, "penis", 0.95)], color="white")

        # 1) 성기 SAM 호출의 positive points(label=1)가 손 BBox 내부에 절대 찍히지 않음 검증
        # 주의: P0.5 Sub-BBox 분할 시 성기 높이가 줄어들 수 있으므로 성기 폭(>=115) vs 손 폭(<=110)으로 구분
        genital_calls = [c for c in calls if (c["kwargs"]["bboxes"][0][2] - c["kwargs"]["bboxes"][0][0]) >= 115]
        hand_calls = [c for c in calls if (c["kwargs"]["bboxes"][0][2] - c["kwargs"]["bboxes"][0][0]) < 115]
        assert len(genital_calls) >= 1, label_case
        assert len(hand_calls) >= 1, label_case

        min_genital_lb_y1 = min(int(c["kwargs"]["bboxes"][0][1]) for c in genital_calls)
        for gc in genital_calls:
            lb = gc["kwargs"]["bboxes"][0]
            rx1 = 140 - lb[0]
            ry1 = 80 - min_genital_lb_y1
            pts = gc["kwargs"]["points"][0]
            lbls = gc["kwargs"]["labels"][0]
            for pt, lbl in zip(pts, lbls):
                gx, gy = pt[0] + rx1, pt[1] + ry1
                if lbl == 1:
                    assert not (hx1 <= gx <= hx2 and hy1 <= gy <= hy2), f"{label_case}: pos pt inside hand"

        # 2) 손 SAM 호출에도 손 바깥쪽 성기 노출 코어(negative label=0)가 전달되었는지 검증
        hc = hand_calls[0]
        assert 1 in hc["kwargs"]["labels"][0] and 0 in hc["kwargs"]["labels"][0], label_case

        # 3) 최종 이미지: 손 위로 노출된 귀두 상단(200, 115)은 순백색 유지, 손 중심은 원본 피부색 보호
        assert out.getpixel((200, 115)) == (255, 255, 255), label_case
        assert out.getpixel((200, int((hy1 + hy2) / 2))) == skin_color, label_case

    # 4) connectedComponentsWithStats 내부 구멍 보존 단독 검증 (detect_hands=0 상태에서도 SAM 내부 구멍 비메움)
    monkeypatch.setattr(img_detect, "detect_hands", lambda *a, **kw: [])

    def _hole_sam(crop_pil, **kw):
        cw, ch = crop_pil.size
        lb = kw["bboxes"][0]
        rx1 = 140 - lb[0]
        ry1 = 80 - lb[1]
        m = np.zeros((ch, cw), dtype=np.float32)
        m[max(0, lb[1]):min(ch, lb[3]), max(0, lb[0]):min(cw, lb[2])] = 1.0
        # 중앙 (180..220, 180..220) 위치에 40x40 내부 구멍 생성
        m[max(0, 180 - ry1):min(ch, 220 - ry1), max(0, 180 - rx1):min(cw, 220 - rx1)] = 0.0
        return [_FakeRes(m)]

    monkeypatch.setattr(censor, "get_sam_model", lambda: _hole_sam)
    out_hole = apply_silhouette(img, [(gbox, "penis", 0.95)], color="white")
    assert out_hole.getpixel((200, 120)) == (255, 255, 255)
    assert out_hole.getpixel((200, 200)) == skin_color


def test_extract_black_censor_mask_and_restore_skin():
    """kiro 단일 완성본의 솔리드 블랙 마스크 추출 및 피부 톤 인페인팅 역복원 검증."""
    from scripts.extract_censor_seg_dataset import extract_black_censor_mask_and_restore_skin

    skin_color = (238, 188, 168)
    img = Image.new("RGB", (400, 400), skin_color)
    draw = ImageDraw.Draw(img)
    # 타겟 영역(중심 200, 220)에 수작업 솔리드 블랙 실루엣 그리기
    draw.rounded_rectangle([165, 130, 235, 310], radius=24, fill=(0, 0, 0))
    # 상단 머리카락 경계(y <= 60)는 비검열 영역으로 배제되어야 함
    draw.rectangle([0, 0, 400, 50], fill=(0, 0, 0))

    restored_arr, mask, lines = extract_black_censor_mask_and_restore_skin(img, class_id=0)
    assert mask.shape == (400, 400)
    assert mask[220, 200] == 255
    assert mask[25, 200] == 0
    assert len(lines) == 1

    # 복원 이미지에서 원래 검은색이던 타겟 중심 픽셀이 주변 피부 톤으로 역복원되어야 함
    center_rgb = restored_arr[220, 200]
    assert int(center_rgb[0]) > 150 and int(center_rgb[1]) > 100


def test_p0_lineart_outer_snap_respects_protection_mask():
    """Line-Art Outer Snap absorbs adjacent dark line-art while guaranteeing 0px intrusion into protection_mask."""
    import numpy as np
    from plepa_engine import censor

    h, w = 200, 200
    img_np = np.full((h, w, 3), (240, 200, 180), dtype=np.uint8)

    # Core foreground mask: [70:130, 80:120]
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[70:130, 80:120] = 255

    # Draw 2px dark line-art outline on left (x=78..79) and right (x=120..121)
    img_np[70:130, 78:80] = (25, 20, 20)
    img_np[70:130, 120:122] = (25, 20, 20)

    # Protect the right edge (simulating foreground hand/lip mask)
    protection_mask = np.zeros((h, w), dtype=bool)
    protection_mask[:, 120:] = True

    snapped = censor._snap_to_outer_lineart(
        mask, img_np, scale=1.0, protection_mask=protection_mask, max_steps=2
    )

    assert snapped.dtype == np.uint8
    # Unprotected left dark line-art (x=79) should be absorbed
    assert snapped[100, 79] > 128
    # Bright background beyond dark line-art (x=76) must remain unmasked
    assert snapped[100, 76] == 0
    # Protected zone (x>=120) must have 0px intrusion even with dark line-art
    assert not np.any(snapped[:, 120:] > 0)


def test_p0_bottom_edge_false_positive_gate():
    """Bottom-edge gate drops low-conf / flat sliver / fluid artifacts while keeping real vertical targets."""
    import numpy as np
    from plepa_engine import censor

    img_w, img_h = 832, 1216
    img_rgb = np.full((img_h, img_w, 3), (225, 180, 160), dtype=np.uint8)
    skin_mask = np.full((img_h, img_w), 255, dtype=np.uint8)

    # Bright white splash/fluid region at bottom left-center
    img_rgb[1100:1216, 300:460] = (250, 250, 250)
    skin_mask[1100:1216, 300:460] = 0

    candidates = [
        # Primary upper target
        ((320, 420, 450, 780), "penis", 0.84),
        # Low-confidence isolated bottom blob -> should drop
        ((330, 1120, 430, 1214), "penis", 0.25),
        # Tiny flat sliver clipped to bottom border (<14% primary area) -> should drop
        ((280, 1175, 450, 1216), "penis", 0.55),
        # Bright fluid bottom region with zero skin ratio -> should drop
        ((310, 1105, 450, 1216), "penis", 0.72),
    ]
    kept = censor._filter_bottom_edge_false_positives(
        candidates, img_w=img_w, img_h=img_h, img_rgb_np=img_rgb, skin_mask_np=skin_mask
    )
    assert len(kept) == 1
    assert kept[0][0] == (320, 420, 450, 780)

    # Genuine vertical secondary target with real skin and strong score should survive
    candidates_multi = [
        ((370, 725, 473, 971), "penis", 0.81),
        ((358, 988, 487, 1197), "penis", 0.83),
    ]
    kept_multi = censor._filter_bottom_edge_false_positives(
        candidates_multi,
        img_w=img_w,
        img_h=img_h,
        img_rgb_np=np.full((img_h, img_w, 3), (215, 165, 145), dtype=np.uint8),
        skin_mask_np=np.full((img_h, img_w), 255, dtype=np.uint8),
    )
    assert len(kept_multi) == 2


def test_p0_benchmark_metrics_helpers():
    """Verify Mask IoU and Boundary IoU helper behaviors for P4 evaluation."""
    import numpy as np
    from scripts.benchmark_censor_metrics import compute_mask_iou, compute_boundary_iou

    gt = np.zeros((256, 256), dtype=bool)
    gt[60:180, 90:150] = True

    assert compute_mask_iou(gt, gt) == 1.0
    assert compute_boundary_iou(gt, gt) == 1.0

    empty = np.zeros((256, 256), dtype=bool)
    assert compute_mask_iou(empty, gt) == 0.0
    assert compute_boundary_iou(empty, gt) == 0.0

    eroded_1px = np.zeros((256, 256), dtype=bool)
    eroded_1px[61:179, 91:149] = True
    m_iou = compute_mask_iou(eroded_1px, gt)
    b_iou = compute_boundary_iou(eroded_1px, gt)
    assert 0.0 < b_iou < m_iou < 1.0

    # Eroded by 4px exceeds 2px boundary band on 256x256 -> Boundary IoU drops to 0 while Mask IoU remains high
    eroded_4px = np.zeros((256, 256), dtype=bool)
    eroded_4px[64:176, 94:146] = True
    assert compute_boundary_iou(eroded_4px, gt) == 0.0
    assert compute_mask_iou(eroded_4px, gt) > 0.8


def test_p05_hand_split_sub_bbox_preserves_upper_tip(monkeypatch):
    """P0.5: 손이 성기 중간을 가로질러 상단 귀두가 작게 노출돼도 Sub-BBox 분할 + 영역별 독립 보존으로 유지됨을 검증합니다."""
    import imgutils.detect as img_detect
    import plepa_engine.censor as censor

    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: None)
    monkeypatch.setattr(img_detect, "detect_faces", lambda *a, **kw: [])

    skin_color = (238, 188, 168)
    img = Image.new("RGB", (400, 520), skin_color)
    gbox = (130, 60, 270, 440)       # 폭 140, 높이 380
    hand_box = (115, 190, 285, 265)   # 성기 중간을 완전히 가로지르는 손 BBox

    class _FakeMaskData:
        def __init__(self, arr):
            self._arr = arr

        def cpu(self):
            return self

        def numpy(self):
            return self._arr

    class _FakeRes:
        def __init__(self, mask_2d):
            self.masks = type("_M", (), {"data": _FakeMaskData(mask_2d[None, :, :].astype(np.float32))})()

    genital_sub_bboxes = []

    def _fake_sam(crop_pil, **kw):
        cw, ch = crop_pil.size
        lb = [int(v) for v in kw["bboxes"][0]]
        bw = lb[2] - lb[0]
        m = np.zeros((ch, cw), dtype=np.float32)

        if bw >= 160:
            # 손 SAM 호출 (폭 170): 가로지르는 손 영역 반환
            m[max(0, lb[1]):min(ch, lb[3]), max(0, lb[0]):min(cw, lb[2])] = 1.0
            return [_FakeRes(m)]

        # 성기 Sub-BBox 호출 (폭 140)
        genital_sub_bboxes.append(tuple(lb))
        pts = kw["points"][0]
        lbls = kw["labels"][0]
        pos_ys = [pt[1] for pt, l in zip(pts, lbls) if l == 1]
        mid_cx = (lb[0] + lb[2]) // 2
        if pos_ys and max(pos_ys) < lb[3] - 40:
            # 상단 귀두: 매우 작은 컴포넌트(~260px, 하단 14000px의 2% 미만 -> 기존 max*0.15 필터에선 증발)
            cy_u = min(pos_ys)
            m[max(0, cy_u - 8):min(ch, cy_u + 10), max(0, mid_cx - 8):min(cw, mid_cx + 8)] = 1.0
        else:
            # 하단 기둥/음낭: 거대 컴포넌트(~13,000px)
            m[max(lb[1] + 5, 0):min(lb[3] - 5, ch), max(lb[0] + 15, 0):min(lb[2] - 15, cw)] = 1.0
        return [_FakeRes(m)]

    monkeypatch.setattr(censor, "get_sam_model", lambda: _fake_sam)
    monkeypatch.setattr(img_detect, "detect_hands", lambda *a, **kw: [(hand_box, "hand", 0.92)])

    out = apply_silhouette(img, [(gbox, "penis", 0.94)], color="white")
    out_np = np.array(out)

    # 1) Sub-BBox 분할 호출이 최소 2회(상단 + 하단) 발생해야 함
    assert len(genital_sub_bboxes) >= 2
    assert max(b[3] - b[1] for b in genital_sub_bboxes) < (gbox[3] - gbox[1])

    # 2) 손 위쪽 상단 귀두 영역(y: 90~175)과 아래쪽 기저 영역(y: 280~425) 모두 백색 마스킹 보존
    white_mask = (out_np[:, :, 0] > 250) & (out_np[:, :, 1] > 250) & (out_np[:, :, 2] > 250)
    upper_white = int(np.count_nonzero(white_mask[90:175, 160:240]))
    lower_white = int(np.count_nonzero(white_mask[280:425, 140:260]))
    assert upper_white >= 120, f"상단 귀두가 소멸되었습니다: {upper_white}px"
    assert lower_white >= 1000, f"하단 영역이 유실되었습니다: {lower_white}px"


def test_p05_in_box_blocky_overexpansion_pruned(monkeypatch):
    """P0.5: 테두리에 살짝 닿지 않아도 박스 내부를 직사각형/블록형으로 과팽창한 SAM 마스크를 감지·억제함을 검증합니다."""
    import imgutils.detect as img_detect
    import plepa_engine.censor as censor

    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: None)
    monkeypatch.setattr(img_detect, "detect_faces", lambda *a, **kw: [])
    monkeypatch.setattr(img_detect, "detect_hands", lambda *a, **kw: [])

    skin_color = (238, 188, 168)
    img = Image.new("RGB", (400, 400), skin_color)
    gbox = (120, 80, 280, 320)

    # 단위 누수 분류기 직접 검증: 테두리에 4px 안 닿은 92% 네모 과팽창 블록 -> blocky_leak=True
    sub_test = np.zeros((240, 160), dtype=np.uint8)
    sub_test[4:236, 4:156] = 255
    g_leak, b_leak = censor._classify_sam_mask_leak(sub_test, 0, 0, 160, 240, 0, 0, 160, 240)
    assert not g_leak and b_leak

    # 정상 슬림 타원은 global_leak/blocky_leak 모두 False여야 함
    sub_oval = np.zeros((240, 160), dtype=np.uint8)
    import cv2 as _cv2
    _cv2.ellipse(sub_oval, (80, 120), (42, 105), 0, 0, 360, 255, -1)
    g_ok, b_ok = censor._classify_sam_mask_leak(sub_oval, 0, 0, 160, 240, 0, 0, 160, 240)
    assert not g_ok and not b_ok

    class _FakeMaskData:
        def __init__(self, arr):
            self._arr = arr

        def cpu(self):
            return self

        def numpy(self):
            return self._arr

    class _FakeRes:
        def __init__(self, mask_2d):
            self.masks = type("_M", (), {"data": _FakeMaskData(mask_2d[None, :, :].astype(np.float32))})()

    def _fake_blocky_sam(crop_pil, **kw):
        cw, ch = crop_pil.size
        lb = [int(v) for v in kw["bboxes"][0]]
        m = np.zeros((ch, cw), dtype=np.float32)
        # BBox 경계에서 4px만 안쪽인 거대 직사각형 블록 출력
        m[max(0, lb[1] + 4):min(ch, lb[3] - 4), max(0, lb[0] + 4):min(cw, lb[2] - 4)] = 1.0
        return [_FakeRes(m)]

    monkeypatch.setattr(censor, "get_sam_model", lambda: _fake_blocky_sam)

    out = apply_silhouette(img, [(gbox, "penis", 0.90)], color="white")
    out_np = np.array(out)

    # 외곽 네모 모서리((126, 86))는 코어 가드에 의해 깎여 피부색 유지, 중앙((200, 200))은 검열됨
    corner_pixel = out_np[86, 126]
    center_pixel = out_np[200, 200]
    assert int(corner_pixel[2]) < 210, f"네모 과팽창 모서리가 깎이지 않음: {corner_pixel}"
    assert int(center_pixel[0]) > 250 and int(center_pixel[2]) > 250


def test_p1_hybrid_dual_gating_ensemble(monkeypatch):
    """P1: _resolve_hybrid_targets_and_mask()의 Fast-Path(>=0.85), Case A(구제), Case B(하단 FP 기각), Case C(SAM 폴백)를 검증합니다."""
    import plepa_engine.censor as censor

    img = Image.new("RGB", (500, 600), (235, 185, 165))
    skin_np = np.full((600, 500), 255, dtype=np.uint8)
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: object())

    # 0) Fast Path: 초고신뢰 YOLO-seg (>=0.92) -> DeepGHS 우회 및 직결 폴리곤 마스크
    seg_fast = [
        ((180, 140, 290, 320), "penis", 0.93, np.array([[185, 145], [285, 145], [285, 315], [185, 315]])),
    ]
    monkeypatch.setattr(censor, "_infer_custom_censor_seg_items", lambda *a, **kw: seg_fast)
    monkeypatch.setattr(
        censor,
        "_detect_target_candidates",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("DeepGHS should be skipped on high_seg >= 0.85")),
    )
    boxes_fast, mask_fast, fb_fast = censor._resolve_hybrid_targets_and_mask(img, skin_np=skin_np)
    assert len(boxes_fast) == 1
    assert fb_fast == []
    assert mask_fast is not None and int(np.count_nonzero(mask_fast)) > 5000

    # 0-b) P2: 0.70(기존 0.85 장벽 미만, 0.92 미만) -> Fast-Path를 우회하지 않고 Semantic-Guided SAM 라우팅 (타이트 YOLO 박스+prior 전달)
    seg_mid = [
        ((180, 140, 290, 320), "penis", 0.70, np.array([[185, 145], [285, 145], [285, 315], [185, 315]])),
    ]
    deep_mid = [((175, 135, 295, 325), "penis", 0.80)]
    monkeypatch.setattr(censor, "_infer_custom_censor_seg_items", lambda *a, **kw: seg_mid)
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: deep_mid)
    boxes_mid, mask_mid, fb_mid, priors_mid, ctx_mid = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np
    )
    assert len(boxes_mid) == 1
    assert boxes_mid[0][0] == (180, 140, 290, 320)
    assert mask_mid is None
    assert priors_mid is not None and priors_mid[0] is not None
    assert ctx_mid == [(175, 135, 295, 325)]

    # 1) Case B: DeepGHS 2건 중 Primary만 YOLO와 합의, 하단 고립 오탐 기각 -> YOLO 타이트 박스+prior로 SAM 정밀 세그멘테이션 라우팅
    seg_case_ab = [
        ((180, 140, 290, 320), "penis", 0.45, np.array([[185, 145], [285, 145], [285, 315], [185, 315]])),
    ]
    deep_case_ab = [
        ((175, 135, 295, 325), "penis", 0.72),   # primary
        ((200, 440, 300, 560), "penis", 0.21),   # 하단(yc=500 > 600*0.68=408), isolated skin FP -> 기각 대상
    ]
    monkeypatch.setattr(censor, "_infer_custom_censor_seg_items", lambda *a, **kw: seg_case_ab)
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: deep_case_ab)

    boxes_ab, mask_ab, fb_ab = censor._resolve_hybrid_targets_and_mask(img, skin_np=skin_np)
    assert len(boxes_ab) == 1
    assert boxes_ab[0][0] == (180, 140, 290, 320)
    assert mask_ab is None
    assert fb_ab == boxes_ab

    # 2) Case A: DeepGHS 0건 미탐 시 YOLO-seg(0.45) 단독 구제 -> SAM P0.5 정밀 마스킹으로 전달
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: [])
    boxes_rescue, mask_rescue, fb_rescue = censor._resolve_hybrid_targets_and_mask(img, skin_np=skin_np)
    assert len(boxes_rescue) == 1
    assert boxes_rescue[0][0] == (180, 140, 290, 320)
    assert mask_rescue is None
    assert fb_rescue == boxes_rescue

    # 3) Case C: YOLO-seg 0건 + DeepGHS 탐지 -> MobileSAM P0.5 fallback_boxes로 위임
    deep_case_c = [((160, 120, 280, 340), "penis", 0.65)]
    monkeypatch.setattr(censor, "_infer_custom_censor_seg_items", lambda *a, **kw: [])
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: deep_case_c)

    boxes_c, mask_c, fb_c = censor._resolve_hybrid_targets_and_mask(img, skin_np=skin_np)
    assert len(boxes_c) == 1
    assert mask_c is None
    assert fb_c == deep_case_c


def test_p2_semantic_guided_sam_projection_and_fallback(monkeypatch):
    """P2: yolo_prior_mask의 distanceTransform 코어 Positive(1) + 외곽 Negative(0) 투영, Envelope 클램핑, Empty/Leak 폴백을 검증합니다."""
    import cv2
    import imgutils.detect as img_detect
    import plepa_engine.censor as censor

    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: None)
    monkeypatch.setattr(img_detect, "detect_faces", lambda *a, **kw: [])
    monkeypatch.setattr(img_detect, "detect_hands", lambda *a, **kw: [])

    # Warm skin canvas (diagonal BBox upper-left contains large belly skin at (105, 105))
    img = Image.new("RGB", (400, 400), (242, 198, 178))
    context_box = (80, 80, 300, 300)
    tight_box = (95, 95, 285, 285)

    # Diagonal shaft inside prior mask (from bottom-left (105, 275) to top-right (275, 105))
    prior = np.zeros((400, 400), dtype=np.uint8)
    cv2.line(prior, (105, 275), (275, 105), 255, thickness=28)

    class _FakeMaskData:
        def __init__(self, arr):
            self._arr = arr

        def cpu(self):
            return self

        def numpy(self):
            return self._arr

    class _FakeRes:
        def __init__(self, arr_3d):
            self.masks = type("_M", (), {"data": _FakeMaskData(arr_3d.astype(np.float32))})()

    captured = []

    def _fake_sam_spill(crop_pil, **kw):
        cw, ch = crop_pil.size
        pts = kw["points"][0]
        lbls = kw["labels"][0]
        captured.append((list(pts), list(lbls), cw, ch, tuple(kw["bboxes"][0])))
        # Intentionally spill SAM mask into upper-left belly corner while also covering shaft
        m = np.zeros((ch, cw), dtype=np.float32)
        cv2.line(m, (15, ch - 15), (cw - 15, 15), 1.0, thickness=32)
        m[0:70, 0:70] = 1.0  # false belly spill inside BBox top-left
        return [_FakeRes(m[None, :, :])]

    monkeypatch.setattr(censor, "get_sam_model", lambda: _fake_sam_spill)
    out = censor.apply_silhouette(
        img,
        [(tight_box, "penis", 0.68)],
        color="white",
        yolo_prior_masks=[prior],
        context_boxes=[context_box],
    )
    out_np = np.array(out)

    assert len(captured) >= 1
    pts, lbls, _, _, _ = captured[0]
    pos_pts = [pt for pt, l in zip(pts, lbls) if l == 1]
    neg_pts = [pt for pt, l in zip(pts, lbls) if l == 0]
    assert len(pos_pts) >= 1
    assert len(neg_pts) >= 1
    # Verify outer skin negatives lie outside the prior shaft & positive points lie on/near the prior shaft
    # Note: crop origin is near max(0, x1-pad) — check global white mask result strictly:
    white_mask = (out_np[:, :, 0] > 250) & (out_np[:, :, 1] > 250) & (out_np[:, :, 2] > 250)
    shaft_center_white = int(np.count_nonzero(white_mask[175:205, 175:205]))
    belly_corner_white = int(np.count_nonzero(white_mask[95:125, 95:125]))
    assert shaft_center_white >= 400, f"대각선 코어 마스킹 누락: {shaft_center_white}px"
    assert belly_corner_white == 0, f"외곽 복부 오검열 발생: {belly_corner_white}px"

    # Empty SAM 2.1 output (0 masks) -> fallback cleanly to yolo_prior_mask
    def _fake_sam_empty(crop_pil, **kw):
        cw, ch = crop_pil.size
        return [_FakeRes(np.zeros((0, ch, cw), dtype=np.float32))]

    monkeypatch.setattr(censor, "get_sam_model", lambda: _fake_sam_empty)
    out_empty = censor.apply_silhouette(
        img,
        [(tight_box, "penis", 0.68)],
        color="white",
        yolo_prior_masks=[prior],
        context_boxes=[context_box],
    )
    empty_np = np.array(out_empty)
    white_empty = (empty_np[:, :, 0] > 250) & (empty_np[:, :, 1] > 250) & (empty_np[:, :, 2] > 250)
    assert int(np.count_nonzero(white_empty[175:205, 175:205])) >= 300
    assert int(np.count_nonzero(white_empty[95:125, 95:125])) == 0


def test_p2_hand_split_preserved_vs_bottom_echo_suppressed(monkeypatch):
    """P2: 손 분할 상/하단 다중 타겟은 보존하고, 손 분할 없는 하단 체액/접합 Echo는 yolo_conf < 0.58에서 기각함을 검증합니다."""
    import plepa_engine.censor as censor

    img = Image.new("RGB", (500, 700), (235, 185, 165))
    skin_np = np.full((700, 500), 255, dtype=np.uint8)
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: object())

    upper_box = (170, 185, 310, 340)
    lower_box = (165, 440, 315, 620)  # y2_ratio = 620/700 = 0.886 > 0.82
    hand_between = (140, 350, 340, 425)

    # 1) MIK #187-style: 1 coarse DeepGHS box + 2 YOLO-seg hand-split boxes -> keep both tight YOLO splits
    poly_u = np.array([[175, 190], [305, 190], [305, 335], [175, 335]])
    poly_l = np.array([[170, 445], [310, 445], [310, 615], [170, 615]])
    monkeypatch.setattr(
        censor,
        "_detect_target_candidates",
        lambda *a, **kw: [((155, 180, 325, 625), "penis", 0.78)],
    )
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [
            (upper_box, "penis", 0.70, poly_u),
            (lower_box, "penis", 0.56, poly_l),
        ],
    )
    boxes_1a, _, _, priors_1a, ctx_1a = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[hand_between]
    )
    assert len(boxes_1a) == 2
    assert {b[0] for b in boxes_1a} == {upper_box, lower_box}
    assert priors_1a is not None and all(p is not None for p in priors_1a)
    assert ctx_1a == [(155, 180, 325, 625), (155, 180, 325, 625)]

    # 2) MIK #156-style: 2 DeepGHS boxes (upper primary + adjacent lower echo), no hand between, lower YOLO conf=0.45 (<0.58)
    monkeypatch.setattr(
        censor,
        "_detect_target_candidates",
        lambda *a, **kw: [(upper_box, "penis", 0.80), (lower_box, "penis", 0.76)],
    )
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [
            (upper_box, "penis", 0.62, poly_u),
            (lower_box, "penis", 0.45, poly_l),
        ],
    )
    boxes_echo_drop, _, _, _, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[]
    )
    assert [b[0] for b in boxes_echo_drop] == [upper_box]

    # Same geometry, WITH hand between -> both preserved even when lower YOLO conf=0.45
    boxes_hand_keep, _, _, _, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[hand_between]
    )
    assert {b[0] for b in boxes_hand_keep} == {upper_box, lower_box}

    # Same geometry, NO hand, lower YOLO conf=0.64 (>= 0.58) -> both preserved
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [
            (upper_box, "penis", 0.62, poly_u),
            (lower_box, "penis", 0.64, poly_l),
        ],
    )
    boxes_high_yolo_keep, _, _, _, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[]
    )
    assert {b[0] for b in boxes_high_yolo_keep} == {upper_box, lower_box}


def test_p2_sam_model_promotion_and_mobile_fallback(monkeypatch):
    """P2: get_sam_model()이 SAM 2.1(sam2.1_s.pt)을 우선 로드하고, 미존재·실패 시 mobile_sam.pt로 무중단 폴백함을 검증합니다."""
    import sys
    import types
    from pathlib import Path
    import plepa_engine.censor as censor

    censor.unload_censor_models()
    monkeypatch.delenv("PLEPA_SAM_MODEL", raising=False)

    loaded_calls = []

    def _fake_sam_ok(name):
        loaded_calls.append(name)
        return {"loaded": name}

    fake_ultra = types.SimpleNamespace(SAM=_fake_sam_ok)
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultra)

    m1 = censor.get_sam_model()
    assert len(loaded_calls) == 1
    assert Path(loaded_calls[0]).name == "sam2.1_s.pt"
    assert Path(m1["loaded"]).name == "sam2.1_s.pt"

    # Failure on sam2.1_s.pt must fall back cleanly to mobile_sam.pt
    censor.unload_censor_models()
    fallback_calls = []

    def _fake_sam_fallback(name):
        fallback_calls.append(name)
        if "sam2.1" in str(name):
            raise FileNotFoundError("sam2.1_s.pt not present")
        return {"loaded": name}

    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(SAM=_fake_sam_fallback))
    m2 = censor.get_sam_model()
    assert len(fallback_calls) >= 2
    assert Path(fallback_calls[0]).name == "sam2.1_s.pt"
    assert Path(fallback_calls[-1]).name == "mobile_sam.pt"
    assert Path(m2["loaded"]).name == "mobile_sam.pt"
    censor.unload_censor_models()


def test_p25_residual_span_branch_a_hand_split(monkeypatch):
    """P2.5 분기 A: YOLO가 상단만 잡고 교차 손 아래 DeepGHS 잔여 구간이 남은 경우 하단 residual sub_box를 추가 보존함을 검증합니다."""
    import plepa_engine.censor as censor

    img = Image.new("RGB", (500, 700), (235, 185, 165))
    skin_np = np.full((700, 500), 255, dtype=np.uint8)
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: object())

    d_box = (155, 180, 325, 625)  # h=445, y2/H=0.893 > 0.82
    upper_box = (170, 185, 310, 340)  # cov_y = 155/445 = 0.348 < 0.62
    hand_between = (140, 350, 340, 425)
    poly_u = np.array([[175, 190], [305, 190], [305, 335], [175, 335]])

    monkeypatch.setattr(
        censor,
        "_detect_target_candidates",
        lambda *a, **kw: [(d_box, "penis", 0.80)],
    )
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [(upper_box, "penis", 0.72, poly_u)],
    )

    boxes, _, _, priors, ctxs = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[hand_between]
    )
    assert len(boxes) == 2
    assert boxes[0][0] == upper_box
    assert priors[0] is not None
    res_box = boxes[1][0]
    assert res_box[1] >= upper_box[3]
    assert res_box[3] == d_box[3]
    assert priors[1] is None
    assert ctxs[1] is None


def test_p25_residual_span_branch_b_union_extension_and_belly_guard(monkeypatch):
    """P2.5 분기 B: 손 가로질림 없이 YOLO가 상반부만 잡은 경우 Union Span 확장 및 축 연장 코리도 복원 + 복부 스필 차단을 검증합니다."""
    import cv2
    import plepa_engine.censor as censor

    img = Image.new("RGB", (500, 700), (235, 185, 165))
    skin_np = np.full((700, 500), 255, dtype=np.uint8)
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: object())

    # Vertical/slightly slanted shaft centered at x~240 from y=190 to y=600
    d_box = (150, 180, 330, 610)  # h=430
    upper_box = (205, 185, 275, 350)  # cov_y=165/430=0.384 < 0.62, bot_res=260
    poly_u = np.array([[215, 190], [265, 190], [265, 345], [215, 345]])

    monkeypatch.setattr(
        censor,
        "_detect_target_candidates",
        lambda *a, **kw: [(d_box, "penis", 0.79)],
    )
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [(upper_box, "penis", 0.68, poly_u)],
    )

    boxes, _, _, priors, ctxs = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[]
    )
    assert len(boxes) == 1
    assert boxes[0][0] == d_box
    assert ctxs[0] == d_box
    assert priors[0] is not None

    class _FakeMaskData:
        def __init__(self, arr):
            self._arr = arr

        def cpu(self):
            return self

        def numpy(self):
            return self._arr

    class _FakeRes:
        def __init__(self, arr_3d):
            self.masks = type("_M", (), {"data": _FakeMaskData(arr_3d.astype(np.float32))})()

    captured = []

    def _fake_sam_full(crop_pil, **kw):
        cw, ch = crop_pil.size
        pts = kw["points"][0]
        lbls = kw["labels"][0]
        captured.append((list(pts), list(lbls), cw, ch, tuple(kw["bboxes"][0])))
        m = np.zeros((ch, cw), dtype=np.float32)
        # Draw true vertical shaft down through center + false spill in top-left corner
        cx = cw // 2
        cv2.line(m, (cx, 15), (cx, ch - 15), 1.0, thickness=46)
        m[0:80, 0:60] = 1.0
        return [_FakeRes(m[None, :, :])]

    monkeypatch.setattr(censor, "get_sam_model", lambda: _fake_sam_full)
    out = censor.apply_silhouette(
        img,
        boxes,
        color="white",
        fallback_boxes=boxes,
        yolo_prior_masks=priors,
        context_boxes=ctxs,
        skin_np=skin_np,
    )
    out_np = np.array(out)
    white_mask = (out_np[:, :, 0] > 250) & (out_np[:, :, 1] > 250) & (out_np[:, :, 2] > 250)

    assert len(captured) >= 2  # initial prior positive + auxiliary axial positive point
    assert all(1 in lbls and 0 in lbls for _, lbls, _, _, _ in captured)

    upper_white = int(np.count_nonzero(white_mask[210:330, 215:265]))
    lower_ext_white = int(np.count_nonzero(white_mask[440:560, 215:265]))
    belly_spill = int(np.count_nonzero(white_mask[180:220, 150:190]))
    assert upper_white >= 1500
    assert lower_ext_white >= 1500, f"연장 구간 하단 기저부 복원 부족: {lower_ext_white}px"
    assert belly_spill == 0, f"연장 복원 중 상좌측 복부 스필 발생: {belly_spill}px"


def test_p25_case_a_rescue_threshold_area_and_skin_gate(monkeypatch):
    """P2.5: DeepGHS 0건일 때 conf 0.19~0.25 구간의 면적(>=900px)·피부(>=0.12) 게이트를 검증합니다."""
    import plepa_engine.censor as censor

    img = Image.new("RGB", (600, 1100), (235, 185, 165))
    skin_full = np.full((1100, 600), 255, dtype=np.uint8)
    skin_empty = np.zeros((1100, 600), dtype=np.uint8)
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: object())
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: [])

    # 1) aya_131-style: conf=0.21, area=56x54=3024 (>=900), high skin -> rescued
    rescue_box = (247, 952, 303, 1006)
    poly_ok = np.array([[250, 955], [300, 955], [300, 1003], [250, 1003]])
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [(rescue_box, "penis", 0.21, poly_ok)],
    )
    boxes_ok, _, _, _, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_full, hand_boxes=[]
    )
    assert [b[0] for b in boxes_ok] == [rescue_box]

    # 2) Same box & conf=0.21, skin_ratio=0 (<0.12) -> rejected
    boxes_no_skin, _, _, _, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_empty, hand_boxes=[]
    )
    assert boxes_no_skin == []

    # 3) Tiny noise box: area=20x30=600 (<900), conf=0.21, high skin -> rejected
    tiny_box = (260, 960, 280, 990)
    poly_tiny = np.array([[261, 961], [279, 961], [279, 989], [261, 989]])
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [(tiny_box, "penis", 0.21, poly_tiny)],
    )
    boxes_tiny, _, _, _, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_full, hand_boxes=[]
    )
    assert boxes_tiny == []

    # 4) Below min floor conf=0.17 (<0.19) with large box & high skin -> rejected
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [(rescue_box, "penis", 0.17, poly_ok)],
    )
    boxes_low_conf, _, _, _, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_full, hand_boxes=[]
    )
    assert boxes_low_conf == []


def test_p25_prior_purity_ceiling_gate_and_lopsided_residual_x_clamp(monkeypatch):
    """P2.5 보강: 경계 미세파편·이탈 인접 YOLO 프라이어 배제, 상단 극초반 2차 오탐 차단, 편측 대각 손분할 X축 클램핑을 검증합니다."""
    import plepa_engine.censor as censor

    img = Image.new("RGB", (832, 1216), (235, 185, 165))
    skin_np = np.full((1216, 832), 255, dtype=np.uint8)
    monkeypatch.setattr(censor, "get_custom_censor_seg_model", lambda: object())

    # 1) dom_126-style tiny border speck (4.3% area, <6% inter/d_area, conf=0.354) + kei_162-style top ceiling FP (yc/h=0.105 < 0.14)
    d_dom = (464, 394, 645, 779)
    speck = (617, 543, 661, 611)
    top_fp = (368, 88, 482, 168)
    poly_sp = np.array([[618, 545], [660, 545], [660, 610], [618, 610]])
    poly_top = np.array([[370, 90], [480, 90], [480, 166], [370, 166]])
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: [(d_dom, "penis", 0.84)])
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [(speck, "penis", 0.354, poly_sp), (top_fp, "penis", 0.403, poly_top)],
    )
    boxes_1, _, _, priors_1, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[]
    )
    assert [b[0] for b in boxes_1] == [d_dom]
    assert priors_1 == [None]

    # 2) cla_125-style off-center shifted adjacent YOLO box (centroid outside d_box, inter/s_area < 0.55, conf=0.474)
    d_cla = (313, 832, 500, 1150)
    shifted = (415, 986, 590, 1165)
    poly_sh = np.array([[418, 990], [588, 990], [588, 1160], [418, 1160]])
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: [(d_cla, "penis", 0.58)])
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [(shifted, "penis", 0.474, poly_sh)],
    )
    boxes_2, _, _, priors_2, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[]
    )
    assert [b[0] for b in boxes_2] == [d_cla]
    assert priors_2 == [None]

    # 3) kei_187-style lopsided diagonal Branch A (left_uncov=116, right_uncov=22) -> lower residual X2 clamped < 340
    d_kei = (166, 678, 554, 1088)
    yolo_u = (282, 686, 532, 934)
    hand_mid = (294, 884, 482, 995)
    poly_ku = np.array([[285, 690], [530, 690], [530, 930], [285, 930]])
    monkeypatch.setattr(censor, "_detect_target_candidates", lambda *a, **kw: [(d_kei, "penis", 0.83)])
    monkeypatch.setattr(
        censor,
        "_infer_custom_censor_seg_items",
        lambda *a, **kw: [(yolo_u, "penis", 0.65, poly_ku)],
    )
    boxes_3, _, _, priors_3, _ = censor._resolve_hybrid_targets_with_priors(
        img, skin_np=skin_np, hand_boxes=[hand_mid]
    )
    assert len(boxes_3) == 2
    assert boxes_3[0][0] == yolo_u
    res_box = boxes_3[1][0]
    assert res_box[0] == 166
    assert res_box[2] <= 335
    assert res_box[1] >= 934 and res_box[3] == 1088
    assert priors_3[1] is None



