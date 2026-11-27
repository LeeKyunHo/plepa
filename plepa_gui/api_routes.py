"""
plepa_gui.api_routes
에셋 관리(삭제·휴지통·복원) 및 백그라운드 재생성(단독 리롤, 누락분 일괄 생성) 전용 FastAPI 라우터.
모바일 뷰어와 PC 갤러리 양쪽에서 공용 REST API로 호출됩니다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.job_manager import global_job_manager
from plepa_gui.api_file_ops import (
    atomic_copy_file as _atomic_copy_file,
    atomic_save_webp as _atomic_save_webp,
    enqueue_fill_missing_jobs,
    enqueue_reroll_job,
    execute_reapply_censor,
    execute_retouch_asset,
)
from plepa_gui.api_schemas import (
    DeleteAssetRequest,
    FillMissingRequest,
    ReapplyCensorAssetRequest,
    RerollRequest,
    RestoreOriginAssetRequest,
    RetouchAssetRequest,
    UndoAssetRequest,
)
from plepa_gui.api_security import (
    _COOKIE_NAME,
    _SAFE_ROSTER_PATTERN,
    ensure_not_origin_target as _ensure_not_origin_target,
    extract_pose_code_from_name as _extract_pose_code_from_name,
    find_project_origin_for_asset,
    get_optional_mobile_token,
    require_optional_api_auth as _require_optional_api_auth,
    resolve_safe_project_file,
    validate_roster_name as _validate_roster_name,
    verify_optional_request_auth,
)


def _resolve_safe_project_file(rel_path: str) -> Path:
    return resolve_safe_project_file(rel_path, projects_dir=PROJECTS_DIR)


def _find_project_origin_for_asset(target_path: Path) -> Optional[Path]:
    return find_project_origin_for_asset(target_path, projects_dir=PROJECTS_DIR)


api_router = APIRouter(
    prefix="/api/assets",
    tags=["Assets & Generation API"],
    dependencies=[Depends(_require_optional_api_auth)],
)


@api_router.get("/job-status")
async def api_job_status() -> Dict[str, Any]:
    """전역 백그라운드 리롤/배치 대기열 및 최근 완료 기록을 반환합니다."""
    return global_job_manager.get_status()


@api_router.post("/delete")
async def api_delete_asset(req: DeleteAssetRequest) -> Dict[str, Any]:
    """에셋 및 쌍둥이 파일(_origin, _censored)을 휴지통으로 안전하게 이동."""
    target_path = _resolve_safe_project_file(req.rel_path)
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"에셋 파일을 찾을 수 없습니다: {req.rel_path}")
    res = default_asset_service.delete_asset_bundle(target_path)
    return {"success": res["success"], "data": res}


@api_router.post("/undo")
async def api_undo_delete(req: UndoAssetRequest) -> Dict[str, Any]:
    """휴지통으로 이동되었던 에셋 번들을 원래 위치로 복원(Undo)."""
    ok = default_asset_service.restore_asset_bundle(req.moved)
    if not ok and req.moved:
        raise HTTPException(status_code=400, detail="복원할 수 없는 경로 또는 존재하지 않는 파일입니다.")
    return {"success": ok}


@api_router.get("/missing-summary")
async def api_missing_summary(roster: str = DEFAULT_ROSTER) -> Dict[str, Any]:
    """로스터 내 캐릭터별 누락 포즈 목록 및 총 누락 수 전수 집계."""
    safe_roster = _validate_roster_name(roster)
    missing_map = default_asset_service.get_missing_poses_by_character(safe_roster)
    total_missing = sum(len(v) for v in missing_map.values())
    return {
        "roster": safe_roster,
        "total_missing": total_missing,
        "by_char": {k: len(v) for k, v in missing_map.items()},
        "details": missing_map,
    }


@api_router.post("/reroll")
async def api_reroll_asset(req: RerollRequest) -> Dict[str, Any]:
    """단일 컷 백그라운드 리롤(재생성) - GlobalJobManager FIFO 대기열 직렬화."""
    safe_roster = _validate_roster_name(req.roster)
    return enqueue_reroll_job(req, safe_roster, default_config_service, global_job_manager)


@api_router.post("/fill-missing")
async def api_fill_missing(req: FillMissingRequest) -> Dict[str, Any]:
    """비어있는(누락된) 포즈만 자동 선별하여 GlobalJobManager FIFO 대기열에 직렬 등록."""
    safe_roster = _validate_roster_name(req.roster)
    return enqueue_fill_missing_jobs(req, safe_roster, default_asset_service, default_config_service, global_job_manager)


@api_router.post("/restore-origin")
async def api_restore_origin(req: RestoreOriginAssetRequest) -> Dict[str, Any]:
    """매핑되는 무검열 원본(_origin) 이미지로 본체 에셋을 원자적으로 복원합니다."""
    if req.roster:
        _validate_roster_name(req.roster)
    target_path = _resolve_safe_project_file(req.rel_path)
    _ensure_not_origin_target(target_path)

    origin_path = _find_project_origin_for_asset(target_path)
    if origin_path is None:
        raise HTTPException(status_code=404, detail=f"원본(_origin) 파일을 찾을 수 없습니다: {req.rel_path}")

    _atomic_copy_file(origin_path, target_path)
    return {
        "success": True,
        "rel_path": req.rel_path,
        "origin_path": str(origin_path),
        "message": "오리지널 원본 이미지로 복원 완료",
    }


@api_router.post("/reapply-censor")
async def api_reapply_censor(req: ReapplyCensorAssetRequest) -> Dict[str, Any]:
    """ComfyUI 재생성 없이 무검열 원본(_origin)으로부터 0.2초 만에 재검열하여 저장합니다."""
    if req.roster:
        _validate_roster_name(req.roster)
    target_path = _resolve_safe_project_file(req.rel_path)
    _ensure_not_origin_target(target_path)

    origin_path = _find_project_origin_for_asset(target_path)
    if origin_path is None:
        raise HTTPException(status_code=404, detail=f"원본(_origin) 파일을 찾을 수 없습니다: {req.rel_path}")

    return execute_reapply_censor(req, target_path, origin_path, PROJECTS_DIR)


@api_router.post("/retouch")
async def api_retouch_asset(req: RetouchAssetRequest) -> Dict[str, Any]:
    """수동 캔버스 덧칠/검열 결과를 본체 에셋 파일에 원자적으로 덮어씁니다 (_origin 무손실 보존)."""
    if req.roster:
        _validate_roster_name(req.roster)
    target_path = _resolve_safe_project_file(req.rel_path)
    _ensure_not_origin_target(target_path)
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"에셋 파일을 찾을 수 없습니다: {req.rel_path}")
    return execute_retouch_asset(req, target_path)


__all__ = [
    "DeleteAssetRequest",
    "FillMissingRequest",
    "ReapplyCensorAssetRequest",
    "RerollRequest",
    "RestoreOriginAssetRequest",
    "RetouchAssetRequest",
    "UndoAssetRequest",
    "_COOKIE_NAME",
    "_SAFE_ROSTER_PATTERN",
    "_atomic_copy_file",
    "_atomic_save_webp",
    "_ensure_not_origin_target",
    "_extract_pose_code_from_name",
    "_find_project_origin_for_asset",
    "_require_optional_api_auth",
    "_resolve_safe_project_file",
    "_validate_roster_name",
    "api_router",
    "get_optional_mobile_token",
    "verify_optional_request_auth",
]
