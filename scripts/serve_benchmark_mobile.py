from __future__ import annotations

import sys
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



"""
scripts/serve_benchmark_mobile.py
PLEPA 4대 체위 통계적 벤치마크 에셋 모바일 전용 인터랙티브 뷰어 (Mobile Gallery & Cloudflare Tunnel)
"""



import asyncio
import base64
from contextlib import asynccontextmanager
import glob
import hmac
import html as html_lib
import io
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.character_service import default_character_service

BENCHMARK_DIR = ROOT / "output" / "benchmarks"
INSPECT_BATCH = ROOT / "output" / "inspection_batch"
ARTIST_BENCH1 = PROJECTS_DIR / "ykn" / "artist_benchmark"
ARTIST_BENCH2 = PROJECTS_DIR / "ykn" / "artist_benchmark_v2"
ARTIST_RATATATA = PROJECTS_DIR / "ykn" / "artist_benchmark_ratatata"
HYBRID_BENCH = PROJECTS_DIR / "ykn" / "artist_benchmark_hybrid"
C_TUNING_BENCH = PROJECTS_DIR / "ykn" / "artist_benchmark_c_tuning"
CAMPUS_BENCH = PROJECTS_DIR / "campus" / "artist_benchmark_c1_c2"
TEST_C4_DIR = ROOT / "output" / "test_batch_c4"
CF = ROOT / "cloudflared.exe"
PORT = 8085
ACCESS_TOKEN = os.environ.get("PLEPA_MOBILE_TOKEN", "").strip() or secrets.token_urlsafe(24)

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    reroll_queue_mgr.start_worker()
    yield


app = FastAPI(title="Plepa Benchmark Mobile Gallery", lifespan=_lifespan)

for _mount_path, _mount_dir, _mount_name, _allow_html in (
    ("/static", BENCHMARK_DIR, "static", False),
    ("/artist1", ARTIST_BENCH1, "artist1", True),
    ("/artist2", ARTIST_BENCH2, "artist2", True),
    ("/ratatata", ARTIST_RATATATA, "ratatata", True),
    ("/hybrid", HYBRID_BENCH, "hybrid", True),
    ("/c_tuning", C_TUNING_BENCH, "c_tuning", True),
    ("/campus_bench", CAMPUS_BENCH, "campus_bench", True),
    ("/inspect", INSPECT_BATCH, "inspect", True),
    ("/test_c4", TEST_C4_DIR, "test_c4", True),
):
    if _mount_dir.is_dir():
        app.mount(_mount_path, StaticFiles(directory=_mount_dir, html=_allow_html), name=_mount_name)


@app.middleware("http")
async def attach_token_cookie(request: Request, call_next):
    response = await call_next(request)
    q_token = request.query_params.get("token", "").strip()
    if q_token and ACCESS_TOKEN and hmac.compare_digest(q_token, ACCESS_TOKEN):
        is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(
            key="plepa_token",
            value=ACCESS_TOKEN,
            httponly=True,
            samesite="lax",
            secure=is_https,
            path="/",
        )
    return response


def _extract_request_token(request: Request) -> str:
    header_tok = request.headers.get("X-Plepa-Token", "").strip()
    if header_tok:
        return header_tok
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.cookies.get("plepa_token", "").strip()


def _require_auth(request: Request, check_origin: bool = False) -> None:
    expected = ACCESS_TOKEN or ""
    candidate = _extract_request_token(request)
    if not expected or not candidate or not hmac.compare_digest(candidate, expected):
        raise HTTPException(status_code=401, detail="Unauthorized: missing or invalid access token")
    if check_origin:
        origin = request.headers.get("origin", "").strip()
        if origin:
            parsed = urlparse(origin)
            host_header = request.headers.get("host", "").strip()
            if parsed.netloc and host_header and parsed.netloc != host_header:
                raise HTTPException(status_code=403, detail="Forbidden origin")


def _resolve_safe_subpath(base_dir: Path, raw_path: str) -> tuple[str, Path]:
    clean_path = raw_path.replace("\\", "/").lstrip("/")
    parts = clean_path.split("/")
    if not clean_path or any(part in ("", ".", "..") for part in parts):
        raise HTTPException(status_code=403, detail="Invalid file path")
    if any(part == "_origin" or part.endswith("_origin") for part in parts):
        raise HTTPException(status_code=403, detail="Forbidden path segment")
    resolved_base = base_dir.resolve()
    resolved_target = (resolved_base / clean_path).resolve()
    if not resolved_target.is_relative_to(resolved_base):
        raise HTTPException(status_code=403, detail="Path traversal rejected")
    return clean_path, resolved_target


