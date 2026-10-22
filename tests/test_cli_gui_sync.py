"""
tests.test_cli_gui_sync
CLI, Engine, GUI 삼위일체(Trinity Sync) 동기화 계약 자동 검증 테스트.
- 엔진의 파라미터가 누락 없이 CLI와 GUI에 바인딩되었는지 검사
- GUI에 은퇴한 레거시(FLUX) UI 잔재가 재유입되지 않았는지 검사
- pose_sets.json 프리셋(sample10 등)이 정상 해석되는지 검사
"""

import dataclasses
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = None
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
)
from plepa_engine.services.pose_service import default_pose_service
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
    import argparse
    from batch_generator import main
    import inspect
    
    # batch_generator.py 소스코드 내 parser 인자 등록 여부 직접 검사
    bg_path = Path(__file__).resolve().parent.parent / "batch_generator.py"
    content = bg_path.read_text(encoding="utf-8")
    
    for spec in GENERATION_OPTION_SPECS:
        flag = spec["cli_flag"]
        assert f'"{flag}"' in content or f"'{flag}'" in content, (
            f"GENERATION_OPTION_SPECS의 '{flag}' 플래그가 batch_generator.py에 등록되어 있지 않습니다."
        )


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

