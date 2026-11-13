"""
tests/test_pose_doc_sync.py
포즈 DB(SSOT) ↔ POSE_MAPPING.md 문서 간 실시간 동기화 상태를 검증하는 단위 테스트.
GEMINI.md 제3조(포즈 매핑 문서 실시간 동기화 원칙) 준수 여부를 자동화하여 검증합니다.
"""

from pathlib import Path
from plepa_engine.config import ROOT_DIR
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.precheck import check_pose_doc_sync, run_pregeneration_check


def test_root_pose_mapping_sync():
    """루트 POSE_MAPPING.md가 SDXL 포즈 DB의 모든 3자리 코드를 100% 포함하는지 검증."""
    doc_path = ROOT_DIR / "POSE_MAPPING.md"
    assert doc_path.exists(), "루트 POSE_MAPPING.md가 존재해야 합니다."

    ok, missing = default_pose_service.check_pose_doc_sync(doc_path=doc_path)
    assert ok, f"POSE_MAPPING.md에 누락된 포즈 코드가 있습니다: {missing}"
    assert len(missing) == 0


def test_docs_pose_mapping_v2_sync():
    """docs/POSE_MAPPING_V2.md가 SDXL 포즈 DB의 모든 3자리 코드를 100% 포함하는지 검증."""
    doc_path = ROOT_DIR / "docs" / "POSE_MAPPING_V2.md"
    assert doc_path.exists(), "docs/POSE_MAPPING_V2.md가 존재해야 합니다."

    ok, missing = default_pose_service.check_pose_doc_sync(doc_path=doc_path)
    assert ok, f"docs/POSE_MAPPING_V2.md에 누락된 포즈 코드가 있습니다: {missing}"
    assert len(missing) == 0


def test_check_pose_doc_sync_detects_missing(tmp_path):
    """일부 코드가 누락된 임시 문서를 검증했을 때 누락 코드가 정상 감지되는지 검증."""
    fake_doc = tmp_path / "FAKE_MAPPING.md"
    # 000, 001만 포함된 문서 작성
    fake_doc.write_text("# Fake Mapping\n000_평상\n001_미소\n", encoding="utf-8")

    ok, missing = default_pose_service.check_pose_doc_sync(doc_path=fake_doc)
    assert not ok
    assert len(missing) > 0
    assert "000" not in missing
    assert "001" not in missing
    assert "002" in missing


def test_precheck_includes_doc_sync():
    """precheck 실행 시 문서 동기화 검증이 정상 통과하는지 확인."""
    ok, missing = check_pose_doc_sync()
    assert ok and missing == []

    report = run_pregeneration_check("campus")
    doc_sync_errors = [err for err in report.errors if "[문서동기화규칙]" in err]
    assert len(doc_sync_errors) == 0, f"사전 점검에서 문서 동기화 위반 감지: {doc_sync_errors}"


def test_legacy_flux_isolated_from_core_top_level():
    """SDXL 메인 모듈 최상단에서 레거시 FLUX 모듈을 즉시 import하지 않는지 검증."""
    for rel_path in (
        "batch_generator.py",
        "plepa_engine/prompt_builder.py",
        "plepa_engine/workflow_templates.py",
    ):
        content = (ROOT_DIR / rel_path).read_text(encoding="utf-8")
        top_level_legacy_imports = [
            line
            for line in content.splitlines()
            if not line.startswith((" ", "\t", "#"))
            and "plepa_engine.legacy" in line
            and ("import " in line or "from " in line)
        ]
        assert not top_level_legacy_imports, f"{rel_path} 최상단에 레거시 import 잔존: {top_level_legacy_imports}"

