"""
tests.test_cli_gui_sync
CLI, Engine, GUI 삼위일체(Trinity Sync) 동기화 계약 자동 검증 테스트.
- 엔진의 파라미터가 누락 없이 CLI와 GUI에 바인딩되었는지 검사
- CLI 인자 파싱 기본값과 GENERATION_OPTION_SPECS 및 엔진 워크플로우 기본 동작이 일치하는지 검증
- GUI에 은퇴한 레거시(FLUX) UI 잔재가 재유입되지 않았는지 검사
- pose_sets.json 프리셋(sample10 등)이 정상 해석되는지 동적 검사
- 완성된 프로덕션 에셋 무손실 보존 상태 영구 가드레일 동적 검증
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
            assert getattr(default_args, field) is None
            assert spec_default is True
        elif field == "censor":
            assert getattr(default_args, field) is False
            assert spec_default is True
        else:
            cli_val = getattr(default_args, field, None)
            assert cli_val == spec_default, (
                f"옵션 '{field}'의 CLI 기본값({cli_val})이 GENERATION_OPTION_SPECS 기본값({spec_default})과 불일치합니다."
            )


def test_workflow_templates_detailer_default_behavior():
    """build_sdxl_workflow에서 use_face_detailer=None 시 FaceDetailer가 기본 활성화되는지 검증."""
    wf_default = build_sdxl_workflow(
        positive_prompt="test",
        negative_prompt="test",
        output_prefix="test",
        use_face_detailer=None,
    )
    class_types_default = [node.get("class_type") for node in wf_default.values() if isinstance(node, dict)]
    assert "FaceDetailer" in class_types_default, "기본 워크플로우(use_face_detailer=None)에 FaceDetailer 노드가 누락되었습니다."

    wf_disabled = build_sdxl_workflow(
        positive_prompt="test",
        negative_prompt="test",
        output_prefix="test",
        use_face_detailer=False,
    )
    class_types_disabled = [node.get("class_type") for node in wf_disabled.values() if isinstance(node, dict)]
    assert "FaceDetailer" not in class_types_disabled, "use_face_detailer=False 워크플로우에 FaceDetailer 노드가 잔류합니다."

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
    """pose_sets.json의 sample10 프리셋이 pose_service에서 누락 없이 동적으로 해석되는지 검증."""
    sets = default_pose_service.load_pose_sets()
    sample10_set = next((s for s in sets if s.id == "sample10"), None)
    assert sample10_set is not None, "data/pose_sets.json에 'sample10' 프리셋이 누락되었습니다."
    assert len(sample10_set.codes) > 0

    db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
    resolved = default_pose_service.resolve_pose_codes("sample10", db)
    assert resolved == sample10_set.codes, (
        f"resolve_pose_codes('sample10') 결과({resolved})가 정의된 코드({sample10_set.codes})와 일치해야 합니다."
    )


def test_header_active_roster_sync():
    """상단 헤더의 전역 활성 로스터 상태 관리 헬퍼 정상 동작 검증."""
    original = get_active_roster()
    try:
        set_active_roster("campus")
        assert get_active_roster() == "campus"
    finally:
        set_active_roster(original)


def test_system_health_diagnostics():
    """시스템 통합 무결성 진단(HealthService)이 결함(FAIL) 0건으로 전수 통과하는지 검증."""
    from plepa_engine.services.health_service import default_health_service
    results = default_health_service.run_full_diagnostics(check_comfy=False)
    assert len(results) >= 1
    fails = [r for r in results if r.status == "FAIL"]
    assert not fails, f"시스템 무결성 진단 실패 항목 발견: {[f'{r.stage_index}. {r.name}: {r.message}' for r in fails]}"


def test_grounding_production_asset_lossless_guardrail():
    """캠퍼스 및 YKN 프로덕션 에셋과 원본 백업이 훼손·삭제되지 않았는지 동적으로 스캔하여 검증."""
    for roster, min_assets, min_origins in [("campus", 108, 70), ("ykn", 115, 50)]:
        chars_dir = PROJECTS_DIR / roster / "characters"
        assets_dir = PROJECTS_DIR / roster / "assets"
        char_prefixes = sorted([f.stem for f in chars_dir.glob("*.json")])
        assert len(char_prefixes) > 0

        for char in char_prefixes:
            char_dir = assets_dir / char
            assert char_dir.exists(), f"[{roster}/{char}] 에셋 디렉토리가 존재하지 않습니다."
            main_files = [f for f in char_dir.rglob("*.webp") if "_trash" not in f.parts]
            assert len(main_files) >= min_assets, (
                f"[{roster}/{char}] 에셋 수량이 최소 기준({min_assets}장) 미달입니다 (현재: {len(main_files)}장)."
            )

            origin_dir = assets_dir / f"{char}_origin"
            assert origin_dir.exists(), f"[{roster}/{char}] 원본 백업 디렉토리가 존재하지 않습니다."
            origin_files = list(origin_dir.rglob("*.webp"))
            assert len(origin_files) >= min_origins, (
                f"[{roster}/{char}] 원본 백업 수량이 최소 기준({min_origins}장) 미달입니다 (현재: {len(origin_files)}장)."
            )
