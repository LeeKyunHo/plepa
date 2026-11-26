"""
plepa_engine.services.generation.runner
단건 에셋 분기 처리기: 소급 검열, 기존/사본 보존, dry-run, mock 및 ComfyUI 실행 라우팅.
"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from plepa_engine.models import CharacterConfig, GenerationResult
from plepa_engine.services.generation.plan import BatchPlan, generate_mock_image
from plepa_engine.services.generation.prepare import PoseWorkItem
from plepa_engine.services.generation.qc_runner import execute_comfy_with_qc_and_censor


def resolve_origin_path_compat(
    filename: str,
    sub_origin_dir: Path,
    legacy_sub_origin: Optional[Path],
    origin_dir: Path,
) -> Path:
    """2대/6대/플랫 구조 호환 원본(_origin) 백업 경로를 우선순위에 따라 탐색합니다."""
    candidates = [sub_origin_dir / filename]
    if legacy_sub_origin is not None:
        candidates.append(legacy_sub_origin / filename)
    candidates.append(origin_dir / filename)
    for cand in candidates:
        if cand.exists():
            return cand
    return sub_origin_dir / filename


def apply_censor_to_asset_atomic(
    *,
    censor_file_fn: Callable[..., Optional[Path]],
    origin_path: Path,
    out_path: Path,
    params: Any,
    pose_code: str,
    roster: str,
    src_for_backup: Optional[Path] = None,
    overwrite_origin: bool = False,
    is_nude: bool = False,
    is_otokonoko: Optional[bool] = None,
) -> bool:
    """무검열 원본(_origin) 백업 후 검열본을 원자적 임시파일 경유 os.replace로 교체합니다."""
    backup_source = src_for_backup or out_path
    if (overwrite_origin or not origin_path.exists()) and backup_source.exists():
        origin_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_source, origin_path)

    targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
    tmp_censored = out_path.parent / f".tmp_{uuid.uuid4().hex[:6]}_{out_path.name}"
    try:
        c_res = censor_file_fn(
            origin_path,
            dst_path=tmp_censored,
            style=params.censor_style,
            targets=targets,
            pose_code=pose_code,
            enable_anchor_fallback=params.anchor_fallback,
            backup_dir=None,
            roster=roster,
            is_nude=is_nude,
            is_otokonoko=is_otokonoko,
        )
        if c_res and c_res.exists():
            os.replace(tmp_censored, out_path)
            return True
        return False
    finally:
        if tmp_censored.exists():
            tmp_censored.unlink(missing_ok=True)


def handle_censor_only_item(
    *,
    item: PoseWorkItem,
    char: CharacterConfig,
    origin_dir: Path,
    actual_roster: str,
    should_censor: bool,
    is_char_otokonoko: bool,
    params: Any,
    apply_censor_fn: Callable[..., bool],
    quiet: bool,
) -> GenerationResult:
    """`--censor-only` 모드에서 기존 원본을 소급 검열해 결과 객체를 반환합니다."""
    origin_path = resolve_origin_path_compat(
        item.out_path.name, item.sub_origin_dir, item.legacy_sub_origin, origin_dir
    )
    src_path = origin_path if (origin_path.exists() and origin_path.stat().st_size > 0) else item.out_path
    if not (src_path.exists() and src_path.stat().st_size > 0):
        if not quiet:
            print(" [원본 파일 없음: 건너뜀]")
        return GenerationResult(target=item.target, success=False, duration_sec=0.0, error_message="원본 파일 없음")

    if should_censor:
        applied = apply_censor_fn(
            origin_path, item.out_path, item.sub_origin_dir, params, item.pose.code, actual_roster,
            src_for_backup=src_path, is_nude=item.is_nude, is_otokonoko=is_char_otokonoko,
        )
        if not quiet:
            if applied:
                print(f" [검열본 적용: assets/{char.prefix}/{item.out_path.name} (원본: {char.prefix}_origin/)]")
            else:
                print(" [검열 대상 미감지(원본 유지, _origin 백업 완비)]")
    elif not quiet:
        print(" [비-H씬(검열 대상 아님): 건너뜀]")
    return GenerationResult(target=item.target, success=True, image_path=item.out_path, duration_sec=0.0)


def handle_existing_or_legacy_item(
    *,
    item: PoseWorkItem,
    char: CharacterConfig,
    origin_dir: Path,
    actual_roster: str,
    should_censor: bool,
    is_char_otokonoko: bool,
    existing_manifest_qc_failed: set[str],
    params: Any,
    apply_censor_fn: Callable[..., bool],
    quiet: bool,
) -> Optional[GenerationResult]:
    """기존 파일 스킵 또는 레거시 사본 복제 조건을 검사하고, 해당 시 결과를 반환합니다."""
    code_key = str(item.code).strip()
    is_prev_qc_failed = params.retry_qc_failed and (code_key in existing_manifest_qc_failed)

    if not params.overwrite and not is_prev_qc_failed and item.out_path.exists() and item.out_path.stat().st_size > 0:
        if not quiet:
            print(" [기존 파일 보존: 건너뜀]", end="")
        if should_censor:
            origin_path = resolve_origin_path_compat(
                item.out_path.name, item.sub_origin_dir, item.legacy_sub_origin, origin_dir
            )
            applied = apply_censor_fn(
                origin_path, item.out_path, item.sub_origin_dir, params, item.pose.code, actual_roster,
                is_nude=item.is_nude, is_otokonoko=is_char_otokonoko,
            )
            if applied and not quiet:
                print(f" [검열본 적용: assets/{char.prefix}/{item.out_path.name} (원본: {char.prefix}_origin/)]", end="")
        if not quiet:
            print()
        return GenerationResult(target=item.target, success=True, image_path=item.out_path, duration_sec=0.0)

    if is_prev_qc_failed and not quiet and item.out_path.exists():
        print(" [이전 QC 불량 이력 감지 -> 자동 재생성]", end="")

    if not params.overwrite and not is_prev_qc_failed and not item.out_path.exists() and item.legacy_path.exists() and item.legacy_path.stat().st_size > 0:
        try:
            item.out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.legacy_path, item.out_path)
            if not quiet:
                print(" [기존 원본에서 하이브리드 사본 복제 완료]", end="")
            if should_censor:
                origin_path = resolve_origin_path_compat(item.out_path.name, item.sub_origin_dir, None, origin_dir)
                applied = apply_censor_fn(
                    origin_path, item.out_path, item.sub_origin_dir, params, item.pose.code, actual_roster,
                    is_nude=item.is_nude, is_otokonoko=is_char_otokonoko,
                )
                if applied and not quiet:
                    print(f" [검열본 적용: assets/{char.prefix}/{item.out_path.name} (원본: {char.prefix}_origin/)]", end="")
            if not quiet:
                print()
            return GenerationResult(target=item.target, success=True, image_path=item.out_path, duration_sec=0.0)
        except Exception as cpe:
            if not quiet:
                print(f" [사본 복제 실패({cpe}) -> 신규 생성 진행]", end="")
    return None


def dispatch_pose_work_item(
    *,
    item: PoseWorkItem,
    char: CharacterConfig,
    origin_dir: Path,
    actual_roster: str,
    plan: BatchPlan,
    existing_manifest_qc_failed: set[str],
    params: Any,
    validate_fn: Callable[..., Any],
    is_censor_req_fn: Callable[..., bool],
    apply_censor_fn: Callable[..., bool],
    quiet: bool,
) -> GenerationResult:
    """단건 포즈 작업을 censor_only / 기존보존 / dry_run / mock / ComfyUI 경로로 분기 실행합니다."""
    is_char_otokonoko = (
        str(getattr(char, "gender", "") or "").strip().lower() == "otokonoko"
        or "otokonoko" in (getattr(char, "sdxl_positive", "") or "").lower()
    )
    should_censor = (not params.dry_run) and params.censor and is_censor_req_fn(
        pose_code=item.code, pose=item.pose, is_nude=item.is_nude,
        file_path=item.out_path, roster=actual_roster, is_otokonoko=is_char_otokonoko,
    )

    if params.censor_only:
        return handle_censor_only_item(
            item=item, char=char, origin_dir=origin_dir, actual_roster=actual_roster,
            should_censor=should_censor, is_char_otokonoko=is_char_otokonoko,
            params=params, apply_censor_fn=apply_censor_fn, quiet=quiet,
        )

    preserved = handle_existing_or_legacy_item(
        item=item, char=char, origin_dir=origin_dir, actual_roster=actual_roster,
        should_censor=should_censor, is_char_otokonoko=is_char_otokonoko,
        existing_manifest_qc_failed=existing_manifest_qc_failed,
        params=params, apply_censor_fn=apply_censor_fn, quiet=quiet,
    )
    if preserved is not None:
        return preserved

    if params.dry_run:
        if not quiet:
            print(" [DRY-RUN 완료]")
        return GenerationResult(target=item.target, success=True, image_path=item.out_path, duration_sec=0.0)

    if params.mock:
        item_start = time.time()
        generate_mock_image(item.out_path)
        duration = time.time() - item_start
        if not quiet:
            print(f" [MOCK 생성 완료: {duration:.3f}초]")
        return GenerationResult(target=item.target, success=True, image_path=item.out_path, duration_sec=duration)

    return execute_comfy_with_qc_and_censor(
        client=plan.client, item=item, char=char, actual_roster=actual_roster,
        should_censor=should_censor, is_char_otokonoko=is_char_otokonoko,
        params=params, validate_fn=validate_fn,
        is_censor_req_fn=is_censor_req_fn, apply_censor_fn=apply_censor_fn, quiet=quiet,
    )
