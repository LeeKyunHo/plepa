"""
plepa_gui.api_routes
에셋 관리(삭제·휴지통·복원) 및 백그라운드 재생성(단독 리롤, 누락분 일괄 생성) 전용 FastAPI 라우터.
모바일 뷰어와 PC 갤러리 양쪽에서 공용 REST API로 호출됩니다.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.generation_service import GenerationParams, default_generation_service

api_router = APIRouter(prefix="/api/assets", tags=["Assets & Generation API"])


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
    target_path = PROJECTS_DIR / req.rel_path
    if not target_path.is_file():
        # 혹시 선행 슬래시가 붙어있을 경우 대비
        clean_rel = req.rel_path.lstrip("/\\")
        target_path = PROJECTS_DIR / clean_rel

    if not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"에셋 파일을 찾을 수 없습니다: {req.rel_path}")

    res = default_asset_service.delete_asset_bundle(target_path)
    return {"success": res["success"], "data": res}


@api_router.post("/undo")
async def api_undo_delete(req: UndoAssetRequest) -> Dict[str, Any]:
    """휴지통으로 이동되었던 에셋 번들을 원래 위치로 복원(Undo)."""
    ok = default_asset_service.restore_asset_bundle(req.moved)
    return {"success": ok}


@api_router.get("/missing-summary")
async def api_missing_summary(roster: str = DEFAULT_ROSTER) -> Dict[str, Any]:
    """로스터 내 캐릭터별 누락 포즈 목록 및 총 누락 수 전수 집계."""
    missing_map = default_asset_service.get_missing_poses_by_character(roster)
    total_missing = sum(len(v) for v in missing_map.values())
    return {
        "roster": roster,
        "total_missing": total_missing,
        "by_char": {k: len(v) for k, v in missing_map.items()},
        "details": missing_map,
    }


def _run_background_batch(params: GenerationParams) -> None:
    """백그라운드 스레드에서 안전하게 배치 생성 실행."""
    try:
        default_generation_service.run_batch(params)
    except Exception as ex:
        print(f"[API Background Error] 배치 생성 실패: {ex}")


@api_router.post("/reroll")
async def api_reroll_asset(req: RerollRequest, bg_tasks: BackgroundTasks) -> Dict[str, Any]:
    """단일 컷 백그라운드 리롤(재생성) 트리거."""
    params = GenerationParams(
        character_expr=req.char,
        pose_expr=req.code,
        roster=req.roster,
        overwrite=True,
        censor=True,
        reuse_seed=req.reuse_seed,
    )
    bg_tasks.add_task(_run_background_batch, params)
    return {
        "success": True,
        "message": f"#{req.code} [{req.char}] 리롤 생성이 시작되었습니다.",
        "char": req.char,
        "code": req.code,
    }


@api_router.post("/fill-missing")
async def api_fill_missing(req: FillMissingRequest, bg_tasks: BackgroundTasks) -> Dict[str, Any]:
    """비어있는(누락된) 포즈만 자동 선별하여 백그라운드 일괄 생성."""
    missing_map = default_asset_service.get_missing_poses_by_character(req.roster)

    target_chars = [req.char] if req.char else list(missing_map.keys())
    tasks_queued = 0

    for char_pfx in target_chars:
        codes = missing_map.get(char_pfx, [])
        if not codes:
            continue
        tasks_queued += len(codes)
        params = GenerationParams(
            character_expr=char_pfx,
            pose_expr=",".join(codes),
            roster=req.roster,
            overwrite=False,  # 기존 파일 절대 덮어쓰지 않고 누락된 포즈만 채움
            censor=True,
        )
        bg_tasks.add_task(_run_background_batch, params)

    return {
        "success": True,
        "tasks_queued": tasks_queued,
        "message": f"총 {tasks_queued}개의 누락 포즈 생성이 시작되었습니다.",
    }
