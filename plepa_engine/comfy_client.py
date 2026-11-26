"""
plepa_engine.comfy_client
ComfyUI 로컬 REST & WebSocket API 비동기 통신 클라이언트.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
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

from plepa_engine.comfy_transport import (
    build_image_upload_request,
    download_and_save_webp,
    fetch_node_options,
    open_client_websocket,
    parse_prompt_http_error,
    wait_for_generation_result,
)
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

        result["checkpoints"] = fetch_node_options(self.base_url, "CheckpointLoaderSimple", "ckpt_name")
        result["unets"] = fetch_node_options(self.base_url, "UnetLoaderGGUF", "unet_name")
        result["vaes"] = fetch_node_options(self.base_url, "VAELoader", "vae_name")
        result["upscalers"] = fetch_node_options(self.base_url, "UpscaleModelLoader", "model_name")
        return result

    def get_registered_node_names(self) -> set[str]:
        """ComfyUI 서버에 등록된 전체 노드 클래스명 집합을 조회합니다."""
        if not self.check_connection():
            return set()
        try:
            req = urllib.request.Request(f"{self.base_url}/object_info")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return set(data.keys())
        except Exception:
            return set()

    def check_missing_custom_nodes(
        self, required_nodes: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        필수 커스텀 노드가 ComfyUI 서버에 실제로 등록되어 있는지 검증합니다.
        누락된 노드가 있을 경우 {노드클래스명: 확장팩이름} 딕셔너리를 반환합니다.
        서버 미가동이거나 모두 등록되어 있으면 빈 딕셔너리를 반환합니다.
        """
        if required_nodes is None:
            from plepa_engine.workflow_templates import REQUIRED_CUSTOM_NODES
            required_nodes = REQUIRED_CUSTOM_NODES

        if not self.check_connection():
            return {}

        registered = self.get_registered_node_names()
        if not registered:
            return {}

        return {
            node_name: pack_name
            for node_name, pack_name in required_nodes.items()
            if node_name not in registered
        }

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

        req, filename = build_image_upload_request(self.base_url, file_path)
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                remote_name = result.get("name", filename)
                with _IMAGE_UPLOAD_CACHE_LOCK:
                    _IMAGE_UPLOAD_CACHE[cache_key] = (mtime_ns, file_size, remote_name)
                return remote_name
        except Exception as e:
            raise ComfyClientError(f"ComfyUI 이미지 업로드 실패: {e}") from e

    def _submit_workflow(self, workflow: Dict[str, Any], ws: Any, is_shared: bool) -> str:
        payload = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                prompt_id = result.get("prompt_id")
        except urllib.error.HTTPError as he:
            if not is_shared:
                ws.close()
            err_detail = parse_prompt_http_error(he)
            raise ComfyClientError(f"작업 큐 등록 실패 (HTTP {he.code}: {he.reason}){err_detail}") from he
        except Exception as e:
            if not is_shared:
                ws.close()
            raise ComfyClientError(f"작업 큐 등록 실패: {e}") from e

        if not prompt_id:
            if not is_shared:
                ws.close()
            raise ComfyClientError("ComfyUI로부터 prompt_id를 수신하지 못했습니다.")
        return prompt_id

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
            try:
                ws.settimeout(min(2.0, max(0.2, float(timeout_sec))))
            except Exception:
                pass
        else:
            if not self.check_connection():
                raise ComfyClientError(
                    f"ComfyUI 서버({self.base_url})에 연결할 수 없습니다.\n"
                    f"'run_nvidia_gpu.bat'가 실행 중인지 확인해 주십시오."
                )
            ws = open_client_websocket(self.ws_url, self.client_id, timeout_sec, websocket)

        prompt_id = self._submit_workflow(workflow, ws, is_shared)
        output_image_info = wait_for_generation_result(
            ws=ws,
            base_url=self.base_url,
            ws_url=self.ws_url,
            client_id=self.client_id,
            prompt_id=prompt_id,
            timeout_sec=timeout_sec,
            progress_cb=progress_cb,
            is_shared=is_shared,
            set_shared_ws=lambda new_ws: setattr(self, "_shared_ws", new_ws),
            ws_mod=websocket,
            error_cls=ComfyClientError,
        )
        if not output_image_info:
            raise ComfyClientError("생성된 이미지 정보를 수신하지 못했습니다.")

        return download_and_save_webp(
            base_url=self.base_url,
            output_image_info=output_image_info,
            output_path=output_path,
            pil_image_mod=Image,
            webp_quality=WEBP_QUALITY,
            webp_method=WEBP_METHOD,
            atomic_replace_fn=_atomic_replace_with_retry,
            error_cls=ComfyClientError,
        )


def verify_required_nodes(
    host: str = COMFY_HOST,
    required_nodes: Optional[Dict[str, str]] = None,
) -> Tuple[bool, Dict[str, str]]:
    """
    ComfyUI 서버에 필수 커스텀 노드가 모두 등록되어 있는지 확인하는 경량 헬퍼 함수.
    반환값: (모두_존재_여부, 누락된_노드_딕셔너리)
    - ComfyUI 미가동 시: (False, {"SERVER_UNREACHABLE": f"ComfyUI 서버({host}) 미가동"})
    - 노드 누락 시: (False, {노드명: 확장팩명})
    - 정상 구동 시: (True, {})
    """
    client = ComfyClient(host=host)
    if not client.check_connection():
        return False, {"SERVER_UNREACHABLE": f"ComfyUI 서버({host})에 연결할 수 없습니다."}

    missing = client.check_missing_custom_nodes(required_nodes=required_nodes)
    if missing:
        return False, missing
    return True, {}
