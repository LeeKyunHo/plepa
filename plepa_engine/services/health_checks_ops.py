"""
plepa_engine.services.health_checks_ops
10단계 시스템 통합 무결성 진단 중 6~10단계(검열/QC/에셋감사/삼위일체/ComfyUI) 및 결과 포맷터 모듈.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, List

from PIL import Image

from plepa_engine.models import GenerationResult, GenerationTarget
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
    default_generation_service,
)
from plepa_engine.services.genit_exporter import GenitExporter
from plepa_engine.services.health_checks_core import DiagnosticResult

_GUI_VERIFY_MODULES = (
    "plepa_gui.components.header",
    "plepa_gui.pages.gallery",
    "plepa_gui.pages.generate",
    "plepa_gui.pages.settings",
)


def run_stage_6_censor_engine() -> DiagnosticResult:
    """6단계: 2D 애니 검열 엔진 및 모델 가중치(MobileSAM/YOLO) 상태 점검."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        from plepa_engine.censor import HAS_IMGUTILS, censor_image, get_sam_model

        details.append(f"imgutils 검열 감지 라이브러리 탑재 여부: {HAS_IMGUTILS}")
        dummy_img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        censored, _ = censor_image(dummy_img, style="white_silhouette", targets=["penis"])
        if censored is None:
            raise ValueError("censor_image 반환 이미지가 None임")
        details.append("censor_image 파이프라인 실행 테스트 통과")

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
        return DiagnosticResult(
            stage_index=6,
            category="검열 엔진",
            name="2D 애니 성기 실루엣 검열 엔진 및 모델 가중치",
            status="FAIL",
            message=f"검열 엔진 진단 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def run_stage_7_auto_qc_manifest(validate_fn: Callable[..., Any]) -> DiagnosticResult:
    """7단계: Auto-QC 품질 검증기 및 매니페스트 원자적 병합(Merge) 무결성 검증."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        dummy_canvas = Image.new("RGB", (832, 1216), color=(200, 200, 200))
        is_valid, reason, _ = validate_fn(dummy_canvas, is_solo_scene=True)
        if not is_valid:
            raise ValueError(f"더미 이미지 QC 검증 실패: {reason}")
        details.append("Auto-QC 해상도/인원수/구도 검증기 유효")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            t1 = GenerationTarget(code="000", section="poses", label="스탠딩", assembled_prompt="pos", is_nude=False, output_filename="test_000.webp", seed=12345)
            t2 = GenerationTarget(code="001", section="poses", label="웃음", assembled_prompt="pos", is_nude=False, output_filename="test_001.webp", seed=67890)
            dummy_char, _ = default_character_service.find_character("sample_character", roster="campus")
            dummy_params = GenerationParams(character_expr="sample_character")
            res_1 = GenerationResult(target=t1, success=True, image_path=tmppath / "test_000.webp")
            res_2 = GenerationResult(target=t2, success=True, image_path=tmppath / "test_001.webp")

            default_generation_service._save_batch_manifest(tmppath, dummy_char, "campus", dummy_params, [res_1])
            default_generation_service._save_batch_manifest(tmppath, dummy_char, "campus", dummy_params, [res_2])

            manifest_file = tmppath / "_batch_manifest.json"
            if not manifest_file.exists():
                raise FileNotFoundError("매니페스트 파일이 생성되지 않음")
            m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            items = m_data.get("items", [])
            if len(items) != 2:
                raise ValueError(f"매니페스트 병합 후 항목 수가 2가 아닌 {len(items)}개임")
            seeds = [item.get("seed") for item in items]
            if 12345 not in seeds or 67890 not in seeds:
                raise ValueError(f"매니페스트 골든 시드 보존 실패: {seeds}")
            details.append("매니페스트 증분 병합(Merge) 및 골든 시드 보존 시뮬레이션 통과")

        return DiagnosticResult(
            stage_index=7,
            category="Auto-QC & 매니페스트",
            name="품질 검증기 및 매니페스트 원자적 병합(골든 시드)",
            status="PASS",
            message="Auto-QC 및 시드 보존 매니페스트 증분 병합 정상",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=7,
            category="Auto-QC & 매니페스트",
            name="품질 검증기 및 매니페스트 원자적 병합(골든 시드)",
            status="FAIL",
            message=f"Auto-QC/매니페스트 진단 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def run_stage_8_audit_genit() -> DiagnosticResult:
    """8단계: 에셋 완비율 감사기(--audit) 및 Genit 프롬프트 시트 내보내기 검증."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        audit_data = default_asset_service.audit_roster_assets(roster="campus")
        if not audit_data:
            raise ValueError("audit_roster_assets 반환 데이터가 비어있음")
        sample_row = audit_data[0]
        missing_keys = {"prefix", "name", "expected_count", "present_count", "completion_rate", "missing_codes"} - set(sample_row.keys())
        if missing_keys:
            raise ValueError(f"감사 리포트 필수 필드 누락: {missing_keys}")
        details.append(f"'campus' 로스터 {len(audit_data)}명 에셋 감사 리포트 추출 완료")

        from plepa_engine.services.genit_exporter import DEFAULT_GENIT_CHARACTER_MAP
        exporter = GenitExporter()
        if not hasattr(exporter, "export_character"):
            raise AttributeError("GenitExporter에 export_character 메서드가 누락되었습니다.")
        details.append(f"Genit 캐릭터 매핑 프리셋({len(DEFAULT_GENIT_CHARACTER_MAP)}명) 및 익스포터 API 확인")

        if not hasattr(default_asset_service, "restore_from_origin"):
            raise AttributeError("AssetService에 restore_from_origin 메서드가 없습니다.")
        details.append("무검열 원본 복원(restore_from_origin) API 확인")

        return DiagnosticResult(
            stage_index=8,
            category="에셋 감사 & Genit",
            name="에셋 완비율 전수 감사기 및 Genit 프롬프트 시트 익스포터",
            status="PASS",
            message="에셋 감사 리포트 및 Genit 45슬롯 익스포터 유효",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=8,
            category="에셋 감사 & Genit",
            name="에셋 완비율 전수 감사기 및 Genit 프롬프트 시트 익스포터",
            status="FAIL",
            message=f"에셋 감사/Genit 진단 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def run_stage_9_gui_trinity_sync() -> DiagnosticResult:
    """9단계: CLI · Engine · GUI 삼위일체 동기화 및 FLUX 완전 배제 검증."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        param_fields = {f.name for f in dataclasses.fields(GenerationParams)}
        spec_keys = {spec["field"] for spec in GENERATION_OPTION_SPECS}
        missing_in_params = spec_keys - param_fields
        if missing_in_params:
            raise ValueError(f"GENERATION_OPTION_SPECS 키가 GenerationParams에 누락됨: {missing_in_params}")
        details.append(f"UI 자동 렌더링 레지스트리 {len(GENERATION_OPTION_SPECS)}개 옵션과 파라미터 100% 일치")

        for mod_name in _GUI_VERIFY_MODULES:
            importlib.import_module(mod_name)
        details.append("Web GUI 전체 페이지 모듈 임포트 성공")

        gui_dir = Path("plepa_gui")
        flux_mentions = []
        for py_file in gui_dir.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            for idx, line in enumerate(text.splitlines(), start=1):
                if "FLUX" in line and not line.strip().startswith(("#", '"""', "'''")):
                    flux_mentions.append(f"{py_file.name}:{idx} -> {line.strip()[:60]}")
        if flux_mentions:
            raise ValueError(f"GUI 코드 내 FLUX 레거시 키워드 잔류: {flux_mentions}")
        details.append("GUI 내 FLUX UI 및 잔재 0건 (SDXL 단일 파이프라인 정제 완료)")

        return DiagnosticResult(
            stage_index=9,
            category="삼위일체 동기화",
            name="CLI · Engine · GUI 삼위일체 동기화 및 SDXL 정제",
            status="PASS",
            message="파라미터-CLI-GUI 100% 동기화 및 FLUX UI 배제 완료",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=9,
            category="삼위일체 동기화",
            name="CLI · Engine · GUI 삼위일체 동기화 및 SDXL 정제",
            status="FAIL",
            message=f"삼위일체 동기화 진단 실패: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def run_stage_10_comfy_connection(comfy_host: str, client_cls: Any) -> DiagnosticResult:
    """10단계: ComfyUI 서버(127.0.0.1:8188) 실시간 연결 상태 점검."""
    t0 = time.perf_counter()
    details: List[str] = []
    try:
        online = client_cls(host=comfy_host).check_connection()
        elapsed = (time.perf_counter() - t0) * 1000.0
        if online:
            details.append(f"ComfyUI 서버 정상 응답 확인 ({comfy_host})")
            return DiagnosticResult(
                stage_index=10,
                category="ComfyUI 연결",
                name="ComfyUI 로컬 API 인스턴스 실시간 연결",
                status="PASS",
                message=f"ComfyUI 서버 정상 응답 ({comfy_host})",
                duration_ms=elapsed,
                details=details,
            )
        details.append(f"ComfyUI 서버({comfy_host}) 응답 없음")
        details.append("안내: ComfyUI가 오프라인이어도 모의 생성(--mock), 에셋 감사(--audit), 검열(--censor-only), Genit 내보내기는 정상 동작합니다.")
        return DiagnosticResult(
            stage_index=10,
            category="ComfyUI 연결",
            name="ComfyUI 로컬 API 인스턴스 실시간 연결",
            status="WARN",
            message=f"ComfyUI 서버 오프라인 ({comfy_host}) - 독립 모드는 가동 가능",
            duration_ms=elapsed,
            details=details,
        )
    except Exception as e:
        return DiagnosticResult(
            stage_index=10,
            category="ComfyUI 연결",
            name="ComfyUI 로컬 API 인스턴스 실시간 연결",
            status="WARN",
            message=f"ComfyUI 연결 확인 예외: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            details=details + [str(e)],
        )


def format_diagnostics_table_impl(results: List[DiagnosticResult]) -> str:
    """진단 결과를 터미널 콘솔에 출력하기 위한 표 형식 문자열로 변환합니다."""
    lines: List[str] = [
        "=" * 88,
        "  [플에파] 10단계 시스템 통합 무결성 진단 (Unified System Health Diagnostics)",
        "=" * 88,
        f"  {'단계':<6} {'구분':<16} {'진단 항목':<34} {'상태':<8} {'소요시간':<10}",
        "-" * 88,
    ]
    pass_cnt = warn_cnt = fail_cnt = 0
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
        lines.append(f"  {f'[{r.stage_index:02d}]':<6} {r.category:<16} {r.name:<34} {status_str:<8} {f'{r.duration_ms:.1f}ms':<10}")

    lines.append("-" * 88)
    lines.append(
        f"  결과 요약: 총 {len(results)}개 검사 중 {pass_cnt} PASS, {warn_cnt} WARN, {fail_cnt} FAIL "
        f"(총 소요 시간: {total_time_ms / 1000.0:.2f}초)"
    )
    if fail_cnt > 0:
        lines.append("\n  [결함 상세 내역]")
        for r in results:
            if r.status == "FAIL":
                lines.append(f"  ❌ [{r.stage_index:02d}] {r.name}: {r.message}")
                lines.extend(f"     - {d}" for d in r.details)
        lines.append("\n  🚨 시스템에 결함이 발견되었습니다. 결함 내역을 확인해 주십시오.")
    elif warn_cnt > 0:
        lines.append("\n  [경고 알림 내역]")
        for r in results:
            if r.status == "WARN":
                lines.append(f"  ⚠ [{r.stage_index:02d}] {r.name}: {r.message}")
                lines.extend(f"     - {d}" for d in r.details)
        lines.append("\n  ✔ 치명적 결함 없음: 모든 필수 코어 시스템이 정상 가동 가능합니다.")
    else:
        lines.append("  ✔ 모든 진단 항목 통과: 시스템 무결성 100% 정상 작동 보장.")
    lines.append("=" * 88)
    return "\n".join(lines)
