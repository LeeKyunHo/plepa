"""
plepa_gui.api_file_ops
원자적 이미지 교체, 재검열·수동 리터치 저장 및 백그라운드 리롤 큐 등록 비즈니스 로직.
"""

from __future__ import annotations

import base64
import io
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException
from PIL import Image

from plepa_engine.config import DEFAULT_ROSTER
from plepa_engine.services.generation_service import GenerationParams
from plepa_gui.api_schemas import (
    FillMissingRequest,
    ReapplyCensorAssetRequest,
    RerollRequest,
    RetouchAssetRequest,
)
from plepa_gui.api_security import extract_pose_code_from_name


def atomic_copy_file(src: Path, dst: Path) -> None:
    """임시 파일 경유 os.replace로 원본 파일을 원자적으로 복사합니다."""
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


def atomic_save_webp(img: Image.Image, dst: Path) -> None:
    """PIL 이미지를 임시 WEBP 파일로 인코딩 후 원자적으로 교체합니다."""
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


def resolve_qc_flags(conf: Dict[str, Any], auto_qc: Any, strict_censor_qc: Any) -> tuple[bool, bool]:
    """요청 오버라이드 또는 전역 설정에서 Auto-QC / 엄격 검열 QC 플래그를 해석합니다."""
    resolved_auto = bool(conf.get("auto_qc", True)) if auto_qc is None else bool(auto_qc)
    resolved_strict = bool(conf.get("strict_censor_qc", False)) if strict_censor_qc is None else bool(strict_censor_qc)
    return resolved_auto, resolved_strict


def enqueue_reroll_job(req: RerollRequest, safe_roster: str, config_service: Any, job_manager: Any) -> Dict[str, Any]:
    """단일 컷 리롤 요청을 GlobalJobManager FIFO 큐에 등록하고 응답 페이로드를 반환합니다."""
    conf = config_service.get_config()
    auto_qc, strict_censor_qc = resolve_qc_flags(conf, req.auto_qc, req.strict_censor_qc)
    params = GenerationParams(
        character_expr=req.char,
        pose_expr=req.code,
        roster=safe_roster,
        overwrite=True,
        censor=req.censor,
        censor_style=req.censor_style or conf.get("censor_style", "white_silhouette"),
        censor_targets=req.censor_targets or conf.get("censor_targets", "penis"),
        auto_qc=auto_qc,
        strict_censor_qc=strict_censor_qc,
        reuse_seed=req.reuse_seed,
    )
    started, queue_pos = job_manager.enqueue_job(params, label=f"리롤 {req.char}:{req.code}")
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
        "auto_qc": auto_qc,
        "strict_censor_qc": strict_censor_qc,
    }


def enqueue_fill_missing_jobs(
    req: FillMissingRequest,
    safe_roster: str,
    asset_service: Any,
    config_service: Any,
    job_manager: Any,
) -> Dict[str, Any]:
    """누락된 포즈만 선별하여 캐릭터별 작업을 GlobalJobManager FIFO 큐에 등록합니다."""
    conf = config_service.get_config()
    censor_style = req.censor_style or conf.get("censor_style", "white_silhouette")
    censor_targets = req.censor_targets or conf.get("censor_targets", "penis")
    auto_qc, strict_censor_qc = resolve_qc_flags(conf, req.auto_qc, req.strict_censor_qc)
    missing_map = asset_service.get_missing_poses_by_character(safe_roster)

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
            overwrite=False,
            censor=req.censor,
            censor_style=censor_style,
            censor_targets=censor_targets,
            auto_qc=auto_qc,
            strict_censor_qc=strict_censor_qc,
        )
        job_manager.enqueue_job(params, label=f"누락채우기 {char_pfx} ({len(codes)}종)")

    return {
        "success": True,
        "tasks_queued": tasks_queued,
        "jobs_submitted": jobs_submitted,
        "auto_qc": auto_qc,
        "strict_censor_qc": strict_censor_qc,
        "message": f"총 {tasks_queued}개의 누락 포즈 생성이 대기열({jobs_submitted}건)에 안전하게 등록되었습니다.",
    }


def execute_reapply_censor(
    req: ReapplyCensorAssetRequest,
    target_path: Path,
    origin_path: Path,
    projects_dir: Path,
) -> Dict[str, Any]:
    """무검열 원본(_origin)으로부터 즉시 재검열을 수행하고 본체 파일을 원자적으로 교체합니다."""
    from plepa_engine.censor import censor_image

    pose_code = (req.pose_code or "").strip() or extract_pose_code_from_name(target_path.name)
    targets = tuple(t.strip() for t in (req.censor_targets or "penis").split(",") if t.strip()) or ("penis",)

    roster_name = req.roster
    if not roster_name:
        try:
            roster_name = target_path.resolve().relative_to(projects_dir.resolve()).parts[0]
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
    atomic_save_webp(censored_img, target_path)

    return {
        "success": True,
        "rel_path": req.rel_path,
        "censor_style": req.censor_style,
        "detected_count": int(det_count),
        "message": f"{req.censor_style} 즉시 재검열 완료 (탐지 {int(det_count)}건)",
    }


def execute_retouch_asset(req: RetouchAssetRequest, target_path: Path) -> Dict[str, Any]:
    """Base64 수동 캔버스 덧칠 결과를 디코딩하여 본체 WEBP 파일에 원자적으로 덮어씁니다."""
    raw_b64 = (req.image_base64 or "").strip()
    if not raw_b64:
        raise HTTPException(status_code=400, detail="이미지 데이터가 비어 있습니다.")
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        img_bytes = base64.b64decode(raw_b64, validate=False)
        with Image.open(io.BytesIO(img_bytes)) as opened_img:
            img = opened_img.convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 이미지 데이터입니다: {exc}") from exc

    atomic_save_webp(img, target_path)
    return {
        "success": True,
        "rel_path": req.rel_path,
        "filename": target_path.name,
        "timestamp": int(time.time()),
        "message": "수동 검열 저장 및 파일 교체 완료",
    }
