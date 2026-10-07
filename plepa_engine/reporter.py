"""
plepa_engine.reporter
콘솔 리포트 출력 및 젠잇(Gen-IT) 마크다운 자동 조립 모듈.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Sequence
from plepa_engine.models import GenerationResult, PoseEntry

SEPARATOR = "═" * 70


def asset_filename(
    prefix: str,
    code: str | int,
    label: str = "",
    naming: str = "hybrid",
) -> str:
    """
    플에파 에셋 파일명 형식:
    - hybrid: prefix_000_평상.webp (기본 권장값: 000~159 순서 정렬 + 한글 직관성 동시 확보)
    - code: prefix_000.webp (기존 3자리 번호형)
    - label: prefix_평상.webp (순수 한글형)
    """
    code_str = f"{int(code):03d}"
    clean_label = label.strip().replace(" ", "_").replace("/", "_")
    if naming == "code" or not clean_label:
        return f"{prefix}_{code_str}.webp"
    elif naming == "label":
        return f"{prefix}_{clean_label}.webp"
    else:  # hybrid
        return f"{prefix}_{code_str}_{clean_label}.webp"


def open_in_explorer(path: Path | str) -> None:
    """완료 시 결과 폴더 또는 파일을 윈도우 파일 탐색기로 확실히 오픈."""
    if os.name == "nt":
        import subprocess
        target = Path(path).resolve()
        try:
            if target.is_file():
                # 파일인 경우 탐색기에서 해당 파일 선택 상태로 열기
                subprocess.Popen(["explorer.exe", f"/select,{str(target)}"])
            else:
                target.mkdir(parents=True, exist_ok=True)
                subprocess.Popen(["explorer.exe", str(target)])
            return
        except Exception:
            pass
        try:
            os.startfile(str(target if not target.is_file() else target.parent))
        except Exception:
            pass


def print_batch_summary(
    prefix: str,
    results: Sequence[GenerationResult],
    save_dir: Path,
    total_duration_sec: float,
) -> None:
    """배치 생성 결과 요약 콘솔 출력."""
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count

    print("\n" + SEPARATOR)
    print(f"  [플에파] {prefix} 배치 생성 완료 보고서")
    print(SEPARATOR)
    print(f"• 저장 경로: {save_dir}")
    print(f"• 성공: {success_count}개 / 실패: {fail_count}개 (총 {len(results)}개)")
    print(f"• 총 소요 시간: {total_duration_sec:.1f}초 (평균 장당 {total_duration_sec/max(1, len(results)):.1f}초)")

    if fail_count > 0:
        print("\n[실패 목록]")
        for r in results:
            if not r.success:
                print(f"  - [{r.target.code}] {r.target.label}: {r.error_message}")
    print(SEPARATOR + "\n")
