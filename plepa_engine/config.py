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
DATA_DIR = ROOT_DIR / "data"
THEMES_DIR = DATA_DIR / "themes"
DOCS_DIR = ROOT_DIR / "docs"
SCRIPTS_DIR = ROOT_DIR / "scripts"
DEFAULT_ROSTER = "default"
POSE_SETS_PATH = DATA_DIR / "pose_sets.json"
LEGACY_DATA_DIR = DATA_DIR / "legacy"
SDXL_POSE_DB_PATH = DATA_DIR / "sdxl_pose_database.json"
FLUX_POSE_DB_PATH = LEGACY_DATA_DIR / "flux_pose_database.json"  # [레거시 격리]
POSE_DB_PATH = SDXL_POSE_DB_PATH  # 시스템 공식 기본 포즈 DB (SDXL 표준 단일화)

# ── ComfyUI 통신 설정 ──
COMFY_HOST = os.environ.get("COMFYUI_HOST", "127.0.0.1:8188")
COMFY_URL = f"http://{COMFY_HOST}"
COMFY_WS_URL = f"ws://{COMFY_HOST}/ws"

# ── SDXL 메인 엔진 기본 식별자 및 파라미터 (ADR 4, ADR 19 확정) ──
DEFAULT_ENGINE = os.environ.get("PLEPA_DEFAULT_ENGINE", "sdxl")
DEFAULT_SDXL_CKPT = os.environ.get("PLEPA_SDXL_CKPT", "unholyDesireMixSinister_v90.safetensors")
DEFAULT_SDXL_STEPS = 24
DEFAULT_SDXL_CFG = 5.0
DEFAULT_SDXL_SAMPLER = "dpmpp_2m"
DEFAULT_SDXL_SCHEDULER = "karras"
DEFAULT_SDXL_WIDTH = 832
DEFAULT_SDXL_HEIGHT = 1216
DEFAULT_CLIP_SKIP = 2
DEFAULT_REF_WEIGHT = 0.0

# ── 웹포맷(WebP) 저장 품질 ──
WEBP_QUALITY = 95
WEBP_METHOD = 4

# ── 공용 후처리 모델 (Face Detailer & Upscaler) ──
DEFAULT_UPSCALER = os.environ.get("PLEPA_UPSCALER", "4x-UltraSharp.pth")
DEFAULT_BBOX_DETECTOR = "bbox/face_yolov8m.pt"

# ── [레거시] FLUX.1 [dev] 모델 파라미터 (plepa_engine.legacy 패키지 참조) ──
DEFAULT_UNET_GGUF = os.environ.get("PLEPA_UNET", "flux1-dev-Q6_K.gguf")
DEFAULT_CLIP_1 = os.environ.get("PLEPA_CLIP1", "t5xxl_fp8_e4m3fn.safetensors")
DEFAULT_CLIP_2 = os.environ.get("PLEPA_CLIP2", "clip_l.safetensors")
DEFAULT_VAE = os.environ.get("PLEPA_VAE", "ae.safetensors")
DEFAULT_STEPS = 20
DEFAULT_GUIDANCE = 3.5
DEFAULT_SAMPLER = "euler"
DEFAULT_SCHEDULER = "simple"
DEFAULT_WIDTH = 896
DEFAULT_HEIGHT = 1152


# ── default_mode 맵핑 (키로 roster.py 이식) ──
_DEFAULT_MODE_MAP = {
    "sdxl": "sdxl",
    "flux": "flux",
    "fast": "sdxl",
    "quality": "flux",
    "q": "flux",
    "f": "sdxl",
}

def resolve_default_mode(raw_mode: str | None) -> str:
    """
    캐릭터 JSON default_mode 필드를 정규화.
    - None → DEFAULT_ENGINE 반환
    - 유효한 별칭 → "sdxl" 또는 "flux" 반환
    - 그 외 → ValueError
    """
    if raw_mode is None:
        return DEFAULT_ENGINE
    
    normalized = str(raw_mode).strip().lower()
    if not normalized:
        return DEFAULT_ENGINE
    
    if normalized in _DEFAULT_MODE_MAP:
        return _DEFAULT_MODE_MAP[normalized]
    
    valid_keys = ", ".join(sorted(_DEFAULT_MODE_MAP.keys()))
    raise ValueError(
        f"Invalid default_mode '{raw_mode}'. "
        f"Valid options: {valid_keys}"
    )


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

