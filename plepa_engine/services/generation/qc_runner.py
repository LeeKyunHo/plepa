"""
plepa_engine.services.generation.qc_runner
ComfyUI 생성 실행, Auto-QC 및 strict_censor_qc 재시도 루프, 진단 가이드 출력 헬퍼.
"""

from __future__ import annotations

import copy
import random
import time
from typing import Any, Callable, Dict, Optional

from plepa_engine.comfy_client import ComfyClientError
from plepa_engine.models import CharacterConfig, GenerationResult, PoseEntry
from plepa_engine.services.generation.prepare import PoseWorkItem


def _build_qc_diagnostic_hint(fail_reason: str, qc_is_solo: bool) -> str:
    if "인원" in fail_reason or "머리" in fail_reason or "얼굴" in fail_reason:
        return (
            "단독 씬인데 제3자가 침범하고 있습니다. 프롬프트의 1girl/solo/partner 태그 충돌을 점검하세요."
            if qc_is_solo
            else "2인 씬에서 허용된 인원·머리·얼굴 상한을 초과했습니다. mob_tier/partner_pos 및 모브 얼굴 차단 네거티브를 점검하세요."
        )
    if "손 증식" in fail_reason or "손" in fail_reason:
        return "손이 비정상 증식하고 있습니다. 스킨십/손 태그 가중치를 낮추거나 Hand Detailer를 활성화하세요."
    if "화각 드리프트" in fail_reason:
        return "상반신 씬인데 전신 롱샷으로 이탈했습니다. 네거티브 (full body:1.4)를 점검하세요."
    return f"프롬프트 키워드 간의 충돌 가능성을 점검하세요: {fail_reason}"


def _run_qc_checks_for_attempt(
    *,
    item: PoseWorkItem,
    char: CharacterConfig,
    actual_roster: str,
    should_censor: bool,
    is_char_otokonoko: bool,
    attempt: int,
    params: Any,
    validate_fn: Callable[..., Any],
    is_censor_req_fn: Callable[..., bool],
    quiet: bool,
) -> Optional[str]:
    """단일 생성 시도에 대해 Auto-QC 및 strict_censor_qc를 실행하고 실패 사유(통과 시 None)를 반환합니다."""
    pose: PoseEntry = item.pose
    pose_mob_tier = getattr(pose, "mob_tier", None)
    if pose_mob_tier == 0:
        qc_is_solo, qc_is_two_person, qc_is_offscreen = True, False, True
    elif pose_mob_tier in (1, 2, 3):
        qc_is_solo, qc_is_two_person, qc_is_offscreen = False, True, True
    else:
        qc_is_solo, qc_is_two_person, qc_is_offscreen = pose.is_solo_scene, pose.is_two_person, pose.is_offscreen_partner

    qc_prompt = pose.get_prompt(getattr(char, "gender", "female")) if callable(getattr(pose, "get_prompt", None)) else (pose.prompt or "")
    pose_partner_pos = (getattr(pose, "partner_pos", None) or "").strip().lower()
    pose_mob_shadow = bool(getattr(pose, "mob_shadow", False))
    qc_allow_partner_head = (
        pose_mob_tier == 2
        or (qc_is_two_person and pose_partner_pos in ("behind", "above", "below", "side_kiss", "side_cuddle", "carry", "bury_chest", "between_thighs"))
    )
    is_kiss = "kiss" in qc_prompt.lower() or str(item.target.code) in ("060", "061", "019")
    qc_allow_partner_shadow_face = pose_mob_shadow and pose_partner_pos == "side_cuddle"

    passed, fail_reason, _ = validate_fn(
        image=item.out_path,
        is_solo_scene=qc_is_solo,
        is_two_person=qc_is_two_person,
        is_offscreen_partner=qc_is_offscreen,
        is_kiss_scene=is_kiss,
        allow_partner_head=qc_allow_partner_head,
        allow_partner_shadow_face=qc_allow_partner_shadow_face,
        section=item.target.section,
        prompt=qc_prompt,
    )
    if not passed:
        if attempt + 1 >= params.prompt_alert_threshold and not quiet:
            guide_msg = _build_qc_diagnostic_hint(fail_reason, qc_is_solo)
            print(f"\n    🚨 [프롬프트 점검 경고] #{item.code} {pose.label} ({attempt+1}회 연속 결함!)\n       └─ 사유: {fail_reason}\n       └─ 진단 가이드: {guide_msg}", flush=True)
        if not quiet:
            tag = f"재시도 {attempt+1}/{params.max_retries}" if attempt < params.max_retries else "최대 재시도 초과"
            print(f" [Auto-QC 불량({tag}): {fail_reason}]" if attempt >= params.max_retries else f" [Auto-QC 불량: {fail_reason} -> {tag}]", end="", flush=True)
        return fail_reason

    if not quiet and attempt > 0:
        print(f" [Auto-QC 통과(재시도 {attempt}회)]", end="", flush=True)

    if (
        params.strict_censor_qc
        and getattr(pose, "mob_tier", None) not in (0, 1, 2)
        and (
            should_censor
            or is_censor_req_fn(
                pose_code=item.code, pose=pose, is_nude=item.is_nude,
                file_path=item.out_path, roster=actual_roster, is_otokonoko=is_char_otokonoko,
            )
        )
    ):
        from plepa_engine.censor import POSE_SAFE_ANCHORS, detect_genitals, get_pose_category
        code_norm = str(item.target.code).strip()
        if get_pose_category(code_norm, roster=actual_roster) in POSE_SAFE_ANCHORS:
            c_targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
            boxes = detect_genitals(str(item.out_path), targets=c_targets, pose_code=code_norm, roster=actual_roster)
            if not boxes:
                if not quiet:
                    msg = f"재시도 {attempt+1}/{params.max_retries}" if attempt < params.max_retries else "최대 재시도 초과"
                    print(f" [검열 QC 불량({msg}): 성기 미탐지]" if attempt >= params.max_retries else f" [검열 QC 불량: 성기 미탐지 -> {msg}]", end="", flush=True)
                return "필수 성인 씬 성기 미탐지(구도 불량)"
    return None


