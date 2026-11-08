"""
tests/test_dynamic_aspect_ratio.py
전 포즈 단일 세로형 종횡비(832x1216) 일관성 및 사용자 지정 해상도 계약 테스트:
1. 상반신/바스트/클로즈업 포즈도 1:1 정방형 변질 없이 기본 832x1216 세로형 유지
2. 전신/일상/웨딩 침대 포즈도 기본 832x1216 유지
3. 사용자가 직접 해상도를 명시한 경우 사용자 지정값 우선
4. 실제 포즈 DB 전 구간 832x1216 단일 비율 계약 검증
"""

from dataclasses import dataclass
from plepa_engine.services.generation_service import get_optimal_resolution_for_pose
from plepa_engine.services.pose_service import default_pose_service


@dataclass
class DummyPose:
    code: str
    prompt: str = ""
    sdxl_positive: str = ""
    framing: str = ""


def test_unified_aspect_ratio_close_up():
    """상반신/클로즈업 씬도 비율 파편화 없이 832x1216 세로형을 일관되게 유지."""
    pose_oral = DummyPose(code="T01", prompt="upper body close-up, deepthroat")
    w, h = get_optimal_resolution_for_pose(pose_oral, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (832, 1216)

    pose_focus = DummyPose(code="T03", prompt="face focus, tight bust shot", framing="close_up")
    w, h = get_optimal_resolution_for_pose(pose_focus, default_w=832, default_h=1216, engine="sdxl")
    assert (w, h) == (832, 1216)


def test_unified_aspect_ratio_all_db_poses():
    """실제 포즈 DB의 모든 포즈가 832x1216 단일 비율을 유지하는지 계약 검증."""
    db = default_pose_service.load_pose_db(engine="sdxl")
    for wp in db.values():
        w, h = get_optimal_resolution_for_pose(wp, default_w=832, default_h=1216, engine="sdxl")
        assert (w, h) == (832, 1216), f"포즈 {wp.code}({wp.label})는 세로형(832x1216)이어야 합니다."


def test_dynamic_aspect_ratio_user_specified():
    """사용자가 해상도를 직접 지정한 경우 사용자 지정값 유지."""
    pose_oral = DummyPose(code="T01", prompt="upper body close-up")
    w, h = get_optimal_resolution_for_pose(
        pose_oral, default_w=768, default_h=1344, engine="sdxl", user_specified=True
    )
    assert (w, h) == (768, 1344)
