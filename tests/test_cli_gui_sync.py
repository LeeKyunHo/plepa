"""
tests.test_cli_gui_sync
CLI, Engine, GUI 삼위일체(Trinity Sync) 동기화 계약 자동 검증 테스트.
- 엔진의 파라미터가 누락 없이 CLI와 GUI에 바인딩되었는지 검사
- CLI 인자 파싱 기본값과 GENERATION_OPTION_SPECS 및 엔진 워크플로우 기본 동작이 일치하는지 검증
- GUI에 은퇴한 레거시(FLUX) UI 잔재가 재유입되지 않았는지 검사
- pose_sets.json 프리셋(sample10 등)이 정상 해석되는지 검사
- 완성된 648장 프로덕션 에셋 무손실 보존 상태 영구 가드레일 검증
"""

import dataclasses
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = None

from batch_generator import create_parser
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
)
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.workflow_templates import build_sdxl_workflow
from plepa_gui.components.header import get_active_roster, set_active_roster


def test_generation_option_specs_match_params():
    """GENERATION_OPTION_SPECS의 모든 field가 GenerationParams 데이터클래스에 실존하는지 검증."""
    param_field_names = {f.name for f in dataclasses.fields(GenerationParams)}

    for spec in GENERATION_OPTION_SPECS:
        field_name = spec["field"]
        assert field_name in param_field_names, (
            f"GENERATION_OPTION_SPECS의 '{field_name}' 필드가 GenerationParams에 정의되어 있지 않습니다."
        )


def test_generation_option_specs_match_cli_parser():
    """GENERATION_OPTION_SPECS의 모든 cli_flag가 batch_generator.py parser에 등록되어 있는지 검증."""
    bg_path = Path(__file__).resolve().parent.parent / "batch_generator.py"
    content = bg_path.read_text(encoding="utf-8")

    for spec in GENERATION_OPTION_SPECS:
        flag = spec["cli_flag"]
        assert f'"{flag}"' in content or f"'{flag}'" in content, (
            f"GENERATION_OPTION_SPECS의 '{flag}' 플래그가 batch_generator.py에 등록되어 있지 않습니다."
        )


def test_generation_option_specs_default_values_sync_with_cli():
    """CLI 빈 인수 실행 시 기본 파싱값과 GENERATION_OPTION_SPECS의 기본값 정합성 E2E 검증."""
    parser = create_parser()
    default_args = parser.parse_args([])

    for spec in GENERATION_OPTION_SPECS:
        field = spec["field"]
        spec_default = spec["default"]

        if field == "face_detailer":
            # face_detailer는 CLI에서 None(미지정)으로 들어오며,
            # 엔진(workflow_templates)에서 None일 때 기본 True로 작동해야 함
            assert getattr(default_args, field) is None
            assert spec_default is True
        elif field == "censor":
            # censor는 GUI 대시보드에서는 검열본 안전 표시를 위해 기본 True로 체크되어 렌더링되나,
            # CLI에서는 사용자 선택을 존중하여 명시적 --censor 플래그가 주어질 때만 활성화됨
            assert getattr(default_args, field) is False
            assert spec_default is True
        else:
            cli_val = getattr(default_args, field, None)
            assert cli_val == spec_default, (
                f"옵션 '{field}'의 CLI 기본값({cli_val})이 GENERATION_OPTION_SPECS 기본값({spec_default})과 불일치합니다."
            )


def test_workflow_templates_detailer_default_behavior():
    """build_sdxl_workflow에서 use_face_detailer=None 시 FaceDetailer가 기본 활성화되는지 검증."""
    # 1. 기본값 (use_face_detailer=None) 호출 시 FaceDetailer 노드가 반드시 포함되어야 함
    wf_default = build_sdxl_workflow(
        positive_prompt="test",
        negative_prompt="test",
        output_prefix="test",
        use_face_detailer=None,
    )
    class_types_default = [node.get("class_type") for node in wf_default.values() if isinstance(node, dict)]
    assert "FaceDetailer" in class_types_default, "기본 워크플로우(use_face_detailer=None)에 FaceDetailer 노드가 누락되었습니다."

    # 2. 명시적 False 호출 시 FaceDetailer 노드가 배제되어야 함
    wf_disabled = build_sdxl_workflow(
        positive_prompt="test",
        negative_prompt="test",
        output_prefix="test",
        use_face_detailer=False,
    )
    class_types_disabled = [node.get("class_type") for node in wf_disabled.values() if isinstance(node, dict)]
    assert "FaceDetailer" not in class_types_disabled, "use_face_detailer=False 워크플로우에 FaceDetailer 노드가 잔류합니다."

    # 3. Hand Detailer 활성화 시 손 검출기(hand_yolov8s.pt) 모델이 바인딩되어야 함
    wf_hand = build_sdxl_workflow(
        positive_prompt="test",
        negative_prompt="test",
        output_prefix="test",
        use_hand_detailer=True,
    )
    hand_detectors = [
        node["inputs"]["model_name"]
        for node in wf_hand.values()
        if isinstance(node, dict)
        and node.get("class_type") == "UltralyticsDetectorProvider"
        and "hand" in node.get("inputs", {}).get("model_name", "")
    ]
    assert len(hand_detectors) >= 1, "use_hand_detailer=True 워크플로우에 손 검출기 노드가 누락되었습니다."


