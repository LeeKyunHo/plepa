"""
tests/test_security_and_atomic_io.py
C1(인증/경로 탐색/XSS 방어), C2(원자적 파일 교체/원본 보존), C4(임포트 부작용 제거/큐 상한) 회귀 테스트.
"""

from __future__ import annotations

import ast
import base64
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from plepa_engine import censor, comfy_client
from plepa_engine.models import PoseEntry
from plepa_engine.services import genit_exporter
from plepa_engine.services.upscale_service import UpscaleService
from plepa_gui.api_routes import api_router
import scripts.generate_inspection_viewer as giv
import scripts.mobile_gallery as mg
import scripts.serve_benchmark_mobile as sbm


def _tiny_webp_bytes(color=(120, 40, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, "WEBP", quality=80)
    return buf.getvalue()


def test_serve_benchmark_auth_origin_and_cookie(monkeypatch, tmp_path):
    """C1: serve_benchmark_mobile 인증, Origin 검증, ?token 쿠키 및 리터치 원자 저장 검증."""
    monkeypatch.setattr(sbm, "ACCESS_TOKEN", "test-secret-token-42")
    monkeypatch.setattr(sbm, "INSPECT_BATCH", tmp_path / "inspect")
    monkeypatch.setattr(sbm, "BENCHMARK_DIR", tmp_path / "benchmarks")
    monkeypatch.setattr(sbm, "PROJECTS_DIR", tmp_path / "projects")

    target = sbm.INSPECT_BATCH / "aya" / "01_normal" / "aya_001_smile.webp"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_tiny_webp_bytes((10, 20, 30)))

    client = TestClient(sbm.app)
    b64_img = base64.b64encode(_tiny_webp_bytes((200, 10, 10))).decode("ascii")

    # 1. 토큰 없이 변경/상태 엔드포인트 호출 시 모두 401 차단
    assert client.get("/api/reroll_queue_status").status_code == 401
    assert client.post("/api/retouch_censor", json={"file_path": "aya/01_normal/aya_001_smile.webp", "image_base64": b64_img}).status_code == 401
    assert client.post("/api/restore_origin", json={"file_path": "aya/01_normal/aya_001_smile.webp"}).status_code == 401
    assert client.post("/api/reroll_queue", json={"file_path": "aya/01_normal/aya_001_smile.webp", "char_code": "aya", "pose_code": "001"}).status_code == 401
    assert client.post("/api/reroll_pose", json={"file_path": "aya/01_normal/aya_001_smile.webp", "char_code": "aya", "pose_code": "001"}).status_code == 401

    # 2. 헤더/Bearer 토큰으로 인증 허용
    r_status = client.get("/api/reroll_queue_status", headers={"X-Plepa-Token": "test-secret-token-42"})
    assert r_status.status_code == 200
    assert r_status.json()["success"] is True

    r_bearer = client.get("/api/reroll_queue_status", headers={"Authorization": "Bearer test-secret-token-42"})
    assert r_bearer.status_code == 200

    # 3. ?token=... 미들웨어가 HttpOnly 쿠키를 발급하여 후속 요청을 인증하는지 검증
    r_cookie_seed = client.get("/api/data?token=test-secret-token-42")
    assert r_cookie_seed.status_code == 200
    assert "plepa_token" in r_cookie_seed.cookies
    assert client.get("/api/reroll_queue_status").status_code == 200

    # 4. 외부 Origin 헤더가 Host와 불일치할 때 403 차단
    r_foreign_origin = client.post(
        "/api/retouch_censor",
        headers={
            "X-Plepa-Token": "test-secret-token-42",
            "Host": "testserver",
            "Origin": "https://evil.attacker.example",
        },
        json={"file_path": "aya/01_normal/aya_001_smile.webp", "image_base64": b64_img},
    )
    assert r_foreign_origin.status_code == 403

    # 5. 정상 토큰 + 정상 경로 리터치 저장
    r_ok = client.post(
        "/api/retouch_censor",
        headers={"X-Plepa-Token": "test-secret-token-42"},
        json={"file_path": "aya/01_normal/aya_001_smile.webp", "image_base64": b64_img},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["success"] is True
    assert (sbm.BENCHMARK_DIR / "ground_truth" / "01_normal" / "aya_001_smile.webp").is_file()


def test_serve_benchmark_path_traversal_blocked(monkeypatch, tmp_path):
    """C1: serve_benchmark_mobile 경로 탈출 및 _origin 접근 차단."""
    monkeypatch.setattr(sbm, "ACCESS_TOKEN", "tok-xyz")
    monkeypatch.setattr(sbm, "INSPECT_BATCH", tmp_path / "inspect")
    sbm.INSPECT_BATCH.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.webp"
    outside.write_bytes(_tiny_webp_bytes())

    client = TestClient(sbm.app)
    b64_img = base64.b64encode(_tiny_webp_bytes()).decode("ascii")
    headers = {"X-Plepa-Token": "tok-xyz"}

    for bad_path in ("../outside.webp", "aya/../../outside.webp", "aya/_origin/01_normal/x.webp"):
        r1 = client.post("/api/retouch_censor", headers=headers, json={"file_path": bad_path, "image_base64": b64_img})
        r2 = client.post("/api/restore_origin", headers=headers, json={"file_path": bad_path})
        r3 = client.post("/api/reroll_queue", headers=headers, json={"file_path": bad_path, "char_code": "aya", "pose_code": "001"})
        assert r1.status_code == 403
        assert r2.status_code == 403
        assert r3.status_code == 403


def test_mobile_gallery_traversal_and_xss_defense(monkeypatch, tmp_path):
    """C1: mobile_gallery /asset 경로 탈출, _origin 차단 및 JS XSS 이스케이프 검증."""
    assets = tmp_path / "assets"
    normal = assets / "hay" / "01_normal"
    normal.mkdir(parents=True)
    (normal / "hay_001_smile.webp").write_bytes(_tiny_webp_bytes())

    origin_dir = assets / "hay" / "_origin" / "01_normal"
    origin_dir.mkdir(parents=True)
    (origin_dir / "hay_001_smile.webp").write_bytes(_tiny_webp_bytes())

    secret = tmp_path / "secret.webp"
    secret.write_bytes(b"TOPSECRET")

    monkeypatch.setattr(mg, "ASSETS_DIR", assets)
    client = TestClient(mg.app)

    assert client.get("/asset/hay/01_normal/hay_001_smile.webp").status_code == 200
    assert client.get("/asset/hay/_origin/01_normal/hay_001_smile.webp").status_code == 403
    assert client.get("/asset/%2e%2e/secret.webp").status_code == 403
    assert mg.serve_asset("../secret.webp").status_code == 403

    html_resp = client.get("/")
    assert html_resp.status_code == 200
    assert "escapeHtml" in html_resp.text
    assert 'onclick="openModal(this.dataset.url, this.dataset.title)"' in html_resp.text


def test_gui_api_routes_path_traversal_roster_validation_and_undo(tmp_path, monkeypatch):
    """C1: plepa_gui/api_routes 로스터 인젝션(400), 파일 삭제 경로 탈출(403), 복원 실패(400) 검증."""
    from plepa_gui import api_routes

    monkeypatch.setattr(api_routes, "PROJECTS_DIR", tmp_path / "projects")
    api_routes.PROJECTS_DIR.mkdir(parents=True)

    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)

    r_bad_roster = client.get("/api/assets/missing-summary?roster=../evil")
    assert r_bad_roster.status_code == 400

    r_bad_del = client.post("/api/assets/delete", json={"rel_path": "../../etc/passwd"})
    assert r_bad_del.status_code == 400

    r_bad_undo = client.post(
        "/api/assets/undo",
        json={"moved": [{"orig": str(tmp_path / "missing.webp"), "trash": str(tmp_path / "no_trash.webp")}]},
    )
    assert r_bad_undo.status_code == 400


