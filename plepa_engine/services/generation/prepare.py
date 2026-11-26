"""
plepa_engine.services.generation.prepare
캐릭터 작업 디렉터리/레퍼런스 준비 및 단일 포즈 워크플로우·GenerationTarget 조립 헬퍼.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from plepa_engine.config import DEFAULT_REF_WEIGHT, PROJECTS_DIR
from plepa_engine.models import CharacterConfig, GenerationTarget, PoseEntry
from plepa_engine.prompt_builder import assemble_sdxl_prompt, resolve_pose_outfit_slot
from plepa_engine.reporter import asset_filename, get_legacy_subfolder_for_code, get_subfolder_for_code
from plepa_engine.services.generation.plan import BatchPlan
from plepa_engine.services.generation_options import resolve_workflow_loras
from plepa_engine.workflow_templates import build_sdxl_workflow

_TWO_PERSON_TOKENS = (
    "1boy", "partner", "faceless male", "bald male", "kiss", "hug", "carry",
    "grab", "spooning", "blowjob", "missionary", "doggystyle", "cowgirl",
    "fellatio", "cunnilingus", "paizuri",
)


@dataclass
class PoseWorkItem:
    code: str
    pose: PoseEntry
    out_path: Path
    legacy_path: Path
    sub_out_dir: Path
    sub_origin_dir: Path
    legacy_sub_origin: Path
    is_nude: bool
    workflow: Dict[str, Any]
    target: GenerationTarget


def resolve_char_workspace_and_ref(
    *,
    char_idx: int,
    total_chars: int,
    char: CharacterConfig,
    actual_roster: str,
    params: Any,
    asset_svc: Any,
    client: Any,
    quiet: bool,
    projects_dir: Optional[Path] = None,
) -> Tuple[Path, Path, Optional[str], float]:
    """캐릭터별 출력/원본 디렉터리를 준비하고 IP-Adapter 레퍼런스를 탐색·업로드합니다."""
    eff_projects_dir = projects_dir or PROJECTS_DIR
    base_asset_root = (Path(params.out_dir) / actual_roster) if params.out_dir else (eff_projects_dir / actual_roster / "assets")
    if params.ckpt_tag:
        output_dir = base_asset_root / char.prefix / f"ckpt_{params.ckpt_tag}"
        origin_dir = base_asset_root / f"{char.prefix}_origin" / f"ckpt_{params.ckpt_tag}"
    else:
        output_dir = base_asset_root / char.prefix
        origin_dir = base_asset_root / f"{char.prefix}_origin"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print(f"\n▶ [{char_idx}/{total_chars}] {char.name} ({char.prefix}) [로스터: {actual_roster}]")
        if params.out_dir:
            print(f"  별도 출력 폴더: {output_dir}")
        elif params.ckpt_tag:
            print(f"  저장 위치: assets/{char.prefix}/ckpt_{params.ckpt_tag}/")
        if params.bg:
            print(f"  즉석 배경: '{params.bg}' 적용")
        elif params.bg_preset and params.bg_preset not in ("default", "auto", ""):
            print(f"  배경 프리셋: '{params.bg_preset}' 고정 적용")
        else:
            print("  배경 프리셋: 포즈별 자동 매핑(Auto) 적용")

    ref_file_name = None
    ref_weight = params.ref_weight if params.ref_weight is not None else getattr(char, "ref_weight", DEFAULT_REF_WEIGHT)
    if not params.no_ref and ref_weight > 0.0:
        ref_path = asset_svc.find_reference_image(char.prefix, actual_roster, custom_path=params.ref_image)
        if ref_path:
            if not params.dry_run and not params.mock and not params.censor_only:
                try:
                    ref_file_name = client.upload_image(ref_path)
                except Exception as ue:
                    if not quiet:
                        print(f"  [경고] 레퍼런스 업로드 실패 ({ue}) - 순수 프롬프트로 진행")
                    ref_file_name = None
            else:
                ref_file_name = ref_path.name
            if not quiet:
                print(f"  IP-Adapter: '{ref_path.name}' 적용 (가중치: {ref_weight:.2f})")
        elif not quiet:
            print("  IP-Adapter: 레퍼런스 이미지 없음 (순수 프롬프트 생성)")
    elif not quiet:
        print("  IP-Adapter: 비활성화 (순수 고화질 프롬프트 생성)")

    return output_dir, origin_dir, ref_file_name, ref_weight


def _resolve_3track_paths(
    output_dir: Path,
    origin_dir: Path,
    prefix: str,
    code: str,
    label: str,
    naming: str,
) -> Tuple[Path, Path, Path, Path, Path]:
    subfolder = get_subfolder_for_code(code)
    sub_out_dir = output_dir / subfolder
    sub_origin_dir = origin_dir / subfolder
    out_name = asset_filename(prefix, code, label=label, naming=naming)
    legacy_name = asset_filename(prefix, code, naming="code")

    legacy_subfolder = get_legacy_subfolder_for_code(code)
    legacy_sub_out = output_dir / legacy_subfolder
    legacy_sub_origin = origin_dir / legacy_subfolder

    out_path = next(
        (c for c in (sub_out_dir / out_name, legacy_sub_out / out_name, output_dir / out_name) if c.exists()),
        None,
    )
    if out_path is None:
        sub_out_dir.mkdir(parents=True, exist_ok=True)
        out_path = sub_out_dir / out_name

    legacy_path = next(
        (c for c in (sub_out_dir / legacy_name, legacy_sub_out / legacy_name, output_dir / legacy_name) if c.exists()),
        sub_out_dir / legacy_name,
    )
    return out_path, legacy_path, sub_out_dir, sub_origin_dir, legacy_sub_origin


def _apply_seed_override_to_workflow(workflow: Dict[str, Any], seed_val: int) -> None:
    for node_data in workflow.values():
        if isinstance(node_data, dict) and "inputs" in node_data:
            inp = node_data["inputs"]
            if "seed" in inp:
                inp["seed"] = seed_val
            elif "noise_seed" in inp:
                inp["noise_seed"] = seed_val


def build_pose_work_item(
    *,
    idx: int,
    total_char_codes: int,
    code: str,
    pose: PoseEntry,
    char: CharacterConfig,
    actual_roster: str,
    output_dir: Path,
    origin_dir: Path,
    ref_file_name: Optional[str],
    ref_weight: float,
    existing_manifest_seeds: Dict[str, Any],
    plan: BatchPlan,
    params: Any,
    bg_svc: Any,
    pose_bg_svc: Any,
    get_opt_res_fn: Callable[..., Tuple[int, int]],
    compute_det_seed_fn: Callable[[str, str], int],
    quiet: bool,
) -> PoseWorkItem:
    """단일 포즈의 3-Track 경로·배경·프롬프트·시드·워크플로우·Target을 조립합니다."""
    out_path, legacy_path, sub_out_dir, sub_origin_dir, legacy_sub_origin = _resolve_3track_paths(
        output_dir, origin_dir, char.prefix, code, pose.label, params.naming
    )

    if params.bg:
        effective_bg_prompt = params.bg.strip()
    elif params.bg_preset and params.bg_preset not in ("default", "auto", ""):
        effective_bg_prompt = bg_svc.get_preset(actual_roster, key=params.bg_preset, engine="sdxl")
    else:
        pose_bg_key = pose_bg_svc.get_background_for_pose(actual_roster, code)
        effective_bg_prompt = bg_svc.get_preset(actual_roster, key=pose_bg_key, engine="sdxl")

    pos_prompt, neg_prompt, is_nude = assemble_sdxl_prompt(
        char, pose, bg_prompt=effective_bg_prompt,
        custom_pos=params.custom_pos, custom_neg=params.custom_neg, checkpoint_name=plan.ckpt_name,
    )

    p_low = pose.prompt.lower()
    outfit_slot = resolve_pose_outfit_slot(pose)
    if is_nude or outfit_slot != "default" or pose.section not in ("emotions", "genit_emotions") or any(kw in p_low for kw in _TWO_PERSON_TOKENS):
        ref_mode = "face_only"
    else:
        ref_mode = "full"

    eff_w, eff_h = get_opt_res_fn(
        pose, plan.width, plan.height, engine="sdxl",
        user_specified=(params.width is not None or params.height is not None),
    )
    code_key = str(code).strip()
    sdxl_seed = params.seed if params.seed is not None else -1
    if sdxl_seed < 0 and params.reuse_seed and code_key in existing_manifest_seeds:
        sdxl_seed = existing_manifest_seeds[code_key]
    elif sdxl_seed < 0 and params.deterministic_pose_seed:
        sdxl_seed = compute_det_seed_fn(code, char.prefix)

    workflow = build_sdxl_workflow(
        positive_prompt=pos_prompt, negative_prompt=neg_prompt,
        output_prefix=f"{char.prefix}_{code}", seed=sdxl_seed,
        width=eff_w, height=eff_h, steps=plan.steps, cfg=plan.cfg,
        sampler=plan.sampler, scheduler=plan.scheduler, ckpt_name=plan.ckpt_name,
        use_face_detailer=params.face_detailer, use_hand_detailer=params.hand_detailer,
        use_freeu=params.freeu, use_upscale=params.upscale,
        ref_image_name=ref_file_name, ref_weight=ref_weight, ref_mode=ref_mode,
        loras=resolve_workflow_loras(char, params),
    )

    current_seed = None
    for node_data in workflow.values():
        if isinstance(node_data, dict) and "inputs" in node_data:
            inp = node_data["inputs"]
            if "seed" in inp:
                current_seed = inp["seed"]
                break
            if "noise_seed" in inp:
                current_seed = inp["noise_seed"]
                break

    if params.seed is not None:
        _apply_seed_override_to_workflow(workflow, params.seed)
        current_seed = params.seed
    elif params.reuse_seed and code_key in existing_manifest_seeds:
        reused = existing_manifest_seeds[code_key]
        _apply_seed_override_to_workflow(workflow, reused)
        current_seed = reused

    target = GenerationTarget(
        code=code, section=pose.section, label=pose.label,
        assembled_prompt=pos_prompt, is_nude=is_nude,
        output_filename=out_path.name, seed=current_seed,
        character_prefix=char.prefix, character_name=char.name,
    )
    if not quiet:
        track_info = f" [IP-A: {ref_mode}]" if (params.engine == "sdxl" and ref_file_name) else ""
        print(f"  [{idx:02d}/{total_char_codes:02d}] #{code} {pose.label:<10} ({pose.section}){track_info} -> {out_path.name}", end="", flush=True)

    return PoseWorkItem(
        code=code, pose=pose, out_path=out_path, legacy_path=legacy_path,
        sub_out_dir=sub_out_dir, sub_origin_dir=sub_origin_dir,
        legacy_sub_origin=legacy_sub_origin, is_nude=is_nude,
        workflow=workflow, target=target,
    )
