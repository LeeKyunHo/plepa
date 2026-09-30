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
URL_PLACEHOLDER = "{{url}}"


def asset_filename(prefix: str, code: str) -> str:
    """플에파 에셋 파일명 형식: prefix_code.webp"""
    # 2자리 이상 유지 (예: 00, 01, 140)
    return f"{prefix}_{code}.webp"


def build_genit_block(
    prefix: str,
    results: Sequence[GenerationResult],
    pose_map: Dict[str, PoseEntry],
) -> str:
    """
    젠잇(Gen-IT) 호환 마크다운 블록 조립.
    """
    successful_results = [r for r in results if r.success]
    if not successful_results:
        return ""

    codes = [r.target.code for r in successful_results]
    urls = [f"{URL_PLACEHOLDER}{prefix}/{asset_filename(prefix, c)}" for c in codes]
    calls = "\n".join(urls)
    files = "\n".join(
        f"- `{url}` ({pose_map[c].label if c in pose_map else '미상'})"
        for c, url in zip(codes, urls)
    )

    guide_lines = []
    current_sec = None
    for r in successful_results:
        c = r.target.code
        sec = r.target.section
        label = r.target.label
        if sec != current_sec:
            current_sec = sec
            guide_lines.append(f"\n[{sec}]")
        guide_lines.append(f"  {label:<26} -> {asset_filename(prefix, c)}")
    guide = "\n".join(guide_lines).strip()

    status_template = f"""[캐릭터이름: {prefix}]
[직책: 직책입력]
[호감도: 0/100]
[의상: 착의상태]
[현재위치: 장소입력]
[심리상태: 감정상태]
[외형특징: {prefix} 주요외형]"""

    return f"""
{SEPARATOR}
  젠잇(Gen-IT) 복사용 플에파 에셋 블록 | {prefix}   (총 {len(successful_results)}개)
{SEPARATOR}

### {prefix} 이미지 호출 코드
{calls}

### {prefix} 파일 목록
{files}

### {prefix} 상태 매핑 가이드
{guide}

### {prefix} 상태창 템플릿
{status_template}
{SEPARATOR}
"""


def open_in_explorer(path: Path) -> None:
    """완료 시 결과 폴더를 윈도우 파일 탐색기로 자동 오픈."""
    if os.name == "nt" and path.exists():
        try:
            os.startfile(path)
        except OSError:
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