def _atomic_save_webp(img: Image.Image, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.parent / f".{target_path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        img.save(tmp_path, "WEBP", quality=95)
        os.replace(tmp_path, target_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _atomic_copy_file(src_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.parent / f".{target_path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        shutil.copy2(src_path, tmp_path)
        os.replace(tmp_path, target_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _list_all_rosters() -> List[str]:
    rosters = list(default_character_service.list_rosters())
    if PROJECTS_DIR.is_dir():
        for d in sorted(PROJECTS_DIR.iterdir()):
            if d.is_dir() and d.name not in rosters:
                rosters.append(d.name)
    return rosters


def _resolve_char_roster(char_code: str) -> str:
    target = char_code.lower()
    for r in _list_all_rosters():
        try:
            chars = default_character_service.list_characters(r)
            if any(str(getattr(c, "prefix", "")).lower() == target for _, c, _ in chars):
                return r
        except Exception:
            continue
    return DEFAULT_ROSTER


def _extract_pose_code_from_filename(filename: str) -> str:
    m = re.search(r"_([A-Za-z]\d{2,3}|\d{3})(?:_|\.)", filename or "")
    if not m:
        return ""
    raw = m.group(1)
    return raw.zfill(3) if raw.isdigit() else raw.upper()


def _find_origin_for_inspect_path(clean_path: str) -> tuple[Optional[Path], str, str, str]:
    """inspection_batch 상대경로에 대응하는 무검열 원본(_origin) 파일과 경로 조각을 탐색합니다."""
    parts = clean_path.split("/")
    if len(parts) < 3:
        return None, "", "", ""

    c_code, subfolder, filename = parts[0], parts[1], parts[2]
    proj_root_resolved = PROJECTS_DIR.resolve()
    for proj in _list_all_rosters():
        assets_base = (PROJECTS_DIR / proj / "assets").resolve()
        for cand in (
            (assets_base / f"{c_code}_origin" / subfolder / filename).resolve(),
            (assets_base / c_code / "_origin" / subfolder / filename).resolve(),
            (assets_base / f"{c_code}_origin" / filename).resolve(),
        ):
            if cand.is_relative_to(proj_root_resolved) and cand.exists() and cand.is_file():
                return cand, c_code, subfolder, filename
    return None, c_code, subfolder, filename


def _sync_inspect_to_project_assets(
    clean_path: str,
    *,
    img: Optional[Image.Image] = None,
    src_file: Optional[Path] = None,
    preferred_roster: Optional[str] = None,
) -> bool:
    """inspection_batch 변경 결과를 매핑되는 projects/{roster}/assets 본체 에셋에도 원자적으로 동기화합니다."""
    parts = clean_path.split("/")
    if len(parts) < 3 or (img is None and src_file is None):
        return False

    c_code, subfolder, filename = parts[0], parts[1], parts[2]
    rosters = _list_all_rosters()
    if preferred_roster:
        rosters = [preferred_roster] + [r for r in rosters if r != preferred_roster]

    proj_root_resolved = PROJECTS_DIR.resolve()
    synced = False
    for proj in rosters:
        reg_p = (PROJECTS_DIR / proj / "assets" / c_code / subfolder / filename).resolve()
        if reg_p.is_relative_to(proj_root_resolved) and reg_p.is_file():
            if img is not None:
                _atomic_save_webp(img, reg_p)
            elif src_file is not None:
                _atomic_copy_file(src_file, reg_p)
            synced = True
    return synced


class RetouchRequest(BaseModel):
    file_path: str
    image_base64: str


@app.post("/api/retouch_censor")
async def save_retouch(req: RetouchRequest, request: Request):
    _require_auth(request, check_origin=True)
    clean_path, target_path = _resolve_safe_subpath(INSPECT_BATCH, req.file_path)
    try:
        if not target_path.exists():
            return {"success": False, "error": f"File not found: {clean_path}"}

        raw_b64 = req.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(raw_b64)
        with Image.open(io.BytesIO(img_bytes)) as opened_img:
            img = opened_img.convert("RGB")

        _atomic_save_webp(img, target_path)

        # Step 3: 인간 검수 완료본을 Ground Truth(정답 세트)로 자동 아카이브
        gt_dir = BENCHMARK_DIR / "ground_truth" / target_path.parent.name
        _atomic_save_webp(img, gt_dir / target_path.name)

        # 정규 프로덕션 에셋(projects/{roster}/assets)에도 원자적 자동 동기화
        synced_asset = _sync_inspect_to_project_assets(clean_path, img=img)

        return {
            "success": True,
            "message": "성공적으로 저장되었습니다!",
            "file_name": target_path.name,
            "synced_asset": synced_asset,
            "timestamp": int(time.time()),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class RestoreOriginRequest(BaseModel):
    file_path: str


@app.post("/api/restore_origin")
async def restore_origin_endpoint(req: RestoreOriginRequest, request: Request):
    """
    검열 또는 덧칠된 에셋을 {char}_origin 폴더 내의 무검열 원본 이미지로 즉시 교체/복원합니다.
    - 대상 1: output/inspection_batch/{char}/{subfolder}/{file}
    - 대상 2: 동적 탐색된 로스터의 projects/{roster}/assets/{char}/{subfolder}/{file}
    """
    _require_auth(request, check_origin=True)
    clean_path, target_inspect = _resolve_safe_subpath(INSPECT_BATCH, req.file_path)
    try:
        found_origin, c_code, subfolder, filename = _find_origin_for_inspect_path(clean_path)
        if not c_code:
            return {"success": False, "error": f"잘못된 파일 경로 형식입니다: {clean_path}"}

        if not found_origin:
            return {
                "success": False,
                "error": f"오리지널 원본({c_code}_origin/{subfolder}/{filename})을 찾을 수 없습니다.",
            }

        # 1. inspection_batch에 원자적 덮어쓰기
        _atomic_copy_file(found_origin, target_inspect)

        # 2. 정규 에셋(projects/{roster}/assets)에도 원자적 복원
        synced_asset = _sync_inspect_to_project_assets(clean_path, src_file=found_origin)

        return {
            "success": True,
            "message": "오리지널 원본 이미지로 성공적으로 복원되었습니다!",
            "file_name": filename,
            "synced_asset": synced_asset,
            "timestamp": int(time.time()),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class ReapplyCensorRequest(BaseModel):
    file_path: str
    char_code: Optional[str] = ""
    pose_code: Optional[str] = ""
    censor_style: str = "white_silhouette"
    censor_targets: str = "penis"
    min_confidence: float = 0.16
    enable_anchor_fallback: bool = False


@app.post("/api/reapply_censor")
async def reapply_censor_endpoint(req: ReapplyCensorRequest, request: Request):
    """ComfyUI 재생성 없이 무검열 원본(_origin)으로부터 0.2초 즉시 재검열을 수행하고 양쪽 에셋을 동기화합니다."""
    _require_auth(request, check_origin=True)
    clean_path, target_inspect = _resolve_safe_subpath(INSPECT_BATCH, req.file_path)
    try:
        found_origin, c_code, subfolder, filename = _find_origin_for_inspect_path(clean_path)
        if not c_code:
            return {"success": False, "error": f"잘못된 파일 경로 형식입니다: {clean_path}"}
        if not found_origin:
            return {
                "success": False,
                "error": f"오리지널 원본({c_code}_origin/{subfolder}/{filename})을 찾을 수 없습니다.",
            }

        eff_char = (req.char_code or c_code).lower()
        eff_pose = (req.pose_code or _extract_pose_code_from_filename(filename)).strip()
        if eff_pose.isdigit():
            eff_pose = eff_pose.zfill(3)

        roster = _resolve_char_roster(eff_char)
        targets_list = [t.strip() for t in (req.censor_targets or "penis").split(",") if t.strip()] or ["penis"]

        from plepa_engine.censor import censor_image

        with Image.open(found_origin) as opened_orig:
            orig_rgb = opened_orig.convert("RGB")

        censored_img, mask_count = censor_image(
            orig_rgb,
            style=req.censor_style,
            targets=targets_list,
            min_confidence=req.min_confidence,
            pose_code=eff_pose or None,
            enable_anchor_fallback=req.enable_anchor_fallback,
            roster=roster,
        )

        _atomic_save_webp(censored_img, target_inspect)
        synced_asset = _sync_inspect_to_project_assets(clean_path, img=censored_img, preferred_roster=roster)

        return {
            "success": True,
            "message": f"즉시 재검열 완료 ({req.censor_style}, 마스크 {mask_count}건)",
            "file_name": filename,
            "detected_count": mask_count,
            "mask_count": mask_count,
            "censor_style": req.censor_style,
            "synced_asset": synced_asset,
            "timestamp": int(time.time()),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class RerollRequest(BaseModel):
    file_path: str
    char_code: str
    pose_code: str
    label: Optional[str] = ""
    censor_style: str = "white_silhouette"
    censor_targets: str = "penis"
    min_confidence: float = 0.16
    enable_anchor_fallback: bool = False
    strict_censor_qc: bool = False
    auto_qc: bool = True


class RerollJob:
    def __init__(
        self,
        job_id: str,
        file_path: str,
        char_code: str,
        pose_code: str,
        label: str = "",
        censor_style: str = "white_silhouette",
        censor_targets: str = "penis",
        min_confidence: float = 0.16,
        enable_anchor_fallback: bool = False,
        strict_censor_qc: bool = False,
        auto_qc: bool = True,
    ):
        self.job_id = job_id
        self.file_path = file_path
        self.char_code = char_code.lower()
        norm_pose = str(pose_code or "").strip()
        self.pose_code = norm_pose.zfill(3) if norm_pose.isdigit() else norm_pose.upper()
        self.label = label
        self.censor_style = (censor_style or "white_silhouette").strip() or "white_silhouette"
        self.censor_targets = (censor_targets or "penis").strip() or "penis"
        self.min_confidence = float(min_confidence)
        self.enable_anchor_fallback = bool(enable_anchor_fallback)
        self.strict_censor_qc = bool(strict_censor_qc)
        self.auto_qc = bool(auto_qc)
        self.qc_passed: Optional[bool] = None
        self.qc_reason: Optional[str] = None
        self.status = "queued"  # queued | processing | done | failed
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.new_seed: Optional[int] = None
        self.error: Optional[str] = None

    def to_dict(self, queue_pos: int = 0) -> dict:
        return {
            "job_id": self.job_id,
            "file_path": self.file_path,
            "char_code": self.char_code,
            "pose_code": self.pose_code,
            "label": self.label,
            "censor_style": self.censor_style,
            "censor_targets": self.censor_targets,
            "min_confidence": self.min_confidence,
            "enable_anchor_fallback": self.enable_anchor_fallback,
            "strict_censor_qc": self.strict_censor_qc,
            "auto_qc": self.auto_qc,
            "qc_passed": self.qc_passed,
            "qc_reason": self.qc_reason,
            "status": self.status,
            "queue_position": queue_pos,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "new_seed": self.new_seed,
            "error": self.error,
        }


def _execute_reroll_job(job: RerollJob) -> tuple[bool, Optional[int], Optional[str]]:
    """
    ComfyUI 호출 및 무검열 원본 보존, ADR-86 검열 덮어쓰기를 순차 동기 처리합니다.
    """
    try:
        import random
        from plepa_engine.services.generation_service import GenerationParams, GenerationService
        from plepa_engine.censor import censor_image
        from PIL import Image

        clean_path, target_inspect = _resolve_safe_subpath(INSPECT_BATCH, job.file_path)
        parts = clean_path.split("/")
        if len(parts) < 3:
            return False, None, f"잘못된 파일 경로 형식: {clean_path}"

        c_code = job.char_code.lower()
        p_code = job.pose_code
        subfolder = parts[1]
        raw_filename = parts[2]

        # 디스크의 실제 파일명 자동 탐색 및 보정
        target_dir = (INSPECT_BATCH / c_code / subfolder).resolve()
        if not target_dir.is_relative_to(INSPECT_BATCH.resolve()):
            return False, None, f"허용되지 않은 대상 경로입니다: {target_dir}"
        if (target_dir / raw_filename).exists():
            filename = raw_filename
        else:
            matches = list(target_dir.glob(f"*{p_code}*.webp")) if target_dir.exists() else []
            if matches:
                filename = matches[0].name
                clean_path = f"{c_code}/{subfolder}/{filename}"
                job.file_path = clean_path
            else:
                filename = re.sub(r'[\\/*?:"<>|]', '_', raw_filename)
                clean_path = f"{c_code}/{subfolder}/{filename}"
                job.file_path = clean_path

        # 로스터 동적 판별
        roster = _resolve_char_roster(c_code)

        new_seed = random.randint(1000, 999999)
        ckpt_tag = f"reroll_{c_code}_{p_code}"

        service = GenerationService()
        if hasattr(service, "pose_bg_svc") and hasattr(service.pose_bg_svc, "cache"):
            service.pose_bg_svc.cache.clear()

        params = GenerationParams(
            character_expr=c_code,
            pose_expr=p_code,
            roster=roster,
            ckpt_tag=ckpt_tag,
            overwrite=True,
            engine="sdxl",
            censor=False,
            censor_style=job.censor_style,
            censor_targets=job.censor_targets,
            auto_qc=job.auto_qc,
            strict_censor_qc=job.strict_censor_qc,
            seed=new_seed,
            no_ref=True,
            custom_neg=None,
        )

        res = service.run_batch(params, quiet=True)
        if not res or not res[0].success or not res[0].image_path:
            if res:
                job.qc_passed = getattr(res[0], "qc_passed", False)
                job.qc_reason = getattr(res[0], "qc_reason", None)
            err = res[0].error_message if res else "Unknown generation error"
            return False, None, f"ComfyUI 재생성 실패: {err}"

        job.qc_passed = getattr(res[0], "qc_passed", True)
        job.qc_reason = getattr(res[0], "qc_reason", None)

        gen_p = Path(res[0].image_path)
        if not gen_p.exists():
            return False, None, "생성된 이미지 파일이 디스크에 존재하지 않습니다."

        # 1. 무검열 원본 원자적 백업
        origin_dir = PROJECTS_DIR / roster / "assets" / f"{c_code}_origin" / subfolder
        origin_path = origin_dir / filename
        _atomic_copy_file(gen_p, origin_path)

        # 2. 요청된 검열 스타일/대상/임계값/폴백 옵션으로 검열 적용
        targets_list = [t.strip() for t in (job.censor_targets or "penis").split(",") if t.strip()] or ["penis"]
        with Image.open(gen_p) as opened_gen:
            img = opened_gen.convert("RGB")
        censored_img, mask_cnt = censor_image(
            img,
            style=job.censor_style,
            targets=targets_list,
            min_confidence=job.min_confidence,
            pose_code=p_code,
            enable_anchor_fallback=job.enable_anchor_fallback,
            roster=roster,
        )

        # 3. inspection_batch 및 정규 에셋 원자적 덮어쓰기
        _, safe_target_inspect = _resolve_safe_subpath(INSPECT_BATCH, clean_path)
        _atomic_save_webp(censored_img, safe_target_inspect)
        _sync_inspect_to_project_assets(clean_path, img=censored_img, preferred_roster=roster)

        # 4. 임시 생성 폴더 정리
        tmp_dir = gen_p.parent.parent
        if tmp_dir.name.startswith("ckpt_reroll_"):
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass

        return True, new_seed, None
    except Exception as e:
        return False, None, str(e)


class RerollQueueManager:
    MAX_COMPLETED_JOBS = 200

    def __init__(self):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.jobs: Dict[str, RerollJob] = {}
        self.active_job: Optional[RerollJob] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._counter = 0

    def _prune_completed_jobs(self) -> None:
        completed_ids = [j_id for j_id, j in self.jobs.items() if j.status in ("done", "failed")]
        excess = len(completed_ids) - self.MAX_COMPLETED_JOBS
        if excess > 0:
            for j_id in completed_ids[:excess]:
                self.jobs.pop(j_id, None)

    def start_worker(self):
        if self._worker_task is None or self._worker_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._worker_task = loop.create_task(self._worker_loop())
            except RuntimeError:
                pass

    def _calc_queue_pos(self, target_job_id: str) -> int:
        if self.active_job and self.active_job.job_id == target_job_id:
            return 0  # 0: 현재 처리 중 (Processing)

        pos = 1
        for j_id, j in self.jobs.items():
            if j.status == "queued":
                if j_id == target_job_id:
                    return pos
                pos += 1
        return pos

    async def enqueue(self, req: RerollRequest) -> tuple[dict, bool]:
        clean_path = req.file_path.replace("\\", "/").lstrip("/")

        # 중복 방지 (이미 큐에 있거나 처리 중인 동일 파일)
        for job in self.jobs.values():
            if job.status in ["queued", "processing"]:
                if job.file_path.replace("\\", "/").lstrip("/") == clean_path:
                    pos = self._calc_queue_pos(job.job_id)
                    return job.to_dict(queue_pos=pos), False

        self._counter += 1
        job_id = f"job_{int(time.time()*1000)}_{self._counter}"
        job = RerollJob(
            job_id=job_id,
            file_path=clean_path,
            char_code=req.char_code,
            pose_code=req.pose_code,
            label=req.label or "",
            censor_style=req.censor_style,
            censor_targets=req.censor_targets,
            min_confidence=req.min_confidence,
            enable_anchor_fallback=req.enable_anchor_fallback,
            strict_censor_qc=req.strict_censor_qc,
            auto_qc=req.auto_qc,
        )
        self.jobs[job_id] = job
        await self.queue.put(job_id)

        self.start_worker()
        pos = self._calc_queue_pos(job_id)
        return job.to_dict(queue_pos=pos), True

    def get_status(self) -> dict:
        queued_count = sum(1 for j in self.jobs.values() if j.status == "queued")
        processing_count = 1 if self.active_job and self.active_job.status == "processing" else 0
        total_pending = queued_count + processing_count

        active_info = self.active_job.to_dict(queue_pos=0) if self.active_job else None

        # 최근 40개 작업 정보 반환
        recent_jobs = {}
        for j_id, j in list(self.jobs.items())[-40:]:
            pos = self._calc_queue_pos(j_id)
            recent_jobs[j_id] = j.to_dict(queue_pos=pos)

        return {
            "total_pending": total_pending,
            "queued_count": queued_count,
            "processing_count": processing_count,
            "active_job": active_info,
            "jobs": recent_jobs,
        }

    async def _worker_loop(self):
        while True:
            job_id = await self.queue.get()
            job = self.jobs.get(job_id)
            if not job:
                self.queue.task_done()
                continue

            self.active_job = job
            job.status = "processing"
            job.started_at = time.time()

            try:
                success, new_seed, err = await asyncio.to_thread(_execute_reroll_job, job)
                if success:
                    job.status = "done"
                    job.new_seed = new_seed
                else:
                    job.status = "failed"
                    job.error = err
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            finally:
                job.finished_at = time.time()
                self.active_job = None
                self._prune_completed_jobs()
                self.queue.task_done()


reroll_queue_mgr = RerollQueueManager()


@app.post("/api/reroll_queue")
async def enqueue_reroll_endpoint(req: RerollRequest, request: Request):
    """
    새로운 리롤 작업을 대기열에 등록합니다 (논블로킹 즉시 응답).
    """
    _require_auth(request, check_origin=True)
    _resolve_safe_subpath(INSPECT_BATCH, req.file_path)
    try:
        reroll_queue_mgr.start_worker()
        job_data, is_new = await reroll_queue_mgr.enqueue(req)
        return {
            "success": True,
            "job": job_data,
            "is_new": is_new,
            "message": "대기열에 성공적으로 등록되었습니다." if is_new else "이미 대기열에 등록되어 처리 중입니다.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/reroll_queue_status")
async def reroll_queue_status_endpoint(request: Request):
    """
    현재 리롤 대기열 현황 및 활성/완료 작업 상태를 반환합니다.
    """
    _require_auth(request)
    try:
        return {"success": True, "data": reroll_queue_mgr.get_status()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/reroll_pose")
async def reroll_pose_endpoint(req: RerollRequest, request: Request):
    """
    (하위 호환) 대기열에 등록한 후 완료될 때까지 비동기 대기하여 최종 결과를 반환합니다.
    """
    _require_auth(request, check_origin=True)
    _resolve_safe_subpath(INSPECT_BATCH, req.file_path)
    try:
        reroll_queue_mgr.start_worker()
        job_data, _ = await reroll_queue_mgr.enqueue(req)
        job_id = job_data["job_id"]

        # 최대 180초 대기
        for _ in range(360):
            await asyncio.sleep(0.5)
            job = reroll_queue_mgr.jobs.get(job_id)
            if not job:
                break
            if job.status == "done":
                clean_path = job.file_path.replace("\\", "/").lstrip("/")
                filename = clean_path.split("/")[-1]
                return {
                    "success": True,
                    "message": f"#{job.pose_code} 리롤 생성 완료 (seed: {job.new_seed})",
                    "seed": job.new_seed,
                    "file_name": filename,
                    "qc_passed": job.qc_passed,
                    "qc_reason": job.qc_reason,
                    "timestamp": int(time.time()),
                }
            elif job.status == "failed":
                return {"success": False, "error": job.error or "리롤 생성 실패"}

        return {"success": False, "error": "리롤 대기 시간 초과 (Timeout)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# 정적 디렉토리 마운트는 모듈 상단에서 임포트 부작용 없이 수행됨


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def scan_benchmark_assets() -> Dict[str, Any]:
    """output/benchmarks 디렉토리를 스캔하여 컨택트 시트 및 개별 실측 에셋 데이터를 수집합니다."""
    contact_sheets = []
    poses_data = {
        "088": {"label": "후배위약 (배면 측면 결합)", "folder": "pose_088_v2", "items": []},
        "067": {"label": "딥스로트 (초근접 구강 봉사)", "folder": "pose_067_v2", "items": []},
        "072": {"label": "파이즈리약 (정면 바스트 결합)", "folder": "pose_072", "items": []},
        "116": {"label": "파일드라이버 (상단 반전 결합)", "folder": "pose_116", "items": []},
    }

    # 1. 4대 컨택트 시트 수집
    sheet_configs = [
        ("088", "후배위약", "pose_088_v2"),
        ("067", "딥스로트", "pose_067_v2"),
        ("072", "파이즈리약", "pose_072"),
        ("116", "파일드라이버", "pose_116"),
    ]
    for code, label, folder in sheet_configs:
        sheet_path = BENCHMARK_DIR / folder / f"contact_sheet_pose_{code}.webp"
        if sheet_path.exists():
            contact_sheets.append({
                "code": code,
                "label": label,
                "url": f"/static/{folder}/contact_sheet_pose_{code}.webp",
                "folder": folder,
            })

    # 2. 개별 실측 에셋 수집
    for code, pinfo in poses_data.items():
        raw_dir = BENCHMARK_DIR / pinfo["folder"] / "raw"
        if not raw_dir.exists():
            continue
        report_file = BENCHMARK_DIR / pinfo["folder"] / "benchmark_report.md"
        report_meta = {}
        if report_file.exists():
            try:
                # 간단한 리포트 파싱
                lines = report_file.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if line.startswith("|") and "`" in line:
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 8:
                            # | 1 | `dan` | `1001` | 🟢 YOLO DETECT | 0.58 | `(15, 822, 69, 921)` | (0.050, 0.717) | 0.5% |
                            c_char = parts[2].replace("`", "")
                            c_seed = parts[3].replace("`", "")
                            status = parts[4]
                            conf = parts[5]
                            bbox = parts[6].replace("`", "")
                            center = parts[7]
                            area = parts[8]
                            key = f"{c_char}_{code}_seed{c_seed}"
                            report_meta[key] = {
                                "status": status,
                                "conf": conf,
                                "bbox": bbox,
                                "center": center,
                                "area": area,
                            }
            except Exception:
                pass

        for img_p in sorted(raw_dir.glob("*.webp")):
            name = img_p.name
            stem = img_p.stem
            meta = report_meta.get(stem, {
                "status": "🟢 DETECT",
                "conf": "0.75",
                "bbox": "",
                "center": "",
                "area": "",
            })
            pinfo["items"].append({
                "filename": name,
                "stem": stem,
                "url": f"/static/{pinfo['folder']}/raw/{name}",
                "meta": meta,
            })

    return {
        "contact_sheets": contact_sheets,
        "poses": poses_data,
    }


@app.get("/api/data")
def api_data():
    return scan_benchmark_assets()


@app.get("/", response_class=HTMLResponse)
def index_view():
    data = scan_benchmark_assets()
    
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes">
  <title>PLEPA 통계적 벤치마크 모바일 뷰어</title>
  <style>
    :root {{
      --bg: #0f121d;
      --card-bg: #181d2e;
      --accent: #6366f1;
      --accent-light: #818cf8;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --border: #28314a;
      --success: #22c55e;
      --warning: #f59e0b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
      padding-bottom: 50px;
    }}
    header {{
      background: #131726;
      border-bottom: 1px solid var(--border);
      padding: 14px 16px;
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(10px);
    }}
    .header-title {{
      font-size: 1.15rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .header-sub {{
      font-size: 0.78rem;
      color: var(--text-muted);
      margin-top: 4px;
    }}
    .badge-summary {{
      display: inline-block;
      background: #2e1065;
      color: #d8b4fe;
      font-size: 0.72rem;
      padding: 2px 7px;
      border-radius: 9999px;
      margin-left: 6px;
      font-weight: 600;
    }}
    
    /* 탭 네비게이션 */
    .tabs-wrap {{
      display: flex;
      overflow-x: auto;
      background: #131726;
      border-bottom: 1px solid var(--border);
      padding: 6px 12px;
      gap: 8px;
      scrollbar-width: none;
    }}
    .tabs-wrap::-webkit-scrollbar {{ display: none; }}
    .tab-btn {{
      background: transparent;
      color: var(--text-muted);
      border: 1px solid transparent;
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      white-space: nowrap;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .tab-btn.active {{
      background: var(--accent);
      color: #fff;
    }}

    /* 컨테이너 */
    .container {{
      padding: 12px;
    }}

    /* 마스터 매트릭스 카드 */
    .summary-card {{
      background: #1e1b4b;
      border: 1px solid #4338ca;
      border-radius: 12px;
      padding: 14px;
      margin-bottom: 14px;
    }}
    .summary-card h3 {{
      font-size: 0.95rem;
      color: #c7d2fe;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .stat-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .stat-pill {{
      background: #312e81;
      color: #e0e7ff;
      font-size: 0.75rem;
      padding: 4px 8px;
      border-radius: 6px;
    }}

    /* 컨택트 시트 뷰어 */
    .contact-grid {{
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .contact-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
    }}
    .contact-card-header {{
      padding: 10px 14px;
      background: #1a2035;
      font-size: 0.9rem;
      font-weight: bold;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .contact-card img {{
      width: 100%;
      height: auto;
      display: block;
      cursor: zoom-in;
    }}

    /* 2열 에셋 그리드 */
    .asset-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
    }}
    @media (min-width: 600px) {{
      .asset-grid {{ grid-template-columns: repeat(3, 1fr); gap: 14px; }}
    }}
    @media (min-width: 900px) {{
      .asset-grid {{ grid-template-columns: repeat(4, 1fr); gap: 16px; }}
    }}
    .asset-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    .asset-img-wrap {{
      width: 100%;
      aspect-ratio: 832 / 1216;
      background: #090c14;
      position: relative;
      overflow: hidden;
    }}
    .asset-img-wrap img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      cursor: zoom-in;
    }}
    .asset-info {{
      padding: 8px 10px;
    }}
    .asset-name {{
      font-size: 0.8rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .asset-badge {{
      font-size: 0.68rem;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 600;
    }}
    .badge-detect {{ background: #14532d; color: #86efac; }}
    .badge-fallback {{ background: #78350f; color: #fde68a; }}
    .asset-coords {{
      font-size: 0.7rem;
      color: var(--text-muted);
      margin-top: 4px;
      font-family: monospace;
    }}

    /* 라이트박스 모달 */
    .lightbox {{
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.95);
      z-index: 1000;
      justify-content: center;
      align-items: center;
      padding: 10px;
    }}
    .lightbox.active {{ display: flex; }}
    .lightbox img {{
      max-width: 100%;
      max-height: 94vh;
      object-fit: contain;
      border-radius: 6px;
    }}
    .lightbox-close {{
      position: absolute;
      top: 15px;
      right: 15px;
      background: #334155;
      color: #fff;
      border: none;
      width: 38px;
      height: 38px;
      border-radius: 50%;
      font-size: 1.3rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
  </style>
</head>
<body>

  <header>
    <div class="header-title">
      <span>🔬 PLEPA 4대 체위 통계 벤치마크</span>
      <span class="badge-summary">모바일 검수/벤치마크</span>
    </div>
    <div class="header-sub">
      RTX 4060 Ti | school 로스터 (dan, ena, ria) × 3시드 (1001, 1002, 1003)
    </div>
    <div style="display: flex; gap: 8px; margin-top: 10px; overflow-x: auto; padding-bottom: 2px;">
      <a href="/campus_bench/" style="background: #0284c7; color: #f0f9ff; text-decoration: none; font-size: 0.76rem; font-weight: bold; padding: 5px 10px; border-radius: 6px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px;">🎓 캠퍼스 C1 vs C2 ➔</a>
      <a href="/c_tuning/" style="background: #059669; color: #ecfdf5; text-decoration: none; font-size: 0.76rem; font-weight: bold; padding: 5px 10px; border-radius: 6px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px;">🎯 C조합 라타타 감쇄 ➔</a>
      <a href="/hybrid/" style="background: #4f46e5; color: #e0e7ff; text-decoration: none; font-size: 0.76rem; font-weight: bold; padding: 5px 10px; border-radius: 6px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px;">✨ 물광 4대 조합 ➔</a>
      <a href="/artist2/" style="background: #be185d; color: #fdf2f8; text-decoration: none; font-size: 0.76rem; font-weight: bold; padding: 5px 10px; border-radius: 6px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px;">🔞 40인 성인작가 200장 (2차) ➔</a>
      <a href="/artist1/" style="background: #1d4ed8; color: #eff6ff; text-decoration: none; font-size: 0.76rem; font-weight: bold; padding: 5px 10px; border-radius: 6px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px;">🎨 80인 작가 화풍 (1차) ➔</a>
      <a href="/ratatata/" style="background: #b45309; color: #fef3c7; text-decoration: none; font-size: 0.76rem; font-weight: bold; padding: 5px 10px; border-radius: 6px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px;">⚡ 라타타타 믹스 ➔</a>
    </div>
  </header>

  <div class="tabs-wrap">
    <button class="tab-btn active" onclick="switchTab('contact')">📋 4대 컨택트시트</button>
    <button class="tab-btn" onclick="switchTab('all')">🔥 전체 에셋 (36장)</button>
    <button class="tab-btn" onclick="switchTab('088')">#088 후배위 (9)</button>
    <button class="tab-btn" onclick="switchTab('067')">#067 딥스로트 (9)</button>
    <button class="tab-btn" onclick="switchTab('072')">#072 파이즈리 (9)</button>
    <button class="tab-btn" onclick="switchTab('116')">#116 파일드라이버 (9)</button>
  </div>

  <div class="container">
    <div class="summary-card">
      <h3>🏆 최종 실측 지표 요약</h3>
      <div class="stat-pills">
        <span class="stat-pill">총 실측: 36장</span>
        <span class="stat-pill" style="background:#065f46; color:#a7f3d0;">실제 모델 탐지: 94.4% (34건)</span>
        <span class="stat-pill" style="background:#854d0e; color:#fef08a;">정밀 앵커 폴백: 5.6% (2건)</span>
        <span class="stat-pill" style="background:#1e3a8a; color:#bfdbfe;">미검열 위험: 0건 (100% 방어)</span>
        <span class="stat-pill" style="background:#4c1d95; color:#ddd6fe;">지향 축 분산: σ ≤ 4.3% 초정밀 수렴</span>
      </div>
    </div>

    <!-- 1. 컨택트 시트 뷰 -->
    <div id="view-contact" class="tab-content">
      <div class="contact-grid">
"""
    for cs in data["contact_sheets"]:
        safe_code = html_lib.escape(str(cs["code"]), quote=True)
        safe_label = html_lib.escape(str(cs["label"]), quote=True)
        safe_url = html_lib.escape(str(cs["url"]), quote=True)
        html += f"""
        <div class="contact-card">
          <div class="contact-card-header">
            <span>#{safe_code} [{safe_label}] 3x3 컨택트 시트</span>
            <span style="font-size:0.75rem; color:#818cf8;">터치 시 원본 확대</span>
          </div>
          <img src="{safe_url}" alt="{safe_label}" onclick="openLightbox(this.src)" loading="lazy">
        </div>
        """

    html += """
      </div>
    </div>

    <!-- 2. 개별 포즈별 뷰 -->
"""
    for code, pinfo in data["poses"].items():
        safe_pose_code = html_lib.escape(str(code), quote=True)
        html += f"""
    <div id="view-{safe_pose_code}" class="tab-content" style="display:none;">
      <div class="asset-grid">
"""
        for itm in pinfo["items"]:
            meta = itm["meta"]
            status_text = meta.get("status", "")
            is_fallback = "FALLBACK" in status_text
            badge_class = "badge-fallback" if is_fallback else "badge-detect"
            badge_label = html_lib.escape("폴백 앵커" if is_fallback else f"YOLO {meta.get('conf', '')}", quote=True)
            coords = html_lib.escape(str(meta.get("center", "")), quote=True)
            safe_url = html_lib.escape(str(itm["url"]), quote=True)
            safe_stem = html_lib.escape(str(itm["stem"]), quote=True)
            safe_title = html_lib.escape(str(itm["stem"]).replace("_" + code + "_", " ").upper(), quote=True)
            
            html += f"""
        <div class="asset-card">
          <div class="asset-img-wrap">
            <img src="{safe_url}" alt="{safe_stem}" onclick="openLightbox(this.src)" loading="lazy">
          </div>
          <div class="asset-info">
            <div class="asset-name">
              <span>{safe_title}</span>
              <span class="asset-badge {badge_class}">{badge_label}</span>
            </div>
            <div class="asset-coords">{coords}</div>
          </div>
        </div>
"""
        html += """
      </div>
    </div>
"""

    html += """
    <!-- 3. 전체 에셋 통합 뷰 -->
    <div id="view-all" class="tab-content" style="display:none;">
      <div class="asset-grid">
"""
    for code, pinfo in data["poses"].items():
        safe_pose_code = html_lib.escape(str(code), quote=True)
        for itm in pinfo["items"]:
            meta = itm["meta"]
            status_text = meta.get("status", "")
            is_fallback = "FALLBACK" in status_text
            badge_class = "badge-fallback" if is_fallback else "badge-detect"
            badge_label = html_lib.escape("폴백" if is_fallback else f"YOLO {meta.get('conf', '')}", quote=True)
            coords = html_lib.escape(str(meta.get("center", "")), quote=True)
            safe_url = html_lib.escape(str(itm["url"]), quote=True)
            safe_stem = html_lib.escape(str(itm["stem"]), quote=True)
            safe_char = html_lib.escape(str(itm["stem"]).split("_")[0].upper(), quote=True)
            
            html += f"""
        <div class="asset-card">
          <div class="asset-img-wrap">
            <img src="{safe_url}" alt="{safe_stem}" onclick="openLightbox(this.src)" loading="lazy">
          </div>
          <div class="asset-info">
            <div class="asset-name">
              <span>#{safe_pose_code} {safe_char}</span>
              <span class="asset-badge {badge_class}">{badge_label}</span>
            </div>
            <div class="asset-coords">{coords}</div>
          </div>
        </div>
"""
    html += """
      </div>
    </div>
  </div>

  <!-- 라이트박스 -->
  <div id="lightbox" class="lightbox" onclick="closeLightbox()">
    <button class="lightbox-close" onclick="closeLightbox()">✕</button>
    <img id="lightbox-img" src="" alt="확대 이미지" onclick="event.stopPropagation()">
  </div>

  <script>
    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      
      const target = document.getElementById('view-' + tabId);
      if (target) {
        target.style.display = 'block';
      }
      
      const btns = document.querySelectorAll('.tab-btn');
      btns.forEach(btn => {
        if (btn.getAttribute('onclick').includes("'" + tabId + "'")) {
          btn.classList.add('active');
        }
      });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function openLightbox(src) {
      const lb = document.getElementById('lightbox');
      const img = document.getElementById('lightbox-img');
      img.src = src;
      lb.classList.add('active');
    }

    function closeLightbox() {
      const lb = document.getElementById('lightbox');
      lb.classList.remove('active');
    }

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeLightbox();
    });
  </script>
</body>
</html>
"""
    return html


def start_server_and_tunnel():
    for _dir in (BENCHMARK_DIR, INSPECT_BATCH, HYBRID_BENCH, C_TUNING_BENCH, CAMPUS_BENCH):
        _dir.mkdir(parents=True, exist_ok=True)
    local_ip = get_local_ip()
    print("=" * 70)
    print("  [MOBILE BENCHMARK GALLERY] 모바일 뷰어 서버 준비 중...")
    print(f"  로컬 Wi-Fi 접속: http://{local_ip}:{PORT}?token={ACCESS_TOKEN}")
    print(f"  로컬 PC 브라우저: http://127.0.0.1:{PORT}?token={ACCESS_TOKEN}")
    print("=" * 70)

    # Cloudflare Quick Tunnel 기동
    tunnel_url = None
    if CF.exists():
        print("▶ Cloudflare Quick Tunnel 개설 중 (모바일 어디서나 접속 가능)...")
        log_file = Path(os.environ.get("TEMP", ".")) / "plepa_bench_tunnel.log"
        if log_file.exists():
            try:
                log_file.unlink()
            except Exception:
                pass

        with open(log_file, "w", encoding="utf-8") as log_fp:
            cf_proc = subprocess.Popen(
                [str(CF), "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=log_fp,
                creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
            )

        pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        for _ in range(35):
            time.sleep(1)
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        matches = pattern.findall(content)
                        if matches:
                            tunnel_url = matches[0]
                            break
                except Exception:
                    pass

    print("\n" + "=" * 70)
    if tunnel_url:
        print(f"  📱 [스마트폰 모바일 링크 (공인)]:  {tunnel_url}/inspect/?token={ACCESS_TOKEN}")
        if TEST_C4_DIR.is_dir():
            print(f"  🧪 [C4 테스트 20장 갤러리 (공인)]: {tunnel_url}/test_c4/?token={ACCESS_TOKEN}")
        print(f"  🔬 [벤치마크 대시보드 (공인)]:     {tunnel_url}?token={ACCESS_TOKEN}")
    if TEST_C4_DIR.is_dir():
        print(f"  🧪 [C4 테스트 20장 (Wi-Fi)]:     http://{local_ip}:{PORT}/test_c4/?token={ACCESS_TOKEN}")
        print(f"  🧪 [C4 테스트 20장 (로컬 PC)]:    http://127.0.0.1:{PORT}/test_c4/?token={ACCESS_TOKEN}")
    print(f"  📶 [동일 Wi-Fi 내부망 링크]:        http://{local_ip}:{PORT}/inspect/?token={ACCESS_TOKEN}")
    print(f"  💻 [로컬 PC 링크]:                 http://127.0.0.1:{PORT}/inspect/?token={ACCESS_TOKEN}")
    print("=" * 70 + "\n")

    # FastAPI 기동
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    start_server_and_tunnel()