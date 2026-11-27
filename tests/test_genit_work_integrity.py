"""
tests.test_genit_work_integrity
Gen-IT 상용 5탭 완성본(docs/genit/*.md)과 로스터 실제 디스크 에셋 간의
글자수 한도, 8대 통일 변수, 포즈 에셋 무결성 연쇄 동기화 상시 검증 테스트.
- 스마트 해시 캐시 기반으로 변경 없는 문서는 0.001초 만에 초고속 패스
"""

from pathlib import Path
from scripts.validate_genit_rules import (
    GENIT_HIDDEN_LIMIT,
    GENIT_PROMPT_COMBINED_LIMIT,
    validate_prompts_section,
)
from scripts.validate_genit_work import run_all_validations


def _build_prompt_section_body(
    main_len: int,
    add_len: int,
    hidden_len: int = 500,
    prologue_len: int = 200,
) -> str:
    """Gen-IT 5탭 프롬프트 길이 검증용 최소 마크다운 본문을 생성합니다."""
    main_text = "A" * main_len
    status_call = "[@id=Status|turn=1|time=낮|location=도서관]"
    prol_text = status_call + ("B" * max(0, prologue_len - len(status_call)))
    hidden_text = "C" * hidden_len
    add_text = "D" * add_len
    return (
        "## 2-0. [메인 프롬프트]\n```text\n"
        f"{main_text}\n```\n\n"
        "## 2-1. [시작 설정 1: 테스트 루트]\n"
        "```text\n테스트 루트\n```\n"
        f"```text\n{prol_text}\n```\n"
        f"```text\n{hidden_text}\n```\n"
        f"```text\n{add_text}\n```\n"
        "```text\n추천 답변\n```\n"
    )


def test_genit_active_works_integrity():
    """docs/genit/ 내 모든 활성(active) 완성본의 5탭 무결성 및 로스터 실존 에셋 정합성 상시 검증."""
    passed = run_all_validations(force_all=False, no_cache=False)
    assert passed is True, "docs/genit/ 내 활성 완성본 중 무결성 검증을 통과하지 못한 문서가 있습니다."


def test_genit_prompt_combined_limit_12000_boundary():
    """메인 + max(추가) == 12,000자(9,500+2,500)는 통과하고, 12,001자(9,501+2,500)는 실패해야 합니다."""
    assert GENIT_PROMPT_COMBINED_LIMIT == 12000

    ok_errors = []
    validate_prompts_section(_build_prompt_section_body(9500, 2500), ok_errors)
    assert ok_errors == []

    fail_errors = []
    validate_prompts_section(_build_prompt_section_body(9501, 2500), fail_errors)
    assert len(fail_errors) == 1
    assert "12,000자 초과" in fail_errors[0]


def test_genit_hidden_prompt_is_independent_buffer():
    """히든 프롬프트(<=2,000자)는 12,000자 합산 한도에 포함되지 않는 독립 버퍼로 동작해야 합니다."""
    assert GENIT_HIDDEN_LIMIT == 2000

    ok_errors = []
    validate_prompts_section(_build_prompt_section_body(9500, 2500, hidden_len=2000), ok_errors)
    assert ok_errors == []

    hidden_fail_errors = []
    validate_prompts_section(_build_prompt_section_body(9500, 2500, hidden_len=2001), hidden_fail_errors)
    assert len(hidden_fail_errors) == 1
    assert "히든 프롬프트 2,000자 초과" in hidden_fail_errors[0]
