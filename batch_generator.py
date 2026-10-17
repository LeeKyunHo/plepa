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
from plepa_engine.services.health_service import (
    default_health_service,
    format_diagnostics_table,
)
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.workflow_templates import build_flux_workflow, build_sdxl_workflow



# ==========================================
# 기존 모듈 하위 호환성 유지 래퍼 함수들
# ==========================================

def load_pose_db(engine: str = "flux", path: Optional[Path] = None) -> Dict[str, PoseEntry]:
    """엔진(flux / sdxl)에 맞는 포즈 데이터베이스 로드 및 PoseEntry 딕셔너리로 변환."""
    return default_pose_service.load_pose_db(engine=engine, path=path)


def get_available_rosters() -> List[str]:
    """등록된 캐릭터가 존재하는 모든 로스터 폴더 목록 반환."""
    return default_character_service.list_rosters()


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


def resolve_pose_codes(expr: str, db: Dict[str, PoseEntry], roster: Optional[str] = None) -> List[str]:
    """사용자가 지정한 포즈 표현식(all, emotions, 00..19, 01,02 등)을 코드 목록으로 해석."""
    return default_pose_service.resolve_pose_codes(expr=expr, db=db, roster=roster)


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


def print_roster_audit(roster: str = DEFAULT_ROSTER) -> int:
    """로스터 내 캐릭터들의 에셋 완비율, 누락 포즈, 검열 원본 백업 여부를 전수 감사하여 콘솔 테이블로 출력합니다."""
    reports = default_asset_service.audit_roster_assets(roster=roster)
    if not reports:
        print(f"\n[안내] 로스터 '{roster}'에 감사할 캐릭터가 없습니다.")
        return 0

    print("=" * 95)
    print(f"  [플에파 에셋 전수 감사 리포트] 로스터: {roster} (총 {len(reports)}명)")
    print("=" * 95)
    header = f"  {'식별자':<8} {'이름':<14} {'성별':<10} {'보유 / 기대':<14} {'완비율':<10} {'_origin 백업':<14} {'라벨불일치':<10} {'누락 코드'}"
    print(header)
    print("  " + "-" * 91)

    for r in reports:
        cnt_str = f"{r['present_count']} / {r['expected_count']}"
        rate_str = f"{r['completion_rate']}%"
        origin_str = f"{r['origin_count']}장"
        outdated_str = f"{r['outdated_labels']}건" if r['outdated_labels'] > 0 else "0건"
        missing = r['missing_codes']
        if not missing:
            missing_str = "완벽 (누락 없음)"
        elif len(missing) <= 6:
            missing_str = ",".join(missing)
        else:
            missing_str = f"{','.join(missing[:5])}.. (+{len(missing)-5}개)"

        print(f"  {r['prefix']:<8} {r['name']:<14} {r['gender']:<10} {cnt_str:<14} {rate_str:<10} {origin_str:<14} {outdated_str:<10} {missing_str}")

    print("=" * 95)
    return 0


