"""
plepa_engine.checkpoint_service
체크포인트 프로필 매칭 및 최적 파라미터 제공 서비스.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from plepa_engine.config import ROOT_DIR


@dataclass
class CheckpointProfile:
    """체크포인트 최적 설정 프로필"""
    name: str
    engine: str
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    clip_skip: int = 2
    baked_vae: bool = False
    recommended_upscaler: str = "4x-UltraSharp.pth"
    hires_steps: int = 20
    hires_denoise: float = 0.35
    quality_positive: str = ""
    quality_negative: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    recommended_settings: Dict[str, any] = field(default_factory=dict)
    match_patterns: List[str] = field(default_factory=list)


class CheckpointService:
    """체크포인트 프로필 관리 서비스"""
    
    _instance: Optional['CheckpointService'] = None
    _profiles: Dict[str, CheckpointProfile] = {}
    _default_sdxl: Optional[CheckpointProfile] = None
    _default_flux: Optional[CheckpointProfile] = None
    _loaded: bool = False
    
    def __new__(cls):
        """싱글톤 패턴 (앱 전역에서 한 번만 로드)"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """프로필 로드 (최초 1회만 실행)"""
        if not self._loaded:
            self._load_profiles()
            self._loaded = True
    
    def _load_profiles(self):
        """checkpoint_profiles.json 로드"""
        profile_path = ROOT_DIR / "plepa_engine" / "checkpoint_profiles.json"
        
        if not profile_path.exists():
            raise FileNotFoundError(
                f"체크포인트 프로필 파일을 찾을 수 없습니다: {profile_path}\n"
                f"plepa_engine/checkpoint_profiles.json 파일이 필요합니다."
            )
        
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 각 프로필 파싱
        profiles_data = data.get("profiles", {})
        for ckpt_filename, profile_dict in profiles_data.items():
            profile = self._dict_to_profile(profile_dict)
            self._profiles[ckpt_filename] = profile
        
        # 기본 프로필 로드
        if "default_sdxl" in data:
            self._default_sdxl = self._dict_to_profile(data["default_sdxl"])
        if "default_flux" in data:
            self._default_flux = self._dict_to_profile(data["default_flux"])
    
    @staticmethod
    def _dict_to_profile(profile_dict: Dict) -> CheckpointProfile:
        """딕셔너리를 CheckpointProfile 객체로 변환"""
        return CheckpointProfile(
            name=profile_dict.get("name", "Unknown"),
            engine=profile_dict.get("engine", "sdxl"),
            width=profile_dict.get("width", 832),
            height=profile_dict.get("height", 1216),
            steps=profile_dict.get("steps", 25),
            cfg=profile_dict.get("cfg", 6.5),
            sampler=profile_dict.get("sampler", "dpmpp_sde"),
            scheduler=profile_dict.get("scheduler", "karras"),
            clip_skip=profile_dict.get("clip_skip", 2),
            baked_vae=profile_dict.get("baked_vae", False),
            recommended_upscaler=profile_dict.get("recommended_upscaler", "4x-UltraSharp.pth"),
            hires_steps=profile_dict.get("hires_steps", 20),
            hires_denoise=profile_dict.get("hires_denoise", 0.35),
            quality_positive=profile_dict.get("quality_positive", ""),
            quality_negative=profile_dict.get("quality_negative", ""),
            description=profile_dict.get("description", ""),
            tags=profile_dict.get("tags", []),
            recommended_settings=profile_dict.get("recommended_settings", {}),
            match_patterns=profile_dict.get("match_patterns", [])
        )
    
    def get_profile_for_checkpoint(self, ckpt_name: str, engine: str = "sdxl") -> CheckpointProfile:
        """
        체크포인트 파일명에 맞는 프로필 반환
        
        Args:
            ckpt_name: 체크포인트 파일명 (예: "waiIllustriousSDXL_v170.safetensors")
            engine: "sdxl" 또는 "flux"
        
        Returns:
            CheckpointProfile: 매칭된 프로필 또는 기본 프로필
        
        Examples:
            >>> service = CheckpointService()
            >>> profile = service.get_profile_for_checkpoint("waiIllustriousSDXL_v170.safetensors")
            >>> print(f"{profile.name}: {profile.width}x{profile.height}")
            WAI-Illustrious-SDXL v17: 1024x1344
        """
        if not ckpt_name:
            return self._get_default_profile(engine)
        
        # 1. 완전 일치 (파일명 정확히 동일)
        if ckpt_name in self._profiles:
            return self._profiles[ckpt_name]
        
        # 2. 패턴 매칭 (부분 문자열 검색)
        ckpt_lower = ckpt_name.lower()
        for profile in self._profiles.values():
            for pattern in profile.match_patterns:
                if pattern.lower() in ckpt_lower:
                    return profile
        
        # 3. 파일명 부분 매칭 (등록된 키의 일부가 포함된 경우)
        for registered_name, profile in self._profiles.items():
            # 확장자 제거하고 비교
            registered_base = registered_name.replace(".safetensors", "").lower()
            ckpt_base = ckpt_name.replace(".safetensors", "").replace(".ckpt", "").lower()
            
            if registered_base in ckpt_base or ckpt_base in registered_base:
                return profile
        
        # 4. 매칭 실패 → 기본 프로필
        return self._get_default_profile(engine)
    
    def _get_default_profile(self, engine: str) -> CheckpointProfile:
        """기본 프로필 반환"""
        if engine == "flux" and self._default_flux:
            return self._default_flux
        if self._default_sdxl:
            return self._default_sdxl
        
        # 최악의 폴백 (JSON 로드 실패 시)
        return CheckpointProfile(
            name="Fallback SDXL",
            engine="sdxl",
            width=832,
            height=1216,
            steps=25,
            cfg=6.5,
            sampler="dpmpp_sde",
            scheduler="karras"
        )
    
    def list_all_profiles(self) -> List[CheckpointProfile]:
        """등록된 모든 프로필 목록 반환"""
        return list(self._profiles.values())
    
    def get_profile_by_name(self, name: str) -> Optional[CheckpointProfile]:
        """프로필 이름으로 검색"""
        for profile in self._profiles.values():
            if profile.name.lower() == name.lower():
                return profile
        return None
    
    def search_profiles(self, query: str) -> List[CheckpointProfile]:
        """
        프로필 검색 (이름, 태그, 설명에서 검색)
        
        Args:
            query: 검색어
        
        Returns:
            매칭된 프로필 리스트
        """
        results = []
        query_lower = query.lower()
        
        for profile in self._profiles.values():
            if (query_lower in profile.name.lower() or
                query_lower in profile.description.lower() or
                any(query_lower in tag.lower() for tag in profile.tags)):
                results.append(profile)
        
        return results
    
    def get_recommended_settings_summary(self, ckpt_name: str, engine: str = "sdxl") -> str:
        """
        체크포인트의 권장 설정 요약 문자열 생성 (GUI 표시용)
        
        Args:
            ckpt_name: 체크포인트 파일명
            engine: 엔진 타입
        
        Returns:
            요약 문자열 (예: "CFG 6.0 | 25스텝 | 1024x1344 | Euler a")
        """
        profile = self.get_profile_for_checkpoint(ckpt_name, engine)
        return (
            f"CFG {profile.cfg} | "
            f"{profile.steps}스텝 | "
            f"{profile.width}x{profile.height} | "
            f"{profile.sampler}"
        )
    
    def apply_profile_to_options(
        self,
        options: Dict,
        ckpt_name: str,
        engine: str = "sdxl",
        override_user_values: bool = False
    ) -> Dict:
        """
        GenerationOptions 딕셔너리에 프로필 적용
        
        Args:
            options: 현재 설정 딕셔너리
            ckpt_name: 체크포인트 파일명
            engine: 엔진 타입
            override_user_values: True면 사용자 값도 덮어쓰기, False면 None/기본값만 교체
        
        Returns:
            프로필 적용된 옵션 딕셔너리
        """
        profile = self.get_profile_for_checkpoint(ckpt_name, engine)
        
        # 기본값 정의 (이 값들이면 프로필 값으로 교체)
        default_values = {
            "width": 832,
            "height": 1216,
            "steps": 25,
            "cfg": 6.5,
            "sampler": "dpmpp_sde",
            "scheduler": "karras"
        }
        
        for key, profile_value in {
            "width": profile.width,
            "height": profile.height,
            "steps": profile.steps,
            "cfg": profile.cfg,
            "sampler": profile.sampler,
            "scheduler": profile.scheduler
        }.items():
            current_value = options.get(key)
            
            if override_user_values:
                # 무조건 덮어쓰기
                options[key] = profile_value
            elif current_value is None or current_value == default_values.get(key):
                # 기본값이거나 None이면 프로필 값 적용
                options[key] = profile_value
        
        return options


# 전역 서비스 인스턴스 (앱 전역에서 import하여 사용)
checkpoint_service = CheckpointService()


def get_profile_for_checkpoint(ckpt_name: str, engine: str = "sdxl") -> CheckpointProfile:
    """헬퍼 함수: 전역 서비스 인스턴스 사용"""
    return checkpoint_service.get_profile_for_checkpoint(ckpt_name, engine)


def get_recommended_summary(ckpt_name: str, engine: str = "sdxl") -> str:
    """헬퍼 함수: 권장 설정 요약"""
    return checkpoint_service.get_recommended_settings_summary(ckpt_name, engine)
