"""
tests/test_prompt_diagnostics.py
지능형 프롬프트 결함 자가 진단 및 경고 시스템 단위 테스트:
1. GenerationParams에 freeu 및 prompt_alert_threshold가 정상 기본값으로 탑재되어 있는지 검증
2. GENERATION_OPTION_SPECS에 freeu 옵션이 정상 등록되어 있는지 검증
3. build_sdxl_workflow에서 FreeU 노드가 그래프에 자동 체이닝되는지 검증
"""

import pytest
from plepa_engine.services.generation_service import GENERATION_OPTION_SPECS, GenerationParams
from plepa_engine.workflow_templates import build_sdxl_workflow


def test_generation_params_and_specs():
    """새로운 생성 파라미터 및 옵션 스펙 무결성 검증."""
    params = GenerationParams(character_expr="aya", pose_expr="000")
    assert params.freeu is True
    assert params.prompt_alert_threshold == 2

    # GENERATION_OPTION_SPECS에 freeu가 존재하는지 확인
    spec_fields = [s["field"] for s in GENERATION_OPTION_SPECS]
    assert "freeu" in spec_fields
    assert "hand_detailer" in spec_fields
    assert "face_detailer" in spec_fields


def test_build_sdxl_workflow_freeu():
    """build_sdxl_workflow 호출 시 FreeU 노드가 정상 포함되는지 검증."""
    wf_with_freeu = build_sdxl_workflow(
        positive_prompt="1girl, solo",
        negative_prompt="worst quality",
        output_prefix="test",
        use_freeu=True,
    )
    freeu_nodes = [k for k, v in wf_with_freeu.items() if v.get("class_type") == "FreeU"]
    assert len(freeu_nodes) == 1
    freeu_data = wf_with_freeu[freeu_nodes[0]]
    assert freeu_data["inputs"]["b1"] == 1.02
    assert freeu_data["inputs"]["b2"] == 1.03
    assert freeu_data["inputs"]["s1"] == 0.95

    # use_freeu=False 시 FreeU 노드가 없어야 함
    wf_no_freeu = build_sdxl_workflow(
        positive_prompt="1girl, solo",
        negative_prompt="worst quality",
        output_prefix="test",
        use_freeu=False,
    )
    freeu_nodes_off = [k for k, v in wf_no_freeu.items() if v.get("class_type") == "FreeU"]
    assert len(freeu_nodes_off) == 0
