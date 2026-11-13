"""
plepa_gui.api_routes
에셋 관리(삭제·휴지통·복원) 및 백그라운드 재생성(단독 리롤, 누락분 일괄 생성) 전용 FastAPI 라우터.
모바일 뷰어와 PC 갤러리 양쪽에서 공용 REST API로 호출됩니다.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from PIL import Image
from pydantic import BaseModel

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.generation_service import GenerationParams
from plepa_engine.services.job_manager import global_job_manager

_SAFE_ROSTER_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_COOKIE_NAME = "plepa_token"


def get_optional_mobile_token() -> str:
    """환경변수 PLEPA_MOBILE_TOKEN 반환 (미설정 시 빈 문자열 — 로컬 무인증 호환)."""
    return os.environ.get("PLEPA_MOBILE_TOKEN", "").strip()


def verify_optional_request_auth(request: Request, *, check_origin: bool = False) -> None:
    """
    PLEPA_MOBILE_TOKEN이 설정된 경우에만 토큰 및 Origin을 검증합니다.
    미설정(로컬 PC 단독 구동·오프라인 단위 테스트) 시에는 즉시 통과합니다.
    """
    expected = get_optional_mobile_token()
    if not expected:
        return

    token = request.headers.get("X-Plepa-Token", "").strip()
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    if not token:
        token = (request.cookies.get(_COOKIE_NAME) or "").strip()
    if not token:
        token = (request.query_params.get("token") or "").strip()

    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="유효하지 않은 모바일 인증 토큰입니다.")

    if check_origin:
        host = (request.headers.get("Host") or "").strip().lower()
        origin = (request.headers.get("Origin") or "").strip()
        if origin:
            origin_host = urlparse(origin).netloc.lower()
            if not host or origin_host != host:
                raise HTTPException(status_code=403, detail="허용되지 않은 Origin 요청입니다.")
        else:
            referer = (request.headers.get("Referer") or "").strip()
            if referer:
                ref_host = urlparse(referer).netloc.lower()
                if not host or ref_host != host:
                    raise HTTPException(status_code=403, detail="허용되지 않은 Referer 요청입니다.")


async def _require_optional_api_auth(request: Request) -> None:
    is_mutating = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
    verify_optional_request_auth(request, check_origin=is_mutating)


api_router = APIRouter(
    prefix="/api/assets",
    tags=["Assets & Generation API"],
    dependencies=[Depends(_require_optional_api_auth)],
)


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
    censor: bool = True
    censor_style: Optional[str] = None
    censor_targets: Optional[str] = None


class FillMissingRequest(BaseModel):
    roster: str = DEFAULT_ROSTER
    char: Optional[str] = None
    censor: bool = True
    censor_style: Optional[str] = None
    censor_targets: Optional[str] = None


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


def _ensure_not_origin_target(target_path: Path) -> None:
    if any(part == "_origin" or part.endswith("_origin") for part in target_path.parts):
        raise HTTPException(status_code=403, detail="무검열 원본(_origin) 경로는 직접 덮어쓸 수 없습니다.")


def _find_project_origin_for_asset(target_path: Path) -> Optional[Path]:
    projects_root = PROJECTS_DIR.resolve()
    resolved_target = target_path.resolve()
    parts = resolved_target.parts
    if "assets" not in parts:
        return None

    assets_idx = parts.index("assets")
    if assets_idx + 1 >= len(parts):
        return None

    assets_base = Path(*parts[: assets_idx + 1])
    sub_parts = parts[assets_idx + 1 :]
    char_code = sub_parts[0]
    rel_in_char = Path(*sub_parts[1:]) if len(sub_parts) > 1 else Path(resolved_target.name)

    for cand in (
        (assets_base / f"{char_code}_origin" / rel_in_char).resolve(),
        (assets_base / char_code / "_origin" / rel_in_char).resolve(),
        (assets_base / f"{char_code}_origin" / resolved_target.name).resolve(),
    ):
        if cand.is_relative_to(projects_root) and cand.is_file():
            return cand
    return None


def _extract_pose_code_from_name(filename: str) -> str:
    m = re.search(r"_([A-Za-z]\d{2,3}|\d{3})(?:_|\.)", filename or "")
    if not m:
        return ""
    raw = m.group(1)
    return raw.zfill(3) if raw.isdigit() else raw.upper()


def _atomic_copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.stem}_", suffix=dst.suffix, dir=str(dst.parent))
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
        shutil.copy2(str(src), str(tmp_path))
        os.replace(str(tmp_path), str(dst))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_save_webp(img: Image.Image, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.stem}_", suffix=".webp", dir=str(dst.parent))
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
        img.save(str(tmp_path), "WEBP", quality=92, method=4)
        os.replace(str(tmp_path), str(dst))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


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
    conf = default_config_service.get_config()
    params = GenerationParams(
        character_expr=req.char,
        pose_expr=req.code,
        roster=safe_roster,
        overwrite=True,
        censor=req.censor,
        censor_style=req.censor_style or conf.get("censor_style", "white_silhouette"),
        censor_targets=req.censor_targets or conf.get("censor_targets", "penis"),
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
    conf = default_config_service.get_config()
    censor_style = req.censor_style or conf.get("censor_style", "white_silhouette")
    censor_targets = req.censor_targets or conf.get("censor_targets", "penis")
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
            censor=req.censor,
            censor_style=censor_style,
            censor_targets=censor_targets,
        )
        global_job_manager.enqueue_job(params, label=f"누락채우기 {char_pfx} ({len(codes)}종)")

    return {
        "success": True,
        "tasks_queued": tasks_queued,
        "jobs_submitted": jobs_submitted,
        "message": f"총 {tasks_queued}개의 누락 포즈 생성이 대기열({jobs_submitted}건)에 안전하게 등록되었습니다.",
    }


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

    from plepa_engine.censor import censor_image

    pose_code = (req.pose_code or "").strip() or _extract_pose_code_from_name(target_path.name)
    targets = tuple(t.strip() for t in (req.censor_targets or "penis").split(",") if t.strip()) or ("penis",)

    roster_name = req.roster
    if not roster_name:
        try:
            roster_name = target_path.resolve().relative_to(PROJECTS_DIR.resolve()).parts[0]
        except Exception:
            roster_name = DEFAULT_ROSTER

    with Image.open(origin_path) as raw_img:
        src_img = raw_img.convert("RGB")

    censored_img, det_count = censor_image(
        src_img,
        style=req.censor_style or "white_silhouette",
        targets=targets,
        min_confidence=req.min_confidence,
        pose_code=pose_code or None,
        enable_anchor_fallback=req.enable_anchor_fallback,
        roster=roster_name,
    )
    _atomic_save_webp(censored_img, target_path)

    return {
        "success": True,
        "rel_path": req.rel_path,
        "censor_style": req.censor_style,
        "detected_count": int(det_count),
        "message": f"{req.censor_style} 즉시 재검열 완료 (탐지 {int(det_count)}건)",
    }
