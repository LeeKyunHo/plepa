"""
plepa_engine.graph_builder
ComfyUI 노드 그래프 동적 구성을 위한 경량 GraphBuilder 모듈.
하드코딩된 노드 ID 문자열 상수를 탈피하고, 다중 LoRA/ControlNet/Inpaint 노드를 레고 블록처럼 동적으로 체이닝합니다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union



class WorkflowGraph:
    """
    ComfyUI /prompt 엔드포인트 전송용 노드 그래프를 동적으로 구성하는 경량 빌더.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._counter: int = 0

    @property
    def node_count(self) -> int:
        return self._counter

    def add_node(self, class_type: str, **inputs: Any) -> str:
        """
        신규 노드를 등록하고 유일한 자동 증가 문자열 ID를 반환합니다.
        """
        self._counter += 1
        node_id = str(self._counter)
        self._nodes[node_id] = {
            "class_type": class_type,
            "inputs": dict(inputs),
        }
        return node_id

    def out(self, node_id: str, slot: int = 0) -> List[Union[str, int]]:
        """
        다른 노드의 입력 슬롯에 연결하기 위한 노드 출력 참조([node_id, slot_index])를 반환합니다.
        """
        return [str(node_id), slot]

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """등록된 특정 노드의 원본 딕셔너리를 조회합니다."""
        return self._nodes.get(str(node_id))

    def update_inputs(self, node_id: str, **kwargs: Any) -> None:
        """기존 노드의 입력 값을 갱신합니다."""
        nid = str(node_id)
        if nid in self._nodes:
            self._nodes[nid]["inputs"].update(kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """ComfyUI API 전송용 최종 딕셔너리를 반환합니다."""
        return self._nodes