def run_self_test() -> int:
    """플에파 10단계 시스템 통합 무결성 진단 실행 (HealthService)."""
    results = default_health_service.run_full_diagnostics(check_comfy=True)
    table_str = format_diagnostics_table(results)
    print(table_str)

    has_fail = any(r.status == "FAIL" for r in results)
    return 1 if has_fail else 0



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
    parser.add_argument("--ref_image", "--ref-image", default=None, help="IP-Adapter 참조 이미지 파일 경로 (생략 시 references/{prefix}.webp 자동 탐색)")
    parser.add_argument("--ref_weight", "--ref-weight", type=float, default=None, help="IP-Adapter 영향력 가중치 (0.0~1.0, 기본: 캐릭터 설정치 또는 0.0)")
    parser.add_argument("--no_ref", "--no-ref", action="store_true", default=False, help="레퍼런스 이미지(IP-Adapter)를 비활성화하고 순수 프롬프트로만 생성")
    parser.add_argument("--use-ref", dest="use_ref", action="store_true", default=True, help="레퍼런스 이미지(IP-Adapter) 기능 활성화 (기본값: True)")
    parser.add_argument("--mock", action="store_true", help="ComfyUI 호출 없이 초고속(0.001초) 더미 WebP 이미지 생성으로 파이프라인 무결성 검증")
    parser.add_argument("--dry-run", action="store_true", help="ComfyUI 호출 없이 프롬프트 및 파일명 점검")
    parser.add_argument("--overwrite", "-f", "--force", action="store_true", help="기존 파일이 있어도 강제로 덮어쓰기 (교체/리롤용)")
    parser.add_argument("--skip-existing", action="store_true", help="기존 파일 건너뛰기 (기본값으로 항상 활성화됨)")
    parser.add_argument("--face-detailer", dest="face_detailer", action="store_true", default=None, help="Face Detailer 얼굴 보정 강제 활성화")
    parser.add_argument("--no-face-detailer", dest="face_detailer", action="store_false", help="Face Detailer 얼굴 보정 강제 비활성화")
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
        choices=["white_silhouette", "silhouette", "black_silhouette", "bar", "wide_bar", "slim_bar", "shadow", "mosaic"],
        default="white_silhouette",
        help="검열 시각 스타일 (white_silhouette: MobileSAM 외곽선 화이트 실루엣 [기본값], silhouette/black_silhouette: 외곽선 블랙 실루엣, bar/wide_bar: 와이드 솔리드 바, slim_bar: 미니멀 슬림 바, shadow: 그림자 실루엣, mosaic: 격자 모자이크)"
    )
    parser.add_argument(
        "--censor-targets",
        default="penis,pussy",
        help="검열 대상 부위 (penis, pussy, all, 쉼표 구분 기본: penis,pussy)"
    )
    parser.add_argument("--censor-only", action="store_true", help="ComfyUI 호출 없이 기존 생성된 에셋들의 검열본만 초고속(0.2초) 일괄 갱신/생성")
    parser.add_argument("--reuse-seed", action="store_true", help="_batch_manifest.json에 기록된 기존 골든 시드를 재사용하여 동일 구도로 의상/프롬프트 재생성")
    parser.add_argument("--strict-censor-qc", action="store_true", help="필수 성인 결합/노출 씬에서 성기 미탐지 시 구도 불량으로 판정하여 자동 리롤")
    parser.add_argument("--audit", action="store_true", help="지정된 로스터의 캐릭터별 에셋 완비율, 누락 포즈, 검열 원본 백업 여부 1초 전수 감사 리포트 출력")
    parser.add_argument("--no-qc", action="store_true", help="Auto-QC 품질 검증 및 불량 시 자동 재시도 비활성화")
    parser.add_argument("--max-retries", type=int, default=3, help="Auto-QC 불량 시 최대 재시도(리롤) 횟수 (기본: 3)")
    parser.add_argument("--test", action="store_true", help="시스템 무결성 자가 진단 실행")

    args = parser.parse_args(argv)

    is_all_rosters = args.roster.strip().lower() in ("all", "전체", "*")

    if args.test:
        return run_self_test()

    if args.audit:
        if is_all_rosters:
            rosters = get_available_rosters()
            print("=" * 95)
            print(f"  [플에파 전 로스터 전수 감사 리포트] 총 {len(rosters)}개 로스터: {', '.join(rosters)}")
            print("=" * 95)
            for r in rosters:
                print_roster_audit(roster=r)
            return 0
        return print_roster_audit(roster=args.roster)

    if args.list:
        if is_all_rosters:
            rosters = get_available_rosters()
            print("=" * 82)
            print(f"  [플에파 전 로스터 캐릭터 목록] 총 {len(rosters)}개 로스터: {', '.join(rosters)}")
            print("=" * 82)
            for r in rosters:
                print_roster_characters(roster=r)
            return 0
        return print_roster_characters(roster=args.roster)

    if args.all_chars:
        args.character = "all"

    if not args.character:
        parser.print_help()
        if is_all_rosters:
            print("\n[오류] 전 로스터(-r all) 실행 시 --all-chars (또는 -c all) 옵션으로 대상 캐릭터를 지정해야 합니다.")
        else:
            print("\n[오류] -c/--character 인수로 캐릭터를 지정해야 합니다 (캐릭터 목록 확인: -l / --list).")
        return 1

    target_rosters = get_available_rosters() if is_all_rosters else [args.roster]
    if not target_rosters:
        print(f"\n[오류] 생성 대상 로스터를 찾을 수 없습니다: {args.roster}")
        return 1

    total_rosters = len(target_rosters)
    if is_all_rosters:
        print("=" * 82)
        print(f"  [플에파 전 로스터 일괄 순회] 대상 로스터: {', '.join(target_rosters)} (총 {total_rosters}개)")
        print("=" * 82)

    all_results: List[GenerationResult] = []

    for r_idx, target_roster in enumerate(target_rosters, 1):
        if is_all_rosters:
            print(f"\n▶ [{r_idx}/{total_rosters}] 로스터 작업 시작: '{target_roster}'")

        params = GenerationParams(
            character_expr=args.character,
            pose_expr=args.pose,
            roster=target_roster,
            profile=args.profile,
            engine=args.engine,
            ckpt=args.ckpt,
            bg=args.bg,
            bg_preset=args.bg_preset,
            custom_pos=args.custom_pos,
            custom_neg=args.custom_neg,
            ref_image=args.ref_image,
            ref_weight=args.ref_weight,
            no_ref=args.no_ref,
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
            censor=(args.censor or args.censor_only),
            censor_style=args.censor_style,
            censor_targets=args.censor_targets,
            censor_only=args.censor_only,
            ckpt_tag=args.ckpt_tag,
            auto_qc=(not args.no_qc),
            max_retries=args.max_retries,
            reuse_seed=args.reuse_seed,
            strict_censor_qc=args.strict_censor_qc,
        )

        try:
            results = default_generation_service.run_batch(params)
            all_results.extend(results)
        except ConnectionError as ce:
            print(f"\n[오류] {ce}")
            print("(프롬프트 구성 점검은 --dry-run, 가상 생성 시뮬레이션은 --mock 옵션을 사용하세요)")
            return 1
        except Exception as e:
            if is_all_rosters:
                print(f"  [경고] 로스터 '{target_roster}' 생성 중 오류 발생: {e}")
            else:
                print(f"\n[실행 오류] {e}")
                return 1

    if is_all_rosters:
        print("\n" + "=" * 82)
        print(f"  [플에파 전 로스터 일괄 순회 완료] 총 {len(all_results)}건 처리 완료")
        print("=" * 82)

    # 마지막 에셋 폴더 탐색기 열기
    if not args.dry_run and all_results:
        for r in reversed(all_results):
            if r.image_path and r.image_path.parent.exists():
                open_in_explorer(r.image_path.parent.parent)
                break

    return 0


if __name__ == "__main__":
    sys.exit(main())
