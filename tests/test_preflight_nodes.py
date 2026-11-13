"""
tests/test_preflight_nodes.py
ComfyUI 필수 커스텀 노드 사전 감지(Pre-flight Node Inspection) 기능 단위 테스트.
서버 실제 호출 없이 Mock을 기반으로 100% 오프라인 고속 검증을 수행합니다.
"""

from unittest.mock import MagicMock, patch
import pytest

from plepa_engine.comfy_client import ComfyClient, verify_required_nodes
from plepa_engine.precheck import run_pregeneration_check
from plepa_engine.workflow_templates import REQUIRED_CUSTOM_NODES


def test_required_custom_nodes_defined():
    """필수 커스텀 노드 상수가 핵심 패키지와 함께 정상 정의되어 있는지 검증."""
    assert "FaceDetailer" in REQUIRED_CUSTOM_NODES
    assert REQUIRED_CUSTOM_NODES["FaceDetailer"] == "ComfyUI-Impact-Pack"
    assert "UltralyticsDetectorProvider" in REQUIRED_CUSTOM_NODES
    assert "IPAdapterUnifiedLoader" in REQUIRED_CUSTOM_NODES
    assert REQUIRED_CUSTOM_NODES["IPAdapterUnifiedLoader"] == "ComfyUI_IPAdapter_plus"


def test_check_missing_custom_nodes_all_present():
    """모든 필수 노드가 ComfyUI에 등록되어 있는 경우 누락 목록이 비어 있어야 함."""
    client = ComfyClient()
    mock_registered = set(REQUIRED_CUSTOM_NODES.keys()) | {"CheckpointLoaderSimple", "KSampler"}

    with patch.object(client, "check_connection", return_value=True):
        with patch.object(client, "get_registered_node_names", return_value=mock_registered):
            missing = client.check_missing_custom_nodes()
            assert missing == {}


def test_check_missing_custom_nodes_detects_missing():
    """FaceDetailer 등 특정 노드가 누락된 경우 해당 노드명과 패키지명이 정확히 추출되어야 함."""
    client = ComfyClient()
    # FaceDetailer가 누락된 환경 시뮬레이션
    mock_registered = {"UltralyticsDetectorProvider", "CheckpointLoaderSimple"}

    with patch.object(client, "check_connection", return_value=True):
        with patch.object(client, "get_registered_node_names", return_value=mock_registered):
            missing = client.check_missing_custom_nodes()
            assert "FaceDetailer" in missing
            assert missing["FaceDetailer"] == "ComfyUI-Impact-Pack"
            assert "IPAdapterUnifiedLoader" in missing


def test_check_missing_custom_nodes_when_server_offline():
    """ComfyUI 서버가 꺼져 있을 때는 에러 없이 빈 딕셔너리를 반환해야 함."""
    client = ComfyClient()
    with patch.object(client, "check_connection", return_value=False):
        missing = client.check_missing_custom_nodes()
        assert missing == {}


def test_verify_required_nodes_helper():
    """verify_required_nodes 경량 헬퍼 함수가 (성공_여부, 결과_딕셔너리)를 정상 반환하는지 검증."""
    # 1. 서버 오프라인 케이스
    with patch("plepa_engine.comfy_client.ComfyClient.check_connection", return_value=False):
        ok, res = verify_required_nodes()
        assert not ok
        assert "SERVER_UNREACHABLE" in res

    # 2. 누락 노드 감지 케이스
    with patch("plepa_engine.comfy_client.ComfyClient.check_connection", return_value=True):
        with patch(
            "plepa_engine.comfy_client.ComfyClient.check_missing_custom_nodes",
            return_value={"FaceDetailer": "ComfyUI-Impact-Pack"},
        ):
            ok, res = verify_required_nodes()
            assert not ok
            assert "FaceDetailer" in res

    # 3. 모든 노드 정상 등록 케이스
    with patch("plepa_engine.comfy_client.ComfyClient.check_connection", return_value=True):
        with patch(
            "plepa_engine.comfy_client.ComfyClient.check_missing_custom_nodes",
            return_value={},
        ):
            ok, res = verify_required_nodes()
            assert ok
            assert res == {}


def test_precheck_with_check_comfy_integration():
    """precheck 모듈에서 check_comfy=True 옵션 시 누락 노드가 리포트에 등록되는지 검증."""
    with patch(
        "plepa_engine.comfy_client.verify_required_nodes",
        return_value=(False, {"FaceDetailer": "ComfyUI-Impact-Pack"}),
    ):
        report = run_pregeneration_check("campus", check_comfy=True)
        assert any("FaceDetailer" in err and "ComfyUI-Impact-Pack" in err for err in report.errors)
