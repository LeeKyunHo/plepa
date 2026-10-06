"""
plepa_engine.services.job_manager
애플리케이션 전역 백그라운드 배치 작업 관리자 (Global Job Manager).
브라우저 페이지 이동이나 세션 종료와 무관하게 백그라운드 스레드에서 배치를 계속 유지합니다.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from plepa_engine.models import GenerationResult
from plepa_engine.services.generation_service import GenerationParams, default_generation_service


class GlobalJobManager:
    """전역 비동기 배치 생성 관리 싱글톤."""

    def __init__(self):
        self._lock = threading.Lock()
        self.is_running: bool = False
        self.cancel_requested: bool = False
        self.active_params: Optional[GenerationParams] = None

        self.current: int = 0
        self.total: int = 0
        self.percentage: float = 0.0
        self.current_msg: str = "대기 중"
        self.success_count: int = 0
        self.fail_count: int = 0

        self.logs: List[Dict[str, Any]] = []
        self._thread: Optional[threading.Thread] = None

    def start_job(self, params: GenerationParams) -> bool:
        """새 배치 작업을 전역 백그라운드 스레드로 시작합니다."""
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
            self.logs = []

            self._thread = threading.Thread(target=self._run_worker, args=(params,), daemon=True)
            self._thread.start()
            return True

    def cancel_job(self) -> None:
        """진행 중인 작업에 중단(취소)을 요청합니다."""
        with self._lock:
            if self.is_running:
                self.cancel_requested = True
                self.current_msg = "취소 요청됨... (현재 항목 완료 후 중단)"

    def get_status(self) -> Dict[str, Any]:
        """현재 진행 상태 딕셔너리 반환."""
        with self._lock:
            return {
                "is_running": self.is_running,
                "cancel_requested": self.cancel_requested,
                "current": self.current,
                "total": self.total,
                "percentage": self.percentage,
                "current_msg": self.current_msg,
                "success_count": self.success_count,
                "fail_count": self.fail_count,
                "logs": list(self.logs),
            }

    def _run_worker(self, params: GenerationParams) -> None:
        """백그라운드 스레드에서 실제 생성을 수행하는 워커 메서드."""
        def progress_callback(cur: int, tot: int, res: GenerationResult) -> None:
            with self._lock:
                self.current = cur
                self.total = tot
                self.percentage = (cur / tot) if tot > 0 else 0.0
                if res.success:
                    self.success_count += 1
                else:
                    self.fail_count += 1

                icon_str = "✔" if res.success else "✖"
                msg = f"{icon_str} #{res.target.code} {res.target.label} -> {res.target.output_filename} ({res.duration_sec:.1f}s)"
                self.current_msg = f"진행 중: {cur}/{tot} ({int(self.percentage * 100)}%) - #{res.target.code} {res.target.label}"

                self.logs.append({
                    "success": res.success,
                    "text": msg,
                    "timestamp": time.strftime("%H:%M:%S")
                })
                # 로그는 최대 200개 유지
                if len(self.logs) > 200:
                    self.logs.pop(0)

        def check_cancelled() -> bool:
            return self.cancel_requested

        try:
            results = default_generation_service.run_batch(
                params=params,
                on_progress=progress_callback,
                is_cancelled=check_cancelled,
                quiet=True
            )
            with self._lock:
                succ = sum(1 for r in results if r.success)
                self.current_msg = f"배치 완료! (성공: {succ} / 총 {len(results)})"
        except Exception as e:
            with self._lock:
                self.current_msg = f"오류 발생: {e}"
                self.logs.append({
                    "success": False,
                    "text": f"치명적 오류 발생: {e}",
                    "timestamp": time.strftime("%H:%M:%S")
                })
        finally:
            with self._lock:
                self.is_running = False
                self.cancel_requested = False


# 전역 싱글톤 인스턴스
global_job_manager = GlobalJobManager()
