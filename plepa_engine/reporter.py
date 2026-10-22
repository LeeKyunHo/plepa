"""
plepa_engine.reporter
콘솔 리포트 출력 및 젠잇(Gen-IT) 마크다운 자동 조립 모듈.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from plepa_engine.models import GenerationResult, PoseEntry

SEPARATOR = "═" * 70



def get_subfolder_for_code(code: str | int) -> str:
    """
    포즈 코드에 따른 V3 에셋 대역별 서브폴더명을 반환합니다:
    - 000~019 -> '01_emotions' (감정표현)
    - 020~050 -> '02_daily' (범용 일상)
    - 051~059 -> '03_events' (로스터 이벤트)
    - 060~079 -> '04_romance' (로맨스 & 공용 구강)
    - 080~129, 150~199 -> '05_h_scenes' (범용 H씬 체위)
    - 130~139, 200~209 -> '06_special_h' (로스터 특색 이벤트 H씬)
    """
    try:
        c = int(str(code).strip())
    except (ValueError, TypeError):
        return "02_daily"

    if 0 <= c <= 19:
        return "01_emotions"
    elif 20 <= c <= 50:
        return "02_daily"
    elif 51 <= c <= 59:
        return "03_events"
    elif 60 <= c <= 79:
        return "04_romance"
    elif (80 <= c <= 129) or (150 <= c <= 199):
        return "05_h_scenes"
    elif (130 <= c <= 139) or (200 <= c <= 209):
        return "06_special_h"
    else:
        return "05_h_scenes" if c >= 80 else "02_daily"

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
    try:
        code_str = f"{int(code):03d}"
    except ValueError:
        code_str = str(code).strip().upper()
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
    char_name: Optional[str] = None,
) -> None:
    """배치 생성 결과 요약 콘솔 출력."""
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count
    qc_problem_results = [r for r in results if r.success and not r.qc_passed]
    qc_problem_count = len(qc_problem_results)
    display_name = f"{char_name} ({prefix})" if char_name else prefix

    print("\n" + SEPARATOR)
    print(f"  [플에파] {display_name} 배치 생성 완료 보고서")
    print(SEPARATOR)
    print(f"• 저장 경로: {save_dir}")
    print(f"• 생성 결과: 성공 {success_count}개 / 실패 {fail_count}개 (총 {len(results)}개)")
    if qc_problem_count > 0:
        print(f"• ⚠️ Auto-QC 결함(재시도 한도 초과): {qc_problem_count}개 이미지에서 문제 발생")
    else:
        print(f"• Auto-QC 상태: 전수 정상 합격 (결함 0개)")
    print(f"• 총 소요 시간: {total_duration_sec:.1f}초 (평균 장당 {total_duration_sec/max(1, len(results)):.1f}초)")

    if fail_count > 0:
        print("\n[생성 실패 목록]")
        for r in results:
            if not r.success:
                print(f"  - [{r.target.code}] {r.target.label}: {r.error_message}")

    if qc_problem_count > 0:
        print(f"\n[⚠️ Auto-QC 리롤 한도 초과 결함 목록 (확인 및 수정 권장: 총 {qc_problem_count}건)]")
        for r in qc_problem_results:
            print(f"  - [{r.target.code}] {r.target.label}: {r.qc_reason} (최대 재시도 {r.retries}회 초과 후 강제 저장됨)")
        print(f"\n💡 [권장 사항] {display_name}의 위 {qc_problem_count}개 포즈는 3회 이상 리롤에도 결함이 해결되지 않았습니다.")
        print(f"   포즈 프롬프트 또는 캐릭터 외형 태그 간의 충돌 여부를 점검하고 프롬프트 수정을 권장합니다.")

    print(SEPARATOR + "\n")


def print_overall_batch_summary(
    results: Sequence[GenerationResult],
    total_duration_sec: float,
) -> None:
    """모든 캐릭터 배치 생성이 종료된 후 종합 결과 및 포즈 수정 권장 리포트 출력."""
    if not results:
        return

    # 캐릭터별 그룹화
    by_char: Dict[str, List[GenerationResult]] = {}
    char_names: Dict[str, str] = {}
    for r in results:
        prefix = getattr(r.target, "character_prefix", None) or "unknown"
        name = getattr(r.target, "character_name", None) or prefix
        by_char.setdefault(prefix, []).append(r)
        char_names[prefix] = name

    total_chars = len(by_char)
    total_images = len(results)
    total_success = sum(1 for r in results if r.success)
    total_fails = total_images - total_success
    all_qc_problems = [r for r in results if r.success and not r.qc_passed]
    total_qc_problems = len(all_qc_problems)

    chars_desc = ", ".join(f"{char_names[p]}({p})" for p in by_char)

    banner = "═" * 80
    sub_banner = "─" * 80

    print("\n" + banner)
    print("  [플에파] 전체 캐릭터 에셋 제작 최종 종합 보고서")
    print(banner)
    print(f"• 작업 대상 캐릭터: 총 {total_chars}명 ({chars_desc})")
    print(f"• 총 생성 이미지: {total_images}개 (정상: {total_success - total_qc_problems}개, QC 결함 경고: {total_qc_problems}개, 생성 실패: {total_fails}개)")
    print(f"• 전체 소요 시간: {total_duration_sec:.1f}초")

    # 문제가 있는 캐릭터별 분류
    chars_with_qc_issues: Dict[str, List[GenerationResult]] = {}
    chars_with_failures: Dict[str, List[GenerationResult]] = {}

    for prefix, char_res in by_char.items():
        qc_fails = [r for r in char_res if r.success and not r.qc_passed]
        if qc_fails:
            chars_with_qc_issues[prefix] = qc_fails
        fails = [r for r in char_res if not r.success]
        if fails:
            chars_with_failures[prefix] = fails

    if chars_with_failures:
        print("\n" + sub_banner)
        print(f"❌ [생성 실패 에셋 목록] (총 {sum(len(v) for v in chars_with_failures.values())}건)")
        for prefix, fails in chars_with_failures.items():
            c_name = char_names.get(prefix, prefix)
            print(f"  • {c_name} ({prefix}) - {len(fails)}건 실패:")
            for r in fails:
                print(f"    - [{r.target.code}] {r.target.label}: {r.error_message}")

    if chars_with_qc_issues:
        print("\n" + sub_banner)
        print(f"⚠️ [Auto-QC 리롤 한도 초과 결함 목록 (포즈 수정 강력 권장)] (총 {total_qc_problems}건)")
        for prefix, issues in chars_with_qc_issues.items():
            c_name = char_names.get(prefix, prefix)
            print(f"  • {c_name} ({prefix}) - 총 {len(issues)}건 결함 발생:")
            for r in issues:
                print(f"    - [{r.target.code}] {r.target.label}: {r.qc_reason} (최대 재시도 초과 후 저장됨)")

        print("\n" + sub_banner)
        print("📢 [에이전트 권장 조치사항]")
        print("위에서 보고된 캐릭터별 포즈들은 3회 이상 자동 재시도(리롤) 후에도 Auto-QC 기준을 충족하지 못하고")
        print("결함(남성 모브 얼굴 노출, 색감 과포화, 성기 미탐지 등)이 있는 상태로 저장되었습니다.")
        print("해당 포즈의 프롬프트(`data/sdxl_pose_database.json` 또는 각 로스터의 `pose_overrides.json`)를")
        print("점검하고 충돌 태그를 수정하여 품질을 개선할 것을 강력히 권장합니다.")
    elif not chars_with_failures:
        print("\n" + sub_banner)
        print("✨ 축하합니다! 모든 캐릭터의 에셋이 결함 없이 100% 정상 품질로 완성되었습니다! (QC 결함 0건)")

    print(banner + "\n")
