"""
plepa_engine.comfy_client
ComfyUI 로컬 REST & WebSocket API 비동기 통신 클라이언트.
"""

from __future__ import annotations

import io
import json
import time
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

        with urllib.request.urlopen(view_url, timeout=30.0) as img_resp:
            img_bytes = img_resp.read()

        # PIL 이미지로 변환 후 WebP로 최적화 저장
        image = Image.open(io.BytesIO(img_bytes))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)

        return output_path
