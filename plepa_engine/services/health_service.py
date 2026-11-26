"""
plepa_engine.services.health_service
플에파 시스템 전체 10단계 통합 무결성 진단 서비스 (HealthService) 호환 파사드.
"""

from __future__ import annotations

from typing import List

from plepa_engine.comfy_client import ComfyClient
from plepa_engine.qa_validator import validate_generated_image
from plepa_engine.services.health_checks_core import (
    DiagnosticResult,
    run_stage_1_pose_db,
    run_stage_2_characters_rosters,
    run_stage_3_prompt_pipeline,
    run_stage_4_precheck,
    run_stage_5_workflows,
)
from plepa_engine.services.health_checks_ops import (
    format_diagnostics_table_impl,
    run_stage_6_censor_engine,
    run_stage_7_auto_qc_manifest,
    run_stage_8_audit_genit,
    run_stage_9_gui_trinity_sync,
    run_stage_10_comfy_connection,
)
from plepa_engine.workflow_templates import build_sdxl_workflow


class HealthService:
    """플에파 10단계 시스템 통합 무결성 진단기."""

    def __init__(self, comfy_host: str = "127.0.0.1:8188"):
        self.comfy_host = comfy_host

    def check_stage_1_pose_db(self) -> DiagnosticResult:
        """1단계: SDXL 포즈 데이터베이스 및 프리셋(sample10, campus_108 등) 무결성 검증."""
        return run_stage_1_pose_db()

    def check_stage_2_characters_rosters(self) -> DiagnosticResult:
        """2단계: 캐릭터 설정 및 로스터 무결성 검증 (접두사 고유성, 필수 외형 필드)."""
        return run_stage_2_characters_rosters()

    def check_stage_3_prompt_pipeline(self) -> DiagnosticResult:
        """3단계: SDXL 단일 파이프라인 프롬프트 조립, 의상 착의/탈의 분기, 오토코노코 및 가중치 클램핑 검증."""
        return run_stage_3_prompt_pipeline()

    def check_stage_4_precheck(self) -> DiagnosticResult:
        """4단계: 이미지 생산 사전 점검 (캐릭터 × 포즈 조합 전수 시뮬레이션)."""
        return run_stage_4_precheck()

    def check_stage_5_workflows(self) -> DiagnosticResult:
        """5단계: SDXL 워크플로우 템플릿(기본, Face Detailer, IP-Adapter, 시드 주입) 무결성 검증."""
        return run_stage_5_workflows(build_sdxl_workflow)

    def check_stage_6_censor_engine(self) -> DiagnosticResult:
        """6단계: 2D 애니 검열 엔진 및 모델 가중치(MobileSAM/YOLO) 상태 점검."""
        return run_stage_6_censor_engine()

    def check_stage_7_auto_qc_manifest(self) -> DiagnosticResult:
        """7단계: Auto-QC 품질 검증기 및 매니페스트 원자적 병합(Merge) 무결성 검증."""
        return run_stage_7_auto_qc_manifest(validate_generated_image)

    def check_stage_8_audit_genit(self) -> DiagnosticResult:
        """8단계: 에셋 완비율 감사기(--audit) 및 Genit 프롬프트 시트 내보내기 검증."""
        return run_stage_8_audit_genit()

    def check_stage_9_gui_trinity_sync(self) -> DiagnosticResult:
        """9단계: CLI · Engine · GUI 삼위일체 동기화 및 FLUX 완전 배제 검증."""
        return run_stage_9_gui_trinity_sync()

    def check_stage_10_comfy_connection(self) -> DiagnosticResult:
        """10단계: ComfyUI 서버(127.0.0.1:8188) 실시간 연결 상태 점검."""
        return run_stage_10_comfy_connection(self.comfy_host, ComfyClient)

    def run_full_diagnostics(self, check_comfy: bool = True) -> List[DiagnosticResult]:
        """10단계 전체 진단을 일괄 순차 실행합니다."""
        stages = [
            self.check_stage_1_pose_db,
            self.check_stage_2_characters_rosters,
            self.check_stage_3_prompt_pipeline,
            self.check_stage_4_precheck,
            self.check_stage_5_workflows,
            self.check_stage_6_censor_engine,
            self.check_stage_7_auto_qc_manifest,
            self.check_stage_8_audit_genit,
            self.check_stage_9_gui_trinity_sync,
        ]
        results = [stage_func() for stage_func in stages]
        if check_comfy:
            results.append(self.check_stage_10_comfy_connection())
        return results


def format_diagnostics_table(results: List[DiagnosticResult]) -> str:
    """진단 결과를 터미널 콘솔에 출력하기 위한 고품질 표 형식 문자열로 변환합니다."""
    return format_diagnostics_table_impl(results)


default_health_service = HealthService()
