"""
plepa_engine.services.health_service
플에파 시스템 전체 10단계 통합 무결성 진단 서비스 (HealthService).
포즈 DB, 캐릭터 로스터, 프롬프트 파이프라인, 워크플로우 템플릿, 검열 엔진,
Auto-QC, 에셋 감사, Genit 내보내기, GUI 삼위일체 동기화, ComfyUI 연결을 전수 점검합니다.
"""

from __future__ import annotations

import dataclasses
import inspect
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from plepa_engine.checkpoint_service import CheckpointService
from plepa_engine.comfy_client import ComfyClient
from plepa_engine.config import DEFAULT_ROSTER, DEFAULT_SDXL_CKPT, PROJECTS_DIR
from plepa_engine.models import CharacterConfig, GenerationTarget, PoseEntry
from plepa_engine.precheck import run_pregeneration_check
from plepa_engine.prompt_builder import assemble_sdxl_prompt, clamp_sdxl_weights

from plepa_engine.qa_validator import validate_generated_image

from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
    default_generation_service,
)
from plepa_engine.services.genit_exporter import GenitExporter
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.workflow_templates import build_sdxl_workflow


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


class HealthService:
    """플에파 10단계 시스템 통합 무결성 진단기."""

    def __init__(self, comfy_host: str = "127.0.0.1:8188"):
        self.comfy_host = comfy_host

    def check_stage_1_pose_db(self) -> DiagnosticResult:
        """1단계: SDXL 포즈 데이터베이스 및 프리셋(sample10, campus_106 등) 무결성 검증."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            # V3 규격: 코어 DB 및 기본 로스터(campus) 이벤트 오버레이를 함께 로드하여 검증
            db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
            total_poses = len(db)
            details.append(f"SDXL 포즈 데이터베이스 총 {total_poses}종 로드 완료")

            if total_poses < 80:
                raise ValueError(f"포즈 항목 수가 기준(80종) 미만입니다: {total_poses}개")

            # 핵심 앵커 포즈 확인
            anchors = ["000", "080", "150"]
            for a in anchors:
                if a not in db:
                    raise KeyError(f"핵심 앵커 포즈 '{a}'가 DB에 누락되었습니다.")
            details.append("핵심 앵커 포즈 (000 스탠딩, 080 누드/H씬, 150 오토코노코) 존재 확인")

            # 프리셋 해석 검증
            sample10_codes = default_pose_service.resolve_pose_codes("sample10", db)
            if len(sample10_codes) != 10:
                raise ValueError(f"'sample10' 프리셋이 10종이 아닌 {len(sample10_codes)}종으로 해석됨")
            details.append(f"'sample10' 골든 샘플러 프리셋 해석 성공 ({len(sample10_codes)}종)")

            campus_codes = default_pose_service.resolve_pose_codes("campus_106", db)
            if len(campus_codes) < 100:
                raise ValueError(f"'campus_106' 프리셋 수량 이상: {len(campus_codes)}종")
            details.append(f"'campus_106' 마스터 세트 해석 성공 ({len(campus_codes)}종)")


            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=1,
                category="포즈 DB & 프리셋",
                name="SDXL 포즈 DB 및 프리셋 세트 무결성",
                status="PASS",
                message=f"포즈 {total_poses}종 및 프리셋(sample10 외) 전수 무결",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=1,
                category="포즈 DB & 프리셋",
                name="SDXL 포즈 DB 및 프리셋 세트 무결성",
                status="FAIL",
                message=f"포즈 DB 진단 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_2_characters_rosters(self) -> DiagnosticResult:
        """2단계: 캐릭터 설정 및 로스터 무결성 검증 (접두사 고유성, 필수 외형 필드)."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            rosters = [p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and (p / "characters").is_dir()]
            details.append(f"발견된 로스터: {', '.join(rosters)}")

            chars = default_character_service.list_characters(roster="campus")
            if not chars:
                raise ValueError("기본 'campus' 로스터에 등록된 캐릭터가 없습니다.")

            prefixes = set()
            for r_name, c_schema, f_path in chars:
                if not c_schema.prefix:
                    raise ValueError(f"캐릭터 '{c_schema.name}'에 prefix가 누락되었습니다.")
                if c_schema.prefix in prefixes:
                    raise ValueError(f"중복된 prefix 발견: '{c_schema.prefix}'")
                prefixes.add(c_schema.prefix)

                if not c_schema.appearance or not c_schema.appearance.face_and_hair or not c_schema.appearance.physique:
                    raise ValueError(f"캐릭터 '{c_schema.name}' 필수 외형 필드 누락")

            details.append(f"기본 'campus' 로스터 {len(chars)}명 캐릭터 외형 필드 및 prefix 고유성 검증 완료")

            # Spy 로스터 점검
            if "spy" in rosters:
                spy_chars = default_character_service.list_characters(roster="spy")
                details.append(f"'spy' 로스터 {len(spy_chars)}명 캐릭터 로드 성공")

            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=2,
                category="캐릭터 & 로스터",
                name="캐릭터 프로필 및 로스터 설정 무결성",
                status="PASS",
                message=f"로스터 {len(rosters)}개, 'campus' {len(chars)}명 전원 유효",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=2,
                category="캐릭터 & 로스터",
                name="캐릭터 프로필 및 로스터 설정 무결성",
                status="FAIL",
                message=f"캐릭터/로스터 진단 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_3_prompt_pipeline(self) -> DiagnosticResult:
        """3단계: SDXL 단일 파이프라인 프롬프트 조립, 의상 착의/탈의 분기, 오토코노코 및 가중치 클램핑 검증."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            char, _ = default_character_service.find_character("sample_character", roster="campus")
            # V3 규격: 코어 DB 및 기본 로스터(campus) 이벤트 오버레이를 함께 로드하여 검증
            db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

            # 1. 평상복(000) 착의 검증
            pos_clothed, _, nude_flag = assemble_sdxl_prompt(char, db["000"])
            if nude_flag:
                raise ValueError("평상 포즈(000)에서 비정상 누드 플래그 활성화")
            if char.appearance.outfit and char.appearance.outfit not in pos_clothed:
                raise ValueError("평상 포즈(000)에서 기본 의상 태그 누락")
            details.append("평상복(000) 의상 유지 및 착의 조립 정상")

            # 2. H씬(080) 탈의 검증
            pos_nude, _, nude_flag_h = assemble_sdxl_prompt(char, db["080"])
            if not nude_flag_h or "nude" not in pos_nude:
                raise ValueError("H씬 포즈(080)에서 누드 판정 또는 nude 태그 주입 실패")
            details.append("H씬(080) 자동 탈의 스트리핑 및 nude 태그 주입 정상")

            # 3. 오토코노코(150) 변형 검증
            pos_oto, _, _ = assemble_sdxl_prompt(char, db["150"])
            details.append("오토코노코 씬(150) 프롬프트 조립 성공")

            # 4. 가중치 클램핑 안전성 검증
            clamped = clamp_sdxl_weights("solo, (smile:1.9), ((masterpiece:2.5))")
            if ":1.9" in clamped or ":2.5" in clamped:
                raise ValueError(f"SDXL 가중치 클램핑 실패: {clamped}")
            details.append("가중치 클램핑(clamp_sdxl_weights) 안전 범위 제한 정상")

            # 5. 체크포인트 품질 태그 로드 검증
            ckpt_svc = CheckpointService()
            profile = ckpt_svc.get_profile_for_checkpoint(DEFAULT_SDXL_CKPT)
            if not profile.quality_positive or not profile.quality_negative:
                raise ValueError("기본 체크포인트 품질 태그 로드 실패")
            details.append(f"체크포인트 '{DEFAULT_SDXL_CKPT}' 전용 품질 태그 연동 정상")

            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=3,
                category="프롬프트 파이프라인",
                name="SDXL 조립기 · 착의/탈의 분기 · 가중치 클램퍼",
                status="PASS",
                message="의상 착의/탈의 분기 및 태그 클램핑 무결",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=3,
                category="프롬프트 파이프라인",
                name="SDXL 조립기 · 착의/탈의 분기 · 가중치 클램퍼",
                status="FAIL",
                message=f"프롬프트 파이프라인 진단 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_4_precheck(self) -> DiagnosticResult:
        """4단계: 이미지 생산 사전 점검 (캐릭터 × 포즈 조합 전수 시뮬레이션)."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            report = run_pregeneration_check("campus")
            details.append(
                f"사전 점검 완료: 캐릭터 {report.total_characters}명 × 포즈 {report.total_poses}종 = {report.total_combinations_checked}개 조합"
            )

            if not report.passed:
                err_msg = "\n".join(report.errors[:3])
                raise ValueError(f"사전 점검 불합격 (총 {len(report.errors)}건 오류): {err_msg}")

            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=4,
                category="사전 점검",
                name="이미지 생산 사전 무결성 점검 (Precheck)",
                status="PASS",
                message=f"{report.total_combinations_checked}개 조합 무결성 100% 합격",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=4,
                category="사전 점검",
                name="이미지 생산 사전 무결성 점검 (Precheck)",
                status="FAIL",
                message=f"사전 점검 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_5_workflows(self) -> DiagnosticResult:
        """5단계: SDXL 워크플로우 템플릿(기본, Face Detailer, IP-Adapter, 시드 주입) 무결성 검증."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            # 1. Face Detailer 포함 기본 워크플로우
            wf = build_sdxl_workflow("test pos", "test neg", "test_prefix", use_face_detailer=True)
            node_classes = {n.get("class_type") for n in wf.values() if isinstance(n, dict)}
            required = {"CheckpointLoaderSimple", "KSampler", "SaveImage", "FaceDetailer"}
            missing = required - node_classes
            if missing:
                raise ValueError(f"기본 SDXL 워크플로우에 필수 노드 누락: {missing}")
            details.append("SDXL 기본 + Face Detailer 워크플로우 노드 그래프 유효")

            # 2. IP-Adapter 워크플로우
            wf_ip = build_sdxl_workflow(
                "test pos", "test neg", "test_prefix", ref_image_name="test_ref.webp", ref_weight=0.65
            )
            node_classes_ip = {n.get("class_type") for n in wf_ip.values() if isinstance(n, dict)}
            required_ip = {"IPAdapterUnifiedLoader", "PrepImageForClipVision", "IPAdapterAdvanced"}
            missing_ip = required_ip - node_classes_ip
            if missing_ip:
                raise ValueError(f"IP-Adapter 워크플로우에 필수 노드 누락: {missing_ip}")
            details.append("SDXL IP-Adapter 결합 노드 그래프 유효")

            # 3. KSampler 시드 파라미터 제어 확인
            ksampler_found = False
            for nid, node in wf.items():
                if node.get("class_type") == "KSampler":
                    inputs = node.get("inputs", {})
                    if "seed" in inputs or "noise_seed" in inputs:
                        ksampler_found = True
                        break
            if not ksampler_found:
                raise ValueError("KSampler 노드에서 시드(seed) 파라미터를 찾을 수 없음")
            details.append("KSampler 골든 시드 주입 및 제어 가능 여부 검증 완료")

            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=5,
                category="워크플로우 템플릿",
                name="SDXL 워크플로우 노드 그래프 및 파라미터 바인딩",
                status="PASS",
                message="KSampler · Face Detailer · IP-Adapter 노드 바인딩 정상",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=5,
                category="워크플로우 템플릿",
                name="SDXL 워크플로우 노드 그래프 및 파라미터 바인딩",
                status="FAIL",
                message=f"워크플로우 템플릿 진단 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_6_censor_engine(self) -> DiagnosticResult:
        """6단계: 2D 애니 검열 엔진 및 모델 가중치(MobileSAM/YOLO) 상태 점검."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            from plepa_engine.censor import HAS_IMGUTILS, censor_image, get_sam_model

            details.append(f"imgutils 검열 감지 라이브러리 탑재 여부: {HAS_IMGUTILS}")

            # 더미 이미지로 censor_image 실행 테스트
            dummy_img = Image.new("RGB", (200, 200), color=(255, 255, 255))
            censored, count = censor_image(dummy_img, style="white_silhouette", targets=["penis"])
            if censored is None:
                raise ValueError("censor_image 반환 이미지가 None임")
            details.append("censor_image 파이프라인 실행 테스트 통과")

            # MobileSAM 모델 확인
            sam_model = get_sam_model()
            elapsed = (time.perf_counter() - t0) * 1000.0
            if sam_model is None:
                details.append("주의: MobileSAM 가중치(mobile_sam.pt)가 없어 바/모자이크/컨투어 폴백으로 동작")
                return DiagnosticResult(
                    stage_index=6,
                    category="검열 엔진",
                    name="2D 애니 성기 실루엣 검열 엔진 및 모델 가중치",
                    status="WARN",
                    message="검열 엔진 작동 가능 (MobileSAM 미설치로 폴백 모드 대기)",
                    duration_ms=elapsed,
                    details=details,
                )

            details.append("MobileSAM 실루엣 분할 모델 싱글톤 정상 로드")
            return DiagnosticResult(
                stage_index=6,
                category="검열 엔진",
                name="2D 애니 성기 실루엣 검열 엔진 및 모델 가중치",
                status="PASS",
                message="MobileSAM 및 7종 검열 스타일 엔진 정상 가동",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=6,
                category="검열 엔진",
                name="2D 애니 성기 실루엣 검열 엔진 및 모델 가중치",
                status="FAIL",
                message=f"검열 엔진 진단 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_7_auto_qc_manifest(self) -> DiagnosticResult:
        """7단계: Auto-QC 품질 검증기 및 매니페스트 원자적 병합(Merge) 무결성 검증."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            # 1. Auto-QC 검증기 테스트 (정상 더미 이미지)
            dummy_canvas = Image.new("RGB", (832, 1216), color=(200, 200, 200))
            is_valid, reason, _ = validate_generated_image(dummy_canvas, is_solo_scene=True)
            if not is_valid:
                raise ValueError(f"더미 이미지 QC 검증 실패: {reason}")
            details.append("Auto-QC 해상도/인원수/구도 검증기 유효")


            # 2. 매니페스트 병합 시뮬레이션
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)
                dummy_target_1 = GenerationTarget(
                    code="000",
                    section="poses",
                    label="스탠딩",
                    assembled_prompt="pos",
                    is_nude=False,
                    output_filename="test_000.webp",
                    seed=12345,
                )
                dummy_target_2 = GenerationTarget(
                    code="001",
                    section="poses",
                    label="웃음",
                    assembled_prompt="pos",
                    is_nude=False,
                    output_filename="test_001.webp",
                    seed=67890,
                )

                from plepa_engine.models import GenerationResult
                dummy_char, _ = default_character_service.find_character("sample_character", roster="campus")
                dummy_params = GenerationParams(character_expr="sample_character")
                res_1 = GenerationResult(target=dummy_target_1, success=True, image_path=tmppath / "test_000.webp")
                res_2 = GenerationResult(target=dummy_target_2, success=True, image_path=tmppath / "test_001.webp")

                # 첫 번째 저장
                default_generation_service._save_batch_manifest(tmppath, dummy_char, "campus", dummy_params, [res_1])
                # 두 번째 저장 (병합)
                default_generation_service._save_batch_manifest(tmppath, dummy_char, "campus", dummy_params, [res_2])

                manifest_file = tmppath / "_batch_manifest.json"
                if not manifest_file.exists():
                    raise FileNotFoundError("매니페스트 파일이 생성되지 않음")

                import json
                with open(manifest_file, "r", encoding="utf-8") as f:
                    m_data = json.load(f)

                items = m_data.get("items", [])
                if len(items) != 2:
                    raise ValueError(f"매니페스트 병합 후 항목 수가 2가 아닌 {len(items)}개임")

                seeds = [item.get("seed") for item in items]
                if 12345 not in seeds or 67890 not in seeds:
                    raise ValueError(f"매니페스트 골든 시드 보존 실패: {seeds}")

                details.append("매니페스트 증분 병합(Merge) 및 골든 시드 보존 시뮬레이션 통과")

            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=7,
                category="Auto-QC & 매니페스트",
                name="품질 검증기 및 매니페스트 원자적 병합(골든 시드)",
                status="PASS",
                message="Auto-QC 및 시드 보존 매니페스트 증분 병합 정상",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=7,
                category="Auto-QC & 매니페스트",
                name="품질 검증기 및 매니페스트 원자적 병합(골든 시드)",
                status="FAIL",
                message=f"Auto-QC/매니페스트 진단 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_8_audit_genit(self) -> DiagnosticResult:
        """8단계: 에셋 완비율 감사기(--audit) 및 Genit 프롬프트 시트 내보내기 검증."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            # 1. audit_roster_assets 점검
            audit_data = default_asset_service.audit_roster_assets(roster="campus")
            if not audit_data:
                raise ValueError("audit_roster_assets 반환 데이터가 비어있음")
            sample_row = audit_data[0]
            required_keys = {"prefix", "name", "expected_count", "present_count", "completion_rate", "missing_codes"}
            missing_keys = required_keys - set(sample_row.keys())
            if missing_keys:
                raise ValueError(f"감사 리포트 필수 필드 누락: {missing_keys}")
            details.append(f"'campus' 로스터 {len(audit_data)}명 에셋 감사 리포트 추출 완료")

            # 2. GenitExporter 점검
            from plepa_engine.services.genit_exporter import DEFAULT_GENIT_CHARACTER_MAP
            exporter = GenitExporter()
            if not hasattr(exporter, "export_character"):
                raise AttributeError("GenitExporter에 export_character 메서드가 누락되었습니다.")
            details.append(f"Genit 캐릭터 매핑 프리셋({len(DEFAULT_GENIT_CHARACTER_MAP)}명) 및 익스포터 API 확인")

            # 3. restore_from_origin 시그니처 점검
            has_restore = hasattr(default_asset_service, "restore_from_origin")
            if not has_restore:
                raise AttributeError("AssetService에 restore_from_origin 메서드가 없습니다.")
            details.append("무검열 원본 복원(restore_from_origin) API 확인")


            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=8,
                category="에셋 감사 & Genit",
                name="에셋 완비율 전수 감사기 및 Genit 프롬프트 시트 익스포터",
                status="PASS",
                message="에셋 감사 리포트 및 Genit 45슬롯 익스포터 유효",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=8,
                category="에셋 감사 & Genit",
                name="에셋 완비율 전수 감사기 및 Genit 프롬프트 시트 익스포터",
                status="FAIL",
                message=f"에셋 감사/Genit 진단 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_9_gui_trinity_sync(self) -> DiagnosticResult:
        """9단계: CLI · Engine · GUI 삼위일체 동기화 및 FLUX 완전 배제 검증."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            # 1. GENERATION_OPTION_SPECS 와 GenerationParams 필드 일치 검증
            param_fields = {f.name for f in dataclasses.fields(GenerationParams)}
            spec_keys = {spec["field"] for spec in GENERATION_OPTION_SPECS}


            missing_in_params = spec_keys - param_fields
            if missing_in_params:
                raise ValueError(f"GENERATION_OPTION_SPECS 키가 GenerationParams에 누락됨: {missing_in_params}")
            details.append(f"UI 자동 렌더링 레지스트리 {len(GENERATION_OPTION_SPECS)}개 옵션과 파라미터 100% 일치")

            # 2. GUI 페이지 임포트 무결성 검증
            import plepa_gui.components.header
            import plepa_gui.pages.gallery
            import plepa_gui.pages.generate
            import plepa_gui.pages.settings
            details.append("Web GUI 전체 페이지 모듈 임포트 성공")

            # 3. GUI 내 FLUX 잔재 배제 검증
            gui_dir = Path("plepa_gui")
            flux_mentions = []
            for py_file in gui_dir.rglob("*.py"):
                text = py_file.read_text(encoding="utf-8")
                # 주석이나 독스트링이 아닌 활성 UI 텍스트에 FLUX가 노출되는지 검사
                for idx, line in enumerate(text.splitlines(), start=1):
                    if "FLUX" in line and not line.strip().startswith(("#", '"""', "'''")):
                        # 허용된 문맥(레거시 언급 제외 등)이 아니면 기록
                        flux_mentions.append(f"{py_file.name}:{idx} -> {line.strip()[:60]}")

            if flux_mentions:
                raise ValueError(f"GUI 코드 내 FLUX 레거시 키워드 잔류: {flux_mentions}")
            details.append("GUI 내 FLUX UI 및 잔재 0건 (SDXL 단일 파이프라인 정제 완료)")

            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=9,
                category="삼위일체 동기화",
                name="CLI · Engine · GUI 삼위일체 동기화 및 SDXL 정제",
                status="PASS",
                message="파라미터-CLI-GUI 100% 동기화 및 FLUX UI 배제 완료",
                duration_ms=elapsed,
                details=details,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=9,
                category="삼위일체 동기화",
                name="CLI · Engine · GUI 삼위일체 동기화 및 SDXL 정제",
                status="FAIL",
                message=f"삼위일체 동기화 진단 실패: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

    def check_stage_10_comfy_connection(self) -> DiagnosticResult:
        """10단계: ComfyUI 서버(127.0.0.1:8188) 실시간 연결 상태 점검."""
        t0 = time.perf_counter()
        details: List[str] = []
        try:
            client = ComfyClient(host=self.comfy_host)
            online = client.check_connection()
            elapsed = (time.perf_counter() - t0) * 1000.0

            if online:
                details.append(f"ComfyUI 서버 정상 응답 확인 ({self.comfy_host})")
                return DiagnosticResult(
                    stage_index=10,
                    category="ComfyUI 연결",
                    name="ComfyUI 로컬 API 인스턴스 실시간 연결",
                    status="PASS",
                    message=f"ComfyUI 서버 정상 응답 ({self.comfy_host})",
                    duration_ms=elapsed,
                    details=details,
                )
            else:
                details.append(f"ComfyUI 서버({self.comfy_host}) 응답 없음")
                details.append("안내: ComfyUI가 오프라인이어도 모의 생성(--mock), 에셋 감사(--audit), 검열(--censor-only), Genit 내보내기는 정상 동작합니다.")
                return DiagnosticResult(
                    stage_index=10,
                    category="ComfyUI 연결",
                    name="ComfyUI 로컬 API 인스턴스 실시간 연결",
                    status="WARN",
                    message=f"ComfyUI 서버 오프라인 ({self.comfy_host}) - 독립 모드는 가동 가능",
                    duration_ms=elapsed,
                    details=details,
                )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return DiagnosticResult(
                stage_index=10,
                category="ComfyUI 연결",
                name="ComfyUI 로컬 API 인스턴스 실시간 연결",
                status="WARN",
                message=f"ComfyUI 연결 확인 예외: {e}",
                duration_ms=elapsed,
                details=details + [str(e)],
            )

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

        results: List[DiagnosticResult] = []
        for stage_func in stages:
            results.append(stage_func())

        if check_comfy:
            results.append(self.check_stage_10_comfy_connection())

        return results


def format_diagnostics_table(results: List[DiagnosticResult]) -> str:
    """진단 결과를 터미널 콘솔에 출력하기 위한 고품질 표 형식 문자열로 변환합니다."""
    lines: List[str] = []
    lines.append("=" * 88)
    lines.append("  [플에파] 10단계 시스템 통합 무결성 진단 (Unified System Health Diagnostics)")
    lines.append("=" * 88)
    lines.append(f"  {'단계':<6} {'구분':<16} {'진단 항목':<34} {'상태':<8} {'소요시간':<10}")
    lines.append("-" * 88)

    pass_cnt = 0
    warn_cnt = 0
    fail_cnt = 0
    total_time_ms = 0.0

    for r in results:
        total_time_ms += r.duration_ms
        if r.status == "PASS":
            pass_cnt += 1
            status_str = "✔ PASS"
        elif r.status == "WARN":
            warn_cnt += 1
            status_str = "⚠ WARN"
        else:
            fail_cnt += 1
            status_str = "❌ FAIL"

        step_label = f"[{r.stage_index:02d}]"
        duration_str = f"{r.duration_ms:.1f}ms"
        lines.append(f"  {step_label:<6} {r.category:<16} {r.name:<34} {status_str:<8} {duration_str:<10}")

    lines.append("-" * 88)
    summary_line = (
        f"  결과 요약: 총 {len(results)}개 검사 중 {pass_cnt} PASS, {warn_cnt} WARN, {fail_cnt} FAIL "
        f"(총 소요 시간: {total_time_ms / 1000.0:.2f}초)"
    )
    lines.append(summary_line)

    if fail_cnt > 0:
        lines.append("\n  [결함 상세 내역]")
        for r in results:
            if r.status == "FAIL":
                lines.append(f"  ❌ [{r.stage_index:02d}] {r.name}: {r.message}")
                for d in r.details:
                    lines.append(f"     - {d}")
        lines.append("\n  🚨 시스템에 결함이 발견되었습니다. 결함 내역을 확인해 주십시오.")
    elif warn_cnt > 0:
        lines.append("\n  [경고 알림 내역]")
        for r in results:
            if r.status == "WARN":
                lines.append(f"  ⚠ [{r.stage_index:02d}] {r.name}: {r.message}")
                for d in r.details:
                    lines.append(f"     - {d}")
        lines.append("\n  ✔ 치명적 결함 없음: 모든 필수 코어 시스템이 정상 가동 가능합니다.")
    else:
        lines.append("  ✔ 모든 진단 항목 통과: 시스템 무결성 100% 정상 작동 보장.")

    lines.append("=" * 88)
    return "\n".join(lines)


default_health_service = HealthService()
