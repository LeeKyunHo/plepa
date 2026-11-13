"""
tests/test_comfy_and_job_queue.py
H3(삼위일체 기본값 동기화), H4(GlobalJobManager FIFO 직렬화/취소),
H5(ComfyClient 업로드 캐시 무효화 및 WebSocket /history 폴백) 회귀 테스트.
"""

from __future__ import annotations

import io
import json
import os
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from batch_generator import create_parser
from plepa_engine import comfy_client
from plepa_engine import config as cfg
from plepa_engine.models import GenerationResult, GenerationTarget
from plepa_engine.services import config_service, job_manager
from plepa_engine.services.generation_service import GenerationParams


def test_trinity_defaults_and_cli_parser_sync():
    """H3: config_service.DEFAULT_CONFIG 단일 SDXL 기본값, 레거시 키 부재 및 CLI 파서 정합성 검증."""
    dc = config_service.DEFAULT_CONFIG
    assert dc["default_engine"] == "sdxl"
    assert dc["default_roster"] == "default"
    assert dc["sdxl_steps"] == 24
    assert dc["sdxl_cfg"] == 4.0
    assert dc["sdxl_sampler"] == "dpmpp_2m"
    assert dc["sdxl_scheduler"] == "karras"
    assert dc["sdxl_width"] == 832
    assert dc["sdxl_height"] == 1216
    assert dc["sdxl_ref_weight"] == 0.0
    assert dc["comfy_host"] == cfg.COMFY_HOST

    for legacy_key in ("unet_gguf", "steps", "guidance", "lora"):
        assert legacy_key not in dc

    parser = create_parser()
    default_args = parser.parse_args([])
    assert default_args.engine == "sdxl"
    assert default_args.anchor_fallback is False

    fallback_args = parser.parse_args(["--anchor-fallback"])
    assert fallback_args.anchor_fallback is True

    with pytest.raises(SystemExit):
        parser.parse_args(["--engine", "flux"])


def test_global_job_manager_fifo_serialization_and_cancel(monkeypatch):
    """H4: GlobalJobManager FIFO 순차 직렬 실행 및 취소 시 대기열 콜백 정리 검증."""
    mgr = job_manager.GlobalJobManager()
    events = []
    concurrency = {"active": 0, "max": 0}
    lock = threading.Lock()
    job1_started = threading.Event()
    release_job1 = threading.Event()
    all_done = threading.Event()

    class _FakeGenService:
        def run_batch(self, params, on_progress=None, is_cancelled=None, quiet=True):
            with lock:
                concurrency["active"] += 1
                concurrency["max"] = max(concurrency["max"], concurrency["active"])
            events.append(f"start:{params.pose_expr}")
            if params.pose_expr == "001":
                job1_started.set()
                release_job1.wait(timeout=3.0)
            target = GenerationTarget(
                code=params.pose_expr,
                section="poses",
                label="test",
                assembled_prompt="test",
                is_nude=False,
                output_filename="out.webp",
                character_prefix=params.character_expr,
            )
            res = GenerationResult(target=target, success=True)
            if on_progress:
                on_progress(1, 1, res)
            events.append(f"end:{params.pose_expr}")
            with lock:
                concurrency["active"] -= 1
            return [res]

    monkeypatch.setattr(
        job_manager,
        "default_generation_service",
        _FakeGenService(),
    )

    cb_results = []
    started1, qpos1 = mgr.enqueue_job(
        GenerationParams(character_expr="aya", pose_expr="001"),
        label="job1",
        on_complete=lambda res_list, err: cb_results.append(("job1", bool(res_list), err)),
    )
    assert started1 is True
    assert qpos1 == 0
    assert job1_started.wait(timeout=2.0)

    started2, qpos2 = mgr.enqueue_job(
        GenerationParams(character_expr="aya", pose_expr="002"),
        label="job2",
        on_complete=lambda res_list, err: (cb_results.append(("job2", bool(res_list), err)), all_done.set()),
    )
    assert started2 is False
    assert qpos2 == 1
    assert mgr.get_status()["queue_length"] == 1

    release_job1.set()
    assert all_done.wait(timeout=3.0)

    # 스레드 종료 정리 대기
    deadline = time.time() + 2.0
    while mgr.get_status()["is_running"] and time.time() < deadline:
        time.sleep(0.02)

    assert concurrency["max"] == 1
    assert events == ["start:001", "end:001", "start:002", "end:002"]
    assert cb_results == [("job1", True, None), ("job2", True, None)]

    # 취소 시 대기 중인 큐 작업 콜백도 오류와 함께 해제되는지 검증
    job_c_started = threading.Event()
    release_c = threading.Event()
    queued_err = []
    queued_done = threading.Event()

    class _BlockingGenService:
        def run_batch(self, params, on_progress=None, is_cancelled=None, quiet=True):
            job_c_started.set()
            release_c.wait(timeout=2.0)
            return []

    monkeypatch.setattr(
        job_manager,
        "default_generation_service",
        _BlockingGenService(),
    )
    mgr2 = job_manager.GlobalJobManager()
    mgr2.enqueue_job(GenerationParams(character_expr="aya", pose_expr="010"), label="c1")
    assert job_c_started.wait(timeout=2.0)
    mgr2.enqueue_job(
        GenerationParams(character_expr="aya", pose_expr="011"),
        label="c2",
        on_complete=lambda res_list, err: (queued_err.append((res_list, err)), queued_done.set()),
    )
    mgr2.cancel_job()
    release_c.set()
    assert queued_done.wait(timeout=2.0)
    assert queued_err[0][0] == [] and queued_err[0][1] is not None


