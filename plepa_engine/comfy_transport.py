"""
plepa_engine.comfy_transport
ComfyUI HTTP REST 및 WebSocket 통신, 업로드 페이로드 생성, WebP 저장 저수준 헬퍼 모듈.
"""

from __future__ import annotations

import io
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


def fetch_node_options(base_url: str, node_class: str, field_name: str) -> List[str]:
    """ComfyUI `/object_info/{node_class}` 엔드포인트에서 선택지 목록을 조회합니다."""
    try:
        url = f"{base_url}/object_info/{node_class}"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw = data.get(node_class, {}).get("input", {}).get("required", {}).get(field_name, [[]])
            if isinstance(raw, list) and raw and isinstance(raw[0], list):
                return sorted(raw[0])
            if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], dict) and "options" in raw[1]:
                return sorted(raw[1]["options"])
    except Exception:
        pass
    return []


def build_image_upload_request(base_url: str, file_path: Path) -> Tuple[urllib.request.Request, str]:
    """ComfyUI `/upload/image` 멀티파트 폼 POST 요청 객체를 조립합니다."""
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
        f"{base_url}/upload/image",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    return req, filename


def parse_prompt_http_error(he: urllib.error.HTTPError) -> str:
    """ComfyUI `/prompt` HTTPError 본문에서 노드 검증 에러 상세 문자열을 추출합니다."""
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
    return err_detail


def open_client_websocket(ws_url: str, client_id: str, timeout_sec: float, ws_mod: Any) -> Any:
    """새 ComfyUI WebSocket 연결을 생성하고 수신 타임아웃을 설정합니다."""
    ws = ws_mod.WebSocket()
    ws.connect(f"{ws_url}?clientId={client_id}", timeout=10.0)
    try:
        ws.settimeout(min(2.0, max(0.2, float(timeout_sec))))
    except Exception:
        pass
    return ws


def poll_history_image(base_url: str, prompt_id: str) -> Optional[Dict[str, Any]]:
    """WebSocket 단절 시 `/history/{prompt_id}` 폴링으로 완료된 출력 이미지 메타데이터를 복구합니다."""
    try:
        hist_url = f"{base_url}/history/{urllib.parse.quote(str(prompt_id))}"
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


def _build_ws_exception_tuples(ws_mod: Any) -> Tuple[Tuple[type, ...], Tuple[type, ...]]:
    timeout_excs: Tuple[type, ...] = (TimeoutError, socket.timeout)
    ws_timeout_cls = getattr(ws_mod, "WebSocketTimeoutException", None)
    if isinstance(ws_timeout_cls, type) and issubclass(ws_timeout_cls, BaseException):
        timeout_excs = timeout_excs + (ws_timeout_cls,)

    closed_excs: Tuple[type, ...] = (ConnectionError, EOFError, OSError)
    ws_closed_cls = getattr(ws_mod, "WebSocketConnectionClosedException", None)
    if isinstance(ws_closed_cls, type) and issubclass(ws_closed_cls, BaseException):
        closed_excs = closed_excs + (ws_closed_cls,)
    return timeout_excs, closed_excs


def _reconnect_ws_after_drop(
    ws: Any,
    ws_url: str,
    client_id: str,
    timeout_sec: float,
    ws_mod: Any,
    is_shared: bool,
    set_shared_ws: Callable[[Any], None],
    error_cls: type[Exception],
) -> Any:
    try:
        try:
            ws.close()
        except Exception:
            pass
        new_ws = ws_mod.WebSocket()
        new_ws.connect(f"{ws_url}?clientId={client_id}", timeout=10.0)
        new_ws.settimeout(min(2.0, max(0.2, float(timeout_sec))))
        if is_shared:
            set_shared_ws(new_ws)
        return new_ws
    except Exception as re_err:
        raise error_cls(f"ComfyUI WebSocket 재연결 실패: {re_err}") from re_err


def _handle_ws_text_event(
    msg: str,
    prompt_id: str,
    progress_cb: Optional[Callable[[int, int, str], None]],
    error_cls: type[Exception],
) -> Optional[Dict[str, Any]]:
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
                return output_data["images"][0]
    elif msg_type == "execution_error":
        if data.get("prompt_id") == prompt_id:
            err_msg = data.get("exception_message", "알 수 없는 에러")
            raise error_cls(f"ComfyUI 실행 에러: {err_msg}")
    return None


def wait_for_generation_result(
    *,
    ws: Any,
    base_url: str,
    ws_url: str,
    client_id: str,
    prompt_id: str,
    timeout_sec: float,
    progress_cb: Optional[Callable[[int, int, str], None]],
    is_shared: bool,
    set_shared_ws: Callable[[Any], None],
    ws_mod: Any,
    error_cls: type[Exception],
) -> Optional[Dict[str, Any]]:
    """WebSocket 이벤트 수신, 타임아웃/단절 재연결 및 `/history` 복구 루프를 수행합니다."""
    start_time = time.time()
    output_image_info: Optional[Dict[str, Any]] = None
    timeout_excs, closed_excs = _build_ws_exception_tuples(ws_mod)
    reconnect_attempts = 0

    try:
        while True:
            if time.time() - start_time > timeout_sec:
                raise error_cls(f"생성 대기 시간 초과 ({timeout_sec}초)")

            try:
                msg = ws.recv()
            except timeout_excs:
                continue
            except closed_excs as ce:
                hist_img = poll_history_image(base_url, prompt_id)
                if hist_img is not None:
                    output_image_info = hist_img
                    break
                reconnect_attempts += 1
                if reconnect_attempts > 2 or time.time() - start_time > timeout_sec:
                    raise error_cls(f"ComfyUI WebSocket 연결이 끊어졌습니다: {ce}") from ce
                ws = _reconnect_ws_after_drop(
                    ws, ws_url, client_id, timeout_sec, ws_mod, is_shared, set_shared_ws, error_cls
                )
                continue

            if isinstance(msg, str):
                result_info = _handle_ws_text_event(msg, prompt_id, progress_cb, error_cls)
                if result_info is not None:
                    output_image_info = result_info
                    break
    finally:
        if not is_shared:
            try:
                ws.close()
            except Exception:
                pass

    return output_image_info


def download_and_save_webp(
    *,
    base_url: str,
    output_image_info: Dict[str, Any],
    output_path: Path,
    pil_image_mod: Any,
    webp_quality: int,
    webp_method: int,
    atomic_replace_fn: Callable[[Path, Path, int], None],
    error_cls: type[Exception],
) -> Path:
    """ComfyUI `/view`에서 이미지 바이너리를 내려받아 임시 파일 경유 원자적으로 WebP 저장합니다."""
    filename = output_image_info["filename"]
    subfolder = output_image_info.get("subfolder", "")
    img_type = output_image_info.get("type", "output")

    query = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": img_type})
    view_url = f"{base_url}/view?{query}"

    try:
        with urllib.request.urlopen(view_url, timeout=60.0) as img_resp:
            img_bytes = img_resp.read()

        image = pil_image_mod.open(io.BytesIO(img_bytes))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Windows 파일 락 및 충돌 방지를 위한 원자적 임시 저장 및 단일 os.replace 교체 (원본 선삭제 금지)
        temp_path = output_path.with_name(f".{output_path.stem}_{uuid.uuid4().hex[:6]}.tmp.webp")
        try:
            image.save(temp_path, "WEBP", quality=webp_quality, method=webp_method)
            atomic_replace_fn(temp_path, output_path, 5)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
    except Exception as se:
        raise error_cls(f"이미지 저장 실패 ({output_path.name}): {se}") from se

    return output_path
