"""
plepa_engine.services.generation.plan
배치 생성 파라미터/해상도/결정론적 시드/Mock 유틸리티 및 실행 계획(BatchPlan) 준비 헬퍼.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from plepa_engine.checkpoint_service import CheckpointService
from plepa_engine.config import COMFY_HOST, DEFAULT_SDXL_CKPT, resolve_default_mode
from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.services.config_service import default_config_service


@dataclass
class BatchPlan:
    ckpt_name: str
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    db: Dict[str, PoseEntry]
    target_chars: List[Tuple[CharacterConfig, str]]
    char_pose_map: Dict[str, List[str]]
    total_items: int
    client: Any


def is_portrait_emotion_pose(pose_obj: Any) -> bool:
    """세로형 비율 포즈(000~024 또는 emotions/genit_emotions 섹션)인지 판별합니다."""
    if pose_obj is None:
        return True
    code_s = str(getattr(pose_obj, "code", "") or "").strip()
    if code_s.isdigit():
        return 0 <= int(code_s) <= 24
    return str(getattr(pose_obj, "section", "") or "").strip().lower() in ("emotions", "genit_emotions")


def get_optimal_resolution_for_pose(
    pose_obj: Any,
    default_w: int,
    default_h: int,
    engine: str = "sdxl",
    user_specified: bool = False,
) -> Tuple[int, int]:
    """포즈 대역별 하이브리드 최적 해상도(000~024 세로 832x1216 / 025+ 가로 1216x832)를 반환합니다."""
    del engine
    if user_specified:
        return default_w, default_h
    short_side, long_side = min(default_w, default_h), max(default_w, default_h)
    return (short_side, long_side) if is_portrait_emotion_pose(pose_obj) else (long_side, short_side)


def generate_mock_image(output_path: Path) -> None:
    """ComfyUI 연동 없이 0.001초 만에 더미 WebP 이미지를 생성하여 파이프라인 무결성을 검증합니다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(60, 100, 180))
        img.save(output_path, "WEBP", quality=80)
    except Exception:
        tiny_webp = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0e\x00\x00\x00/x\x00\x00\x00\x00\x00\x88\x88\xfe\x07\x00\x00"
        with open(output_path, "wb") as f:
            f.write(tiny_webp)


def compute_deterministic_pose_seed(pose_code: str, char_prefix: str) -> int:
    """포즈 코드 및 캐릭터 식별자 기반의 프로세스 독립적 결정론적 시드를 산출합니다."""
    code_digits = re.sub(r"\D", "", str(pose_code or "").strip())
    numeric_code = int(code_digits) if code_digits else (zlib.crc32(str(pose_code or "").encode("utf-8")) % 1000)
    char_offset = zlib.crc32(str(char_prefix or "").encode("utf-8")) % 100000
    return numeric_code * 1000 + char_offset


def resolve_effective_sdxl_params(
    params: Any,
    conf: Dict[str, Any],
    profile: Any,
) -> Tuple[int, int, int, float, str, str]:
    """실효 SDXL 생성 파라미터 산출 우선순위: params.* > conf['sdxl_*'] > profile.*."""
    saved_ckpt = str(conf.get("sdxl_ckpt") or "").strip()
    explicit_ckpt = str(params.ckpt or "").strip()
    use_saved_conf = (not explicit_ckpt) or (explicit_ckpt == saved_ckpt)

    def _pick(param_val: Any, conf_key: str, prof_val: Any, caster: Any) -> Any:
        if param_val is not None and (caster is not str or str(param_val).strip()):
            return caster(str(param_val).strip() if caster is str else param_val)
        if use_saved_conf and conf.get(conf_key):
            return caster(str(conf[conf_key]).strip() if caster is str else conf[conf_key])
        return caster(prof_val)

    return (
        _pick(params.width, "sdxl_width", profile.width, int),
        _pick(params.height, "sdxl_height", profile.height, int),
        _pick(params.steps, "sdxl_steps", profile.steps, int),
        _pick(params.cfg, "sdxl_cfg", profile.cfg, float),
        _pick(params.sampler, "sdxl_sampler", profile.sampler, str),
        _pick(params.scheduler, "sdxl_scheduler", profile.scheduler, str),
    )


def normalize_engine_params(params: Any, char_svc: Any, quiet: bool) -> None:
    """단일 캐릭터 default_mode 및 레거시 엔진 지정값을 SDXL 단일 파이프라인으로 정규화합니다."""
    target_chars_prelim = char_svc.resolve_characters(params.character_expr, roster=params.roster)
    if len(target_chars_prelim) == 1:
        char_obj, _ = target_chars_prelim[0]
        if hasattr(char_obj, "default_mode") and char_obj.default_mode:
            try:
                resolved_engine = resolve_default_mode(char_obj.default_mode)
                if resolved_engine != "sdxl":
                    if not quiet:
                        print(f"  [안내] 캐릭터 '{char_obj.prefix}'의 레거시 default_mode '{char_obj.default_mode}'는 SDXL 단일화 원칙에 따라 'sdxl'로 실행됩니다.")
                    resolved_engine = "sdxl"
                params.engine = resolved_engine
            except ValueError as ve:
                if not quiet:
                    print(f"  [경고] 캐릭터 default_mode '{char_obj.default_mode}' 무효: {ve}")

    if params.engine != "sdxl":
        if not quiet:
            print(f"  [안내] 레거시 엔진 '{params.engine}' 요청은 SDXL 단일 파이프라인으로 자동 정규화됩니다.")
        params.engine = "sdxl"


