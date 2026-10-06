"""
plepa_engine.services.config_service
플에파 전역 설정 로드, 수정, 원자적 저장 및 런타임 갱신 서비스.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from plepa_engine.config import ROOT_DIR
from plepa_engine.services.repository import Repository, default_repo

CONFIG_FILE = ROOT_DIR / ".plepa_state" / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "comfy_host": "127.0.0.1:8188",
    "default_engine": "sdxl",
    "default_roster": "don",
    # SDXL 설정
    "sdxl_ckpt": "unholyDesireMixSinister_v90.safetensors",
    "sdxl_steps": 28,
    "sdxl_cfg": 6.5,
    "sdxl_sampler": "dpmpp_sde",
    "sdxl_scheduler": "karras",
    "sdxl_width": 832,
    "sdxl_height": 1216,
    "sdxl_ref_weight": 0.5,
    # FLUX 설정
    "flux_unet": "flux1-dev-Q6_K.gguf",
    "flux_steps": 20,
    "flux_guidance": 3.5,
    "flux_sampler": "euler",
    "flux_scheduler": "simple",
    "flux_width": 896,
    "flux_height": 1152,
    "flux_lora": "modern-anime-lora.safetensors",
    "flux_lora_weight": 0.9,
    # 업스케일러 및 보정
    "upscaler": "4x-UltraSharp.pth",
}


class ConfigService:
    """설정 저장소 관리자."""

    def __init__(self, repo: Repository = default_repo):
        self.repo = repo
        self._ensure_config_exists()

    def _ensure_config_exists(self) -> None:
        """설정 파일이 없으면 기본값으로 초기 생성."""
        if not CONFIG_FILE.exists():
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.repo.write_json(CONFIG_FILE, DEFAULT_CONFIG)

    def get_config(self) -> Dict[str, Any]:
        """현재 저장된 설정 딕셔너리를 반환합니다."""
        try:
            saved = self.repo.read_json(CONFIG_FILE)
            merged = dict(DEFAULT_CONFIG)
            merged.update(saved)
            return merged
        except Exception:
            return dict(DEFAULT_CONFIG)

    def save_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """설정을 업데이트하고 원자적으로 저장합니다."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        current = self.get_config()
        current.update(new_config)
        self.repo.write_json(CONFIG_FILE, current)
        self._apply_runtime(current)
        return current

    def _apply_runtime(self, conf: Dict[str, Any]) -> None:
        """config.py의 전역 런타임 변수에 즉시 반영."""
        import plepa_engine.config as cfg
        if "comfy_host" in conf:
            cfg.COMFY_HOST = conf["comfy_host"]
            cfg.COMFY_URL = f"http://{conf['comfy_host']}"
            cfg.COMFY_WS_URL = f"ws://{conf['comfy_host']}/ws"
        if "default_roster" in conf:
            cfg.DEFAULT_ROSTER = conf["default_roster"]
        if "default_engine" in conf:
            cfg.DEFAULT_ENGINE = conf["default_engine"]
        if "sdxl_ckpt" in conf:
            cfg.DEFAULT_SDXL_CKPT = conf["sdxl_ckpt"]
        if "sdxl_steps" in conf:
            cfg.DEFAULT_SDXL_STEPS = int(conf["sdxl_steps"])
        if "sdxl_cfg" in conf:
            cfg.DEFAULT_SDXL_CFG = float(conf["sdxl_cfg"])
        if "sdxl_sampler" in conf:
            cfg.DEFAULT_SDXL_SAMPLER = conf["sdxl_sampler"]
        if "sdxl_scheduler" in conf:
            cfg.DEFAULT_SDXL_SCHEDULER = conf["sdxl_scheduler"]
        if "sdxl_width" in conf:
            cfg.DEFAULT_SDXL_WIDTH = int(conf["sdxl_width"])
        if "sdxl_height" in conf:
            cfg.DEFAULT_SDXL_HEIGHT = int(conf["sdxl_height"])
        if "flux_unet" in conf:
            cfg.DEFAULT_UNET_GGUF = conf["flux_unet"]


default_config_service = ConfigService()
# 모듈 로드 시 런타임 적용
default_config_service._apply_runtime(default_config_service.get_config())
