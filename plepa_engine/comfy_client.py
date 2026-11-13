"""
plepa_engine.comfy_client
ComfyUI 로컬 REST & WebSocket API 비동기 통신 클라이언트.
"""

from __future__ import annotations

import io
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import websocket
except ImportError:
    websocket = None

from plepa_engine.config import (
    COMFY_HOST,
    COMFY_URL,
    COMFY_WS_URL,
    WEBP_METHOD,
    WEBP_QUALITY,
)

# 프로세스 전역 레퍼런스 이미지 업로드 캐시: {(base_url, str(file_path)): (mtime_ns, size, remote_filename)}
_IMAGE_UPLOAD_CACHE: Dict[Tuple[str, str], Tuple[int, int, str]] = {}
_IMAGE_UPLOAD_CACHE_LOCK = threading.Lock()


def _atomic_replace_with_retry(src_tmp: Path, dst_path: Path, retries: int = 5) -> None:
    """원본 선삭제 없이 단일 os.replace로 원자적 파일 교체를 수행합니다."""
    last_err: Optional[OSError] = None
    for attempt in range(retries):
        try:
            os.replace(src_tmp, dst_path)
            return
        except OSError as oe:
            last_err = oe
            if attempt < retries - 1:
                time.sleep(0.25 * (attempt + 1))
    if last_err is not None:
        raise last_err


class ComfyClientError(Exception):
    """ComfyUI 통신 관련 예외 클래스."""
    pass


