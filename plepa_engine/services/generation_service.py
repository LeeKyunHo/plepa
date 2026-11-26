"""
plepa_engine.services.generation_service
SDXL 단일 파이프라인 배치 이미지 생성 핵심 서비스.
CLI와 GUI가 공통으로 호출하며, 진행률 콜백 및 취소 인터럽트를 지원합니다.
"""

from __future__ import annotations

import logging
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from plepa_engine.censor import censor_file, is_pose_censor_required, unload_censor_models
from plepa_engine.comfy_client import ComfyClient
from plepa_engine.config import DEFAULT_ENGINE, DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.models import CharacterConfig, GenerationResult
from plepa_engine.qa_validator import validate_generated_image
from plepa_engine.reporter import print_batch_summary, print_overall_batch_summary
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.background_service import default_background_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation.manifest import load_manifest_state, save_batch_manifest_atomic
from plepa_engine.services.generation.plan import (
    compute_deterministic_pose_seed,
    generate_mock_image,
    get_optimal_resolution_for_pose,
    is_portrait_emotion_pose,
    prepare_batch_plan,
    resolve_effective_sdxl_params,
)
from plepa_engine.services.generation.prepare import (
    build_pose_work_item,
    resolve_char_workspace_and_ref,
)
from plepa_engine.services.generation.runner import (
    apply_censor_to_asset_atomic,
    dispatch_pose_work_item,
    resolve_origin_path_compat,
)
from plepa_engine.services.generation_options import (  # CLI·Engine·GUI 단일 진실 공급원(SSOT)
    GENERATION_OPTION_SPECS,
    resolve_workflow_loras,
)
from plepa_engine.services.pose_background_service import default_pose_bg_service
from plepa_engine.services.pose_service import default_pose_service

logger = logging.getLogger(__name__)


@dataclass
class GenerationParams:
    """배치 생성 파라미터 컨테이너."""
    character_expr: str
    pose_expr: str = "all"
    roster: str = DEFAULT_ROSTER
    profile: Optional[str] = None
    engine: str = DEFAULT_ENGINE
    ckpt: Optional[str] = None
    bg: Optional[str] = None
    bg_preset: str = "default"
    custom_pos: Optional[str] = None
    custom_neg: Optional[str] = None
    ref_image: Optional[str] = None
    ref_weight: Optional[float] = None
    no_ref: bool = True
    mock: bool = False
    dry_run: bool = False
    overwrite: bool = False
    face_detailer: Optional[bool] = None
    hand_detailer: bool = False
    upscale: bool = False
    steps: Optional[int] = None
    cfg: Optional[float] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    unet: Optional[str] = None
    lora: Optional[str] = None
    lora_weight: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    naming: str = "hybrid"
    censor: bool = False
    censor_style: str = "white_silhouette"
    censor_targets: str = "penis"
    censor_only: bool = False  # 신규 이미지 생성 없이 기존 에셋의 검열본만 일괄 생성
    ckpt_tag: Optional[str] = None  # 체크포인트 비교용 서브폴더 태그 (예: "unholy", "wai")
    auto_qc: bool = True
    max_retries: int = 3
    freeu: bool = True  # ComfyUI FreeU_Advanced SDXL 선명도/질감 부스팅
    prompt_alert_threshold: int = 2  # 연속 불량 시 프롬프트 점검 경고 발령 임계치
    reuse_seed: bool = False  # _batch_manifest.json의 이전 골든 시드 고정 재생성
    deterministic_pose_seed: bool = False  # 포즈 코드·캐릭터 기반 결정론적 시드 자동 고정
    strict_censor_qc: bool = False  # 필수 성인 노출 씬에서 성기 미탐지 시 자동 리롤
    retry_qc_failed: bool = True  # _batch_manifest.json 내 qc_passed=False 항목 overwrite=False 시 자동 재시도
    anchor_fallback: bool = False  # 검열 탐지 실패 시 포즈 기반 안전 앵커 폴백 마스킹 (기본 False)
    seed: Optional[int] = None  # 특정 난수 시드 고정 생성
    out_dir: Optional[str] = None  # 별도 테스트 출력 루트 폴더 (지정 시 out_dir/{roster}/{char}/에 저장)