def test_comfy_upload_cache_invalidation_and_history_fallback(monkeypatch, tmp_path):
    """H5: ComfyClient.upload_image의 mtime/size 캐시 무효화 및 WebSocket 단절 시 /history 폴백 복구 검증."""
    ref_img = tmp_path / "ref.webp"
    Image.new("RGB", (8, 8), (50, 100, 150)).save(ref_img, "WEBP")

    upload_posts = []

    class _FakeResp:
        def __init__(self, payload: bytes, status: int = 200):
            self._payload = payload
            self.status = status

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    webp_buf = io.BytesIO()
    Image.new("RGB", (12, 12), (200, 100, 50)).save(webp_buf, "WEBP")
    view_bytes = webp_buf.getvalue()

    def _fake_urlopen(req, timeout=10.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/system_stats"):
            return _FakeResp(b"{}", status=200)
        if url.endswith("/upload/image"):
            upload_posts.append(url)
            return _FakeResp(json.dumps({"name": f"remote_{len(upload_posts)}.webp"}).encode("utf-8"))
        if url.endswith("/prompt"):
            return _FakeResp(json.dumps({"prompt_id": "pid-999"}).encode("utf-8"))
        if "/history/pid-999" in url:
            hist = {
                "pid-999": {
                    "outputs": {
                        "9": {"images": [{"filename": "done.webp", "subfolder": "", "type": "output"}]}
                    }
                }
            }
            return _FakeResp(json.dumps(hist).encode("utf-8"))
        if "/view?" in url:
            return _FakeResp(view_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    with comfy_client._IMAGE_UPLOAD_CACHE_LOCK:
        saved_cache = dict(comfy_client._IMAGE_UPLOAD_CACHE)
        comfy_client._IMAGE_UPLOAD_CACHE.clear()
    try:
        client = comfy_client.ComfyClient(host="127.0.0.1:8199")
        first = client.upload_image(ref_img)
        second = client.upload_image(ref_img)
        assert first == second
        assert len(upload_posts) == 1

        # 파일 크기 및 수정시각 변경 -> 캐시 무효화되어 재업로드 수행
        Image.new("RGB", (32, 32), (240, 20, 20)).save(ref_img, "WEBP")
        st = ref_img.stat()
        os.utime(ref_img, ns=(st.st_atime_ns + 1_000_000_000, st.st_mtime_ns + 1_000_000_000))
        third = client.upload_image(ref_img)
        assert third != first
        assert len(upload_posts) == 2
    finally:
        with comfy_client._IMAGE_UPLOAD_CACHE_LOCK:
            comfy_client._IMAGE_UPLOAD_CACHE.clear()
            comfy_client._IMAGE_UPLOAD_CACHE.update(saved_cache)

    # WebSocket 단절 시 /history/{prompt_id} 조회를 통해 정상 저장 복구되는지 검증
    fake_ws = MagicMock()
    fake_ws.recv.side_effect = ConnectionError("socket dropped after completion")
    monkeypatch.setattr(comfy_client, "websocket", SimpleNamespace(WebSocket=lambda: fake_ws))

    out_path = tmp_path / "generated" / "aya_001.webp"
    saved_path = client.generate_image(workflow={"1": {}}, output_path=out_path, timeout_sec=5.0)
    assert saved_path == out_path
    assert out_path.is_file()
    with Image.open(out_path) as loaded:
        assert loaded.size == (12, 12)
