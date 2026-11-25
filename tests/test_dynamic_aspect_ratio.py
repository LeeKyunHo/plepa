"""
tests/test_dynamic_aspect_ratio.py
포즈 대역별 하이브리드 종횡비(감정·초반 포즈 000~024 세로형 832x1216 / 그 외 025+ 가로형 1216x832) 및 사용자 지정 해상도 계약 테스트:
1. 000~024 또는 emotions 섹션은 세로형(832x1216) 유지
2. 025+ 일상·이벤트·로맨스·H씬 포즈는 가로형(1216x832) 자동 전환
3. 사용자가 직접 해상도를 명시한 경우(user_specified=True) 사용자 지정값 우선
4. 실제 포즈 DB 전 구간 하이브리드 비율 계약 검증
"""

from dataclasses import dataclass
from plepa_engine.services.generation_service import (
    get_optimal_resolution_for_pose,
    is_portrait_emotion_pose,
)
from plepa_engine.services.pose_service import default_pose_service


@dataclass
class DummyPose:
    code: str
    prompt: str = ""
    sdxl_positive: str = ""
    framing: str = ""
    section: str = ""


def test_hybrid_aspect_ratio_emotions_vs_others():
    """감정·초반 포즈(000~024 / emotions)는 세로형(832x1216), 그 외(025+)는 가로형(1216x832)을 반환."""
    pose_emo_code = DummyPose(code="003", prompt="blushing, tight bust portrait")
    assert get_optimal_resolution_for_pose(pose_emo_code, default_w=832, default_h=1216, engine="sdxl") == (832, 1216)

    pose_024 = DummyPose(code="024", prompt="looking back", section="poses")
    assert get_optimal_resolution_for_pose(pose_024, default_w=832, default_h=1216, engine="sdxl") == (832, 1216)

    pose_025 = DummyPose(code="025", prompt="lying on sofa", section="poses")
    assert get_optimal_resolution_for_pose(pose_025, default_w=832, default_h=1216, engine="sdxl") == (1216, 832)

    pose_emo_sec = DummyPose(code="A01", prompt="happy smile", section="emotions")
    assert get_optimal_resolution_for_pose(pose_emo_sec, default_w=832, default_h=1216, engine="sdxl") == (832, 1216)

    pose_oral = DummyPose(code="T01", prompt="upper body close-up, deepthroat")
    assert get_optimal_resolution_for_pose(pose_oral, default_w=832, default_h=1216, engine="sdxl") == (1216, 832)

    pose_focus = DummyPose(code="060", prompt="face focus, tight bust shot", framing="close_up", section="romance")
    assert get_optimal_resolution_for_pose(pose_focus, default_w=832, default_h=1216, engine="sdxl") == (1216, 832)


def test_hybrid_aspect_ratio_all_db_poses():
    """실제 포즈 DB의 모든 포즈가 000~024 세로 / 025+ 가로 하이브리드 계약을 준수하는지 검증."""
    db = default_pose_service.load_pose_db(engine="sdxl")
    for wp in db.values():
        w, h = get_optimal_resolution_for_pose(wp, default_w=832, default_h=1216, engine="sdxl")
        expected = (832, 1216) if is_portrait_emotion_pose(wp) else (1216, 832)
        assert (w, h) == expected, f"포즈 {wp.code}({wp.label}) 예상={expected}, 실제={(w, h)}"


def test_dynamic_aspect_ratio_user_specified():
    """사용자가 해상도를 직접 지정한 경우 포즈 번호와 무관하게 사용자 지정값 유지."""
    pose_oral = DummyPose(code="T01", prompt="upper body close-up")
    w, h = get_optimal_resolution_for_pose(
        pose_oral, default_w=768, default_h=1344, engine="sdxl", user_specified=True
    )
    assert (w, h) == (768, 1344)

    pose_emo = DummyPose(code="003", prompt="blushing")
    w2, h2 = get_optimal_resolution_for_pose(
        pose_emo, default_w=1344, default_h=768, engine="sdxl", user_specified=True
    )
    assert (w2, h2) == (1344, 768)
