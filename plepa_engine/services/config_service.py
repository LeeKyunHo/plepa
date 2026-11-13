"""
plepa_engine.services.config_service
플에파 전역 설정 로드, 수정, 원자적 저장 및 런타임 갱신 서비스.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from plepa_engine.config import (
    COMFY_HOST,
    DEFAULT_ENGINE,
    DEFAULT_REF_WEIGHT,
    DEFAULT_ROSTER,
    DEFAULT_SDXL_CFG,
    DEFAULT_SDXL_CKPT,
    DEFAULT_SDXL_HEIGHT,
    DEFAULT_SDXL_SAMPLER,
    DEFAULT_SDXL_SCHEDULER,
    DEFAULT_SDXL_STEPS,
    DEFAULT_SDXL_WIDTH,
    ROOT_DIR,
)
from plepa_engine.services.repository import Repository, default_repo

CONFIG_FILE = ROOT_DIR / ".plepa_state" / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "comfy_host": COMFY_HOST,
    "default_engine": DEFAULT_ENGINE,
    "default_roster": DEFAULT_ROSTER,
    # SDXL 설정
    "sdxl_ckpt": DEFAULT_SDXL_CKPT,
    "sdxl_steps": DEFAULT_SDXL_STEPS,
    "sdxl_cfg": DEFAULT_SDXL_CFG,
    "sdxl_sampler": DEFAULT_SDXL_SAMPLER,
    "sdxl_scheduler": DEFAULT_SDXL_SCHEDULER,
    "sdxl_width": DEFAULT_SDXL_WIDTH,
    "sdxl_height": DEFAULT_SDXL_HEIGHT,
    "sdxl_ref_weight": DEFAULT_REF_WEIGHT,
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


default_config_service = ConfigService()
# 모듈 로드 시 런타임 적용
default_config_service._apply_runtime(default_config_service.get_config())