def test_inspection_viewer_escapes_html_and_forwards_token(tmp_path, monkeypatch):
    """C1: generate_inspection_viewer HTML 이스케이프 및 X-Plepa-Token 전달 JS 삽입 검증."""
    insp = tmp_path / "inspect"
    sample = insp / "aya" / "02_h_scenes" / "aya_064_test.webp"
    sample.parent.mkdir(parents=True)
    sample.write_bytes(_tiny_webp_bytes())

    xss_pose = PoseEntry(
        code="064",
        section="h_scenes",
        label="<script>alert('xss')</script>",
        prompt="test",
    )
    monkeypatch.setattr(giv.default_pose_service, "load_pose_db", lambda engine="sdxl", roster="campus": {"064": xss_pose})

    html_path = giv.generate_inspection_html(inspection_dir=insp, roster="campus")
    content = html_path.read_text(encoding="utf-8")

    assert "<script>alert('xss')</script>" not in content
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in content
    assert "getPlepaAuthHeaders" in content
    assert "X-Plepa-Token" in content


def test_atomic_file_replacement_preserves_originals_on_failure(tmp_path, monkeypatch):
    """C2: upscale_service, censor_file, genit_exporter, comfy_client 실패 시 기존 파일 손실 없음 검증."""
    # 1. UpscaleService 실패 시 기존 output_path 무손실 보존
    src_up = tmp_path / "in.webp"
    out_up = tmp_path / "out.webp"
    src_up.write_bytes(_tiny_webp_bytes())
    out_up.write_bytes(b"ORIGINAL_UPSCALE_DATA")

    mock_client = MagicMock()
    mock_client.check_connection.return_value = True
    mock_client.upload_image.return_value = "in.webp"
    mock_client.generate_image.side_effect = RuntimeError("simulated comfy failure")
    svc = UpscaleService(client=mock_client)

    with pytest.raises(RuntimeError):
        svc.upscale_file(src_up, output_path=out_up)
    assert out_up.read_bytes() == b"ORIGINAL_UPSCALE_DATA"
    assert not list(tmp_path.glob(".tmp_*"))

    # 2. censor_file 저장 실패 시 기존 dst_path 무손실 보존
    src_c = tmp_path / "aya_088_raw.png"
    dst_c = tmp_path / "censored.webp"
    Image.new("RGB", (16, 16), (10, 20, 30)).save(src_c, "PNG")
    dst_c.write_bytes(b"ORIGINAL_CENSORED_BYTES")

    monkeypatch.setattr(censor, "censor_image", lambda *a, **kw: (Image.new("RGB", (16, 16), (255, 255, 255)), 1))

    def _fail_save(*args, **kwargs):
        raise OSError("disk full during temp write")

    monkeypatch.setattr(Image.Image, "save", _fail_save)
    with pytest.raises(OSError):
        censor.censor_file(src_c, dst_path=dst_c, pose_code="088")
    assert dst_c.read_bytes() == b"ORIGINAL_CENSORED_BYTES"
    assert not list(tmp_path.glob("*.tmp*"))

    # 3. GenitExporter.export_character 실패 시 기존 대상 에셋 무손실 보존
    proj_root = tmp_path / "projects"
    asset_src = proj_root / "custom" / "assets" / "aa" / "01_emotions" / "aa_A00_hi.webp"
    asset_src.parent.mkdir(parents=True)
    asset_src.write_bytes(b"NEW_ASSET_BYTES")

    dist_dir = tmp_path / "dist"
    existing_dest = dist_dir / "AA" / "A0.webp"
    existing_dest.parent.mkdir(parents=True)
    existing_dest.write_bytes(b"OLD_GENIT_BYTES")

    monkeypatch.setattr(genit_exporter, "PROJECTS_DIR", proj_root)
    monkeypatch.setattr(genit_exporter.shutil, "copy2", lambda *a, **kw: (_ for _ in ()).throw(OSError("copy interrupted")))

    exporter = genit_exporter.GenitExporter()
    with pytest.raises(OSError):
        exporter.export_character(roster="custom", char_prefix="aa", char_name="테스트", output_dir=dist_dir)
    assert existing_dest.read_bytes() == b"OLD_GENIT_BYTES"
    assert not list((dist_dir / "AA").glob("*.tmp"))

    # 4. comfy_client._atomic_replace_with_retry 재시도 및 원본 미삭제 교체 검증
    tmp_src = tmp_path / "new.tmp"
    dst_comfy = tmp_path / "final.webp"
    tmp_src.write_bytes(b"NEW_COMFY_DATA")
    dst_comfy.write_bytes(b"OLD_COMFY_DATA")

    real_replace = comfy_client.os.replace
    attempts = {"n": 0}

    def _flaky_replace(s, d):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("transient lock")
        return real_replace(s, d)

    monkeypatch.setattr(comfy_client.os, "replace", _flaky_replace)
    monkeypatch.setattr(comfy_client.time, "sleep", lambda *_: None)
    comfy_client._atomic_replace_with_retry(tmp_src, dst_comfy, retries=5)
    assert attempts["n"] == 3
    assert dst_comfy.read_bytes() == b"NEW_COMFY_DATA"


