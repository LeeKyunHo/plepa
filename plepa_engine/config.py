"""
plepa_engine.config
플에파 전용 기본 설정 및 환경 변수 처리 모듈.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── 기본 경로 (상대 경로 기준 자동 산출) ──
ROOT_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT_DIR / "projects"
DEFAULT_ROSTER = "default"
POSE_DB_PATH = ROOT_DIR / "flux_pose_database.json"

# ── ComfyUI 통신 설정 ──
COMFY_HOST = os.environ.get("COMFYUI_HOST", "127.0.0.1:8188")
COMFY_URL = f"http://{COMFY_HOST}"
COMFY_WS_URL = f"ws://{COMFY_HOST}/ws"

# ── 플럭스 모델 기본 식별자 ──
DEFAULT_UNET_GGUF = os.environ.get("PLEPA_UNET", "flux1-dev-Q6_K.gguf")
DEFAULT_CLIP_1 = os.environ.get("PLEPA_CLIP1", "t5xxl_fp8_e4m3fn.safetensors")
DEFAULT_CLIP_2 = os.environ.get("PLEPA_CLIP2", "clip_l.safetensors")
DEFAULT_VAE = os.environ.get("PLEPA_VAE", "ae.safetensors")
DEFAULT_UPSCALER = os.environ.get("PLEPA_UPSCALER", "4x-UltraSharp.pth")
DEFAULT_BBOX_DETECTOR = "bbox/face_yolov8m.pt"

# ── 플럭스 샘플링 파라미터 (FLUX.1 [dev] 표준) ──
DEFAULT_STEPS = 20
DEFAULT_GUIDANCE = 3.5
DEFAULT_SAMPLER = "euler"
DEFAULT_SCHEDULER = "simple"
DEFAULT_WIDTH = 896
DEFAULT_HEIGHT = 1152

# ── 웹포맷(WebP) 저장 품질 ──
WEBP_QUALITY = 95
WEBP_METHOD = 6

# ── 기본 엔진 (sdxl: 고속 2D 애니 체크포인트 [기본값], flux: FLUX.1 [dev] GGUF) ──
DEFAULT_ENGINE = os.environ.get("PLEPA_DEFAULT_ENGINE", "sdxl")

# ── SDXL (Unholy Desire Mix Sinister v9.0 등) 기본 식별자 및 파라미터 ──
DEFAULT_SDXL_CKPT = os.environ.get("PLEPA_SDXL_CKPT", "unholyDesireMixSinister_v90.safetensors")
DEFAULT_SDXL_STEPS = 30
DEFAULT_SDXL_CFG = 5.0
DEFAULT_SDXL_SAMPLER = "dpmpp_2m"
DEFAULT_SDXL_SCHEDULER = "karras"
DEFAULT_SDXL_WIDTH = 832
DEFAULT_SDXL_HEIGHT = 1216
DEFAULT_CLIP_SKIP = 2
DEFAULT_REF_WEIGHT = 0.5
SDXL_POSE_DB_PATH = ROOT_DIR / "sdxl_pose_database.json"
FLUX_POSE_DB_PATH = ROOT_DIR / "flux_pose_database.json"


def configure_stdio() -> None:
    """윈도우 콘솔 환경에서 유니코드 출력(cp949 에러) 방지."""
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

