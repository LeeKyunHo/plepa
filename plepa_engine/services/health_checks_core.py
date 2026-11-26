"""
plepa_engine.services.health_checks_core
10단계 시스템 통합 무결성 진단 중 1~5단계(포즈 DB, 캐릭터, 프롬프트 파이프라인, 사전점검, 워크플로우) 구현 모듈.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List

from plepa_engine.checkpoint_service import CheckpointService
from plepa_engine.config import DEFAULT_SDXL_CKPT
from plepa_engine.prompt_builder import assemble_sdxl_prompt, clamp_sdxl_weights
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service


@dataclass
class DiagnosticResult:
    """단일 진단 항목 결과."""
    stage_index: int
    category: str
    name: str
    status: str  # "PASS", "WARN", "FAIL"
    message: str
    duration_ms: float
    details: List[str] = field(default_factory=list)

    @property
    def is_pass(self) -> bool:
        return self.status == "PASS"

    @property
    def is_warn(self) -> bool:
        return self.status == "WARN"

    @property
    def is_fail(self) -> bool:
        return self.status == "FAIL"


def run_stage_1_pose_db() -> DiagnosticResult:
    """1단계: SDXL 포즈 데이터베이스 및 프리셋(sample10, campus_108 등) 무결성 검증."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
        total_poses = len(db)
        details.append(f"SDXL 포즈 데이터베이스 총 {total_poses}종 로드 완료")
        if total_poses < 80:
            raise ValueError(f"포즈 항목 수가 기준(80종) 미만입니다: {total_poses}개")

        for a in ("000", "080", "150"):
            if a not in db:
                raise KeyError(f"핵심 앵커 포즈 '{a}'가 DB에 누락되었습니다.")
        details.append("핵심 앵커 포즈 (000 스탠딩, 080 누드/H씬, 150 오토코노코) 존재 확인")

        sample10_codes = default_pose_service.resolve_pose_codes("sample10", db)
        if len(sample10_codes) != 10:
            raise ValueError(f"'sample10' 프리셋이 10종이 아닌 {len(sample10_codes)}종으로 해석됨")
        details.append(f"'sample10' 골든 샘플러 프리셋 해석 성공 ({len(sample10_codes)}종)")

        campus_codes = default_pose_service.resolve_pose_codes("campus_108", db)
        if len(campus_codes) < 100:
            raise ValueError(f"'campus_108' 프리셋 수량 이상: {len(campus_codes)}종")
        details.append(f"'campus_108' 마스터 세트 해석 성공 ({len(campus_codes)}종)")

        return DiagnosticResult(
            stage_index=1,
            category="포즈 DB & 프리셋",
            name="SDXL 포즈 DB 및 프리셋 세트 무결성",
            status="PASS",
            message=f"포즈 {total_poses}종 및 프리셋(sample10 외) 전수 무결",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=1,
            category="포즈 DB & 프리셋",
            name="SDXL 포즈 DB 및 프리셋 세트 무결성",
            status="FAIL",
            message=f"포즈 DB 진단 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def run_stage_2_characters_rosters() -> DiagnosticResult:
    """2단계: 캐릭터 설정 및 로스터 무결성 검증 (접두사 고유성, 필수 외형 필드)."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        rosters = default_character_service.list_rosters(include_legacy=False)
        legacy_rosters = [r for r in default_character_service.list_rosters(include_legacy=True) if r not in rosters]
        details.append(f"활성 로스터: {', '.join(rosters)}" + (f" (레거시 분리: {', '.join(legacy_rosters)})" if legacy_rosters else ""))

        chars = default_character_service.list_characters(roster="campus")
        if not chars:
            raise ValueError("기본 'campus' 로스터에 등록된 캐릭터가 없습니다.")
        prefixes = set()
        for _, c_schema, _ in chars:
            if not c_schema.prefix:
                raise ValueError(f"캐릭터 '{c_schema.name}'에 prefix가 누락되었습니다.")
            if c_schema.prefix in prefixes:
                raise ValueError(f"중복된 prefix 발견: '{c_schema.prefix}'")
            prefixes.add(c_schema.prefix)
            if not c_schema.appearance or not c_schema.appearance.face_and_hair or not c_schema.appearance.physique:
                raise ValueError(f"캐릭터 '{c_schema.name}' 필수 외형 필드 누락")
        details.append(f"기본 'campus' 로스터 {len(chars)}명 캐릭터 외형 필드 및 prefix 고유성 검증 완료")

        if "spy" in rosters:
            spy_chars = default_character_service.list_characters(roster="spy")
            details.append(f"'spy' 로스터 {len(spy_chars)}명 캐릭터 로드 성공")

        return DiagnosticResult(
            stage_index=2,
            category="캐릭터 & 로스터",
            name="캐릭터 프로필 및 로스터 설정 무결성",
            status="PASS",
            message=f"로스터 {len(rosters)}개, 'campus' {len(chars)}명 전원 유효",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=2,
            category="캐릭터 & 로스터",
            name="캐릭터 프로필 및 로스터 설정 무결성",
            status="FAIL",
            message=f"캐릭터/로스터 진단 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def run_stage_3_prompt_pipeline() -> DiagnosticResult:
    """3단계: SDXL 단일 파이프라인 프롬프트 조립, 의상 착의/탈의 분기, 오토코노코 및 가중치 클램핑 검증."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        char, _ = default_character_service.find_character("sample_character", roster="campus")
        db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

        pos_clothed, _, nude_flag = assemble_sdxl_prompt(char, db["000"])
        if nude_flag:
            raise ValueError("평상 포즈(000)에서 비정상 누드 플래그 활성화")
        if char.appearance.outfit and char.appearance.outfit not in pos_clothed:
            raise ValueError("평상 포즈(000)에서 기본 의상 태그 누락")
        details.append("평상복(000) 의상 유지 및 착의 조립 정상")

        pos_nude, _, nude_flag_h = assemble_sdxl_prompt(char, db["080"])
        if not nude_flag_h or "nude" not in pos_nude:
            raise ValueError("H씬 포즈(080)에서 누드 판정 또는 nude 태그 주입 실패")
        details.append("H씬(080) 자동 탈의 스트리핑 및 nude 태그 주입 정상")

        assemble_sdxl_prompt(char, db["150"])
        details.append("오토코노코 씬(150) 프롬프트 조립 성공")

        clamped = clamp_sdxl_weights("solo, (smile:1.9), ((masterpiece:2.5))")
        if ":1.9" in clamped or ":2.5" in clamped:
            raise ValueError(f"SDXL 가중치 클램핑 실패: {clamped}")
        details.append("가중치 클램핑(clamp_sdxl_weights) 안전 범위 제한 정상")

        profile = CheckpointService().get_profile_for_checkpoint(DEFAULT_SDXL_CKPT)
        if not profile.quality_positive or not profile.quality_negative:
            raise ValueError("기본 체크포인트 품질 태그 로드 실패")
        details.append(f"체크포인트 '{DEFAULT_SDXL_CKPT}' 전용 품질 태그 연동 정상")

        return DiagnosticResult(
            stage_index=3,
            category="프롬프트 파이프라인",
            name="SDXL 조립기 · 착의/탈의 분기 · 가중치 클램퍼",
            status="PASS",
            message="의상 착의/탈의 분기 및 태그 클램핑 무결",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=3,
            category="프롬프트 파이프라인",
            name="SDXL 조립기 · 착의/탈의 분기 · 가중치 클램퍼",
            status="FAIL",
            message=f"프롬프트 파이프라인 진단 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def run_stage_4_precheck() -> DiagnosticResult:
    """4단계: 이미지 생산 사전 점검 (캐릭터 × 포즈 조합 전수 시뮬레이션)."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        from plepa_engine.precheck import run_pregeneration_check
        report = run_pregeneration_check("campus")
        details.append(
            f"사전 점검 완료: 캐릭터 {report.total_characters}명 × 포즈 {report.total_poses}종 = {report.total_combinations_checked}개 조합"
        )
        if not report.passed:
            err_msg = "\n".join(report.errors[:3])
            raise ValueError(f"사전 점검 불합격 (총 {len(report.errors)}건 오류): {err_msg}")
        return DiagnosticResult(
            stage_index=4,
            category="사전 점검",
            name="이미지 생산 사전 무결성 점검 (Precheck)",
            status="PASS",
            message=f"{report.total_combinations_checked}개 조합 무결성 100% 합격",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=4,
            category="사전 점검",
            name="이미지 생산 사전 무결성 점검 (Precheck)",
            status="FAIL",
            message=f"사전 점검 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def run_stage_5_workflows(build_workflow_fn: Callable[..., dict]) -> DiagnosticResult:
    """5단계: SDXL 워크플로우 템플릿(기본, Face Detailer, IP-Adapter, 시드 주입) 무결성 검증."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        wf = build_workflow_fn("test pos", "test neg", "test_prefix", use_face_detailer=True)
        node_classes = {n.get("class_type") for n in wf.values() if isinstance(n, dict)}
        missing = {"CheckpointLoaderSimple", "KSampler", "SaveImage", "FaceDetailer"} - node_classes
        if missing:
            raise ValueError(f"기본 SDXL 워크플로우에 필수 노드 누락: {missing}")
        details.append("SDXL 기본 + Face Detailer 워크플로우 노드 그래프 유효")

        wf_ip = build_workflow_fn("test pos", "test neg", "test_prefix", ref_image_name="test_ref.webp", ref_weight=0.65)
        node_classes_ip = {n.get("class_type") for n in wf_ip.values() if isinstance(n, dict)}
        missing_ip = {"IPAdapterUnifiedLoader", "PrepImageForClipVision", "IPAdapterAdvanced"} - node_classes_ip
        if missing_ip:
            raise ValueError(f"IP-Adapter 워크플로우에 필수 노드 누락: {missing_ip}")
        details.append("SDXL IP-Adapter 결합 노드 그래프 유효")

        ksampler_found = any(
            node.get("class_type") == "KSampler" and ("seed" in node.get("inputs", {}) or "noise_seed" in node.get("inputs", {}))
            for node in wf.values()
        )
        if not ksampler_found:
            raise ValueError("KSampler 노드에서 시드(seed) 파라미터를 찾을 수 없음")
        details.append("KSampler 골든 시드 주입 및 제어 가능 여부 검증 완료")

        return DiagnosticResult(
            stage_index=5,
            category="워크플로우 템플릿",
            name="SDXL 워크플로우 노드 그래프 및 파라미터 바인딩",
            status="PASS",
            message="KSampler · Face Detailer · IP-Adapter 노드 바인딩 정상",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=5,
            category="워크플로우 템플릿",
            name="SDXL 워크플로우 노드 그래프 및 파라미터 바인딩",
            status="FAIL",
            message=f"워크플로우 템플릿 진단 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )
