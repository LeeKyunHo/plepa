"""
tests/test_censor_and_pipeline_fixes.py
H1(검열 targets 존중/로스터 캐시 격리/영숫자 정규식/폴백 기본값),
H2(custom_neg/pose.negative_add 격리 및 괄호 균형),
H6(GenitExporter & mobile_viewer 동적 로스터) 회귀 테스트.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from plepa_engine import censor
from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import assemble_sdxl_prompt
from plepa_engine.prompt_pipeline import remove_conflicting_tags_from_negative
from plepa_engine.services import genit_exporter
from plepa_engine.services.schemas import CharacterSchema
from plepa_gui.pages import mobile_viewer


def _make_skin_image(w: int = 500, h: int = 500) -> Image.Image:
    arr = np.full((h, w, 3), (245, 200, 180), dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def test_censor_image_and_verify_heal_honor_targets(monkeypatch):
    """H1: censor_image와 verify_and_heal_censor가 targets 인수를 엄격히 준수하는지 검증."""
    skin_img = _make_skin_image()
    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)

    # pussy만 탐지된 상황: targets=("penis",)는 무시하고 targets=("pussy",)/("all",)만 수용
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda *a, **kw: [((150, 300, 260, 420), "pussy", 0.90)],
    )
    _, cnt_penis_only = censor.censor_image(skin_img, targets=("penis",), pose_code="067")
    _, cnt_pussy = censor.censor_image(skin_img, targets=("pussy",), pose_code="067")
    _, cnt_all = censor.censor_image(skin_img, targets=("all",), pose_code="067")
    assert cnt_penis_only == 0
    assert cnt_pussy >= 1
    assert cnt_all >= 1

    # verify_and_heal_censor 역시 targets=("penis",)일 때 pussy 오탐을 무시해야 함
    _, healed_penis = censor.verify_and_heal_censor(skin_img, targets=("penis",))
    _, healed_pussy = censor.verify_and_heal_censor(skin_img, targets=("pussy",))
    assert healed_penis is False
    assert healed_pussy is True


def test_censor_pose_db_cache_isolation_and_defaults(monkeypatch):
    """H1: _get_cached_pose_db 로스터별 캐시 격리, 영숫자 코드 정규식, enable_anchor_fallback 기본 False 검증."""
    calls = []

    def _fake_load(engine="sdxl", roster="campus"):
        calls.append(roster)
        return {
            "088": PoseEntry(code="088", section="h_scenes", label="후배위", prompt="doggystyle")
        }

    with censor._POSE_DB_CACHE_LOCK:
        saved = dict(censor._POSE_DB_CACHE)
        censor._POSE_DB_CACHE.clear()
    try:
        monkeypatch.setattr(
            "plepa_engine.services.pose_service.default_pose_service.load_pose_db",
            _fake_load,
        )
        db1 = censor._get_cached_pose_db("campus")
        db2 = censor._get_cached_pose_db("campus")
        db3 = censor._get_cached_pose_db("ykn")
        assert db1 is db2
        assert db3 is not db1
        assert calls == ["campus", "ykn"]
    finally:
        with censor._POSE_DB_CACHE_LOCK:
            censor._POSE_DB_CACHE.clear()
            censor._POSE_DB_CACHE.update(saved)

    # 영숫자 성인 코드(N01) 및 일반 면제 코드(010) 판별 검증
    assert censor.is_pose_censor_required(file_path=Path("aya_N01_pose.webp")) is True
    assert censor.is_pose_censor_required(file_path=Path("aya_010_happy.webp")) is False

    # enable_anchor_fallback 기본값 False 계약 검증
    sig = inspect.signature(censor.censor_image)
    assert sig.parameters["enable_anchor_fallback"].default is False


def test_pipeline_isolates_custom_and_pose_negatives_from_mob_strip():
    """H2: pose.negative_add와 custom_neg의 남성 관련 부정 태그가 2인 씬 스트리핑에 훼손되지 않아야 함."""
    char = CharacterConfig(
        prefix="test",
        name="TestChar",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="long black hair, red eyes",
            physique="slender",
            outfit="school uniform",
        ),
        sdxl_positive="masterpiece BREAK 1girl, long black hair, red eyes, white shirt, pleated skirt",
        sdxl_negative="worst quality, lowres",
    )
    pose = PoseEntry(
        code="088",
        section="h_scenes",
        label="후배위",
        prompt="doggystyle, 1girl, partner, sex from behind",
        negative_add="multiple boys, 2boys, extra hands",
    )
    pos, neg, _ = assemble_sdxl_prompt(
        char=char,
        pose=pose,
        bg_prompt="bedroom",
        custom_neg="1boy focus, fat man",
    )
    assert "multiple boys" in neg
    assert "2boys" in neg
    assert "extra hands" in neg
    assert "1boy focus" in neg
    assert "fat man" in neg
    assert pos.count("(") == pos.count(")")
    assert neg.count("(") == neg.count(")")


def test_pipeline_clothed_oral_and_conflict_strip_balance_parentheses():
    """H2: 착의 구강 씬([패치 E]) 및 부정 충돌 제거 시 짝이 맞지 않는 괄호가 남지 않아야 함."""
    char = CharacterConfig(
        prefix="aya",
        name="아야",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="silver hair",
            physique="large breasts",
            outfit="open shirt, black sheer pantyhose",
        ),
        sdxl_positive="masterpiece BREAK (1girl:1.1), silver hair, (open shirt, black sheer pantyhose:1.15)",
        sdxl_negative="worst quality, lowres",
    )
    pose = PoseEntry(
        code="067",
        section="h_scenes",
        label="딥스로트",
        prompt="fellatio, deepthroat, 1boy, penis, kneeling",
        required_outfit="default",
    )
    pos, neg, is_nude = assemble_sdxl_prompt(char=char, pose=pose, bg_prompt="classroom")
    assert is_nude is False
    assert pos.count("(") == pos.count(")")
    assert neg.count("(") == neg.count(")")

    # 중첩 가중치 괄호 내 충돌 태그 제거 후에도 괄호 균형 유지
    cleaned_neg, removed = remove_conflicting_tags_from_negative(
        "smile, open mouth",
        "worst quality, (smile:1.2, bad hands), ((open mouth)), lowres",
    )
    assert "smile" in removed
    assert cleaned_neg.count("(") == cleaned_neg.count(")")
    assert "bad hands" in cleaned_neg


def test_dynamic_genit_exporter_and_mobile_viewer_non_campus(monkeypatch, tmp_path):
    """H6: GenitExporter genit_map.json 동적 매핑 및 mobile_viewer 임의 로스터 동적 탐색 검증."""
    custom_dir = tmp_path / "nebula"
    (custom_dir / "assets" / "zz" / "01_normal").mkdir(parents=True)
    (custom_dir / "assets" / "zz" / "01_normal" / "zz_020_wave.webp").write_bytes(b"WEBP")
    (custom_dir / "genit_map.json").write_text('{"zz": "NZ"}', encoding="utf-8")

    monkeypatch.setattr(genit_exporter, "PROJECTS_DIR", tmp_path)
    assert genit_exporter.GenitExporter.resolve_export_code("테스트", "zz", roster="nebula") == "NZ"

    monkeypatch.setattr(mobile_viewer, "PROJECTS_DIR", tmp_path)
    schema = CharacterSchema(prefix="zz", name="제트", gender="female")
    monkeypatch.setattr(
        mobile_viewer.default_character_service,
        "list_characters",
        lambda roster=None: [("nebula", schema, custom_dir / "characters" / "zz.json")],
    )
    monkeypatch.setattr(
        "plepa_engine.services.asset_service.default_asset_service.get_missing_poses_by_character",
        lambda roster=None: {"zz": []},
    )

    data = mobile_viewer.get_mobile_gallery_data(roster="nebula")
    assert data["roster"] == "nebula"
    assert [c["id"] for c in data["chars"]] == ["zz"]
    assert len(data["items"]) == 1
    assert data["items"][0]["code"] == "020"
    assert data["items"][0]["label"] == "wave"
    html_out = mobile_viewer.generate_mobile_viewer_html(roster="nebula")
    assert "제트" in html_out
    assert "아야" not in html_out


def test_underdesk_prompt_female_floor_and_clothed_partner():
    """ADR-93: 책상밑 포즈(#126) 조립 시 여성 의자 태그 배제 및 파트너 상의 착의 주입 검증."""
    from plepa_engine.services.character_service import default_character_service
    from plepa_engine.services.pose_service import default_pose_service
    from plepa_engine.prompt_builder import assemble_sdxl_prompt

    char, _ = default_character_service.find_character("mai", roster="campus")
    pose = default_pose_service.load_pose_db("sdxl")["126"]
    pos, neg, is_nude = assemble_sdxl_prompt(char, pose, bg_prompt="")

    assert is_nude is False
    assert "clothed male partner" in pos.lower()
    assert "white shirt" in pos.lower()
    assert "female sitting on chair" in neg.lower()
    assert "shirtless male" in neg.lower()


def test_strict_censor_qc_reroll_and_single_backup_and_unload(monkeypatch, tmp_path):
    """C2-1: strict_censor_qc=True 시 088 포즈에서 detect_genitals 정상 호출, 미탐지 리롤, 단일 백업 및 unload 검증."""
    from contextlib import nullcontext
    from plepa_engine.services import generation_service as gs_mod

    monkeypatch.setattr(gs_mod, "PROJECTS_DIR", tmp_path)

    char = CharacterConfig(
        prefix="tst",
        name="테스트",
        gender="female",
        appearance=CharacterAppearance(
            face_and_hair="black hair",
            physique="average",
            outfit="uniform",
        ),
        sdxl_positive="masterpiece BREAK 1girl, black hair",
        sdxl_negative="worst quality",
    )
    pose_088 = PoseEntry(code="088", section="h_scenes", label="후배위", prompt="doggystyle, 1boy, penis, sex")

    class _FakeCharSvc:
        def resolve_characters(self, expr, roster=None):
            return [(char, roster or "campus")]

    class _FakePoseSvc:
        def load_pose_db(self, engine="sdxl", roster=None):
            return {"088": pose_088}

        def resolve_pose_codes(self, expr, db, roster=None):
            return ["088"]

        def is_pose_allowed_for_character(self, pose, char_obj, roster=None, code=None):
            return True

    class _FakeBgSvc:
        def get_preset(self, roster, key="auto", engine="sdxl"):
            return "bedroom"

    class _FakePoseBgSvc:
        def get_background_for_pose(self, roster, code):
            return "default"

    class _FakeAssetSvc:
        def find_reference_image(self, prefix, roster, custom_path=None):
            return None

    class _FakeClient:
        def __init__(self, *a, **kw):
            self.calls = 0

        def check_connection(self):
            return True

        def session(self):
            return nullcontext()

        def generate_image(self, workflow, output_path, **kw):
            self.calls += 1
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _make_skin_image(128, 128).save(output_path, "WEBP")

    fake_client = _FakeClient()
    monkeypatch.setattr(gs_mod, "ComfyClient", lambda *a, **kw: fake_client)
    monkeypatch.setattr(gs_mod, "validate_generated_image", lambda *a, **kw: (True, "OK", {}))

    detect_calls = []
    # 1차 시도: 미탐지([]) -> 리롤 트리거, 2차 시도: 탐지 성공
    def _fake_detect_genitals(img_path, targets=("penis",), min_confidence=0.22, pose_code=None, roster=None, **kw):
        detect_calls.append({"pose_code": pose_code, "targets": list(targets), "roster": roster})
        if len(detect_calls) == 1:
            return []
        return [((20, 40, 80, 100), "penis", 0.91)]

    monkeypatch.setattr(censor, "detect_genitals", _fake_detect_genitals)

    censor_file_kwargs = []

    def _fake_censor_file(src_path, dst_path=None, **kw):
        censor_file_kwargs.append(kw)
        dst = Path(dst_path)
        _make_skin_image(128, 128).save(dst, "WEBP")
        return dst

    monkeypatch.setattr(gs_mod, "censor_file", _fake_censor_file)

    unload_calls = []
    monkeypatch.setattr(gs_mod, "unload_censor_models", lambda: unload_calls.append(True))

    svc = gs_mod.GenerationService(
        character_svc=_FakeCharSvc(),
        pose_svc=_FakePoseSvc(),
        bg_svc=_FakeBgSvc(),
        asset_svc=_FakeAssetSvc(),
        pose_bg_svc=_FakePoseBgSvc(),
    )
    params = gs_mod.GenerationParams(
        character_expr="tst",
        pose_expr="088",
        roster="campus",
        censor=True,
        censor_style="bar",
        censor_targets="penis,pussy",
        strict_censor_qc=True,
        auto_qc=True,
        max_retries=1,
        overwrite=True,
    )
    results = svc.run_batch(params, quiet=True)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].qc_passed is True
    assert results[0].retries == 1
    assert fake_client.calls == 2
    assert len(detect_calls) == 2
    assert detect_calls[0]["pose_code"] == "088"
    assert detect_calls[0]["targets"] == ["penis", "pussy"]
    assert detect_calls[0]["roster"] == "campus"
    assert len(censor_file_kwargs) == 1
    assert censor_file_kwargs[0]["backup_dir"] is None
    assert censor_file_kwargs[0]["style"] == "bar"
    assert len(unload_calls) == 1

    # 최대 재시도(max_retries=0 -> 1회만 시도)에서도 계속 미탐지 시 qc_passed=False 판정 검증
    detect_calls.clear()
    monkeypatch.setattr(censor, "detect_genitals", lambda *a, **kw: [])
    params_fail = gs_mod.GenerationParams(
        character_expr="tst",
        pose_expr="088",
        roster="campus",
        censor=True,
        strict_censor_qc=True,
        auto_qc=True,
        max_retries=0,
        overwrite=True,
    )
    fail_res = svc.run_batch(params_fail, quiet=True)
    assert fail_res[0].qc_passed is False
    assert "미탐지" in (fail_res[0].qc_reason or "")


