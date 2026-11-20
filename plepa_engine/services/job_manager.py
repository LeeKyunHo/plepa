"""
plepa_engine.services.job_manager
애플리케이션 전역 백그라운드 배치 작업 관리자 (Global Job Manager).
브라우저 페이지 이동이나 세션 종료와 무관하게 백그라운드 스레드에서 배치를 계속 유지합니다.
"""

from __future__ import annotations

from collections import deque
import threading
import time
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from plepa_engine.config import DEFAULT_SDXL_CFG, DEFAULT_SDXL_STEPS
from plepa_engine.models import GenerationResult
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.generation_service import GenerationParams, default_generation_service


class GlobalJobManager:
    """전역 비동기 배치 생성 관리 싱글톤 (FIFO 순차 대기열 지원)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.is_running: bool = False
        self.cancel_requested: bool = False
        self.active_params: Optional[GenerationParams] = None
        self._queue: Deque[
            Tuple[
                GenerationParams,
                str,
                Optional[Callable[[List[GenerationResult], Optional[Exception]], None]],
                Dict[str, Any],
            ]
        ] = deque()

        self.current: int = 0
        self.total: int = 0
        self.percentage: float = 0.0
        self.current_msg: str = "대기 중"
        self.success_count: int = 0
        self.fail_count: int = 0
        self.latest_result: Optional[Dict[str, Any]] = None

        self.logs: List[Dict[str, Any]] = []
        self._job_seq: int = 0
        self._active_job_record: Optional[Dict[str, Any]] = None
        self._job_history: Deque[Dict[str, Any]] = deque(maxlen=80)
        self._completed_items: Deque[Dict[str, Any]] = deque(maxlen=120)
        self._thread: Optional[threading.Thread] = None

    def _create_job_record(
        self,
        params: GenerationParams,
        label: str,
        status: str,
    ) -> Dict[str, Any]:
        self._job_seq += 1
        now_str = time.strftime("%H:%M:%S")
        record = {
            "job_id": self._job_seq,
            "label": label or f"{params.character_expr}:{params.pose_expr}",
            "char": params.character_expr,
            "pose": params.pose_expr,
            "roster": params.roster,
            "reuse_seed": bool(getattr(params, "reuse_seed", False)),
            "status": status,
            "queued_at": now_str,
            "started_at": now_str if status == "running" else None,
            "started_ts": time.perf_counter() if status == "running" else None,
            "finished_at": None,
            "duration_sec": None,
            "results": [],
            "error": None,
        }
        self._job_history.append(record)
        return record

    @staticmethod
    def _serialize_job_record(record: Dict[str, Any]) -> Dict[str, Any]:
        out = {k: v for k, v in record.items() if k != "started_ts"}
        out["results"] = [dict(item) for item in record.get("results", [])]
        return out

    def clear_history(self) -> None:
        """완료·취소·실패된 작업 기록과 완성 이미지 이력을 비웁니다 (실행 중/대기 중 항목 유지)."""
        with self._lock:
            kept_jobs = [
                rec for rec in self._job_history
                if rec.get("status") in ("running", "queued")
            ]
            self._job_history.clear()
            self._job_history.extend(kept_jobs)
            self._completed_items.clear()

    @staticmethod
    def _format_start_log(params: GenerationParams, prefix_label: str = "가동") -> Dict[str, Any]:
        conf = default_config_service.get_config()
        cfg_val = params.cfg if params.cfg is not None else conf.get("sdxl_cfg", DEFAULT_SDXL_CFG)
        steps_val = params.steps if params.steps is not None else conf.get("sdxl_steps", DEFAULT_SDXL_STEPS)
        return {
            "success": True,
            "text": f"[{prefix_label}] 파이프라인: SDXL | 대상: {params.character_expr}:{params.pose_expr} | CFG: {cfg_val} | 스텝: {steps_val}",
            "timestamp": time.strftime("%H:%M:%S"),
        }

    def start_job(self, params: GenerationParams) -> bool:
        """새 배치 작업을 전역 백그라운드 스레드로 시작합니다. 실행 중이면 False를 반환합니다."""
        with self._lock:
            if self.is_running:
                return False

            self.is_running = True
            self.cancel_requested = False
            self.active_params = params
            self.current = 0
            self.total = 0
            self.percentage = 0.0
            self.current_msg = "배치 작업 시작 중..."
            self.success_count = 0
            self.fail_count = 0
            self.latest_result = None
            self.logs = [self._format_start_log(params)]
            self._active_job_record = self._create_job_record(params, "", "running")

            self._thread = threading.Thread(target=self._run_worker, args=(params,), daemon=True)
            self._thread.start()
            return True

    def enqueue_job(
        self,
        params: GenerationParams,
        label: str = "",
        on_complete: Optional[Callable[[List[GenerationResult], Optional[Exception]], None]] = None,
    ) -> Tuple[bool, int]:
        """
        백그라운드 작업을 FIFO 대기열에 안전하게 등록합니다.
        다른 배치·리롤과 ComfyUI 리소스/파일 쓰기 경합 없이 순차 실행됩니다.
        반환값: (즉시 실행 시작 여부, 현재 대기열 순번[즉시 실행 시 0])
        """
        with self._lock:
            if not self.is_running:
                self.is_running = True
                self.cancel_requested = False
                self.active_params = params
                self.current = 0
                self.total = 0
                self.percentage = 0.0
                self.current_msg = f"작업 시작 중: {label}" if label else "배치 작업 시작 중..."
                self.success_count = 0
                self.fail_count = 0
                self.latest_result = None
                self.logs = [self._format_start_log(params, prefix_label="가동")]
                self._active_job_record = self._create_job_record(params, label, "running")

                self._thread = threading.Thread(
                    target=self._run_worker, args=(params, on_complete), daemon=True
                )
                self._thread.start()
                return True, 0

            queued_record = self._create_job_record(params, label, "queued")
            self._queue.append((params, label, on_complete, queued_record))
            pos = len(self._queue)
            desc = label or f"{params.character_expr}:{params.pose_expr}"
            self.logs.append({
                "success": True,
                "text": f"[대기열 등록 #{pos}] {desc} (이전 작업 완료 후 순차 실행)",
                "timestamp": time.strftime("%H:%M:%S"),
            })
            if len(self.logs) > 200:
                self.logs.pop(0)
            return False, pos

    def cancel_job(self) -> None:
        """진행 중인 작업 및 대기열에 중단(취소)을 요청합니다."""
        with self._lock:
            while self._queue:
                _, _, pending_cb, pending_rec = self._queue.popleft()
                pending_rec["status"] = "cancelled"
                pending_rec["finished_at"] = time.strftime("%H:%M:%S")
                if pending_cb is not None:
                    try:
                        pending_cb([], InterruptedError("대기열 작업이 취소되었습니다."))
                    except Exception:
                        pass
            if self.is_running:
                self.cancel_requested = True
                self.current_msg = "취소 요청됨... (현재 항목 완료 후 중단)"

    def get_status(self) -> Dict[str, Any]:
        """현재 진행 상태 딕셔너리 반환."""
        with self._lock:
            return {
                "is_running": self.is_running,
                "cancel_requested": self.cancel_requested,
                "queue_length": len(self._queue),
                "current": self.current,
                "total": self.total,
                "percentage": self.percentage,
                "current_msg": self.current_msg,
                "success_count": self.success_count,
                "fail_count": self.fail_count,
                "logs": list(self.logs),
                "latest_result": dict(self.latest_result) if self.latest_result else None,
                "active_job": self._serialize_job_record(self._active_job_record) if self._active_job_record else None,
                "queued_jobs": [self._serialize_job_record(item[3]) for item in self._queue],
                "job_history": [self._serialize_job_record(rec) for rec in reversed(self._job_history)],
                "completed_items": [dict(item) for item in reversed(self._completed_items)],
            }

    def _run_worker(
        self,
        params: GenerationParams,
        on_complete: Optional[Callable[[List[GenerationResult], Optional[Exception]], None]] = None,
    ) -> None:
        """백그라운드 스레드에서 실제 생성을 수행하고 대기열을 순차 소비하는 워커 메서드."""
        def progress_callback(cur: int, tot: int, res: GenerationResult) -> None:
            with self._lock:
                self.current = cur
                self.total = tot
                self.percentage = (cur / tot) if tot > 0 else 0.0
                now_ts = time.strftime("%H:%M:%S")
                rec = self._active_job_record
                item_entry = {
                    "job_id": rec["job_id"] if rec else None,
                    "char": res.target.character_prefix or (self.active_params.character_expr if self.active_params else ""),
                    "roster": self.active_params.roster if self.active_params else "",
                    "code": res.target.code,
                    "label": res.target.label,
                    "filename": res.target.output_filename,
                    "image_path": str(res.image_path) if res.image_path else "",
                    "seed": getattr(res.target, "seed", None),
                    "duration_sec": round(float(res.duration_sec or 0.0), 1),
                    "success": bool(res.success),
                    "qc_passed": getattr(res, "qc_passed", None),
                    "qc_reason": getattr(res, "qc_reason", None),
                    "error_message": getattr(res, "error_message", None),
                    "timestamp": now_ts,
                }
                if rec is not None:
                    rec["results"].append(item_entry)

                if res.success:
                    self.success_count += 1
                    self._completed_items.append(item_entry)
                    if res.image_path and res.image_path.exists():
                        self.latest_result = {
                            "image_path": str(res.image_path),
                            "code": res.target.code,
                            "label": res.target.label,
                            "filename": res.target.output_filename,
                            "duration_sec": res.duration_sec,
                            "seed": getattr(res.target, "seed", None),
                            "timestamp": now_ts,
                        }
                else:
                    self.fail_count += 1

                icon_str = "✔" if res.success else "✖"
                msg = f"{icon_str} #{res.target.code} {res.target.label} -> {res.target.output_filename} ({res.duration_sec:.1f}s)"
                self.current_msg = f"진행 중: {cur}/{tot} ({int(self.percentage * 100)}%) - #{res.target.code} {res.target.label}"

                self.logs.append({
                    "success": res.success,
                    "text": msg,
                    "timestamp": now_ts,
                })
                # 로그는 최대 200개 유지
                if len(self.logs) > 200:
                    self.logs.pop(0)

        def check_cancelled() -> bool:
            return self.cancel_requested

        current_params = params
        current_cb = on_complete
        while True:
            run_results: List[GenerationResult] = []
            run_err: Optional[Exception] = None
            try:
                run_results = default_generation_service.run_batch(
                    params=current_params,
                    on_progress=progress_callback,
                    is_cancelled=check_cancelled,
                    quiet=True
                )
                with self._lock:
                    succ = sum(1 for r in run_results if r.success)
                    self.current_msg = f"배치 완료! (성공: {succ} / 총 {len(run_results)})"
            except Exception as e:
                run_err = e
                with self._lock:
                    self.current_msg = f"오류 발생: {e}"
                    self.logs.append({
                        "success": False,
                        "text": f"치명적 오류 발생: {e}",
                        "timestamp": time.strftime("%H:%M:%S")
                    })

            with self._lock:
                rec = self._active_job_record
                if rec is not None:
                    started_ts = rec.get("started_ts")
                    rec["duration_sec"] = round(time.perf_counter() - started_ts, 1) if started_ts else None
                    rec["finished_at"] = time.strftime("%H:%M:%S")
                    if self.cancel_requested:
                        rec["status"] = "cancelled"
                    elif run_err is not None or (run_results and any(not r.success for r in run_results)):
                        rec["status"] = "failed"
                        rec["error"] = str(run_err) if run_err else "일부 항목 생성 실패"
                    else:
                        rec["status"] = "done"

            if current_cb is not None:
                try:
                    current_cb(run_results, run_err)
                except Exception:
                    pass

            with self._lock:
                if not self.cancel_requested and self._queue:
                    next_params, next_label, next_cb, next_rec = self._queue.popleft()
                    next_rec["status"] = "running"
                    next_rec["started_at"] = time.strftime("%H:%M:%S")
                    next_rec["started_ts"] = time.perf_counter()
                    self._active_job_record = next_rec
                    current_params = next_params
                    current_cb = next_cb
                    self.active_params = next_params
                    self.current = 0
                    self.total = 0
                    self.percentage = 0.0
                    self.success_count = 0
                    self.fail_count = 0
                    self.current_msg = f"대기열 실행: {next_label}" if next_label else "대기열 작업 시작 중..."
                    self.logs.append(self._format_start_log(next_params, prefix_label="대기열 실행"))
                    if len(self.logs) > 200:
                        self.logs.pop(0)
                    continue

                if self.cancel_requested:
                    while self._queue:
                        _, _, pending_cb, pending_rec = self._queue.popleft()
                        pending_rec["status"] = "cancelled"
                        pending_rec["finished_at"] = time.strftime("%H:%M:%S")
                        if pending_cb is not None:
                            try:
                                pending_cb([], InterruptedError("작업 취소로 인해 대기열이 비워졌습니다."))
                            except Exception:
                                pass
                self.is_running = False
                self.cancel_requested = False
                self.active_params = None
                self._active_job_record = None
                break


# 전역 싱글톤 인스턴스
global_job_manager = GlobalJobManager()
