"""
plepa_engine.services.generation_service
FLUX / SDXL 듀얼 엔진 배치 이미지 생성 핵심 서비스.
CLI와 GUI가 공통으로 호출하며, 진행률 콜백 및 취소 인터럽트를 지원합니다.
"""

from __future__ import annotations

import copy
import json
import os
import random
import shutil
import time
import uuid
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path

from typing import Callable, Dict, List, Optional, Tuple

from plepa_engine.censor import censor_file
from plepa_engine.checkpoint_service import CheckpointService
from plepa_engine.comfy_client import ComfyClient, ComfyClientError
from plepa_engine.qa_validator import validate_generated_image
from plepa_engine.config import (
    COMFY_HOST,
    DEFAULT_ENGINE,
    DEFAULT_HEIGHT,
    DEFAULT_REF_WEIGHT,
    DEFAULT_ROSTER,
    DEFAULT_SDXL_CFG,
    DEFAULT_SDXL_CKPT,
    DEFAULT_SDXL_HEIGHT,
    DEFAULT_SDXL_SAMPLER,
    DEFAULT_SDXL_SCHEDULER,
    DEFAULT_SDXL_STEPS,
    DEFAULT_SDXL_WIDTH,
    DEFAULT_STEPS,
    DEFAULT_UNET_GGUF,
    DEFAULT_WIDTH,
    PROJECTS_DIR,
)
from plepa_engine.models import (
    CharacterConfig,
    GenerationResult,
    GenerationTarget,
    PoseEntry,
)
from plepa_engine.prompt_builder import assemble_flux_prompt, assemble_sdxl_prompt
from plepa_engine.reporter import asset_filename, print_batch_summary
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.background_service import default_background_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.workflow_templates import build_flux_workflow, build_sdxl_workflow


