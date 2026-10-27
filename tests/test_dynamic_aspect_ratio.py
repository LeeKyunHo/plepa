"""
tests/test_dynamic_aspect_ratio.py
포즈별 동적 종횡비(Dynamic Aspect Ratio) 할당 및 화각 보정 로직 단위/계약 테스트:
1. 상반신/바스트/클로즈업 키워드 포즈는 1024x1024 정방형 반환
2. 전신/일상/웨딩 침대 포즈는 기본 832x1216 유지
3. 사용자가 직접 해상도를 명시한 경우 사용자 지정값 우선
4. 실제 포즈 DB 연동 계약 검증
"""

from dataclasses import dataclass
import pytest
from plepa_engine.services.generation_service import get_optimal_resolution_for_pose
from plepa_engine.services.pose_service import default_pose_service


@dataclass
class DummyPose:
    code: str
    prompt: str = ""
    sdxl_positive: str = ""
    framing: str = ""


def test_dynamic_aspect_ratio_close_up():
    """상반신/클로즈업 씬은 1024x1024 자동 할당."""
    pose_oral = DummyPose(code="T01", prompt="upper body close-up, deepthroat")
    w, h = get_optimal_resolution_for_pose(pose_oral, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (1024, 1024)

    pose_paizuri = DummyPose(code="T02", prompt="paizuri, chest focus")
    w, h = get_optimal_resolution_for_pose(pose_paizuri, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (1024, 1024)

    pose_focus = DummyPose(code="T03", prompt="face focus, tight bust shot")
    w, h = get_optimal_resolution_for_pose(pose_focus, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (1024, 1024)


def test_dynamic_aspect_ratio_full_body():
    """일반 전신/일상 및 침대 결합 포즈는 기본 832x1216 유지."""
    pose_daily = DummyPose(code="T10", prompt="standing, full body, waving hand")
    w, h = get_optimal_resolution_for_pose(pose_daily, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (832, 1216)

    # 실제 DB의 웨딩 침대 씬(095) 등이 잘못 정방형으로 강제되지 않고 832x1216을 유지하는지 계약 검증
    db = default_pose_service.load_pose_db(engine="sdxl")
    wedding_poses = [e for e in db.values() if e.required_outfit == "wedding" and e.section == "h_scenes"]
    for wp in wedding_poses:
        w, h = get_optimal_resolution_for_pose(wp, default_w=832, default_h=1216, engine="sdxl")
        assert (w, h) == (832, 1216), f"웨딩 본방 포즈 {wp.code}({wp.label})는 세로형(832x1216)이어야 합니다."


def test_dynamic_aspect_ratio_user_specified():
    """사용자가 해상도를 직접 지정한 경우 동적 전환 없이 사용자 지정값 유지."""
    pose_oral = DummyPose(code="T01", prompt="upper body close-up, deepthroat")
    w, h = get_optimal_resolution_for_pose(
        pose_oral, default_w=768, default_h=1344, engine="sdxl", user_specified=True
    )
    assert (w, h) == (768, 1344)