def test_detect_target_candidates_iou_merge_priority_and_tiny_noise_filter(monkeypatch):
    """C2-2: IoU > 0.45 다중 박스 병합 시 penis 우선순위 보존 및 < 12px 극소 노이즈 기각 검증."""
    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)
    skin_img = _make_skin_image(832, 832)

    def _fake_detect(im, conf_threshold=0.16):
        if im.size != (832, 832):
            return []
        return [
            ((150, 350, 158, 358), "penis", 0.95),   # 8x8 px 극소 노이즈 (< 12px) -> 기각
            ((200, 400, 320, 540), "pussy", 0.88),   # 큰 박스 1
            ((205, 405, 325, 545), "penis", 0.72),   # IoU > 0.45 겹치는 penis -> 병합 후 라벨은 penis
        ]

    monkeypatch.setattr(censor, "detect_censors", _fake_detect)
    merged = censor._detect_target_candidates(skin_img, targets=("all",), min_confidence=0.16)
    assert len(merged) == 1
    box, lbl, score = merged[0]
    assert box == (200, 400, 325, 545)
    assert lbl == "penis"
    assert score >= 0.88


def test_censor_file_and_run_batch_filesystem_contracts(monkeypatch, tmp_path):
    """C2-3: _origin/_censored 스킵, 미탐지 시 파일 미생성 보장, .png/.jpg/.webp 확장자 정상 인코딩 검증."""
    monkeypatch.setattr(censor, "HAS_IMGUTILS", True)

    # 1. 미탐지(count == 0) 시 출력 파일 미생성 보장
    monkeypatch.setattr(censor, "detect_censors", lambda *a, **kw: [])
    src_zero = tmp_path / "aya_088_doggystyle.webp"
    dst_zero = tmp_path / "aya_088_doggystyle_out.webp"
    _make_skin_image(400, 400).save(src_zero, "WEBP")
    assert censor.censor_file(src_zero, dst_path=dst_zero, pose_code="088") is None
    assert not dst_zero.exists()

    # 2. 탐지 성공 시 .png / .jpg / .webp 각 포맷 정상 인코딩 검증
    monkeypatch.setattr(
        censor,
        "detect_censors",
        lambda im, conf_threshold=0.16: [((120, 160, 240, 300), "penis", 0.92)] if im.size == (400, 400) else [],
    )
    for ext, expected_fmt in ((".png", "PNG"), (".jpg", "JPEG"), (".webp", "WEBP")):
        out_p = tmp_path / f"encoded_088{ext}"
        res_p = censor.censor_file(src_zero, dst_path=out_p, style="bar", pose_code="088")
        assert res_p == out_p and out_p.exists()
        with Image.open(out_p) as saved_im:
            assert saved_im.format == expected_fmt
            assert saved_im.size == (400, 400)

    # 3. run_batch_censor에서 _origin 폴더 및 *_censored.* 파일 자동 스킵 검증
    origin_dir = tmp_path / "batch" / "_origin"
    normal_dir = tmp_path / "batch" / "aya" / "02_h_scenes"
    origin_dir.mkdir(parents=True)
    normal_dir.mkdir(parents=True)

    _make_skin_image(400, 400).save(origin_dir / "aya_088_origin.webp", "WEBP")
    _make_skin_image(400, 400).save(normal_dir / "aya_088_censored.webp", "WEBP")
    _make_skin_image(400, 400).save(normal_dir / "aya_088_doggystyle.webp", "WEBP")

    processed = censor.run_batch_censor(tmp_path / "batch", overwrite=False)
    assert processed == 1
    assert not (origin_dir / "aya_088_origin_censored.webp").exists()
    assert not (normal_dir / "aya_088_censored_censored.webp").exists()
    assert (normal_dir / "aya_088_doggystyle_censored.webp").exists()
