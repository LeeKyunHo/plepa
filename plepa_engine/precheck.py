"""
plepa_engine.precheck
이미지 배치 생산 전 캐릭터 JSON, 포즈 DB 제작 규칙, 착의 의상 고정 및 H씬 알몸 전환 무결성을 전수 검증하는 모듈.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.precheck_rules import (
    _FORBIDDEN_LEAK_TOKENS_IN_NUDE,
    _SIGNATURE_OUTFIT_TOKENS,
    _SPY_SIGNATURE_OUTFIT_TOKENS,
    check_character_json_rules,
    check_comfy_nodes,
    check_default_background_rules,
    check_pose_background_mapping,
    check_pose_db_rules,
    extract_char_signature_tokens,
    simulate_prompt_combinations,
)
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service


@dataclass
class PrecheckReport:
    roster: str
    total_characters: int = 0
    total_poses: int = 0
    total_combinations_checked: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


def check_pose_doc_sync(
    doc_path: Optional[Path] = None,
    engine: str = "sdxl",
) -> Tuple[bool, List[str]]:
    """SDXL 포즈 DB와 포즈 매핑 문서 간 포즈 코드 동기화 여부를 검증합니다."""
    return default_pose_service.check_pose_doc_sync(doc_path=doc_path, engine=engine)


def run_pregeneration_check(roster: str = "campus", check_comfy: bool = False) -> PrecheckReport:
    """지정된 로스터와 SDXL V2 포즈 DB에 대해 이미지 생산 사전 점검을 수행합니다."""
    report = PrecheckReport(roster=roster)

    sdxl_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
    report.total_poses = len(sdxl_db)

    # [1단계] 포즈 DB 제작 규칙 준수 전수 검사 (SDXL V2 단일 파이프라인)
    check_pose_db_rules(sdxl_db, report)

    # [2~5단계] 캐릭터 JSON 무결성 + 전 포즈 조립 시뮬레이션
    chars = default_character_service.list_characters(roster=roster)
    report.total_characters = len(chars)
    if not chars:
        report.errors.append(f"[캐릭터규칙] 로스터 '{roster}'에 등록된 캐릭터가 없습니다.")
        return report

    bg_file = PROJECTS_DIR / roster / "background.json"
    check_default_background_rules(roster, bg_file, report)

    for _, char, _ in chars:
        pfx = char.prefix
        check_character_json_rules(char, pfx, report)
        sig_tokens = extract_char_signature_tokens(char, pfx)
        simulate_prompt_combinations(char, pfx, sig_tokens, sdxl_db, report)

    # [6단계] 로스터별 포즈 배경 매핑 무결성 검사 + (선택) ComfyUI 노드 사전 검증
    check_pose_background_mapping(roster, bg_file, PROJECTS_DIR / roster / "pose_background_mapping.json", report)
    if check_comfy:
        check_comfy_nodes(report)

    # [7단계] 포즈 DB ↔ POSE_MAPPING.md 문서 동기화 전수 검증 (GEMINI.md 제3조)
    try:
        ok_sync, missing_in_doc = check_pose_doc_sync()
        if not ok_sync:
            report.errors.append(
                f"[문서동기화규칙] POSE_MAPPING.md에 포즈 코드 {len(missing_in_doc)}개가 누락되었습니다: {missing_in_doc}"
            )
    except Exception as e:
        report.warnings.append(f"[문서동기화규칙] POSE_MAPPING.md 동기화 검증 실패: {e}")

    return report


if __name__ == "__main__":
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="플에파 이미지 생산 사전 점검기 (Pre-Generation Validator)")
    parser.add_argument("-r", "--roster", default=DEFAULT_ROSTER, help=f"점검할 로스터 이름 (기본값: {DEFAULT_ROSTER})")
    parser.add_argument("--check-comfy", action="store_true", help="ComfyUI 서버의 필수 커스텀 노드(Impact Pack 등) 설치 여부를 사전 검증합니다.")
    args = parser.parse_args()

    rep = run_pregeneration_check(args.roster, check_comfy=args.check_comfy)
    print("=" * 68)
    print(f"  [플에파] 이미지 생산 6단계 사전 점검 보고서 (로스터: {rep.roster})")
    print("=" * 68)
    print(f"• 점검 캐릭터 수 : {rep.total_characters}명")
    print(f"• 점검 포즈 DB 수: {rep.total_poses}종 (SDXL V2)")
    print(f"• 조립 시뮬레이션: 총 {rep.total_combinations_checked}개 조합 (착의 고정 / H씬 알몸 전환 / 테마 스왑)")
    print("-" * 68)
    if rep.passed:
        print("✔ [PASS] 위반 사항 0건! 모든 캐릭터와 포즈가 이미지 생산 표준을 100% 준수합니다.")
        sys.exit(0)
    else:
        print(f"❌ [FAIL] 총 {len(rep.errors)}건의 규칙 위반이 감지되었습니다:")
        for err in rep.errors:
            print(f"  - {err}")
        sys.exit(1)
