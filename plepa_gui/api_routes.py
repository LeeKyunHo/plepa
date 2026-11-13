"""
plepa_gui.api_routes
에셋 관리(삭제·휴지통·복원) 및 백그라운드 재생성(단독 리롤, 누락분 일괄 생성) 전용 FastAPI 라우터.
모바일 뷰어와 PC 갤러리 양쪽에서 공용 REST API로 호출됩니다.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.generation_service import GenerationParams
from plepa_engine.services.job_manager import global_job_manager

api_router = APIRouter(prefix="/api/assets", tags=["Assets & Generation API"])
_SAFE_ROSTER_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_roster_name(roster: str) -> str:
    clean = (roster or "").strip()
    if not clean or not _SAFE_ROSTER_PATTERN.match(clean):
        raise HTTPException(status_code=400, detail=f"유효하지 않은 로스터 이름입니다: {roster!r}")
    return clean


def _resolve_safe_project_file(rel_path: str) -> Path:
    projects_root = PROJECTS_DIR.resolve()
    clean_rel = (rel_path or "").strip().lstrip("/\\")
    if not clean_rel:
        raise HTTPException(status_code=400, detail="유효하지 않은 경로입니다.")
    candidate = (projects_root / clean_rel).resolve()
    try:
        is_inside = candidate.is_relative_to(projects_root)
    except AttributeError:
        is_inside = projects_root in candidate.parents
    if not is_inside or candidate == projects_root:
        raise HTTPException(status_code=400, detail="허용되지 않은 경로 접근입니다.")
    return candidate


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


class FillMissingRequest(BaseModel):
    roster: str = DEFAULT_ROSTER
    char: Optional[str] = None


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
    params = GenerationParams(
        character_expr=req.char,
        pose_expr=req.code,
        roster=safe_roster,
        overwrite=True,
        censor=True,
        reuse_seed=req.reuse_seed,
    )
    started, queue_pos = global_job_manager.enqueue_job(params, label=f"리롤 {req.char}:{req.code}")
    msg = (
        f"#{req.code} [{req.char}] 리롤 생성이 시작되었습니다."
        if started
        else f"#{req.code} [{req.char}] 리롤이 대기열 #{queue_pos}에 등록되었습니다."
    )
    return {
        "success": True,
        "queued": not started,
        "queue_position": queue_pos,
        "message": msg,
        "char": req.char,
        "code": req.code,
    }


@api_router.post("/fill-missing")
async def api_fill_missing(req: FillMissingRequest) -> Dict[str, Any]:
    """비어있는(누락된) 포즈만 자동 선별하여 GlobalJobManager FIFO 대기열에 직렬 등록."""
    safe_roster = _validate_roster_name(req.roster)
    missing_map = default_asset_service.get_missing_poses_by_character(safe_roster)

    target_chars = [req.char] if req.char else list(missing_map.keys())
    tasks_queued = 0
    jobs_submitted = 0

    for char_pfx in target_chars:
        codes = missing_map.get(char_pfx, [])
        if not codes:
            continue
        tasks_queued += len(codes)
        jobs_submitted += 1
        params = GenerationParams(
            character_expr=char_pfx,
            pose_expr=",".join(codes),
            roster=safe_roster,
            overwrite=False,  # 기존 파일 절대 덮어쓰지 않고 누락된 포즈만 채움
            censor=True,
        )
        global_job_manager.enqueue_job(params, label=f"누락채우기 {char_pfx} ({len(codes)}종)")

    return {
        "success": True,
        "tasks_queued": tasks_queued,
        "jobs_submitted": jobs_submitted,
        "message": f"총 {tasks_queued}개의 누락 포즈 생성이 대기열({jobs_submitted}건)에 안전하게 등록되었습니다.",
    }
