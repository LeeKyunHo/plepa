"""
plepa_gui.api_schemas
모바일 뷰어 및 PC 갤러리 공용 REST API Pydantic 요청 스키마 정의.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel

from plepa_engine.config import DEFAULT_ROSTER


class DeleteAssetRequest(BaseModel):
    rel_path: str
    roster: str = DEFAULT_ROSTER


class UndoAssetRequest(BaseModel):
    moved: List[Dict[str, str]]


class RerollRequest(BaseModel):
    char: str
    code: str
    roster: str = DEFAULT_ROSTER
    reuse_seed: bool = False
    censor: bool = True
    censor_style: Optional[str] = None
    censor_targets: Optional[str] = None
    auto_qc: Optional[bool] = None
    strict_censor_qc: Optional[bool] = None


class FillMissingRequest(BaseModel):
    roster: str = DEFAULT_ROSTER
    char: Optional[str] = None
    censor: bool = True
    censor_style: Optional[str] = None
    censor_targets: Optional[str] = None
    auto_qc: Optional[bool] = None
    strict_censor_qc: Optional[bool] = None


class RestoreOriginAssetRequest(BaseModel):
    rel_path: str
    roster: Optional[str] = None


class ReapplyCensorAssetRequest(BaseModel):
    rel_path: str
    censor_style: str = "white_silhouette"
    censor_targets: str = "penis"
    min_confidence: float = 0.16
    enable_anchor_fallback: bool = False
    pose_code: Optional[str] = None
    roster: Optional[str] = None


class RetouchAssetRequest(BaseModel):
    rel_path: str
    image_base64: str
    roster: Optional[str] = None
