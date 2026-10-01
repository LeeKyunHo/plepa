"""
plepa_engine.comfy_client
ComfyUI 로컬 REST & WebSocket API 비동기 통신 클라이언트.
"""

from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

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


class ComfyClientError(Exception):
    """ComfyUI 통신 관련 예외 클래스."""
    pass


class ComfyClient:
    def __init__(self, host: str = COMFY_HOST):
        self.host = host
        self.base_url = f"http://{host}"
        self.ws_url = f"ws://{host}/ws"
        self.client_id = uuid.uuid4().hex

    def check_connection(self) -> bool:
        """ComfyUI 서버 가동 여부를 확인합니다."""
        try:
            req = urllib.request.Request(f"{self.base_url}/system_stats")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def upload_image(self, file_path: Path, overwrite: bool = True) -> str:
        """
        로컬 이미지 파일을 ComfyUI input 디렉토리로 업로드합니다.
        반환값: ComfyUI 내부에서 참조할 파일명
        """
        if not file_path.exists():
            raise FileNotFoundError(f"업로드할 레퍼런스 이미지를 찾을 수 없습니다: {file_path}")

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
                return result.get("name", filename)
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
        """
        if websocket is None or Image is None:
            raise ComfyClientError(
                "필수 라이브러리(websocket-client, Pillow)가 누락되었습니다.\n"
                "'pip install -r requirements.txt'를 먼저 실행해 주십시오."
            )

        if not self.check_connection():
            raise ComfyClientError(
                f"ComfyUI 서버({self.base_url})에 연결할 수 없습니다.\n"
                f"'run_nvidia_gpu.bat'가 실행 중인지 확인해 주십시오."
            )

        ws = websocket.WebSocket()
        ws.connect(f"{self.ws_url}?clientId={self.client_id}")

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
            ws.close()
            raise ComfyClientError(f"작업 큐 등록 실패: {e}") from e

        if not prompt_id:
            ws.close()
            raise ComfyClientError("ComfyUI로부터 prompt_id를 수신하지 못했습니다.")

        # 2. WebSocket 이벤트 루프
        start_time = time.time()
        output_image_info: Optional[Dict[str, Any]] = None

        try:
            while True:
                if time.time() - start_time > timeout_sec:
                    raise ComfyClientError(f"생성 대기 시간 초과 ({timeout_sec}초)")

                msg = ws.recv()
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
            ws.close()

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

            # Windows 파일 락 및 충돌 방지를 위한 원자적 임시 저장 및 교체 (Atomic Save)
            temp_path = output_path.with_name(f"{output_path.stem}_{uuid.uuid4().hex[:6]}.tmp.webp")
            image.save(temp_path, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)

            # 재시도 루프를 통한 안전한 파일 교체
            last_err = None
            for _ in range(5):
                try:
                    if output_path.exists():
                        try:
                            output_path.unlink()
                        except Exception:
                            pass
                    temp_path.replace(output_path)
                    last_err = None
                    break
                except OSError as oe:
                    last_err = oe
                    time.sleep(0.3)

            if last_err is not None:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise last_err

        except Exception as se:
            raise ComfyClientError(f"이미지 저장 실패 ({output_path.name}): {se}") from se

        return output_path
