"""
batch_generator.py
SDXL 단일 파이프라인(Unholy Desire Mix / Pony / Illustrious) 기반 캐릭터 에셋 배치 생성기 (플에파 / PLEPA) - CLI 진입점.
CLI 인터페이스 및 하위 호환성을 유지하며, 실제 처리는 서비스 레이어(plepa_engine.services)에 위임합니다.
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
    DEFAULT_SDXL_CFG,
    DEFAULT_SDXL_CKPT,
    DEFAULT_SDXL_HEIGHT,
    DEFAULT_SDXL_SAMPLER,
    DEFAULT_SDXL_SCHEDULER,
    DEFAULT_SDXL_STEPS,
    DEFAULT_SDXL_WIDTH,
    PROJECTS_DIR,
    configure_stdio,
)

configure_stdio()
from plepa_engine.models import (
    CharacterConfig,
    GenerationResult,
    GenerationTarget,
    PoseEntry,
)
from plepa_engine.prompt_builder import assemble_sdxl_prompt
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
from plepa_engine.workflow_templates import build_sdxl_workflow



# ==========================================
# 기존 모듈 하위 호환성 유지 래퍼 함수들
# ==========================================

def load_pose_db(engine: str = DEFAULT_ENGINE, path: Optional[Path] = None) -> Dict[str, PoseEntry]:
    """포즈 데이터베이스 로드 및 PoseEntry 딕셔너리로 변환 (기본: sdxl)."""
    return default_pose_service.load_pose_db(engine=engine, path=path)


def get_available_rosters(include_legacy: bool = False) -> List[str]:
    """등록된 캐릭터가 존재하는 로스터 폴더 목록 반환 (기본: legacy 제외)."""
    return default_character_service.list_rosters(include_legacy=include_legacy)


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
    from plepa_engine.reporter import report_roster_characters
    return report_roster_characters(roster=roster)


def print_roster_audit(roster: str = DEFAULT_ROSTER) -> int:
    """로스터 내 캐릭터들의 에셋 완비율, 누락 포즈, 검열 원본 백업 여부를 전수 감사하여 출력합니다."""
    from plepa_engine.reporter import report_roster_audit
    return report_roster_audit(roster=roster)


def run_self_test() -> int:
    """플에파 10단계 시스템 통합 무결성 진단 실행 (HealthService)."""
    results = default_health_service.run_full_diagnostics(check_comfy=True)
    table_str = format_diagnostics_table(results)
    print(table_str)

    has_fail = any(r.status == "FAIL" for r in results)
    return 1 if has_fail else 0



def create_parser() -> argparse.ArgumentParser:
    """배치 생성기 CLI ArgumentParser 생성 (단일 진실 공급원)."""
    parser = argparse.ArgumentParser(
        prog="batch_generator",
        description="SDXL 단일 파이프라인(Unholy Desire Mix / Pony / Illustrious) 캐릭터 에셋 배치 생성기 (플에파 / PLEPA)"
    )
    parser.add_argument("-c", "--character", "--char", help="생성할 캐릭터 이름 (예: bjh, sample_character, all)")
    parser.add_argument("-p", "--pose", "--codes", default="all", help="생성할 포즈 코드/범위 (all, emotions, 000..019, 000,001 등)")
    parser.add_argument("--all-chars", action="store_true", help="로스터 내 등록된 모든 캐릭터 일괄 순차 생성 (Kiro 호환 문법)")
    parser.add_argument("-r", "--roster", default=DEFAULT_ROSTER, help=f"로스터 폴더 (기본: {DEFAULT_ROSTER}, all: 활성 로스터 순회)")
    parser.add_argument("--include-legacy", action="store_true", help="status=legacy 구형 로스터까지 -r all 및 목록 대상에 포함")
    parser.add_argument("-l", "--list", action="store_true", help="로스터 내 등록된 캐릭터 프로필 목록을 콘솔 테이블로 출력")
    parser.add_argument("--profile", default=None, help="캐릭터 프로필/의상 선택 (JSON 내 profiles 섹션)")
    parser.add_argument("--engine", choices=["sdxl"], default=DEFAULT_ENGINE, help=f"이미지 생성 엔진 (기본: {DEFAULT_ENGINE} [SDXL 단일 파이프라인])")
    parser.add_argument("--ckpt", default=None, help=f"SDXL 체크포인트 파일명 (기본: 설정값 또는 {DEFAULT_SDXL_CKPT})")
    parser.add_argument("--ckpt-tag", default=None, dest="ckpt_tag", help="체크포인트 비교용 서브폴더 태그 (예: wai, unholy) - 지정 시 assets/prefix/ckpt_태그/ 폴더에 저장")
    parser.add_argument("--bg", default=None, help="즉석 배경 프롬프트 직접 주입 (지정 시 --bg-preset 보다 우선 적용)")
    parser.add_argument("--bg-preset", default="default", help="배경 프리셋 키 (기본: default)")
    parser.add_argument("--custom_pos", "--custom-pos", "--style", dest="custom_pos", default=None, help="추가 긍정 프롬프트 또는 특정 작가 화풍 태그 주입 (예: 'art by ratatatat74')")
    parser.add_argument("--custom_neg", "--custom-neg", dest="custom_neg", default=None, help="추가 네거티브 프롬프트/태그 (SDXL 모드에 결합)")
    parser.add_argument("--ref_image", "--ref-image", default=None, help="IP-Adapter 참조 이미지 파일 경로 (생략 시 references/{prefix}.webp 자동 탐색)")
    parser.add_argument("--ref_weight", "--ref-weight", type=float, default=None, help="IP-Adapter 영향력 가중치 (0.0~1.0, 기본: 캐릭터 설정치 또는 0.0)")
    parser.add_argument("--no_ref", "--no-ref", dest="no_ref", action="store_true", default=True, help="레퍼런스 이미지(IP-Adapter) 비활성화 (기본값: True, 순수 프롬프트 생성)")
    parser.add_argument("--use-ref", "--use_ref", dest="no_ref", action="store_false", help="레퍼런스 이미지(IP-Adapter) 명시적 활성화 (체크포인트·레퍼런스 색감 편향 주의)")
    parser.add_argument("--mock", action="store_true", help="ComfyUI 호출 없이 초고속(0.001초) 더미 WebP 이미지 생성으로 파이프라인 무결성 검증")
    parser.add_argument("--dry-run", action="store_true", help="ComfyUI 호출 없이 프롬프트 및 파일명 점검")
    parser.add_argument("--overwrite", "-f", "--force", action="store_true", help="기존 파일이 있어도 강제로 덮어쓰기 (교체/리롤용)")
    parser.add_argument("--skip-existing", action="store_true", help="기존 파일 건너뛰기 (기본값으로 항상 활성화됨)")
    parser.add_argument("--face-detailer", dest="face_detailer", action="store_true", default=None, help="Face Detailer 얼굴 보정 워크플로우 활성화 (기본: 활성화)")
    parser.add_argument("--no-face-detailer", dest="face_detailer", action="store_false", help="Face Detailer 얼굴 보정 워크플로우 비활성화")
    parser.add_argument("--hand-detailer", dest="hand_detailer", action="store_true", default=False, help="Hand Detailer 손 보정 워크플로우 체이닝 활성화")
    parser.add_argument("--no-hand-detailer", dest="hand_detailer", action="store_false", help="Hand Detailer 손 보정 비활성화")
    parser.add_argument("--freeu", dest="freeu", action="store_true", default=True, help="ComfyUI FreeU_Advanced 노드로 SDXL 선명도 및 질감 부스팅 (기본: 활성화)")
    parser.add_argument("--no-freeu", dest="freeu", action="store_false", help="FreeU 선명도 부스팅 비활성화")
    parser.add_argument("--upscale", action="store_true", help="4x AI 초고화질 업스케일러 활성화")
    parser.add_argument("--steps", type=int, default=None, help=f"샘플링 스텝 수 (기본: {DEFAULT_SDXL_STEPS})")
    parser.add_argument("--cfg", type=float, default=None, help=f"CFG 스케일 (기본: {DEFAULT_SDXL_CFG})")
    parser.add_argument("--sampler", default=None, help=f"샘플러 알고리즘 (기본: {DEFAULT_SDXL_SAMPLER})")
    parser.add_argument("--scheduler", default=None, help=f"스케줄러 (기본: {DEFAULT_SDXL_SCHEDULER})")
    parser.add_argument("--unet", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--lora", default=None, help="LoRA 파일명/체이닝 목록 (쉼표 구분, 'none' 지정 시 비활성, 미지정 시 캐릭터 설정 사용)")
    parser.add_argument("--lora-weight", type=float, default=None, help="LoRA 적용 강도 (미지정 시 캐릭터 기본값 또는 0.8)")
    parser.add_argument("--width", type=int, default=None, help=f"이미지 가로 폭 (기본: {DEFAULT_SDXL_WIDTH})")
    parser.add_argument("--height", type=int, default=None, help=f"이미지 세로 높이 (기본: {DEFAULT_SDXL_HEIGHT})")
    parser.add_argument(
        "--naming",
        choices=["hybrid", "code", "label"],
        default="hybrid",
        help="에셋 파일명 형식 (hybrid: prefix_000_라벨.webp [기본값], code: prefix_000.webp, label: prefix_라벨.webp)"
    )
    parser.add_argument("--censor", action="store_true", help="2D 애니 성기 자동 검열 활성화 (무검열 원본은 {char}_origin/에 백업 보존하고 메인 에셋 경로에 검열본 저장)")
    parser.add_argument(
        "--censor-style",
        choices=["white_silhouette", "black_silhouette", "manga_bar", "manga_glow", "silhouette", "bar", "wide_bar", "slim_bar", "shadow", "mosaic", "debug_bbox"],
        default="white_silhouette",
        help="검열 시각 스타일 (white_silhouette: 외곽선 화이트 실루엣 [기본값], black_silhouette: 외곽선 블랙 실루엣, manga_bar: 주축 회전 망가 블랙 바, manga_glow: 주축+낭심 망가 화이트 글로우, bar/wide_bar: 와이드 솔리드 바, slim_bar: 미니멀 슬림 바, shadow: 그림자 실루엣, mosaic: 격자 모자이크, debug_bbox: BBox 및 신뢰도 가시화 진단 모드)"
    )
    parser.add_argument(
        "--censor-targets",
        default="penis",
        help="검열 대상 부위 (penis, pussy, all, 쉼표 구분 기본: penis)"
    )
    parser.add_argument("--anchor-fallback", action="store_true", help="검열 탐지 0건 시 포즈 DB 앵커 좌표 폴백 마스킹 허용 (기본: False)")
    parser.add_argument("--censor-only", action="store_true", help="ComfyUI 호출 없이 기존 생성된 에셋들의 검열본만 초고속(0.2초) 일괄 갱신/생성")
    parser.add_argument("--seed", type=int, default=None, help="생성에 사용할 난수 시드 값 고정 (미지정 시 무작위)")
    parser.add_argument("--out-dir", default=None, help="별도 출력 루트 폴더 (지정 시 {out_dir}/{roster}/{char}/ 하위에 저장, 기존 에셋 미간섭)")
    parser.add_argument("--reuse-seed", action="store_true", help="_batch_manifest.json에 기록된 기존 골든 시드를 재사용하여 동일 구도로 의상/프롬프트 재생성")
    parser.add_argument("--deterministic-pose-seed", action="store_true", help="포즈 코드 및 캐릭터 식별자 기반 결정론적 시드를 자동 산출하여 구도 편차 억제")
    parser.add_argument("--strict-censor-qc", action="store_true", help="필수 성인 결합/노출 씬에서 성기 미탐지 시 구도 불량으로 판정하여 자동 리롤")
    parser.add_argument("--audit", action="store_true", help="지정된 로스터의 캐릭터별 에셋 완비율, 누락 포즈, 검열 원본 백업 여부 1초 전수 감사 리포트 출력")
    parser.add_argument("--auto-qc", dest="auto_qc", action="store_true", default=True, help="Auto-QC 품질 검증 및 불량 시 자동 재시도 활성화 (기본: 활성화)")
    parser.add_argument("--no-qc", dest="auto_qc", action="store_false", help="Auto-QC 품질 검증 및 불량 시 자동 재시도 비활성화")
    parser.add_argument("--retry-qc-failed", dest="retry_qc_failed", action="store_true", default=True, help="QC 불량 이력 에셋 자동 재시도 (기본: 활성화)")
    parser.add_argument("--no-retry-qc-failed", dest="retry_qc_failed", action="store_false", help="QC 불량 이력 에셋 자동 재시도 비활성화")
    parser.add_argument("--max-retries", type=int, default=3, help="Auto-QC 불량 시 최대 재시도(리롤) 횟수 (기본: 3)")
    parser.add_argument("--prompt-alert-threshold", type=int, default=2, help="연속 불량 시 프롬프트 점검 경고 발령 임계치 (기본: 2)")
    parser.add_argument("--test", action="store_true", help="시스템 무결성 자가 진단 실행")

    return parser


def _run_roster_inspection(args: argparse.Namespace, is_all_rosters: bool) -> int:
    """--list 또는 --audit 로스터 점검 커맨드를 실행합니다."""
    rosters = get_available_rosters(include_legacy=args.include_legacy) if is_all_rosters else [args.roster]
    if args.audit:
        if is_all_rosters:
            print("=" * 95)
            print(f"  [플에파 전 로스터 전수 감사 리포트] 총 {len(rosters)}개 로스터: {', '.join(rosters)}")
            print("=" * 95)
            for r in rosters:
                print_roster_audit(roster=r)
            return 0
        return print_roster_audit(roster=args.roster)

    if is_all_rosters:
        print("=" * 82)
        print(f"  [플에파 전 로스터 캐릭터 목록] 총 {len(rosters)}개 로스터: {', '.join(rosters)}")
        print("=" * 82)
        for r in rosters:
            print_roster_characters(roster=r)
        return 0
    return print_roster_characters(roster=args.roster)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    is_all_rosters = args.roster.strip().lower() in ("all", "전체", "*")

    if args.test:
        return run_self_test()
    if args.audit or args.list:
        return _run_roster_inspection(args, is_all_rosters)

    if args.all_chars:
        args.character = "all"
    if not args.character:
        parser.print_help()
        print(
            "\n[오류] 전 로스터(-r all) 실행 시 --all-chars (또는 -c all) 옵션으로 대상 캐릭터를 지정해야 합니다."
            if is_all_rosters
            else "\n[오류] -c/--character 인수로 캐릭터를 지정해야 합니다 (캐릭터 목록 확인: -l / --list)."
        )
        return 1

    target_rosters = get_available_rosters(include_legacy=args.include_legacy) if is_all_rosters else [args.roster]
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
            character_expr=args.character, pose_expr=args.pose, roster=target_roster,
            profile=args.profile, engine=args.engine, ckpt=args.ckpt, bg=args.bg, bg_preset=args.bg_preset,
            custom_pos=args.custom_pos, custom_neg=args.custom_neg,
            ref_image=args.ref_image, ref_weight=args.ref_weight, no_ref=args.no_ref,
            mock=args.mock, dry_run=args.dry_run, overwrite=args.overwrite,
            face_detailer=args.face_detailer, hand_detailer=args.hand_detailer,
            freeu=args.freeu, upscale=args.upscale, steps=args.steps, cfg=args.cfg,
            sampler=args.sampler, scheduler=args.scheduler, unet=args.unet,
            lora=args.lora, lora_weight=args.lora_weight, width=args.width, height=args.height,
            naming=args.naming, censor=(args.censor or args.censor_only),
            censor_style=args.censor_style, censor_targets=args.censor_targets,
            censor_only=args.censor_only, ckpt_tag=args.ckpt_tag,
            auto_qc=args.auto_qc, max_retries=args.max_retries,
            retry_qc_failed=args.retry_qc_failed, prompt_alert_threshold=args.prompt_alert_threshold,
            reuse_seed=args.reuse_seed, deterministic_pose_seed=args.deterministic_pose_seed,
            strict_censor_qc=args.strict_censor_qc, anchor_fallback=args.anchor_fallback,
            seed=args.seed, out_dir=args.out_dir,
        )
        try:
            all_results.extend(default_generation_service.run_batch(params))
        except ConnectionError as ce:
            print(f"\n[오류] {ce}\n(프롬프트 구성 점검은 --dry-run, 가상 생성 시뮬레이션은 --mock 옵션을 사용하세요)")
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
    if not args.dry_run and all_results:
        for r in reversed(all_results):
            if r.image_path and r.image_path.parent.exists():
                open_in_explorer(r.image_path.parent.parent)
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
