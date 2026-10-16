"""
tests/test_qc_summary.py
Auto-QC 리롤 한도 초과 결함 추적 및 캐릭터별/종합 요약 보고서 검증 테스트
"""

import io
import json
import sys
from pathlib import Path
from plepa_engine.models import CharacterConfig, GenerationResult, GenerationTarget
from plepa_engine.reporter import print_batch_summary, print_overall_batch_summary
from plepa_engine.services.generation_service import GenerationParams, default_generation_service


def test_character_batch_summary_with_qc_defect(capsys):
    """단일 캐릭터 배치 생성 보고서에서 QC 결함 카운트, 포즈 번호/라벨 및 권장 메시지 출력 검증."""
    t0 = GenerationTarget(
        code="000", section="emotions", label="평상",
        assembled_prompt="prompt 0", is_nude=False,
        output_filename="aya_000_평상.webp",
        character_prefix="aya", character_name="아야",
    )
    r0 = GenerationResult(target=t0, success=True, qc_passed=True, retries=0)

    t1 = GenerationTarget(
        code="080", section="h_scenes", label="정상위",
        assembled_prompt="prompt 80", is_nude=True,
        output_filename="aya_080_정상위.webp",
        character_prefix="aya", character_name="아야",
    )
    r1 = GenerationResult(
        target=t1, success=True, qc_passed=False,
        qc_reason="남성 모브 얼굴 노출(faceless 위반)", retries=3,
    )

    print_batch_summary(
        prefix="aya",
        results=[r0, r1],
        save_dir=Path("projects/campus/assets/aya"),
        total_duration_sec=25.0,
        char_name="아야",
    )

    captured = capsys.readouterr().out
    assert "아야 (aya) 배치 생성 완료 보고서" in captured
    assert "1개 이미지에서 문제 발생" in captured
    assert "[080] 정상위: 남성 모브 얼굴 노출(faceless 위반)" in captured
    assert "최대 재시도 3회 초과 후 강제 저장됨" in captured
    assert "프롬프트 수정을 권장합니다" in captured


def test_overall_batch_summary_multi_characters(capsys):
    """모든 캐릭터 배치 종료 시 최종 종합 보고서에서 문제 캐릭터/포즈 정리 및 권장 가이드 출력 검증."""
    # 캐릭터 1: 아야 - 080 결함
    t1 = GenerationTarget(
        code="080", section="h_scenes", label="정상위",
        assembled_prompt="prompt 80", is_nude=True,
        output_filename="aya_080_정상위.webp",
        character_prefix="aya", character_name="아야",
    )
    r1 = GenerationResult(target=t1, success=True, qc_passed=False, qc_reason="남성 모브 얼굴 노출", retries=3)

    # 캐릭터 2: 린 - 130 결함
    t2 = GenerationTarget(
        code="130", section="special_h", label="빈강의실 섹스",
        assembled_prompt="prompt 130", is_nude=False,
        output_filename="rin_130_빈강의실_섹스.webp",
        character_prefix="rin", character_name="린",
    )
    r2 = GenerationResult(target=t2, success=True, qc_passed=False, qc_reason="필수 성인 씬 성기 미탐지(구도 불량)", retries=3)

    # 캐릭터 3: 유키 - 정상
    t3 = GenerationTarget(
        code="000", section="emotions", label="평상",
        assembled_prompt="prompt 0", is_nude=False,
        output_filename="yuki_000_평상.webp",
        character_prefix="yuki", character_name="유키",
    )
    r3 = GenerationResult(target=t3, success=True, qc_passed=True, retries=0)

    print_overall_batch_summary([r1, r2, r3], total_duration_sec=60.0)

    captured = capsys.readouterr().out
    assert "전체 캐릭터 에셋 제작 최종 종합 보고서" in captured
    assert "총 3명" in captured
    assert "아야 (aya)" in captured
    assert "[080] 정상위: 남성 모브 얼굴 노출" in captured
    assert "린 (rin)" in captured
    assert "[130] 빈강의실 섹스: 필수 성인 씬 성기 미탐지(구도 불량)" in captured
    assert "에이전트 권장 조치사항" in captured
    assert "강력히 권장합니다" in captured


def test_overall_batch_summary_all_clean(capsys):
    """모든 캐릭터가 100% 정상 통과했을 때의 클린 메시지 검증."""
    t1 = GenerationTarget(
        code="000", section="emotions", label="평상",
        assembled_prompt="prompt 0", is_nude=False,
        output_filename="aya_000_평상.webp",
        character_prefix="aya", character_name="아야",
    )
    r1 = GenerationResult(target=t1, success=True, qc_passed=True, retries=0)

    print_overall_batch_summary([r1], total_duration_sec=10.0)

    captured = capsys.readouterr().out
    assert "100% 정상 품질로 완성" in captured
    assert "QC 결함 0건" in captured


def test_manifest_qc_defect_tracking(tmp_path: Path):
    """_batch_manifest.json에 qc_passed, qc_reason, retries 및 qc_defect_count가 정확히 기록되는지 검증."""
    char = CharacterConfig.from_dict({
        "prefix": "qc_test",
        "name": "QC 테스트",
        "appearance": {"face_and_hair": "a", "physique": "b", "outfit": "c"}
    })
    params = GenerationParams(character_expr="qc_test")

    t_pass = GenerationTarget(
        code="000", section="emotions", label="평상",
        assembled_prompt="prompt 0", is_nude=False,
        output_filename="qc_test_000_평상.webp",
    )
    r_pass = GenerationResult(target=t_pass, success=True, qc_passed=True, retries=0)

    t_fail = GenerationTarget(
        code="080", section="h_scenes", label="정상위",
        assembled_prompt="prompt 80", is_nude=True,
        output_filename="qc_test_080_정상위.webp",
    )
    r_fail = GenerationResult(
        target=t_fail, success=True, qc_passed=False,
        qc_reason="색감 과포화(Color Burn)", retries=3,
    )

    default_generation_service._save_batch_manifest(tmp_path, char, "default", params, [r_pass, r_fail])

    manifest_file = tmp_path / "_batch_manifest.json"
    assert manifest_file.exists()
    with open(manifest_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_count"] == 2
    assert data["success_count"] == 2
    assert data["qc_defect_count"] == 1

    items_by_code = {it["code"]: it for it in data["items"]}
    assert items_by_code["000"]["qc_passed"] is True
    assert items_by_code["000"]["qc_reason"] is None
    assert items_by_code["000"]["retries"] == 0

    assert items_by_code["080"]["qc_passed"] is False
    assert items_by_code["080"]["qc_reason"] == "색감 과포화(Color Burn)"
    assert items_by_code["080"]["retries"] == 3