def test_no_flux_in_gui_pages():
    """plepa_gui/pages/generate.py와 settings.py에 은퇴한 레거시(FLUX) 선택지가 존재하지 않는지 검증."""
    gui_dir = Path(__file__).resolve().parent.parent / "plepa_gui" / "pages"

    gen_content = (gui_dir / "generate.py").read_text(encoding="utf-8")
    assert "FLUX [레거시]" not in gen_content, "generate.py에 'FLUX [레거시]' UI가 남아있습니다."
    assert "flux_unet" not in gen_content, "generate.py에 'flux_unet' 키가 남아있습니다."

    set_content = (gui_dir / "settings.py").read_text(encoding="utf-8")
    assert "FLUX.1 [dev] GGUF 파라미터" not in set_content, "settings.py에 FLUX 파라미터 카드가 남아있습니다."


def test_sample10_pose_set_integration():
    """pose_sets.json의 sample10 프리셋이 pose_service에서 10개 코드로 온전히 해석되는지 검증."""
    sets = default_pose_service.load_pose_sets()
    sample10_set = next((s for s in sets if s.id == "sample10"), None)
    assert sample10_set is not None, "data/pose_sets.json에 'sample10' 프리셋이 누락되었습니다."
    assert len(sample10_set.codes) == 10, f"sample10 코드는 10개여야 합니다 (현재: {len(sample10_set.codes)}개)."

    # pose_service.resolve_pose_codes() 테스트
    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    resolved = default_pose_service.resolve_pose_codes("sample10", db)
    assert len(resolved) == 10, f"resolve_pose_codes('sample10') 결과가 10개가 아닙니다 (현재: {len(resolved)}개)."
    assert "000" in resolved
    assert "088" in resolved


def test_header_active_roster_sync():
    """상단 헤더의 전역 활성 로스터 상태 관리 헬퍼 정상 동작 검증."""
    original = get_active_roster()
    try:
        set_active_roster("campus")
        assert get_active_roster() == "campus"
    finally:
        set_active_roster(original)


def test_system_health_diagnostics():
    """10단계 시스템 통합 무결성 진단(HealthService)이 결함 없이 전수 통과하는지 검증."""
    from plepa_engine.services.health_service import default_health_service
    results = default_health_service.run_full_diagnostics(check_comfy=False)
    assert len(results) == 9
    fails = [r for r in results if r.status == "FAIL"]
    assert not fails, f"시스템 무결성 진단 실패 항목 발견: {[f'{r.stage_index}. {r.name}: {r.message}' for r in fails]}"


def test_grounding_production_asset_lossless_guardrail():
    """캠퍼스 6인 648장 프로덕션 에셋 및 원본 백업이 단 1장도 훼손·삭제되지 않았는지 영구 검증."""
    campus_assets_dir = PROJECTS_DIR / "campus" / "assets"
    expected_chars = ["aya", "har", "kao", "mai", "shz", "yur"]

    for char in expected_chars:
        char_dir = campus_assets_dir / char
        assert char_dir.exists(), f"캐릭터 '{char}' 에셋 디렉토리가 존재하지 않습니다."
        main_files = list(char_dir.rglob("*.webp"))
        # 최소 108장 이상의 프로덕션 에셋이 무손실 보존되어야 하며, 새 콘텐츠 유입으로 확장될 수 있음
        assert len(main_files) >= 108, (
            f"캐릭터 '{char}' 에셋 수량이 비정상적으로 적습니다 (최소 108장 필요, 현재: {len(main_files)}장)."
        )

        origin_dir = campus_assets_dir / f"{char}_origin"
        assert origin_dir.exists(), f"캐릭터 '{char}' 원본 백업 디렉토리가 존재하지 않습니다."
        origin_files = list(origin_dir.rglob("*.webp"))
        assert len(origin_files) >= 70, (
            f"캐릭터 '{char}' 원본 백업 수량이 비정상적으로 적습니다 (현재: {len(origin_files)}장)."
        )
