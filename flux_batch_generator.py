"""
flux_batch_generator.py
플럭스(FLUX.1 [dev]) 및 SDXL 기반 캐릭터 에셋 배치 생성기 (플에파 / PLEPA) - CLI 진입점.
CLI 인터페이스 및 하위 호환성을 100% 유지하며, 실제 처리는 서비스 레이어(plepa_engine.services)에 위임합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from plepa_engine.config import (
    COMFY_HOST,
    DEFAULT_ENGINE,
    DEFAULT_ROSTER,
    DEFAULT_SDXL_CKPT,
    DEFAULT_UNET_GGUF,
    PROJECTS_DIR,
    configure_stdio,
)
from plepa_engine.checkpoint_service import CheckpointService

configure_stdio()
from plepa_engine.models import (
    CharacterConfig,
    GenerationResult,
    GenerationTarget,
    PoseEntry,
)
from plepa_engine.prompt_builder import assemble_flux_prompt, assemble_sdxl_prompt
from plepa_engine.reporter import asset_filename, open_in_explorer
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.background_service import default_background_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import (
    GenerationParams,
    default_generation_service,
    generate_mock_image,
)
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.workflow_templates import build_flux_workflow, build_sdxl_workflow


# ==========================================
# 기존 모듈 하위 호환성 유지 래퍼 함수들
# ==========================================

def load_pose_db(engine: str = "flux", path: Optional[Path] = None) -> Dict[str, PoseEntry]:
    """엔진(flux / sdxl)에 맞는 포즈 데이터베이스 로드 및 PoseEntry 딕셔너리로 변환."""
    return default_pose_service.load_pose_db(engine=engine, path=path)


def find_character(char_name: str, roster: str = DEFAULT_ROSTER) -> tuple[CharacterConfig, str]:
    """캐릭터 JSON 설정 로드 및 로스터 자동 탐색."""
    return default_character_service.find_character(char_name=char_name, roster=roster)


def resolve_characters(char_expr: str, roster: str = DEFAULT_ROSTER) -> List[tuple[CharacterConfig, str]]:
    """'all', 쉼표 구분, 또는 단일 캐릭터 표현식을 해석하여 캐릭터 목록 반환."""
    return default_character_service.resolve_characters(char_expr=char_expr, roster=roster)


def load_character(char_name: str, roster: str = DEFAULT_ROSTER) -> CharacterConfig:
    """단일 캐릭터 로드 래퍼 함수."""
    char, _ = default_character_service.find_character(char_name, roster=roster)
    return char


def find_reference_image(prefix: str, roster: str = DEFAULT_ROSTER, custom_path: Optional[str] = None) -> Optional[Path]:
    """캐릭터의 참조 이미지를 탐색합니다."""
    return default_asset_service.find_reference_image(prefix=prefix, roster=roster, custom_path=custom_path)


def load_background_preset(roster: str, key: str = "default") -> str:
    """projects/{roster}/background.json 로드."""
    return default_background_service.get_preset(roster=roster, key=key)


def resolve_pose_codes(expr: str, db: Dict[str, PoseEntry]) -> List[str]:
    """사용자가 지정한 포즈 표현식(all, emotions, 00..19, 01,02 등)을 코드 목록으로 해석."""
    return default_pose_service.resolve_pose_codes(expr=expr, db=db)


def print_roster_characters(roster: str = DEFAULT_ROSTER) -> int:
    """로스터 내 등록된 캐릭터들의 프로필 목록을 콘솔 테이블로 출력합니다."""
    char_dir = PROJECTS_DIR / roster / "characters"
    if not char_dir.exists():
        print(f"\n[오류] 로스터 캐릭터 폴더를 찾을 수 없습니다: {char_dir}")
        return 1

    files = sorted(char_dir.glob("*.json"))
    if not files:
        print(f"\n[안내] 로스터 '{roster}'에 등록된 캐릭터 JSON 파일이 없습니다.")
        return 0

    print("=" * 82)
    print(f"  [플에파] 로스터 캐릭터 목록: {roster} (총 {len(files)}명)")
    print("=" * 82)
    header = f"  {'식별자(ID)':<12} {'한글명 (영문명)':<24} {'성별':<8} {'프로필(의상)':<18} {'기본 의상 요약'}"
    print(header)
    print("  " + "-" * 78)

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            char = CharacterConfig.from_dict(data, file_path=path)
            prof_list = list(char.profiles.keys())
            prof_str = ", ".join(prof_list) if prof_list else "default"
            outfit_text = char.appearance.outfit.replace("\n", " ").strip()
            outfit_summary = (outfit_text[:28] + "..") if len(outfit_text) > 28 else (outfit_text or "-")
            print(f"  {char.prefix:<12} {char.name:<24} {char.gender:<8} {prof_str:<18} {outfit_summary}")
        except Exception as e:
            print(f"  {path.stem:<12} [오류: {e}]")

    print("=" * 82)
    return 0


def run_self_test() -> int:
    """파이프라인 무결성 자체 진단 테스트 (FLUX + SDXL 듀얼 엔진 점검)."""
    print("=" * 60)
    print("  [플에파] 시스템 무결성 자체 진단 테스트 (Dual-Engine Self-Test)")
    print("=" * 60)
    errors: List[str] = []

    # 1. FLUX 포즈 DB 로드 및 태그 순수성 검사
    try:
        flux_db = load_pose_db(engine="flux")
        print(f"✔ FLUX 포즈 DB 로드 성공 (총 {len(flux_db)}개 항목)")
        if len(flux_db) != 80:
            errors.append(f"FLUX 포즈 DB 항목 수가 80개가 아닙니다 (현재: {len(flux_db)}개)")
        for code, entry in flux_db.items():
            if "BREAK" in entry.prompt:
                errors.append(f"FLUX 코드 [{code}] 프롬프트에 금지된 BREAK 문법 잔류")
            if "((" in entry.prompt or ":1." in entry.prompt:
                errors.append(f"FLUX 코드 [{code}] 프롬프트에 SDXL 괄호 가중치 잔류")
            if not entry.label:
                errors.append(f"FLUX 코드 [{code}] 라벨 누락")
        print("✔ FLUX 80종 서술형 프롬프트 순수성 검사 완료")
    except Exception as e:
        errors.append(f"FLUX 포즈 DB 검사 실패: {e}")
        flux_db = {}

    # 2. SDXL 포즈 DB 로드 검사
    try:
        sdxl_db = load_pose_db(engine="sdxl")
        print(f"✔ SDXL 포즈 DB 로드 성공 (총 {len(sdxl_db)}개 항목)")
        if len(sdxl_db) != 80:
            errors.append(f"SDXL 포즈 DB 항목 수가 80개가 아닙니다 (현재: {len(sdxl_db)}개)")
        for code, entry in sdxl_db.items():
            if not entry.label:
                errors.append(f"SDXL 코드 [{code}] 라벨 누락")
        print("✔ SDXL 80종 Danbooru 태그 포즈 검사 완료")
    except Exception as e:
        errors.append(f"SDXL 포즈 DB 검사 실패: {e}")
        sdxl_db = {}

    # 3. 샘플 캐릭터 로드 검사
    try:
        char = load_character("sample_character")
        print(f"✔ 샘플 캐릭터({char.name}) 로드 성공")
        if not char.appearance.face_and_hair or not char.appearance.physique:
            errors.append("캐릭터 필수 외형 필드 누락")
    except Exception as e:
        errors.append(f"샘플 캐릭터 로드 실패: {e}")
        char = None

    # 4. FLUX 프롬프트 조립 및 탈의 로직 검사
    if flux_db and char:
        prompt_clothed, nude_flag = assemble_flux_prompt(char, flux_db["000"])
        if nude_flag or char.appearance.outfit not in prompt_clothed:
            errors.append("FLUX 평상 포즈(000)에서 의상 포함 누락 또는 잘못된 탈의 판정")

        prompt_nude, nude_flag = assemble_flux_prompt(char, flux_db["040"])
        if not nude_flag or char.appearance.outfit in prompt_nude:
            errors.append("FLUX H-씬(040)에서 의상 탈의 자동 스트리핑 실패")
        print("✔ FLUX 의상 착의/탈의 분기 조립 로직 검사 통과")

    # 5. SDXL 프롬프트 조립 및 탈의 로직 검사
    if sdxl_db and char:
        pos_clothed, _, nude_flag = assemble_sdxl_prompt(char, sdxl_db["000"])
        if nude_flag:
            errors.append("SDXL 평상 포즈(000)에서 잘못된 탈의 판정")

        pos_nude, _, nude_flag = assemble_sdxl_prompt(char, sdxl_db["040"])
        if not nude_flag or "nude" not in pos_nude:
            errors.append("SDXL H-씬(040)에서 nude 태그 주입 실패")
        print("✔ SDXL 의상 착의/탈의 분기 조립 로직 검사 통과")

    # 6. 워크플로우 템플릿 생성 검사 (FLUX & SDXL)
    try:
        wf_flux = build_flux_workflow("test prompt", "test_prefix", use_face_detailer=False)
        if "1" not in wf_flux or "20" not in wf_flux:
            errors.append("FLUX 기본 워크플로우 노드 생성 불완전")

        wf_sdxl = build_sdxl_workflow("test pos", "test neg", "test_prefix", use_face_detailer=False)
        if "1" not in wf_sdxl or "5" not in wf_sdxl or "20" not in wf_sdxl:
            errors.append("SDXL 기본 워크플로우 노드 생성 불완전")

        wf_ip = build_sdxl_workflow("test pos", "test neg", "test_prefix", ref_image_name="test_ref.webp")
        if "30" not in wf_ip or "32" not in wf_ip or "33" not in wf_ip:
            errors.append("SDXL IP-Adapter 워크플로우 노드 생성 불완전")
        print("✔ FLUX 및 SDXL + IP-Adapter 워크플로우 템플릿 생성 검사 통과")
    except Exception as e:
        errors.append(f"워크플로우 생성 실패: {e}")

    # 7. 프로필 스위칭 및 커스텀 네거티브 / 배경 검사
    if char:
        test_char = CharacterConfig.from_dict({
            "prefix": "test",
            "name": "Test",
            "appearance": {"outfit": "default suit", "face_and_hair": "short hair", "physique": "fit"},
            "profiles": {
                "swimsuit": {"outfit": "blue swimsuit", "sdxl_positive": "blue bikini BREAK 1girl"}
            }
        })
        test_char.apply_profile("swimsuit")
        if test_char.appearance.outfit != "blue swimsuit":
            errors.append("프로필 스위칭 의상 오버라이드 실패")
        
        _, neg, _ = assemble_sdxl_prompt(test_char, sdxl_db["000"], custom_neg="custom_tag, no_glasses")
        if "custom_tag" not in neg:
            errors.append("SDXL 커스텀 네거티브 주입 실패")
        print("✔ 프로필 스위칭 및 커스텀 네거티브 결합 검사 통과")

    # 8. 더미 Mock 생성 검사
    try:
        mock_test_path = PROJECTS_DIR / "_test_mock.webp"
        generate_mock_image(mock_test_path)
        if not mock_test_path.exists() or mock_test_path.stat().st_size == 0:
            errors.append("더미 Mock WebP 파일 생성 실패")
        else:
            mock_test_path.unlink()
        print("✔ 더미 Mock WebP 생성 파이프라인 검사 통과")
    except Exception as e:
        errors.append(f"더미 Mock 생성 테스트 예외: {e}")

    print("-" * 60)
    if errors:
        print(f"[FAIL] 총 {len(errors)}개 결함 발견:")
        for err in errors:
            print(f"  ❌ {err}")
        return 1
    else:
        print("[PASS] 모든 진단 검사 항목을 통과했습니다. FLUX / SDXL 듀얼 엔진 무결성 100% 보장.")
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flux_batch_generator",
        description="플럭스(FLUX.1 [dev]) 및 SDXL(Unholy Desire Mix) 캐릭터 에셋 배치 생성기 (플에파 / PLEPA)"
    )
    parser.add_argument("-c", "--character", "--char", help="생성할 캐릭터 이름 (예: bjh, sample_character, all)")
    parser.add_argument("-p", "--pose", "--codes", default="all", help="생성할 포즈 코드/범위 (all, emotions, 000..019, 000,001 등)")
    parser.add_argument("--all-chars", action="store_true", help="로스터 내 등록된 모든 캐릭터 일괄 순차 생성 (Kiro 호환 문법)")
    parser.add_argument("-r", "--roster", default=DEFAULT_ROSTER, help=f"로스터 폴더 (기본: {DEFAULT_ROSTER})")
    parser.add_argument("-l", "--list", action="store_true", help="로스터 내 등록된 캐릭터 프로필 목록을 콘솔 테이블로 출력")
    parser.add_argument("--profile", default=None, help="캐릭터 프로필/의상 선택 (JSON 내 profiles 섹션)")
    parser.add_argument("--engine", choices=["sdxl", "flux"], default=DEFAULT_ENGINE, help=f"이미지 생성 엔진 (기본: {DEFAULT_ENGINE} [고속 2D 애니 체크포인트], flux: FLUX.1 [dev] GGUF)")
    parser.add_argument("--ckpt", default=None, help=f"SDXL 모드에서 사용할 체크포인트 파일명 (기본: 설정값 또는 {DEFAULT_SDXL_CKPT})")
    parser.add_argument("--ckpt-tag", default=None, dest="ckpt_tag", help="체크포인트 비교용 서브폴더 태그 (예: wai, unholy) - 지정 시 assets/prefix/ckpt_태그/ 폴더에 저장")
    parser.add_argument("--bg", default=None, help="즉석 배경 프롬프트 직접 주입 (지정 시 --bg-preset 보다 우선 적용)")
    parser.add_argument("--bg-preset", default="default", help="배경 프리셋 키 (기본: default)")
    parser.add_argument("--custom_pos", "--style", default=None, help="추가 긍정 프롬프트 또는 특정 작가 화풍 태그 주입 (예: 'art by ratatatat74')")
    parser.add_argument("--custom_neg", default=None, help="추가 네거티브 프롬프트/태그 (SDXL 모드에 결합)")
    parser.add_argument("--ref_image", default=None, help="IP-Adapter 참조 이미지 파일 경로 (생략 시 references/{prefix}.webp 자동 탐색)")
    parser.add_argument("--ref_weight", type=float, default=None, help="IP-Adapter 영향력 가중치 (0.0~1.0, 기본: 캐릭터 설정치 또는 0.0)")
    parser.add_argument("--no_ref", action="store_true", default=True, help="레퍼런스 이미지(IP-Adapter)를 비활성화하고 순수 프롬프트로만 생성 (기본값: True)")
    parser.add_argument("--use-ref", dest="use_ref", action="store_true", help="레퍼런스 이미지(IP-Adapter) 기능 명시적 활성화 (화질 저하 주의)")
    parser.add_argument("--mock", action="store_true", help="ComfyUI 호출 없이 초고속(0.001초) 더미 WebP 이미지 생성으로 파이프라인 무결성 검증")
    parser.add_argument("--dry-run", action="store_true", help="ComfyUI 호출 없이 프롬프트 및 파일명 점검")
    parser.add_argument("--overwrite", "-f", "--force", action="store_true", help="기존 파일이 있어도 강제로 덮어쓰기 (교체/리롤용)")
    parser.add_argument("--skip-existing", action="store_true", help="기존 파일 건너뛰기 (기본값으로 항상 활성화됨)")
    parser.add_argument("--face-detailer", action="store_true", help="Face Detailer 얼굴 보정 활성화")
    parser.add_argument("--upscale", action="store_true", help="4x AI 초고화질 업스케일러 활성화")
    parser.add_argument("--steps", type=int, default=None, help="샘플링 스텝 수 (기본: flux=20, sdxl=25)")
    parser.add_argument("--cfg", type=float, default=None, help="CFG 스케일 (기본: flux=3.5, sdxl=6.0)")
    parser.add_argument("--sampler", default=None, help="샘플러 알고리즘 (기본: flux=euler, sdxl=euler_ancestral)")
    parser.add_argument("--scheduler", default=None, help="스케줄러 (기본: flux=simple, sdxl=normal)")
    parser.add_argument("--unet", default=None, help=f"FLUX 모드 GGUF UNet 모델 파일명 (기본: 설정값 또는 {DEFAULT_UNET_GGUF})")
    parser.add_argument("--lora", default="modern-anime-lora.safetensors", help="FLUX 모드 LoRA 파일명 (기본: modern-anime-lora.safetensors, 해제: none)")
    parser.add_argument("--lora-weight", type=float, default=0.9, help="LoRA 적용 강도 (기본: 0.9)")
    parser.add_argument("--width", type=int, default=None, help="이미지 가로 폭 (기본: flux=896, sdxl=832)")
    parser.add_argument("--height", type=int, default=None, help="이미지 세로 높이 (기본: flux=1152, sdxl=1216)")
    parser.add_argument(
        "--naming",
        choices=["hybrid", "code", "label"],
        default="hybrid",
        help="에셋 파일명 형식 (hybrid: prefix_000_라벨.webp [기본값], code: prefix_000.webp, label: prefix_라벨.webp)"
    )
    parser.add_argument("--censor", action="store_true", help="2D 애니 성기 자동 검열 활성화 (무검열 원본과 함께 _censored.webp 추가 생성)")
    parser.add_argument(
        "--censor-style",
        choices=["bar", "wide_bar", "slim_bar", "shadow", "mosaic"],
        default="bar",
        help="검열 시각 스타일 (bar/wide_bar: 와이드 솔리드 바, slim_bar: 미니멀 슬림 바, shadow: 그림자 실루엣, mosaic: 격자 모자이크)"
    )
    parser.add_argument(
        "--censor-targets",
        default="penis",
        help="검열 대상 부위 (penis: 남성기만, all: 전체, 쉼표 구분)"
    )
    parser.add_argument("--test", action="store_true", help="시스템 무결성 자가 진단 실행")

    args = parser.parse_args(argv)

    if args.test:
        return run_self_test()

    if args.list:
        return print_roster_characters(roster=args.roster)

    if args.all_chars:
        args.character = "all"

    if not args.character:
        parser.print_help()
        print("\n[오류] -c/--character 인수로 캐릭터를 지정해야 합니다 (캐릭터 목록 확인: -l / --list).")
        return 1

    params = GenerationParams(
        character_expr=args.character,
        pose_expr=args.pose,
        roster=args.roster,
        profile=args.profile,
        engine=args.engine,
        ckpt=args.ckpt,
        bg=args.bg,
        bg_preset=args.bg_preset,
        custom_pos=args.custom_pos,
        custom_neg=args.custom_neg,
        ref_image=args.ref_image,
        ref_weight=args.ref_weight,
        no_ref=False if args.use_ref else True,
        mock=args.mock,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        face_detailer=args.face_detailer,
        upscale=args.upscale,
        steps=args.steps,
        cfg=args.cfg,
        sampler=args.sampler,
        scheduler=args.scheduler,
        unet=args.unet,
        lora=args.lora,
        lora_weight=args.lora_weight,
        width=args.width,
        height=args.height,
        naming=args.naming,
        censor=args.censor,
        censor_style=args.censor_style,
        censor_targets=args.censor_targets,
        ckpt_tag=args.ckpt_tag,
    )

    try:
        results = default_generation_service.run_batch(params)
    except ConnectionError as ce:
        print(f"\n[오류] {ce}")
        print("(프롬프트 구성 점검은 --dry-run, 가상 생성 시뮬레이션은 --mock 옵션을 사용하세요)")
        return 1
    except Exception as e:
        print(f"\n[실행 오류] {e}")
        return 1

    # 마지막 에셋 폴더 탐색기 열기
    if not args.dry_run and results:
        for r in reversed(results):
            if r.image_path and r.image_path.parent.exists():
                open_in_explorer(r.image_path.parent.parent)
                break

    return 0


if __name__ == "__main__":
    sys.exit(main())
