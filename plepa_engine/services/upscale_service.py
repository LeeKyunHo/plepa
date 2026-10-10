"""
plepa_engine.services.upscale_service
완성된 이미지를 AI 초해상화 모델(4x-UltraSharp 등)을 사용하여 4K~6K 초고화질로 단독 업스케일하는 전담 서비스.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image

from plepa_engine.comfy_client import ComfyClient, ComfyClientError
from plepa_engine.config import COMFY_HOST, DEFAULT_UPSCALER
from plepa_engine.workflow_templates import build_standalone_upscale_workflow


class UpscaleService:
    """단독 이미지 4K AI 업스케일러 서비스."""

    def __init__(
        self,
        comfy_host: str = COMFY_HOST,
        upscale_model: str = DEFAULT_UPSCALER,
        client: Optional[ComfyClient] = None,
    ):
        self.comfy_host = comfy_host
        self.upscale_model = upscale_model
        self._client: Optional[ComfyClient] = client

    @property
    def client(self) -> ComfyClient:
        if self._client is None:
            self._client = ComfyClient(host=self.comfy_host)
        return self._client

    def get_image_dimensions(self, path: Path) -> Optional[Tuple[int, int]]:
        """이미지의 (가로, 세로) 픽셀 해상도를 반환합니다. 실패 시 None."""
        try:
            path = Path(path)
            if not path.is_file():
                return None
            with Image.open(path) as img:
                return img.size
        except Exception:
            return None

    def is_already_4k(self, path: Path, min_dim: int = 3000) -> bool:
        """이미지가 이미 4K급(가로 또는 세로 3000px 이상)인지 판별합니다."""
        dims = self.get_image_dimensions(path)
        if not dims:
            return False
        return max(dims[0], dims[1]) >= min_dim

    def upscale_file(
        self,
        file_path: Path,
        output_path: Optional[Path] = None,
        overwrite: bool = False,
        upscale_model: Optional[str] = None,
    ) -> Path:
        """
        단일 이미지 파일을 ComfyUI로 전송하여 4x AI 업스케일링을 수행합니다.
        - overwrite=False이고 output_path 미지정 시: '{stem}_4k.webp'로 저장.
        - overwrite=True이고 output_path 미지정 시: 원본 파일을 덮어씀.
        - 반환값: 최종 저장된 파일 Path.
        """
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"업스케일 대상 파일을 찾을 수 없습니다: {file_path}")

        model_name = upscale_model or self.upscale_model

        if output_path is None:
            if overwrite:
                output_path = file_path
            else:
                output_path = file_path.parent / f"{file_path.stem}_4k.webp"
        else:
            output_path = Path(output_path).resolve()

        dims = self.get_image_dimensions(file_path)
        orig_w, orig_h = dims if dims else (0, 0)

        # 1. ComfyUI 연결 확인
        if not self.client.check_connection():
            raise ComfyClientError(
                f"ComfyUI 서버({self.comfy_host})에 연결할 수 없습니다. "
                "ComfyUI가 실행 중인지 확인해 주십시오."
            )

        # 2. 이미지 임시 업로드
        uploaded_name = self.client.upload_image(file_path)

        # 3. 단독 업스케일 워크플로우 구성
        output_prefix = f"upscale_{file_path.stem}"
        workflow = build_standalone_upscale_workflow(
            image_name=uploaded_name,
            output_prefix=output_prefix,
            upscale_model=model_name,
        )

        # 4. 임시 파일로 수신 후 최종 목적지로 이동/덮어쓰기
        temp_out = output_path.parent / f".tmp_{output_path.name}"
        temp_out.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.client.generate_image(workflow=workflow, output_path=temp_out)
            # 원본 교체 시 안전한 교체
            if output_path.exists():
                output_path.unlink()
            temp_out.replace(output_path)
        except Exception:
            if temp_out.exists():
                temp_out.unlink()
            raise

        new_dims = self.get_image_dimensions(output_path)
        new_w, new_h = new_dims if new_dims else (0, 0)
        return output_path

    def upscale_batch(
        self,
        files: List[Path],
        overwrite: bool = False,
        on_progress: Optional[Callable[[int, int, Path, Optional[str]], None]] = None,
    ) -> List[Path]:
        """
        다수의 이미지 목록을 순차적으로 4K 업스케일링합니다.
        on_progress(현재인덱스, 전체개수, 파일경로, 에러메시지_또는_None) 콜백 지원.
        """
        results: List[Path] = []
        total = len(files)

        for idx, f in enumerate(files, 1):
            try:
                out = self.upscale_file(f, overwrite=overwrite)
                results.append(out)
                if on_progress:
                    on_progress(idx, total, out, None)
            except Exception as e:
                if on_progress:
                    on_progress(idx, total, f, str(e))

        return results


default_upscale_service = UpscaleService()