class ComfyClient:
    def __init__(self, host: str = COMFY_HOST):
        self.host = host
        self.base_url = f"http://{host}"
        self.ws_url = f"ws://{host}/ws"
        self.client_id = uuid.uuid4().hex
        self._shared_ws: Optional[Any] = None

    @contextmanager
    def session(self):
        """
        대규모 배치 생성을 위한 WebSocket 세션 재사용 컨텍스트 매니저.
        배치 루프 시작 시 1회만 WebSocket을 연결하고, 블록 종료 시 안전하게 닫습니다.
        """
        if websocket is None:
            raise ComfyClientError("websocket-client 라이브러리가 필요합니다.")

        if not self.check_connection():
            raise ComfyClientError(
                f"ComfyUI 서버({self.base_url})에 연결할 수 없습니다.\n"
                f"'run_nvidia_gpu.bat'가 실행 중인지 확인해 주십시오."
            )

        ws = websocket.WebSocket()
        ws.connect(f"{self.ws_url}?clientId={self.client_id}", timeout=10.0)
        try:
            ws.settimeout(2.0)
        except Exception:
            pass
        self._shared_ws = ws
        try:
            yield self
        finally:
            active_ws = self._shared_ws or ws
            try:
                active_ws.close()
            except Exception:
                pass
            self._shared_ws = None


    def check_connection(self) -> bool:
        """ComfyUI 서버 가동 여부를 확인합니다."""
        try:
            req = urllib.request.Request(f"{self.base_url}/system_stats")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_available_models(self) -> Dict[str, List[str]]:
        """
        ComfyUI에 로드 가능한 모델 목록(체크포인트, GGUF UNet, 업스케일러, VAE 등)을 조회합니다.
        서버 미가동 시 빈 딕셔너리를 반환합니다.
        """
        result: Dict[str, List[str]] = {
            "checkpoints": [],
            "unets": [],
            "upscalers": [],
            "vaes": [],
        }
        if not self.check_connection():
            return result

        def fetch_node_options(node_class: str, field_name: str) -> List[str]:
            try:
                url = f"{self.base_url}/object_info/{node_class}"
                with urllib.request.urlopen(url, timeout=3.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    raw = data.get(node_class, {}).get("input", {}).get("required", {}).get(field_name, [[]])
                    if isinstance(raw, list) and raw and isinstance(raw[0], list):
                        return sorted(raw[0])
                    elif isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], dict) and "options" in raw[1]:
                        return sorted(raw[1]["options"])
            except Exception:
                pass
            return []

        result["checkpoints"] = fetch_node_options("CheckpointLoaderSimple", "ckpt_name")
        result["unets"] = fetch_node_options("UnetLoaderGGUF", "unet_name")
        result["vaes"] = fetch_node_options("VAELoader", "vae_name")
        result["upscalers"] = fetch_node_options("UpscaleModelLoader", "model_name")
        return result

    def upload_image(self, file_path: Path, overwrite: bool = True) -> str:
        """
        로컬 이미지 파일을 ComfyUI input 디렉토리로 업로드합니다.
        mtime 캐싱을 적용하여 동일한 파일의 반복 업로드(I/O 및 네트워크)를 생략합니다.
        반환값: ComfyUI 내부에서 참조할 파일명
        """
        if not file_path.exists():
            raise FileNotFoundError(f"업로드할 레퍼런스 이미지를 찾을 수 없습니다: {file_path}")

        file_path_resolved = file_path.resolve()
        cache_key = (self.base_url, str(file_path_resolved))
        st = file_path_resolved.stat()
        mtime_ns = st.st_mtime_ns
        file_size = st.st_size

        # 스레드 안전 캐시 조회: 동일 서버/파일/수정시각/크기일 때만 업로드 생략
        with _IMAGE_UPLOAD_CACHE_LOCK:
            cached = _IMAGE_UPLOAD_CACHE.get(cache_key)
            if cached is not None:
                cached_mtime_ns, cached_size, cached_name = cached
                if cached_mtime_ns == mtime_ns and cached_size == file_size:
                    return cached_name

        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
        filename = file_path.name
        content_type = "image/png" if file_path.suffix.lower() == ".png" else "image/webp"

        body = bytearray()
        # image 파트
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_path.read_bytes())
        body.extend(b"\r\n")

        # overwrite 파트
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="overwrite"\r\n\r\n')
        body.extend(b"true\r\n")

        # 닫는 바운더리
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                remote_name = result.get("name", filename)
                with _IMAGE_UPLOAD_CACHE_LOCK:
                    _IMAGE_UPLOAD_CACHE[cache_key] = (mtime_ns, file_size, remote_name)
                return remote_name
        except Exception as e:
            raise ComfyClientError(f"ComfyUI 이미지 업로드 실패: {e}") from e

    def generate_image(
        self,
        workflow: Dict[str, Any],
        output_path: Path,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        timeout_sec: float = 600.0,
    ) -> Path:
        """
        워크플로우를 전송하고 생성이 완료될 때까지 WebSocket으로 대기한 후 WebP 파일로 저장합니다.
        session() 컨텍스트 매니저 활성화 시 WebSocket 연결을 재사용합니다.
        """
        if websocket is None or Image is None:
            raise ComfyClientError(
                "필수 라이브러리(websocket-client, Pillow)가 누락되었습니다.\n"
                "'pip install -r requirements.txt'를 먼저 실행해 주십시오."
            )

        is_shared = self._shared_ws is not None
        if is_shared:
            ws = self._shared_ws
        else:
            if not self.check_connection():
                raise ComfyClientError(
                    f"ComfyUI 서버({self.base_url})에 연결할 수 없습니다.\n"
                    f"'run_nvidia_gpu.bat'가 실행 중인지 확인해 주십시오."
                )
            ws = websocket.WebSocket()
            ws.connect(f"{self.ws_url}?clientId={self.client_id}", timeout=10.0)

        try:
            ws.settimeout(min(2.0, max(0.2, float(timeout_sec))))
        except Exception:
            pass

        # 1. 작업 전송
        payload = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                prompt_id = result.get("prompt_id")
        except urllib.error.HTTPError as he:
            if not is_shared:
                ws.close()
            err_detail = ""
            try:
                err_data = json.loads(he.read().decode("utf-8"))
                node_errors = err_data.get("node_errors", {})
                if node_errors:
                    err_lines = []
                    for nid, nval in node_errors.items():
                        c_type = nval.get("class_type", nid)
                        msgs = [err.get("message", "") + ": " + err.get("details", "") for err in nval.get("errors", [])]
                        err_lines.append(f"[{c_type}#{nid}] {'; '.join(msgs)}")
                    err_detail = " -> " + " | ".join(err_lines)
                elif "error" in err_data:
                    err_detail = f" -> {err_data['error'].get('message', '')}"
            except Exception:
                pass
            raise ComfyClientError(f"작업 큐 등록 실패 (HTTP {he.code}: {he.reason}){err_detail}") from he
        except Exception as e:
            if not is_shared:
                ws.close()
            raise ComfyClientError(f"작업 큐 등록 실패: {e}") from e

        if not prompt_id:
            if not is_shared:
                ws.close()
            raise ComfyClientError("ComfyUI로부터 prompt_id를 수신하지 못했습니다.")


        # 2. WebSocket 이벤트 루프 (타임아웃 및 재연결 복구 지원)
        start_time = time.time()
        output_image_info: Optional[Dict[str, Any]] = None
        timeout_excs = (TimeoutError, socket.timeout)
        ws_timeout_cls = getattr(websocket, "WebSocketTimeoutException", None)
        if isinstance(ws_timeout_cls, type) and issubclass(ws_timeout_cls, BaseException):
            timeout_excs = timeout_excs + (ws_timeout_cls,)

        closed_excs: Tuple[type, ...] = (ConnectionError, EOFError, OSError)
        ws_closed_cls = getattr(websocket, "WebSocketConnectionClosedException", None)
        if isinstance(ws_closed_cls, type) and issubclass(ws_closed_cls, BaseException):
            closed_excs = closed_excs + (ws_closed_cls,)

        def _poll_history_image() -> Optional[Dict[str, Any]]:
            try:
                hist_url = f"{self.base_url}/history/{urllib.parse.quote(str(prompt_id))}"
                with urllib.request.urlopen(hist_url, timeout=5.0) as hresp:
                    hist = json.loads(hresp.read().decode("utf-8"))
                entry = hist.get(prompt_id) if isinstance(hist, dict) else None
                if isinstance(entry, dict):
                    for node_out in (entry.get("outputs") or {}).values():
                        imgs = node_out.get("images") if isinstance(node_out, dict) else None
                        if imgs:
                            return imgs[0]
            except Exception:
                pass
            return None

        reconnect_attempts = 0
        try:
            while True:
                if time.time() - start_time > timeout_sec:
                    raise ComfyClientError(f"생성 대기 시간 초과 ({timeout_sec}초)")

                try:
                    msg = ws.recv()
                except timeout_excs:
                    continue
                except closed_excs as ce:
                    hist_img = _poll_history_image()
                    if hist_img is not None:
                        output_image_info = hist_img
                        break
                    reconnect_attempts += 1
                    if reconnect_attempts > 2 or time.time() - start_time > timeout_sec:
                        raise ComfyClientError(f"ComfyUI WebSocket 연결이 끊어졌습니다: {ce}") from ce
                    try:
                        try:
                            ws.close()
                        except Exception:
                            pass
                        ws = websocket.WebSocket()
                        ws.connect(f"{self.ws_url}?clientId={self.client_id}", timeout=10.0)
                        ws.settimeout(min(2.0, max(0.2, float(timeout_sec))))
                        if is_shared:
                            self._shared_ws = ws
                        continue
                    except Exception as re_err:
                        raise ComfyClientError(f"ComfyUI WebSocket 재연결 실패: {re_err}") from re_err

                if isinstance(msg, str):
                    event = json.loads(msg)
                    msg_type = event.get("type")
                    data = event.get("data", {})

                    if msg_type == "progress" and progress_cb:
                        val = data.get("value", 0)
                        max_val = data.get("max", 0)
                        node = data.get("node", "")
                        progress_cb(val, max_val, node)

                    elif msg_type == "executed":
                        if data.get("prompt_id") == prompt_id:
                            output_data = data.get("output", {})
                            if "images" in output_data and output_data["images"]:
                                output_image_info = output_data["images"][0]
                                break

                    elif msg_type == "execution_error":
                        if data.get("prompt_id") == prompt_id:
                            err_msg = data.get("exception_message", "알 수 없는 에러")
                            raise ComfyClientError(f"ComfyUI 실행 에러: {err_msg}")
        finally:
            if not is_shared:
                try:
                    ws.close()
                except Exception:
                    pass


        if not output_image_info:
            raise ComfyClientError("생성된 이미지 정보를 수신하지 못했습니다.")

        # 3. 이미지 바이너리 다운로드 및 WebP 저장
        filename = output_image_info["filename"]
        subfolder = output_image_info.get("subfolder", "")
        img_type = output_image_info.get("type", "output")

        query = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": img_type})
        view_url = f"{self.base_url}/view?{query}"

        try:
            with urllib.request.urlopen(view_url, timeout=60.0) as img_resp:
                img_bytes = img_resp.read()

            image = Image.open(io.BytesIO(img_bytes))
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Windows 파일 락 및 충돌 방지를 위한 원자적 임시 저장 및 단일 os.replace 교체 (원본 선삭제 금지)
            temp_path = output_path.with_name(f".{output_path.stem}_{uuid.uuid4().hex[:6]}.tmp.webp")
            try:
                image.save(temp_path, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
                _atomic_replace_with_retry(temp_path, output_path, retries=5)
            finally:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)

        except Exception as se:
            raise ComfyClientError(f"이미지 저장 실패 ({output_path.name}): {se}") from se

        return output_path
