"""
tests.test_genit_work_integrity
Gen-IT 상용 5탭 완성본(docs/genit/*.md)과 실제 디스크 에셋 간의
글자수 한도, 6대 통일 변수, 108종 포즈 무결성 연쇄 동기화 상시 검증 테스트.
- 스마트 해시 캐시 기반으로 변경 없는 문서는 0.001초 만에 초고속 패스
"""

from pathlib import Path
from scripts.validate_genit_work import run_all_validations


def test_genit_active_works_integrity():
    """docs/genit/ 내 모든 활성(active) 완성본의 5탭 무결성 및 에셋 108종 정합성 상시 검증."""
    passed = run_all_validations(force_all=False, no_cache=False)
    assert passed is True, "docs/genit/ 내 활성 완성본 중 무결성 검증을 통과하지 못한 문서가 있습니다."
