"""
tests/test_mobile_inspection_api.py
Task Censor Phase C3 회귀 테스트:
- 8085 /api/retouch_censor 본체 에셋 3곳 동기화 및 _origin 경로 침범 차단
- 8085 /api/reapply_censor & 8080 /api/assets/reapply-censor 원본 기반 0.2초 재검열
- 8085 /api/reroll_queue 검열 옵션 전달 및 토큰/Origin 인증 차단(401/403)
- 8080 선택적 PLEPA_MOBILE_TOKEN 인증/쿠키 발급 및 로컬 무인증 하위 호환성
- 정적 뷰어 & 8080 모바일 뷰어 UI 컨트롤 렌더링 검증
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from PIL import Image

import plepa_engine.censor as censor_mod
import plepa_engine.services.generation_service as gen_svc_mod
import plepa_gui.api_routes as api_routes_mod
import plepa_gui.app as gui_app_mod
import plepa_gui.pages.mobile_viewer as mobile_viewer_mod
import scripts.generate_inspection_viewer as giv
import scripts.serve_benchmark_mobile as sbm


def _webp_bytes(color=(120, 40, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (12, 12), color).save(buf, "WEBP", quality=95)
    return buf.getvalue()


def _write_webp(path: Path, color=(120, 40, 200)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_webp_bytes(color))
    return path


def _center_pixel(path: Path) -> tuple[int, int, int]:
    with Image.open(path) as im:
        return im.convert("RGB").getpixel((6, 6))


def test_8085_retouch_censor_syncs_three_targets_and_blocks_origin(monkeypatch, tmp_path):
    """8085 /api/retouch_censor 호출 시 inspection_batch, ground_truth, projects/{roster}/assets 3곳 동기화 검증."""
    monkeypatch.setattr(sbm, "ACCESS_TOKEN", "bench-token-8085")
    monkeypatch.setattr(sbm, "INSPECT_BATCH", tmp_path / "inspect")
    monkeypatch.setattr(sbm, "BENCHMARK_DIR", tmp_path / "benchmarks")
    monkeypatch.setattr(sbm, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(sbm.default_character_service, "list_rosters", lambda: ["campus"])

    rel = "aya/02_h_scenes/aya_064_smile.webp"
    inspect_file = _write_webp(sbm.INSPECT_BATCH / rel, (20, 20, 20))
    project_file = _write_webp(sbm.PROJECTS_DIR / "campus" / "assets" / rel, (20, 20, 20))
    origin_file = _write_webp(sbm.PROJECTS_DIR / "campus" / "assets" / "aya_origin" / "02_h_scenes" / "aya_064_smile.webp", (240, 240, 240))

    b64_red = base64.b64encode(_webp_bytes((220, 20, 30))).decode("ascii")
    client = TestClient(sbm.app)

    # _origin 경로 침범 차단(403)
    r_origin_block = client.post(
        "/api/retouch_censor",
        headers={"X-Plepa-Token": "bench-token-8085"},
        json={"file_path": "aya_origin/02_h_scenes/aya_064_smile.webp", "image_base64": b64_red},
    )
    assert r_origin_block.status_code == 403

    # 정상 덧칠 저장 -> 3곳 모두 반영 및 _origin 무손상 보존
    r_ok = client.post(
        "/api/retouch_censor",
        headers={"X-Plepa-Token": "bench-token-8085"},
        json={"file_path": rel, "image_base64": b64_red},
    )
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["success"] is True
    assert body["synced_asset"] is True

    gt_file = sbm.BENCHMARK_DIR / "ground_truth" / "02_h_scenes" / "aya_064_smile.webp"
    assert gt_file.is_file()
    for p in (inspect_file, gt_file, project_file):
        r, g, b = _center_pixel(p)
        assert r > 180 and g < 60 and b < 60

    or_r, or_g, or_b = _center_pixel(origin_file)
    assert or_r > 200 and or_g > 200 and or_b > 200


def test_8085_reapply_censor_from_origin_syncs_assets(monkeypatch, tmp_path):
    """8085 /api/reapply_censor 호출 시 _origin에서 즉시 재검열하여 inspection_batch와 본체 에셋 동기화."""
    monkeypatch.setattr(sbm, "ACCESS_TOKEN", "bench-token-8085")
    monkeypatch.setattr(sbm, "INSPECT_BATCH", tmp_path / "inspect")
    monkeypatch.setattr(sbm, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(sbm.default_character_service, "list_rosters", lambda: ["campus"])

    rel = "aya/02_h_scenes/aya_064_smile.webp"
    inspect_file = _write_webp(sbm.INSPECT_BATCH / rel, (10, 10, 10))
    project_file = _write_webp(sbm.PROJECTS_DIR / "campus" / "assets" / rel, (10, 10, 10))
    origin_file = _write_webp(
        sbm.PROJECTS_DIR / "campus" / "assets" / "aya_origin" / "02_h_scenes" / "aya_064_smile.webp",
        (250, 250, 250),
    )

    captured_calls = []

    def fake_censor_image(image, style="white_silhouette", targets=("penis",), min_confidence=0.16, pose_code=None, enable_anchor_fallback=False, roster=None):
        captured_calls.append({
            "style": style,
            "targets": tuple(targets),
            "min_confidence": min_confidence,
            "pose_code": pose_code,
            "enable_anchor_fallback": enable_anchor_fallback,
            "roster": roster,
            "input_pixel": image.getpixel((6, 6)),
        })
        return Image.new("RGB", image.size, (15, 220, 45)), 2

    monkeypatch.setattr(censor_mod, "censor_image", fake_censor_image)

    client = TestClient(sbm.app)
    r = client.post(
        "/api/reapply_censor",
        headers={"X-Plepa-Token": "bench-token-8085"},
        json={
            "file_path": rel,
            "char_code": "aya",
            "pose_code": "064",
            "censor_style": "mosaic",
            "censor_targets": "penis,breasts",
            "min_confidence": 0.25,
            "enable_anchor_fallback": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["censor_style"] == "mosaic"
    assert data["detected_count"] == 2
    assert data["synced_asset"] is True

    assert len(captured_calls) == 1
    assert captured_calls[0]["style"] == "mosaic"
    assert captured_calls[0]["targets"] == ("penis", "breasts")
    assert captured_calls[0]["min_confidence"] == 0.25
    assert captured_calls[0]["pose_code"] == "064"
    assert captured_calls[0]["enable_anchor_fallback"] is True
    assert captured_calls[0]["roster"] == "campus"

    for p in (inspect_file, project_file):
        r_px, g_px, b_px = _center_pixel(p)
        assert g_px > 180 and r_px < 60

    # 원본 파일 보존
    assert _center_pixel(origin_file)[0] > 210


def test_8085_reroll_forwards_censor_options_and_enforces_auth(monkeypatch, tmp_path):
    """8085 RerollRequest 검열 옵션 전달 및 토큰/Origin 인증(401/403) 검증."""
    monkeypatch.setattr(sbm, "ACCESS_TOKEN", "bench-token-8085")
    monkeypatch.setattr(sbm, "INSPECT_BATCH", tmp_path / "inspect")
    monkeypatch.setattr(sbm, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(sbm.default_character_service, "list_rosters", lambda: ["campus"])

    rel = "aya/02_h_scenes/aya_064_smile.webp"
    inspect_file = _write_webp(sbm.INSPECT_BATCH / rel, (30, 30, 30))
    _write_webp(sbm.PROJECTS_DIR / "campus" / "assets" / rel, (30, 30, 30))

    client = TestClient(sbm.app)

    # 미인증 차단(401)
    assert client.post("/api/reapply_censor", json={"file_path": rel}).status_code == 401
    assert client.post(
        "/api/reroll_queue",
        json={"file_path": rel, "char_code": "aya", "pose_code": "064"},
    ).status_code == 401

    # 외부 Origin 차단(403)
    r_bad_origin = client.post(
        "/api/reapply_censor",
        headers={
            "X-Plepa-Token": "bench-token-8085",
            "Host": "testserver",
            "Origin": "https://evil.example",
        },
        json={"file_path": rel},
    )
    assert r_bad_origin.status_code == 403

    # 큐 등록 시 워커 실행 차단(단위 실행으로 분리 검증)
    monkeypatch.setattr(sbm.reroll_queue_mgr, "jobs", {})
    monkeypatch.setattr(sbm.reroll_queue_mgr, "start_worker", lambda: None)
    r_queue = client.post(
        "/api/reroll_queue",
        headers={"X-Plepa-Token": "bench-token-8085"},
        json={
            "file_path": rel,
            "char_code": "aya",
            "pose_code": "064",
            "label": "smile",
            "censor_style": "bar",
            "censor_targets": "penis",
            "min_confidence": 0.22,
            "enable_anchor_fallback": True,
        },
    )
    assert r_queue.status_code == 200
    job_id = r_queue.json()["job"]["job_id"]
    job_obj = sbm.reroll_queue_mgr.jobs[job_id]
    assert job_obj.censor_style == "bar"
    assert job_obj.censor_targets == "penis"
    assert job_obj.min_confidence == 0.22
    assert job_obj.enable_anchor_fallback is True

    # 워커 실행 시 censor_image로 전달 확인
    generated_src = _write_webp(tmp_path / "comfy_gen.webp", (90, 90, 90))
    captured_worker = {}

    class DummyGenerationService:
        def __init__(self):
            self.pose_bg_svc = SimpleNamespace(cache={})

        def run_batch(self, params, quiet=True):
            captured_worker["params_style"] = params.censor_style
            return [SimpleNamespace(success=True, image_path=str(generated_src), error_message=None)]

    def fake_censor(image, style="white_silhouette", targets=("penis",), min_confidence=0.16, pose_code=None, enable_anchor_fallback=False, roster=None):
        captured_worker["style"] = style
        captured_worker["targets"] = list(targets)
        captured_worker["min_confidence"] = min_confidence
        captured_worker["enable_anchor_fallback"] = enable_anchor_fallback
        return Image.new("RGB", image.size, (40, 90, 230)), 1

    monkeypatch.setattr(gen_svc_mod, "GenerationService", DummyGenerationService)
    monkeypatch.setattr(censor_mod, "censor_image", fake_censor)

    ok, seed, err = sbm._execute_reroll_job(job_obj)
    assert ok is True and err is None and seed is not None
    assert captured_worker["style"] == "bar"
    assert captured_worker["targets"] == ["penis"]
    assert captured_worker["min_confidence"] == 0.22
    assert captured_worker["enable_anchor_fallback"] is True
    assert _center_pixel(inspect_file)[2] > 190


def test_8080_api_reapply_restore_and_optional_token_auth(monkeypatch, tmp_path):
    """8080 /api/assets/reapply-censor, restore-origin 및 선택적 PLEPA_MOBILE_TOKEN 보호 검증."""
    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(api_routes_mod, "PROJECTS_DIR", projects_dir)

    rel = "campus/assets/aya/02_h_scenes/aya_064_smile.webp"
    asset_file = _write_webp(projects_dir / rel, (30, 30, 30))
    origin_file = _write_webp(
        projects_dir / "campus" / "assets" / "aya_origin" / "02_h_scenes" / "aya_064_smile.webp",
        (240, 200, 30),
    )

    monkeypatch.setattr(
        censor_mod,
        "censor_image",
        lambda image, style="white_silhouette", targets=("penis",), min_confidence=0.16, pose_code=None, enable_anchor_fallback=False, roster=None: (
            Image.new("RGB", image.size, (180, 40, 220)),
            1,
        ),
    )

    test_app = FastAPI()
    gui_app_mod.register_optional_token_middleware(test_app)
    test_app.include_router(api_routes_mod.api_router)

    @test_app.get("/mobile", response_class=HTMLResponse)
    def _dummy_mobile():
        return HTMLResponse("<html>ok</html>")

    client = TestClient(test_app)

    # 1. PLEPA_MOBILE_TOKEN 미설정 시 로컬 무인증 호환(100% 패스)
    monkeypatch.delenv("PLEPA_MOBILE_TOKEN", raising=False)
    r_local = client.post(
        "/api/assets/reapply-censor",
        json={"rel_path": rel, "censor_style": "mosaic", "enable_anchor_fallback": True},
    )
    assert r_local.status_code == 200
    assert r_local.json()["success"] is True
    assert _center_pixel(asset_file)[2] > 180

    # 2. PLEPA_MOBILE_TOKEN 설정 시 미인증 차단(401) & 외부 Origin 차단(403)
    monkeypatch.setenv("PLEPA_MOBILE_TOKEN", "studio-secret-8080")
    assert client.post("/api/assets/reapply-censor", json={"rel_path": rel}).status_code == 401
    assert client.post("/api/assets/restore-origin", json={"rel_path": rel}).status_code == 401
    assert client.get("/mobile").status_code == 401

    r_bad_origin = client.post(
        "/api/assets/reapply-censor",
        headers={
            "X-Plepa-Token": "studio-secret-8080",
            "Host": "testserver",
            "Origin": "https://attacker.invalid",
        },
        json={"rel_path": rel},
    )
    assert r_bad_origin.status_code == 403

    # 3. ?token= 진입 시 HttpOnly 쿠키(plepa_token) 발급 및 후속 restore-origin 인증 허용
    r_login = client.get("/mobile?token=studio-secret-8080")
    assert r_login.status_code == 200
    assert r_login.cookies.get("plepa_token") == "studio-secret-8080"

    r_restore = client.post("/api/assets/restore-origin", json={"rel_path": rel})
    assert r_restore.status_code == 200
    assert r_restore.json()["success"] is True
    r_px, g_px, b_px = _center_pixel(asset_file)
    assert r_px > 200 and g_px > 160 and b_px < 70
    assert origin_file.is_file()

    # 4. _origin 경로 직접 수정 시도 차단(403)
    r_origin_write = client.post(
        "/api/assets/restore-origin",
        headers={"X-Plepa-Token": "studio-secret-8080"},
        json={"rel_path": "campus/assets/aya_origin/02_h_scenes/aya_064_smile.webp"},
    )
    assert r_origin_write.status_code == 403


def test_viewers_render_recensor_controls_and_censor_options(monkeypatch, tmp_path):
    """8085 정적 뷰어 & 8080 모바일 뷰어에 재검열 컨트롤 및 검열 옵션이 올바르게 렌더링되는지 검증."""
    # 1. 8085 정적 뷰어 HTML
    inspect_dir = tmp_path / "inspect"
    _write_webp(inspect_dir / "aya" / "02_h_scenes" / "aya_064_smile.webp", (50, 50, 50))
    monkeypatch.setattr(giv, "INSPECT_DIR", inspect_dir)
    monkeypatch.setattr(
        giv.default_character_service,
        "list_characters",
        lambda r: [("aya", SimpleNamespace(name="아야", prefix="aya"), "01.md")],
    )
    out_html = giv.generate_inspection_html(inspection_dir=inspect_dir, roster="campus")
    static_html = out_html.read_text(encoding="utf-8")
    assert "global-censor-style" in static_html
    assert "global-anchor-fallback" in static_html
    assert "reapplyCensor(" in static_html
    assert "debug_bbox" in static_html
    assert "censor_style: censorOpts.censor_style" in static_html
    assert "⚠️ QC경고" in static_html
    assert "job.qc_passed === false" in static_html

    # 2. 8080 모바일 뷰어 HTML
    monkeypatch.setattr(
        mobile_viewer_mod,
        "get_mobile_gallery_data",
        lambda roster="campus": {
            "roster": roster,
            "chars": [{"id": "aya", "name": "아야"}],
            "items": [
                {
                    "char": "aya",
                    "char_name": "아야",
                    "code": "064",
                    "label": "smile",
                    "filename": "aya_064_smile.webp",
                    "rel_path": "campus/assets/aya/02_h_scenes/aya_064_smile.webp",
                    "url": "/projects_static/campus/assets/aya/02_h_scenes/aya_064_smile.webp",
                    "is_recent": True,
                    "is_new": True,
                }
            ],
            "total_missing": 0,
        },
    )
    mob_html = mobile_viewer_mod.generate_mobile_viewer_html(roster="campus")
    assert "censorStyleSelect" in mob_html
    assert "anchorFallbackToggle" in mob_html
    assert "triggerRestoreOrigin(" in mob_html
    assert "triggerReapplyCensor(" in mob_html
    assert "/api/assets/reapply-censor" in mob_html
    assert "/api/assets/restore-origin" in mob_html
    assert "getPlepaAuthHeaders(" in mob_html


def test_8085_reroll_qc_warning_exposed_in_queue_status(monkeypatch, tmp_path):
    """8085 리롤 잡에서 qc_passed=False 발생 시 /api/reroll_queue_status에 경고 메타데이터 노출 검증."""
    monkeypatch.setattr(sbm, "ACCESS_TOKEN", "bench-token-8085")
    monkeypatch.setattr(sbm, "INSPECT_BATCH", tmp_path / "inspect")
    monkeypatch.setattr(sbm, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(sbm.default_character_service, "list_rosters", lambda: ["campus"])
    monkeypatch.setattr(sbm.reroll_queue_mgr, "jobs", {})
    monkeypatch.setattr(sbm.reroll_queue_mgr, "start_worker", lambda: None)

    rel = "aya/02_h_scenes/aya_064_smile.webp"
    _write_webp(sbm.INSPECT_BATCH / rel, (30, 30, 30))
    _write_webp(sbm.PROJECTS_DIR / "campus" / "assets" / rel, (30, 30, 30))

    client = TestClient(sbm.app)
    r_q = client.post(
        "/api/reroll_queue",
        headers={"X-Plepa-Token": "bench-token-8085"},
        json={
            "file_path": rel,
            "char_code": "aya",
            "pose_code": "064",
            "strict_censor_qc": True,
            "auto_qc": True,
        },
    )
    assert r_q.status_code == 200
    job_id = r_q.json()["job"]["job_id"]
    job_obj = sbm.reroll_queue_mgr.jobs[job_id]
    assert job_obj.strict_censor_qc is True
    assert job_obj.auto_qc is True

    generated_src = _write_webp(tmp_path / "comfy_qc_warn.webp", (80, 80, 80))

    class _DummyGenSvc:
        def __init__(self):
            self.pose_bg_svc = SimpleNamespace(cache={})

        def run_batch(self, params, quiet=True):
            assert params.strict_censor_qc is True
            assert params.auto_qc is True
            return [
                SimpleNamespace(
                    success=True,
                    image_path=str(generated_src),
                    error_message=None,
                    qc_passed=False,
                    qc_reason="필수 성인 씬 성기 미탐지(구도 불량)",
                )
            ]

    monkeypatch.setattr(gen_svc_mod, "GenerationService", _DummyGenSvc)
    monkeypatch.setattr(
        censor_mod,
        "censor_image",
        lambda image, **kw: (Image.new("RGB", image.size, (10, 20, 30)), 0),
    )

    ok, seed, err = sbm._execute_reroll_job(job_obj)
    assert ok is True and err is None and seed is not None
    job_obj.status = "done"
    job_obj.new_seed = seed

    r_status = client.get("/api/reroll_queue_status", headers={"X-Plepa-Token": "bench-token-8085"})
    assert r_status.status_code == 200
    job_status = r_status.json()["data"]["jobs"][job_id]
    assert job_status["qc_passed"] is False
    assert job_status["qc_reason"] == "필수 성인 씬 성기 미탐지(구도 불량)"


def test_8080_reroll_and_fill_missing_inherit_config_qc(monkeypatch):
    """8080 /api/assets/reroll 및 /fill-missing의 auto_qc/strict_censor_qc config 상속 및 명시 오버라이드 검증."""
    monkeypatch.delenv("PLEPA_MOBILE_TOKEN", raising=False)
    monkeypatch.setattr(
        api_routes_mod.default_config_service,
        "get_config",
        lambda: {"auto_qc": True, "strict_censor_qc": True, "censor_style": "mosaic", "censor_targets": "penis"},
    )
    monkeypatch.setattr(
        api_routes_mod.default_asset_service,
        "get_missing_poses_by_character",
        lambda roster: {"aya": ["064"]},
    )

    enqueued = []
    monkeypatch.setattr(
        api_routes_mod.global_job_manager,
        "enqueue_job",
        lambda params, label="": (enqueued.append(params) or True, len(enqueued)),
    )

    app = FastAPI()
    app.include_router(api_routes_mod.api_router)
    client = TestClient(app)

    # 1. 미지정 시 Config 상속 (auto_qc=True, strict_censor_qc=True)
    r1 = client.post("/api/assets/reroll", json={"char": "aya", "code": "064", "roster": "campus"})
    assert r1.status_code == 200
    assert r1.json()["auto_qc"] is True
    assert r1.json()["strict_censor_qc"] is True
    assert enqueued[-1].strict_censor_qc is True
    assert enqueued[-1].auto_qc is True

    # 2. 명시적 오버라이드 (strict_censor_qc=False)
    r2 = client.post(
        "/api/assets/fill-missing",
        json={"roster": "campus", "char": "aya", "strict_censor_qc": False, "auto_qc": False},
    )
    assert r2.status_code == 200
    assert r2.json()["strict_censor_qc"] is False
    assert r2.json()["auto_qc"] is False
    assert enqueued[-1].strict_censor_qc is False
    assert enqueued[-1].auto_qc is False