class GenerationService:
    """배치 이미지 생성 파이프라인 서비스."""

    def __init__(
        self,
        character_svc=default_character_service,
        pose_svc=default_pose_service,
        bg_svc=default_background_service,
        asset_svc=default_asset_service,
        pose_bg_svc=default_pose_bg_service,
    ):
        self.char_svc = character_svc
        self.pose_svc = pose_svc
        self.bg_svc = bg_svc
        self.asset_svc = asset_svc
        self.pose_bg_svc = pose_bg_svc

    @staticmethod
    def _resolve_origin_path(
        filename: str,
        sub_origin_dir: Path,
        legacy_sub_origin: Optional[Path],
        origin_dir: Path,
    ) -> Path:
        """2대/6대/플랫 구조 호환 원본(_origin) 백업 경로를 우선순위에 따라 탐색합니다."""
        return resolve_origin_path_compat(filename, sub_origin_dir, legacy_sub_origin, origin_dir)

    @staticmethod
    def _apply_censor_to_asset(
        origin_path: Path,
        out_path: Path,
        sub_origin_dir: Optional[Path],
        params: GenerationParams,
        pose_code: str,
        roster: str,
        src_for_backup: Optional[Path] = None,
        overwrite_origin: bool = False,
        is_nude: bool = False,
        is_otokonoko: Optional[bool] = None,
    ) -> bool:
        """단일 무검열 원본(_origin) 백업을 보장한 뒤 검열본을 원자적 임시파일로 생성하여 out_path를 안전 교체합니다."""
        del sub_origin_dir
        return apply_censor_to_asset_atomic(
            censor_file_fn=censor_file,
            origin_path=origin_path,
            out_path=out_path,
            params=params,
            pose_code=pose_code,
            roster=roster,
            src_for_backup=src_for_backup,
            overwrite_origin=overwrite_origin,
            is_nude=is_nude,
            is_otokonoko=is_otokonoko,
        )

    def run_batch(
        self,
        params: GenerationParams,
        on_progress: Optional[Callable[[int, int, GenerationResult], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        quiet: bool = False,
    ) -> List[GenerationResult]:
        """배치 생성 루프를 실행합니다 (on_progress 및 is_cancelled 인터럽트 지원)."""
        plan = prepare_batch_plan(
            params=params, char_svc=self.char_svc, pose_svc=self.pose_svc,
            resolve_params_fn=resolve_effective_sdxl_params, comfy_client_cls=ComfyClient, quiet=quiet,
        )
        current_item_index = 0
        all_results: List[GenerationResult] = []
        session_cm = plan.client.session() if (not params.dry_run and not params.mock and not params.censor_only) else nullcontext()
        total_batch_start = time.time()

        with session_cm:
            for char_idx, (char, actual_roster) in enumerate(plan.target_chars, 1):
                if is_cancelled and is_cancelled():
                    if not quiet:
                        print("\n[알림] 사용자에 의해 배치가 취소되었습니다.")
                    break

                output_dir, origin_dir, ref_file_name, ref_weight = resolve_char_workspace_and_ref(
                    char_idx=char_idx, total_chars=len(plan.target_chars), char=char, actual_roster=actual_roster,
                    params=params, asset_svc=self.asset_svc, client=plan.client, quiet=quiet, projects_dir=PROJECTS_DIR,
                )
                char_results: List[GenerationResult] = []
                char_start = time.time()
                char_codes = plan.char_pose_map[char.prefix]
                manifest_seeds, manifest_qc_failed = load_manifest_state(output_dir)

                for idx, code in enumerate(char_codes, 1):
                    if is_cancelled and is_cancelled():
                        if not quiet:
                            print("\n[알림] 사용자에 의해 배치가 취소되었습니다.")
                        break
                    current_item_index += 1
                    item = build_pose_work_item(
                        idx=idx, total_char_codes=len(char_codes), code=code, pose=plan.db[code],
                        char=char, actual_roster=actual_roster, output_dir=output_dir, origin_dir=origin_dir,
                        ref_file_name=ref_file_name, ref_weight=ref_weight, existing_manifest_seeds=manifest_seeds,
                        plan=plan, params=params, bg_svc=self.bg_svc, pose_bg_svc=self.pose_bg_svc,
                        get_opt_res_fn=get_optimal_resolution_for_pose, compute_det_seed_fn=compute_deterministic_pose_seed,
                        quiet=quiet,
                    )
                    res = dispatch_pose_work_item(
                        item=item, char=char, origin_dir=origin_dir, actual_roster=actual_roster,
                        plan=plan, existing_manifest_qc_failed=manifest_qc_failed, params=params,
                        validate_fn=validate_generated_image, is_censor_req_fn=is_pose_censor_required,
                        apply_censor_fn=self._apply_censor_to_asset, quiet=quiet,
                    )
                    char_results.append(res)
                    all_results.append(res)
                    if on_progress:
                        on_progress(current_item_index, plan.total_items, res)

                if not quiet:
                    print_batch_summary(char.prefix, char_results, output_dir, time.time() - char_start, char_name=char.name)
                self._save_batch_manifest(output_dir, char, actual_roster, params, char_results)

        if params.censor or params.censor_only or params.strict_censor_qc:
            unload_censor_models()
        if not quiet and all_results:
            print_overall_batch_summary(all_results, time.time() - total_batch_start)
        return all_results

    def _save_batch_manifest(
        self,
        output_dir: Path,
        char: CharacterConfig,
        roster: str,
        params: GenerationParams,
        results: List[GenerationResult],
    ) -> None:
        """배치 실행 기록을 `_batch_manifest.json`에 원자적으로 저장합니다."""
        save_batch_manifest_atomic(output_dir, char, roster, params, results)


default_generation_service = GenerationService()