def _print_batch_banner(plan: BatchPlan, params: Any) -> None:
    print("=" * 60)
    print(f"  [플에파] SDXL 단일 파이프라인 가동 모드: {plan.ckpt_name}")
    print(f"  대상 캐릭터: 총 {len(plan.target_chars)}명 ({', '.join(c.prefix for c, _ in plan.target_chars)})")
    print("  젠더별 포즈 필터링:")
    for char, _ in plan.target_chars:
        pose_count = len(plan.char_pose_map[char.prefix])
        gender_label = "오토코노코(150~209)" if char.gender == "otokonoko" else f"{char.gender}(V3 표준)"
        print(f"    - {char.name} ({char.prefix}): {pose_count}개 [{gender_label}]")
    print(f"  총 생성 에셋: {plan.total_items}개")
    print(f"  해상도: {plan.width}x{plan.height} | 스텝: {plan.steps} | CFG: {plan.cfg} | 샘플러: {plan.sampler} / {plan.scheduler}")
    if params.profile:
        print(f"  프로필: '{params.profile}' 적용")
    if params.bg:
        print(f"  즉석 배경: '{params.bg}'")
    if params.custom_neg:
        print(f"  추가 네거티브: '{params.custom_neg}'")
    if params.mock:
        print("  시뮬레이션: --mock 모드 활성화 (초고속 더미 생성)")
    print(f"  작업 모드: {'강제 덮어쓰기 (--overwrite / -f)' if params.overwrite else '빈칸 채우기 (기본: 기존 파일 보존)'}")
    print(f"  파일명 형식: {params.naming}")
    fd_active = True if params.face_detailer is None else params.face_detailer
    print(f"  보정 옵션: Face Detailer={'활성' if fd_active else '비활성'}, Hand Detailer={'활성' if params.hand_detailer else '비활성'}, Upscale={'활성' if params.upscale else '비활성'}")
    if params.censor:
        print(f"  자동 검열: 활성 (스타일: {params.censor_style}, 대상: {params.censor_targets}, 앵커폴백: {params.anchor_fallback})")
    print("=" * 60)


def prepare_batch_plan(
    *,
    params: Any,
    char_svc: Any,
    pose_svc: Any,
    resolve_params_fn: Callable[..., Tuple[int, int, int, float, str, str]],
    comfy_client_cls: Any,
    quiet: bool,
) -> BatchPlan:
    """설정/체크포인트/캐릭터/포즈 해석과 ComfyUI 사전 연결 검사를 수행합니다."""
    normalize_engine_params(params, char_svc, quiet)

    conf = default_config_service.get_config()
    ckpt_name = params.ckpt or conf.get("sdxl_ckpt", DEFAULT_SDXL_CKPT)
    profile = CheckpointService().get_profile_for_checkpoint(ckpt_name)
    width, height, steps, cfg, sampler, scheduler = resolve_params_fn(params, conf, profile)
    if not quiet and params.ckpt:
        print(f"  체크포인트 프로필: '{profile.name}' 자동 적용")

    db = pose_svc.load_pose_db(engine="sdxl", roster=params.roster)
    target_chars = char_svc.resolve_characters(params.character_expr, roster=params.roster)
    codes = pose_svc.resolve_pose_codes(params.pose_expr, db, roster=params.roster)
    if params.profile:
        target_chars = [(c.with_profile(params.profile), r) for c, r in target_chars]

    comfy_host = conf.get("comfy_host", COMFY_HOST)
    client = comfy_client_cls(host=comfy_host)
    if not params.dry_run and not params.mock and not params.censor_only and not client.check_connection():
        raise ConnectionError(
            f"ComfyUI 서버({comfy_host})에 연결할 수 없습니다. "
            "ComfyUI의 run_nvidia_gpu.bat를 가동해 주십시오."
        )

    char_pose_map = {
        char.prefix: [
            c for c in codes
            if pose_svc.is_pose_allowed_for_character(db.get(c), char, roster=actual_roster, code=c)
        ]
        for char, actual_roster in target_chars
    }
    plan = BatchPlan(
        ckpt_name=ckpt_name,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        sampler=sampler,
        scheduler=scheduler,
        db=db,
        target_chars=target_chars,
        char_pose_map=char_pose_map,
        total_items=sum(len(poses) for poses in char_pose_map.values()),
        client=client,
    )
    if not quiet:
        _print_batch_banner(plan, params)
    return plan