def test_no_import_time_mkdir_and_queue_retention_cap():
    """C4: 모바일 서버 스크립트 임포트 시 디렉토리 자동 생성 부작용 없음 및 완료 큐 상한(200건) 검증."""
    root = Path(__file__).resolve().parent.parent
    for rel in ("scripts/serve_benchmark_mobile.py", "scripts/mobile_gallery.py"):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for stmt in tree.body:
            for node in ast.walk(stmt):
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Compare):
                    continue
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "mkdir":
                    pytest.fail(f"{rel} 모듈 최상위에서 .mkdir() 임포트 부작용 호출 발견")

    mgr = sbm.RerollQueueManager()
    total_done = sbm.RerollQueueManager.MAX_COMPLETED_JOBS + 25
    for idx in range(total_done):
        j = sbm.RerollJob(f"done_{idx}", f"aya/01_normal/p_{idx}.webp", "aya", "001")
        j.status = "done"
        mgr.jobs[j.job_id] = j
    pending = sbm.RerollJob("queued_1", "aya/01_normal/q.webp", "aya", "002")
    pending.status = "queued"
    mgr.jobs[pending.job_id] = pending

    mgr._prune_completed_jobs()
    done_left = [k for k, v in mgr.jobs.items() if v.status in ("done", "failed")]
    assert len(done_left) == sbm.RerollQueueManager.MAX_COMPLETED_JOBS
    assert "queued_1" in mgr.jobs
    assert "done_0" not in mgr.jobs
    assert f"done_{total_done - 1}" in mgr.jobs