def _clone_workflow_with_new_seed(workflow: Dict[str, Any], new_seed: int) -> Dict[str, Any]:
    cloned = copy.deepcopy(workflow)
    for node_data in cloned.values():
        if isinstance(node_data, dict) and "inputs" in node_data:
            inp = node_data["inputs"]
            if "seed" in inp:
                inp["seed"] = new_seed
            elif "noise_seed" in inp:
                inp["noise_seed"] = new_seed
    return cloned


def execute_comfy_with_qc_and_censor(
    *,
    client: Any,
    item: PoseWorkItem,
    char: CharacterConfig,
    actual_roster: str,
    should_censor: bool,
    is_char_otokonoko: bool,
    params: Any,
    validate_fn: Callable[..., Any],
    is_censor_req_fn: Callable[..., bool],
    apply_censor_fn: Callable[..., bool],
    quiet: bool,
) -> GenerationResult:
    """실제 ComfyUI 워크플로우 실행, Auto-QC 리롤 루프, 검열 적용을 수행합니다."""
    item_start = time.time()
    try:
        max_attempts = (params.max_retries + 1) if params.auto_qc else 1
        current_wf = item.workflow
        final_qc_fail: Optional[str] = None
        attempt = 0

        for attempt in range(max_attempts):
            if attempt > 0:
                new_seed = random.randint(1, 2**63 - 1)
                item.target.seed = new_seed
                current_wf = _clone_workflow_with_new_seed(item.workflow, new_seed)

            client.generate_image(workflow=current_wf, output_path=item.out_path)
            if not params.auto_qc:
                break

            final_qc_fail = _run_qc_checks_for_attempt(
                item=item, char=char, actual_roster=actual_roster,
                should_censor=should_censor, is_char_otokonoko=is_char_otokonoko,
                attempt=attempt, params=params,
                validate_fn=validate_fn, is_censor_req_fn=is_censor_req_fn, quiet=quiet,
            )
            if final_qc_fail is None or attempt >= params.max_retries:
                break

        duration = time.time() - item_start
        if not quiet:
            print(f" [완료: {duration:.1f}초]", end="")
        if should_censor:
            origin_path = item.sub_origin_dir / item.out_path.name
            try:
                applied = apply_censor_fn(
                    origin_path, item.out_path, item.sub_origin_dir, params, item.pose.code, actual_roster,
                    overwrite_origin=True, is_nude=item.is_nude, is_otokonoko=is_char_otokonoko,
                )
                if applied and not quiet:
                    print(f" [검열본 적용: assets/{char.prefix}/{item.out_path.name} (원본: {char.prefix}_origin/)]", end="")
            except Exception as ce:
                if not quiet:
                    print(f" [검열 실패: {ce}]", end="")
        if not quiet:
            print()

        return GenerationResult(
            target=item.target, success=True, image_path=item.out_path, duration_sec=duration,
            qc_passed=(final_qc_fail is None), qc_reason=final_qc_fail, retries=attempt,
        )
    except ComfyClientError as ce:
        duration = time.time() - item_start
        if not quiet:
            print(f" [실패: {ce}]")
        return GenerationResult(target=item.target, success=False, duration_sec=duration, error_message=str(ce))
    except Exception as ge:
        duration = time.time() - item_start
        if not quiet:
            print(f" [예외 발생: {ge}]")
        return GenerationResult(target=item.target, success=False, duration_sec=duration, error_message=str(ge))
