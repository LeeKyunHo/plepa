"""
tests/test_dynamic_aspect_ratio.py
포즈별 동적 종횡비(Dynamic Aspect Ratio) 할당 및 화각 보정 로직 단위 테스트:
1. 상반신/바스트/클로즈업 포즈는 기본 규격 대신 1024x1024 정방형 반환
2. 전신/일상 포즈는 기본 832x1216 유지
3. 사용자가 직접 해상도를 명시한 경우 사용자 지정값 우선
"""

from dataclasses import dataclass
import pytest
from plepa_engine.services.generation_service import get_optimal_resolution_for_pose


@dataclass
class DummyPose:
    code: str
    prompt: str = ""
    sdxl_positive: str = ""


def test_dynamic_aspect_ratio_close_up():
    """상반신/클로즈업 씬은 1024x1024 자동 할당."""
    # 067번 딥스로트 (구강)
    pose_oral = DummyPose(code="067", prompt="upper body close-up, deepthroat")
    w, h = get_optimal_resolution_for_pose(pose_oral, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (1024, 1024)

    # 095번 파이즈리
    pose_paizuri = DummyPose(code="095", prompt="paizuri, chest focus")
    w, h = get_optimal_resolution_for_pose(pose_paizuri, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (1024, 1024)

    # 프롬프트에 face focus 가 포함된 경우
    pose_focus = DummyPose(code="048", prompt="face focus, tight bust shot")
    w, h = get_optimal_resolution_for_pose(pose_focus, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (1024, 1024)


def test_dynamic_aspect_ratio_full_body():
    """일반 전신/일상 포즈는 기본 832x1216 유지."""
    pose_daily = DummyPose(code="020", prompt="standing, full body, waving hand")
    w, h = get_optimal_resolution_for_pose(pose_daily, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (832, 1216)


def test_dynamic_aspect_ratio_user_specified():
    """사용자가 해상도를 직접 지정한 경우 동적 전환 없이 사용자 지정값 유지."""
    pose_oral = DummyPose(code="067", prompt="upper body close-up, deepthroat")
    w, h = get_optimal_resolution_for_pose(
        pose_oral, default_w=768, default_h=1344, engine="sdxl", user_specified=True
    )
    assert (w, h) == (768, 1344)