def generate_mock_image(output_path: Path) -> None:
    """ComfyUI 연동 없이 0.001초 만에 더미 WebP 이미지를 생성하여 파이프라인 무결성을 검증합니다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(60, 100, 180))
        img.save(output_path, "WEBP", quality=80)
    except Exception:
        tiny_webp = (
            b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0e\x00\x00\x00/x\x00\x00\x00\x00\x00\x88\x88\xfe\x07\x00\x00"
        )
        with open(output_path, "wb") as f:
            f.write(tiny_webp)


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
    no_ref: bool = False
    mock: bool = False
    dry_run: bool = False
    overwrite: bool = False
    face_detailer: Optional[bool] = None
    upscale: bool = False
    steps: Optional[int] = None
    cfg: Optional[float] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    unet: Optional[str] = None
    lora: str = "modern-anime-lora.safetensors"
    lora_weight: float = 0.9
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
    reuse_seed: bool = False  # _batch_manifest.json의 이전 골든 시드 고정 재생성
    strict_censor_qc: bool = False  # 필수 성인 노출 씬에서 성기 미탐지 시 자동 리롤


# CLI와 GUI가 단일 진실 공급원(SSOT)으로 공유하는 생성 옵션 메타데이터 레지스트리
GENERATION_OPTION_SPECS: List[Dict[str, Any]] = [
    {
        "field": "face_detailer",
        "cli_flag": "--face-detailer",
        "label": "Face Detailer",
        "tooltip": "얼굴 디테일러(Face Detailer) 후처리 적용",
        "default": True,
    },
    {
        "field": "upscale",
        "cli_flag": "--upscale",
        "label": "4x AI 업스케일",
        "tooltip": "4x-UltraSharp 모델을 통한 4K 초해상화",
        "default": False,
    },
    {
        "field": "censor",
        "cli_flag": "--censor",
        "label": "화이트 실루엣 검열",
        "tooltip": "YOLO 자동 탐지 기반 화이트 실루엣 검열 (_origin 백업 유지)",
        "default": True,
    },
    {
        "field": "reuse_seed",
        "cli_flag": "--reuse-seed",
        "label": "🔒 골든 시드 고정",
        "tooltip": "_batch_manifest.json의 이전 시드를 재사용하여 구도를 유지하고 의상/태그만 갱신",
        "default": False,
    },
    {
        "field": "strict_censor_qc",
        "cli_flag": "--strict-censor-qc",
        "label": "🛡️ 엄격 검열 리롤 (Auto-QC)",
        "tooltip": "성인 H씬에서 성기 미탐지(구도 왜곡 등) 시 통과시키지 않고 자동 리롤",
        "default": False,
    },
    {
        "field": "censor_only",
        "cli_flag": "--censor-only",
        "label": "⚡ 0.2초 소급 검열 전용",
        "tooltip": "신규 생성 없이 기존 에셋에 실루엣 검열만 즉시 일괄 적용",
        "default": False,
    },
    {
        "field": "overwrite",
        "cli_flag": "--overwrite",
        "label": "강제 덮어쓰기 (리롤)",
        "tooltip": "기존에 완료된 에셋을 건너뛰지 않고 새로 생성하여 덮어씁니다",
        "default": False,
    },
    {
        "field": "mock",
        "cli_flag": "--mock",
        "label": "Mock 시뮬레이션",
        "tooltip": "ComfyUI 서버 연동 없이 0.001초 가상 생성 테스트",
        "default": False,
    },
]


class GenerationService:
    """배치 이미지 생성 파이프라인 서비스."""

    def __init__(
        self,
        character_svc=default_character_service,
        pose_svc=default_pose_service,
        bg_svc=default_background_service,
        asset_svc=default_asset_service,
    ):
        self.char_svc = character_svc
        self.pose_svc = pose_svc
        self.bg_svc = bg_svc
        self.asset_svc = asset_svc

    def run_batch(
        self,
        params: GenerationParams,
        on_progress: Optional[Callable[[int, int, GenerationResult], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        quiet: bool = False,
    ) -> List[GenerationResult]:
        """
        배치 생성 루프를 실행합니다.
        진행 중 on_progress(현재_항목_인덱스, 전체_항목_수, 결과)를 호출합니다.
        is_cancelled()가 True를 반환하면 생성을 즉시 중단합니다.
        """
        # 0. 단일 캐릭터인 경우 해당 캐릭터의 default_mode를 engine에 자동 반영 (키로 스타일)
        from plepa_engine.config import resolve_default_mode
        target_chars_preliminary = self.char_svc.resolve_characters(params.character_expr, roster=params.roster)
        if len(target_chars_preliminary) == 1:
            char_obj, _ = target_chars_preliminary[0]
            if hasattr(char_obj, 'default_mode') and char_obj.default_mode:
                try:
                    resolved_engine = resolve_default_mode(char_obj.default_mode)
                    if resolved_engine != params.engine:
                        if not quiet:
                            print(f"  [INFO] 캐릭터 '{char_obj.prefix}'의 default_mode '{char_obj.default_mode}' → '{resolved_engine}' 자동 적용")
                        params.engine = resolved_engine
                except ValueError as ve:
                    if not quiet:
                        print(f"  [경고] 캐릭터 default_mode '{char_obj.default_mode}' 무효: {ve}")

        # 1. 전역 설정(Config) 최신값 조회 및 해상도/샘플러 산출
        conf = default_config_service.get_config()
        if params.engine == "sdxl":
            ckpt_name = params.ckpt or conf.get("sdxl_ckpt", DEFAULT_SDXL_CKPT)
            
            # 체크포인트 프로필 자동 적용
            checkpoint_svc = CheckpointService()
            profile = checkpoint_svc.get_profile_for_checkpoint(ckpt_name)
            
            # 우선순위: 사용자 명시 > 프로필 값 > Config 설정 > 기본값
            width = params.width if params.width is not None else profile.width
            height = params.height if params.height is not None else profile.height
            steps = params.steps if params.steps is not None else profile.steps
            cfg = params.cfg if params.cfg is not None else profile.cfg
            sampler = params.sampler if params.sampler is not None else profile.sampler
            scheduler = params.scheduler if params.scheduler is not None else profile.scheduler
            
            if not quiet and params.ckpt:
                print(f"  체크포인트 프로필: '{profile.name}' 자동 적용")
        else:
            width = params.width if params.width is not None else int(conf.get("flux_width", DEFAULT_WIDTH))
            height = params.height if params.height is not None else int(conf.get("flux_height", DEFAULT_HEIGHT))
            steps = params.steps if params.steps is not None else int(conf.get("flux_steps", DEFAULT_STEPS))
            cfg = params.cfg if params.cfg is not None else float(conf.get("flux_guidance", 3.5))
            sampler = params.sampler if params.sampler is not None else conf.get("flux_sampler", "euler")
            scheduler = params.scheduler if params.scheduler is not None else conf.get("flux_scheduler", "simple")
            unet_name = params.unet or conf.get("flux_unet", DEFAULT_UNET_GGUF)
            ckpt_name = None  # FLUX 모드에서는 체크포인트 미사용

        # 2. 포즈 DB 및 대상 캐릭터/포즈 코드 해석
        db = self.pose_svc.load_pose_db(engine=params.engine, roster=params.roster)
        target_chars = self.char_svc.resolve_characters(params.character_expr, roster=params.roster)
        codes = self.pose_svc.resolve_pose_codes(params.pose_expr, db, roster=params.roster)
        
        # 2-1. 젠더별 포즈 필터링 + 로스터 전용 포즈 필터링
        def filter_codes_by_gender_and_roster(base_codes: List[str], char_obj, current_roster: str) -> List[str]:
            """포즈 메타데이터(section, target_gender, allowed_rosters) 기반 데이터 주도형 필터링"""
            filtered = []
            pose_restrictions = getattr(char_obj, 'pose_restrictions', {})
            campus_only_poses = set(pose_restrictions.get('campus_only', []))

            for code in base_codes:
                pose_entry = db.get(code)
                target_gender = getattr(pose_entry, 'target_gender', None) if pose_entry else None
                allowed_rosters = getattr(pose_entry, 'allowed_rosters', None) if pose_entry else None
                section = getattr(pose_entry, 'section', '') if pose_entry else ''

                # 1. 로스터별 전용 포즈 필터링
                if allowed_rosters and current_roster not in allowed_rosters:
                    continue
                # 레거시 campus_only 제약: 타 로스터에서 자체 오버라이드 없이 캠퍼스 전용 코드가 유입되는 경우 방어
                if code in campus_only_poses and current_roster != 'campus':
                    if not allowed_rosters or current_roster not in allowed_rosters:
                        continue


                # 2. 메타데이터(target_gender / section) 기반 젠더 필터링
                if target_gender:
                    if target_gender == "otokonoko" and char_obj.gender != "otokonoko":
                        continue
                    if target_gender in ("female", "girl") and char_obj.gender == "otokonoko":
                        continue
                elif section in ("scenes_otokonoko", "special_otokonoko") and char_obj.gender != "otokonoko":
                    continue
                elif section in ("h_scenes", "special_h") and char_obj.gender == "otokonoko":
                    continue
                else:
                    # 하위 호환 및 숫자 대역 기반 젠더 필터링
                    try:
                        code_num = int(code)
                        # 여성 성인/특수 대역 (080~132): 오토코노코 제외
                        if char_obj.gender == "otokonoko" and (80 <= code_num <= 132 or 48 <= code_num <= 99):
                            continue
                        # 오토코노코 성인/특수 대역 (133~135, 150~219): 여성 제외
                        elif char_obj.gender != "otokonoko" and ((133 <= code_num <= 135) or (148 <= code_num <= 219)):
                            continue
                    except ValueError:
                        pass

                filtered.append(code)
            return filtered


        if params.profile:
            target_chars = [(c.with_profile(params.profile), r) for c, r in target_chars]

        # 3. ComfyUI 연결 검사
        comfy_host = conf.get("comfy_host", COMFY_HOST)
        client = ComfyClient(host=comfy_host)
        if not params.dry_run and not params.mock:
            if not client.check_connection():
                raise ConnectionError(
                    f"ComfyUI 서버({comfy_host})에 연결할 수 없습니다. "
                    "ComfyUI의 run_nvidia_gpu.bat를 가동해 주십시오."
                )

        # 3-1. 캐릭터별 포즈 세트 계산 (젠더 필터링 + 로스터 제약 적용)
        char_pose_map = {}
        for char, actual_roster in target_chars:
            filtered_codes = filter_codes_by_gender_and_roster(codes, char, actual_roster)
            char_pose_map[char.prefix] = filtered_codes
        
        total_items = sum(len(poses) for poses in char_pose_map.values())
        current_item_index = 0
        all_results: List[GenerationResult] = []

        if not quiet:
            print("=" * 60)
            engine_title = f"SDXL ({params.ckpt})" if params.engine == "sdxl" else f"FLUX.1 [dev] (GGUF: {params.unet})"
            print(f"  [플에파] 듀얼 엔진 가동 모드: {engine_title}")
            print(f"  대상 캐릭터: 총 {len(target_chars)}명 ({', '.join(c.prefix for c, _ in target_chars)})")
            print(f"  젠더별 포즈 필터링:")
            for char, _ in target_chars:
                pose_count = len(char_pose_map[char.prefix])
                gender_label = "오토코노코(140번대)" if char.gender == "otokonoko" else f"{char.gender}(40번대)"
                print(f"    - {char.name} ({char.prefix}): {pose_count}개 [{gender_label}]")
            print(f"  총 생성 에셋: {total_items}개")
            print(f"  해상도: {width}x{height} | 스텝: {steps} | CFG: {cfg} | 샘플러: {sampler} / {scheduler}")
            if params.profile:
                print(f"  프로필: '{params.profile}' 적용")
            if params.bg:
                print(f"  즉석 배경: '{params.bg}'")
            if params.custom_neg and params.engine == "sdxl":
                print(f"  추가 네거티브: '{params.custom_neg}'")
            if params.mock:
                print("  시뮬레이션: --mock 모드 활성화 (초고속 더미 생성)")
            if params.engine == "flux":
                print(f"  LoRA: {params.lora} (강도: {params.lora_weight})")
            print(f"  작업 모드: {'강제 덮어쓰기 (--overwrite / -f)' if params.overwrite else '빈칸 채우기 (기본: 기존 파일 보존)'}")
            print(f"  파일명 형식: {params.naming}")
            print(f"  보정 옵션: Face Detailer={'활성' if params.face_detailer else '비활성'}, Upscale={'활성' if params.upscale else '비활성'}")
            if params.censor:
                print(f"  자동 검열: 활성 (스타일: {params.censor_style}, 대상: {params.censor_targets})")
            print("=" * 60)

        session_cm = client.session() if (not params.dry_run and not params.mock) else nullcontext()
        with session_cm:
            for char_idx, (char, actual_roster) in enumerate(target_chars, 1):
                if is_cancelled and is_cancelled():
                    if not quiet:
                        print("\n[알림] 사용자에 의해 배치가 취소되었습니다.")
                    break
    
                bg_prompt = params.bg.strip() if params.bg else self.bg_svc.get_preset(actual_roster, key=params.bg_preset, engine=params.engine)
                # --ckpt-tag 지정 시 체크포인트 비교용 서브폴더에 저장
                if params.ckpt_tag:
                    output_dir = PROJECTS_DIR / actual_roster / "assets" / char.prefix / f"ckpt_{params.ckpt_tag}"
                    origin_dir = PROJECTS_DIR / actual_roster / "assets" / f"{char.prefix}_origin" / f"ckpt_{params.ckpt_tag}"
                else:
                    output_dir = PROJECTS_DIR / actual_roster / "assets" / char.prefix
                    origin_dir = PROJECTS_DIR / actual_roster / "assets" / f"{char.prefix}_origin"
                output_dir.mkdir(parents=True, exist_ok=True)
    
                if not quiet:
                    print(f"\n▶ [{char_idx}/{len(target_chars)}] {char.name} ({char.prefix}) [로스터: {actual_roster}]")
                    if params.ckpt_tag:
                        print(f"  저장 위치: assets/{char.prefix}/ckpt_{params.ckpt_tag}/")
                    if params.bg:
                        print(f"  즉석 배경: '{params.bg}' 적용")
                    elif bg_prompt:
                        print(f"  배경 프리셋: '{params.bg_preset}' 적용")
    
                # IP-Adapter 참조 이미지 탐색 및 업로드
                ref_file_name = None
                ref_weight = params.ref_weight if params.ref_weight is not None else getattr(char, "ref_weight", DEFAULT_REF_WEIGHT)
                if params.engine == "sdxl" and not params.no_ref and ref_weight > 0.0:
                    ref_path = self.asset_svc.find_reference_image(char.prefix, actual_roster, custom_path=params.ref_image)
                    if ref_path:
                        if not params.dry_run and not params.mock:
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
    
                char_results: List[GenerationResult] = []
                total_start = time.time()
                char_codes = char_pose_map[char.prefix]

                existing_manifest_seeds = {}
                manifest_file = output_dir / "_batch_manifest.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file, "r", encoding="utf-8") as mf:
                            m_data = json.load(mf)
                            for itm in m_data.get("items", []):
                                if "code" in itm and itm.get("seed") is not None:
                                    existing_manifest_seeds[str(itm["code"]).strip()] = itm["seed"]
                    except Exception:
                        pass

                for idx, code in enumerate(char_codes, 1):
                    if is_cancelled and is_cancelled():
                        if not quiet:
                            print("\n[알림] 사용자에 의해 배치가 취소되었습니다.")
                        break
    
                    current_item_index += 1
                    pose = db[code]
                    out_name = asset_filename(char.prefix, code, label=pose.label, naming=params.naming)
                    out_path = output_dir / out_name
                    legacy_name = asset_filename(char.prefix, code, naming="code")
                    legacy_path = output_dir / legacy_name
    
                    if params.engine == "sdxl":
                        pos_prompt, neg_prompt, is_nude = assemble_sdxl_prompt(
                            char, pose, bg_prompt=bg_prompt, custom_pos=params.custom_pos, custom_neg=params.custom_neg,
                            checkpoint_name=ckpt_name
                        )
                        display_prompt = pos_prompt

                        # IP-Adapter 2-Track 하이브리드 모드 판별:
                        # - "full": 정적 1인 착의 씬 (emotions 000~019 등)
                        # - "face_only": 역동적 포즈, 테마 의상 스왑, 탈의/H-씬, 2인 모브 등장 씬 전체
                        two_person_tokens = (
                            "1boy", "partner", "faceless male", "bald male", "kiss", "hug", "carry",
                            "grab", "spooning", "blowjob", "missionary", "doggystyle", "cowgirl",
                            "fellatio", "cunnilingus", "paizuri"
                        )
                        p_low = pose.prompt.lower()
                        from plepa_engine.prompt_builder import resolve_pose_outfit_slot
                        outfit_slot = resolve_pose_outfit_slot(pose)
                        if is_nude or outfit_slot != "default" or pose.section not in ("emotions", "genit_emotions") or any(kw in p_low for kw in two_person_tokens):
                            ref_mode = "face_only"
                        else:
                            ref_mode = "full"

                        workflow = build_sdxl_workflow(
                            positive_prompt=pos_prompt,
                            negative_prompt=neg_prompt,
                            output_prefix=f"{char.prefix}_{code}",
                            width=width,
                            height=height,
                            steps=steps,
                            cfg=cfg,
                            sampler=sampler,
                            scheduler=scheduler,
                            ckpt_name=ckpt_name,
                            use_face_detailer=params.face_detailer,
                            use_upscale=params.upscale,
                            ref_image_name=ref_file_name,
                            ref_weight=ref_weight,
                            ref_mode=ref_mode,
                        )
                    else:
                        prompt, is_nude = assemble_flux_prompt(char, pose, bg_prompt=bg_prompt)
                        display_prompt = prompt
                        final_prompt = prompt
                        if params.lora and params.lora.lower() != "none" and "modern-anime" in params.lora.lower():
                            if "modern anime style" not in final_prompt.lower():
                                final_prompt = f"modern anime style, {final_prompt}"
    
                        workflow = build_flux_workflow(
                            prompt=final_prompt,
                            output_prefix=f"{char.prefix}_{code}",
                            width=width,
                            height=height,
                            steps=steps,
                            use_face_detailer=params.face_detailer,
                            use_upscale=params.upscale,
                            unet_name=unet_name,
                            lora_name=params.lora if (params.lora and params.lora.lower() != "none") else None,
                            lora_weight=params.lora_weight,
                        )
    
                    # 워크플로우 시드 추출 및 reuse_seed 처리
                    current_seed = None
                    for node_id, node_data in workflow.items():
                        if isinstance(node_data, dict) and "inputs" in node_data:
                            inp = node_data["inputs"]
                            if "seed" in inp:
                                current_seed = inp["seed"]
                                break
                            elif "noise_seed" in inp:
                                current_seed = inp["noise_seed"]
                                break

                    code_key = str(code).strip()
                    if params.reuse_seed and code_key in existing_manifest_seeds:
                        reused = existing_manifest_seeds[code_key]
                        for node_id, node_data in workflow.items():
                            if isinstance(node_data, dict) and "inputs" in node_data:
                                inp = node_data["inputs"]
                                if "seed" in inp:
                                    inp["seed"] = reused
                                elif "noise_seed" in inp:
                                    inp["noise_seed"] = reused
                        current_seed = reused

                    target = GenerationTarget(
                        code=code,
                        section=pose.section,
                        label=pose.label,
                        assembled_prompt=display_prompt,
                        is_nude=is_nude,
                        output_filename=out_name,
                        seed=current_seed,
                    )
    
                    if not quiet:
                        track_info = f" [IP-A: {ref_mode}]" if (params.engine == "sdxl" and ref_file_name) else ""
                        print(f"  [{idx:02d}/{len(char_codes):02d}] #{code} {pose.label:<10} ({pose.section}){track_info} -> {out_name}", end="", flush=True)
    
                    should_censor = params.censor and (getattr(pose, "is_h_scene", False) or is_nude)

                    # 0. CENSOR-ONLY (기존 이미지 소급 검열 모드: 검열본은 assets/{prefix}/에 교체 배치, 원본은 assets/{prefix}_origin/에 보존)
                    if params.censor_only:
                        origin_path = origin_dir / out_name
                        src_path = origin_path if (origin_path.exists() and origin_path.stat().st_size > 0) else out_path
                        if src_path.exists() and src_path.stat().st_size > 0:
                            if should_censor:
                                targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
                                tmp_censored = output_dir / f".tmp_{out_name}"
                                c_res = censor_file(src_path, dst_path=tmp_censored, style=params.censor_style, targets=targets, pose_code=pose.code)
                                if c_res and c_res.exists():
                                    origin_dir.mkdir(parents=True, exist_ok=True)
                                    # 1. 무검열 원본을 _origin 폴더에 안전하게 보존
                                    if not origin_path.exists():
                                        shutil.copy2(src_path, origin_path)
                                    # 2. 메인 에셋 경로(out_path)에 검열 완성본을 원자적으로 교체 배치
                                    if out_path.exists():
                                        out_path.unlink()
                                    tmp_censored.rename(out_path)
                                    if not quiet:
                                        print(f" [검열본 적용: assets/{char.prefix}/{out_name} (원본: {char.prefix}_origin/)]")
                                    res = GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0)
                                else:
                                    if tmp_censored.exists():
                                        tmp_censored.unlink()
                                    if not quiet:
                                        print(" [검열 대상 미감지(원본 유지)]")
                                    res = GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0)
                            else:
                                if not quiet:
                                    print(" [비-H씬(검열 대상 아님): 건너뜀]")
                                res = GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0)
                        else:
                            if not quiet:
                                print(" [원본 파일 없음: 건너뜀]")
                            res = GenerationResult(target=target, success=False, duration_sec=0.0, error_message="원본 파일 없음")
                        char_results.append(res)
                        all_results.append(res)
                        if on_progress:
                            on_progress(current_item_index, total_items, res)
                        continue

                    # 1. 기존 파일 스킵
                    if not params.overwrite and out_path.exists() and out_path.stat().st_size > 0:
                        if not quiet:
                            print(" [기존 파일 보존: 건너뜀]", end="")
                        if should_censor:
                            origin_path = origin_dir / out_path.name
                            if not origin_path.exists():
                                targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
                                tmp_censored = output_dir / f".tmp_{out_path.name}"
                                c_res = censor_file(out_path, dst_path=tmp_censored, style=params.censor_style, targets=targets, pose_code=pose.code)
                                if c_res and c_res.exists():
                                    origin_dir.mkdir(parents=True, exist_ok=True)
                                    shutil.copy2(out_path, origin_path)
                                    if out_path.exists():
                                        out_path.unlink()
                                    tmp_censored.rename(out_path)
                                    if not quiet:
                                        print(f" [검열본 적용: assets/{char.prefix}/{out_path.name} (원본: {char.prefix}_origin/)]", end="")
                                elif tmp_censored.exists():
                                    tmp_censored.unlink()
                        if not quiet:
                            print()
                        res = GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0)
                        char_results.append(res)
                        all_results.append(res)
                        if on_progress:
                            on_progress(current_item_index, total_items, res)
                        continue

                    # 2. 스마트 사본 보존
                    if not params.overwrite and not out_path.exists() and legacy_path.exists() and legacy_path.stat().st_size > 0:
                        try:
                            shutil.copy2(legacy_path, out_path)
                            if not quiet:
                                print(" [기존 원본에서 하이브리드 사본 복제 완료]", end="")
                            if should_censor:
                                origin_path = origin_dir / out_path.name
                                if not origin_path.exists():
                                    targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
                                    tmp_censored = output_dir / f".tmp_{out_path.name}"
                                    c_res = censor_file(out_path, dst_path=tmp_censored, style=params.censor_style, targets=targets, pose_code=pose.code)
                                    if c_res and c_res.exists():
                                        origin_dir.mkdir(parents=True, exist_ok=True)
                                        shutil.copy2(out_path, origin_path)
                                        if out_path.exists():
                                            out_path.unlink()
                                        tmp_censored.rename(out_path)
                                        if not quiet:
                                            print(f" [검열본 적용: assets/{char.prefix}/{out_path.name} (원본: {char.prefix}_origin/)]", end="")
                                    elif tmp_censored.exists():
                                        tmp_censored.unlink()
                            if not quiet:
                                print()
                            res = GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0)
                            char_results.append(res)
                            all_results.append(res)
                            if on_progress:
                                on_progress(current_item_index, total_items, res)
                            continue
                        except Exception as cpe:
                            if not quiet:
                                print(f" [사본 복제 실패({cpe}) -> 신규 생성 진행]", end="")
    
                    # 3. DRY-RUN
                    if params.dry_run:
                        if not quiet:
                            print(" [DRY-RUN 완료]")
                        res = GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0)
                        char_results.append(res)
                        all_results.append(res)
                        if on_progress:
                            on_progress(current_item_index, total_items, res)
                        continue
    
                    # 4. MOCK 생성
                    if params.mock:
                        item_start = time.time()
                        generate_mock_image(out_path)
                        duration = time.time() - item_start
                        if not quiet:
                            print(f" [MOCK 생성 완료: {duration:.3f}초]")
                        res = GenerationResult(target=target, success=True, image_path=out_path, duration_sec=duration)
                        char_results.append(res)
                        all_results.append(res)
                        if on_progress:
                            on_progress(current_item_index, total_items, res)
                        continue
    
                    # 5. 실제 ComfyUI 생성
                    item_start = time.time()
                    try:
                        max_attempts = (params.max_retries + 1) if params.auto_qc else 1
                        current_wf = workflow
                        final_qc_fail = None

                        for attempt in range(max_attempts):
                            if attempt > 0:
                                new_seed = random.randint(1, 2**63 - 1)
                                target.seed = new_seed
                                current_wf = copy.deepcopy(workflow)
                                for node_id, node_data in current_wf.items():
                                    if isinstance(node_data, dict) and "inputs" in node_data:
                                        inp = node_data["inputs"]
                                        if "seed" in inp:
                                            inp["seed"] = new_seed
                                        elif "noise_seed" in inp:
                                            inp["noise_seed"] = new_seed

                            client.generate_image(workflow=current_wf, output_path=out_path)

                            # Auto-QC 품질 및 결함 검증
                            if params.auto_qc:
                                is_kiss = "kiss" in (pose.prompt or "").lower() or str(target.code) in ("060", "061", "198", "199", "019")
                                passed, fail_reason, _ = validate_generated_image(
                                    image=out_path,
                                    is_solo_scene=pose.is_solo_scene,
                                    is_two_person=pose.is_two_person,
                                    is_offscreen_partner=pose.is_offscreen_partner,
                                    is_kiss_scene=is_kiss,
                                    section=target.section,
                                    prompt=pose.prompt,
                                )
                                if not passed:
                                    final_qc_fail = fail_reason
                                    if attempt < params.max_retries:
                                        if not quiet:
                                            print(f" [Auto-QC 불량: {fail_reason} -> 재시도 {attempt+1}/{params.max_retries}]", end="", flush=True)
                                        continue
                                    else:
                                        if not quiet:
                                            print(f" [Auto-QC 불량(최대 재시도 초과): {fail_reason}]", end="", flush=True)
                                else:
                                    if not quiet and attempt > 0:
                                        print(f" [Auto-QC 통과(재시도 {attempt}회)]", end="", flush=True)

                                # Strict Censor QC: 성인 노출 필수 씬에서 성기 미탐지 시 리롤
                                if should_censor and params.strict_censor_qc:
                                    from plepa_engine.censor import POSE_SAFE_ANCHORS, detect_genitals
                                    code_norm = str(target.code).strip()
                                    if code_norm in POSE_SAFE_ANCHORS:
                                        c_targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
                                        boxes = detect_genitals(str(out_path), targets=c_targets, pose_code=code_norm)
                                        if not boxes:
                                            final_qc_fail = "필수 성인 씬 성기 미탐지(구도 불량)"
                                            if attempt < params.max_retries:
                                                if not quiet:
                                                    print(f" [검열 QC 불량: 성기 미탐지 -> 재시도 {attempt+1}/{params.max_retries}]", end="", flush=True)
                                                continue
                                            else:
                                                if not quiet:
                                                    print(f" [검열 QC 불량(최대 재시도 초과): 성기 미탐지]", end="", flush=True)
                            break

                        duration = time.time() - item_start
                        if not quiet:
                            print(f" [완료: {duration:.1f}초]", end="")
                        if should_censor:
                            targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
                            try:
                                tmp_censored = output_dir / f".tmp_{out_path.name}"
                                c_path = censor_file(out_path, dst_path=tmp_censored, style=params.censor_style, targets=targets, pose_code=pose.code)
                                if c_path and c_path.exists():
                                    origin_dir.mkdir(parents=True, exist_ok=True)
                                    origin_path = origin_dir / out_path.name
                                    shutil.copy2(out_path, origin_path)
                                    if out_path.exists():
                                        out_path.unlink()
                                    tmp_censored.rename(out_path)
                                    if not quiet:
                                        print(f" [검열본 적용: assets/{char.prefix}/{out_path.name} (원본: {char.prefix}_origin/)]", end="")
                                elif tmp_censored.exists():
                                    tmp_censored.unlink()
                            except Exception as ce:
                                if not quiet:
                                    print(f" [검열 실패: {ce}]", end="")
                        if not quiet:
                            print()
                        res = GenerationResult(target=target, success=True, image_path=out_path, duration_sec=duration)
                    except ComfyClientError as ce:
                        duration = time.time() - item_start
                        if not quiet:
                            print(f" [실패: {ce}]")
                        res = GenerationResult(target=target, success=False, duration_sec=duration, error_message=str(ce))
                    except Exception as ge:
                        duration = time.time() - item_start
                        if not quiet:
                            print(f" [예외 발생: {ge}]")
                        res = GenerationResult(target=target, success=False, duration_sec=duration, error_message=str(ge))
    
                    char_results.append(res)
                    all_results.append(res)
                    if on_progress:
                        on_progress(current_item_index, total_items, res)
    
                total_duration = time.time() - total_start
                if not quiet:
                    print_batch_summary(char.prefix, char_results, output_dir, total_duration)

                # 배치 매니페스트 저널 원자적 기록 (_batch_manifest.json)
                self._save_batch_manifest(output_dir, char, actual_roster, params, char_results)
    
        return all_results

    def _save_batch_manifest(
        self,
        output_dir: Path,
        char: CharacterConfig,
        roster: str,
        params: GenerationParams,
        results: List[GenerationResult],
    ) -> None:
        """배치 실행 기록을 _batch_manifest.json에 원자적으로 저장합니다."""
        if not results:
            return

        manifest_path = output_dir / "_batch_manifest.json"
        temp_path = output_dir / f"_batch_manifest_{uuid.uuid4().hex[:6]}.tmp.json"

        existing_items = {}
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    for item in old_data.get("items", []):
                        if "code" in item:
                            existing_items[str(item["code"]).strip()] = item
            except Exception:
                pass

        for r in results:
            t = r.target
            code_key = str(t.code).strip()
            item_entry = {
                "code": t.code,
                "label": t.label,
                "section": t.section,
                "output_filename": getattr(t, "output_filename", ""),
                "success": r.success,
                "skipped": getattr(r, "skipped", False),
                "duration_sec": round(r.duration_sec, 2),
                "error_message": r.error_message,
                "assembled_prompt": getattr(t, "assembled_prompt", ""),
                "seed": getattr(t, "seed", None),
            }
            existing_items[code_key] = item_entry

        def sort_key(k: str):
            try:
                return (0, int(k), "")
            except ValueError:
                return (1, 0, k)

        sorted_codes = sorted(existing_items.keys(), key=sort_key)
        items = [existing_items[c] for c in sorted_codes]

        data = {
            "prefix": char.prefix,
            "character_name": char.name,
            "roster": roster,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "engine": params.engine,
            "checkpoint": getattr(params, "ckpt", None) or getattr(params, "sdxl_ckpt", None) or "default",
            "total_count": len(items),
            "success_count": sum(1 for item in items if item.get("success")),
            "failed_count": sum(1 for item in items if not item.get("success")),
            "items": items,
        }

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(manifest_path)
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            print(f"  [경고] 배치 매니페스트 저장 실패: {e}")


default_generation_service = GenerationService()

