"""
plepa_engine.services.generation_service
FLUX / SDXL 듀얼 엔진 배치 이미지 생성 핵심 서비스.
CLI와 GUI가 공통으로 호출하며, 진행률 콜백 및 취소 인터럽트를 지원합니다.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from plepa_engine.censor import censor_file
from plepa_engine.comfy_client import ComfyClient, ComfyClientError
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
    ckpt: str = DEFAULT_SDXL_CKPT
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
    face_detailer: bool = False
    upscale: bool = False
    steps: Optional[int] = None
    cfg: Optional[float] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    unet: str = DEFAULT_UNET_GGUF
    lora: str = "modern-anime-lora.safetensors"
    lora_weight: float = 0.9
    width: Optional[int] = None
    height: Optional[int] = None
    naming: str = "hybrid"
    censor: bool = False
    censor_style: str = "bar"
    censor_targets: str = "penis"


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
        # 1. 해상도 및 샘플러 기본값 산출
        if params.engine == "sdxl":
            width = params.width if params.width is not None else DEFAULT_SDXL_WIDTH
            height = params.height if params.height is not None else DEFAULT_SDXL_HEIGHT
            steps = params.steps if params.steps is not None else DEFAULT_SDXL_STEPS
            cfg = params.cfg if params.cfg is not None else DEFAULT_SDXL_CFG
            sampler = params.sampler if params.sampler is not None else DEFAULT_SDXL_SAMPLER
            scheduler = params.scheduler if params.scheduler is not None else DEFAULT_SDXL_SCHEDULER
        else:
            width = params.width if params.width is not None else DEFAULT_WIDTH
            height = params.height if params.height is not None else DEFAULT_HEIGHT
            steps = params.steps if params.steps is not None else DEFAULT_STEPS
            cfg = params.cfg if params.cfg is not None else 3.5
            sampler = params.sampler if params.sampler is not None else "euler"
            scheduler = params.scheduler if params.scheduler is not None else "simple"

        # 2. 포즈 DB 및 대상 캐릭터/포즈 코드 해석
        db = self.pose_svc.load_pose_db(engine=params.engine)
        target_chars = self.char_svc.resolve_characters(params.character_expr, roster=params.roster)
        codes = self.pose_svc.resolve_pose_codes(params.pose_expr, db)

        if params.profile:
            for char_obj, _ in target_chars:
                char_obj.apply_profile(params.profile)

        # 3. ComfyUI 연결 검사
        client = ComfyClient(host=COMFY_HOST)
        if not params.dry_run and not params.mock:
            if not client.check_connection():
                raise ConnectionError(
                    f"ComfyUI 서버({COMFY_HOST})에 연결할 수 없습니다. "
                    "ComfyUI의 run_nvidia_gpu.bat를 가동해 주십시오."
                )

        total_items = len(target_chars) * len(codes)
        current_item_index = 0
        all_results: List[GenerationResult] = []

        if not quiet:
            print("=" * 60)
            engine_title = f"SDXL ({params.ckpt})" if params.engine == "sdxl" else f"FLUX.1 [dev] (GGUF: {params.unet})"
            print(f"  [플에파] 듀얼 엔진 가동 모드: {engine_title}")
            print(f"  대상 캐릭터: 총 {len(target_chars)}명 ({', '.join(c.prefix for c, _ in target_chars)})")
            print(f"  캐릭터당 포즈: 총 {len(codes)}개 ({', '.join(codes)}) | 총 {total_items}개 에셋")
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

        for char_idx, (char, actual_roster) in enumerate(target_chars, 1):
            if is_cancelled and is_cancelled():
                if not quiet:
                    print("\n[알림] 사용자에 의해 배치가 취소되었습니다.")
                break

            bg_prompt = params.bg.strip() if params.bg else self.bg_svc.get_preset(actual_roster, key=params.bg_preset, engine=params.engine)
            output_dir = PROJECTS_DIR / actual_roster / "assets" / char.prefix
            output_dir.mkdir(parents=True, exist_ok=True)

            if not quiet:
                print(f"\n▶ [{char_idx}/{len(target_chars)}] {char.name} ({char.prefix}) [로스터: {actual_roster}]")
                if params.bg:
                    print(f"  즉석 배경: '{params.bg}' 적용")
                elif bg_prompt:
                    print(f"  배경 프리셋: '{params.bg_preset}' 적용")

            # IP-Adapter 참조 이미지 탐색 및 업로드
            ref_file_name = None
            ref_weight = params.ref_weight if params.ref_weight is not None else getattr(char, "ref_weight", DEFAULT_REF_WEIGHT)
            if params.engine == "sdxl" and not params.no_ref:
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
            elif params.no_ref and not quiet:
                print("  IP-Adapter: 비활성화 (--no_ref)")

            char_results: List[GenerationResult] = []
            total_start = time.time()

            for idx, code in enumerate(codes, 1):
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
                        char, pose, bg_prompt=bg_prompt, custom_pos=params.custom_pos, custom_neg=params.custom_neg
                    )
                    display_prompt = pos_prompt
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
                        ckpt_name=params.ckpt,
                        use_face_detailer=params.face_detailer,
                        use_upscale=params.upscale,
                        ref_image_name=ref_file_name,
                        ref_weight=ref_weight,
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
                        unet_name=params.unet,
                        lora_name=params.lora if (params.lora and params.lora.lower() != "none") else None,
                        lora_weight=params.lora_weight,
                    )

                target = GenerationTarget(
                    code=code,
                    section=pose.section,
                    label=pose.label,
                    assembled_prompt=display_prompt,
                    is_nude=is_nude,
                    output_filename=out_name,
                )

                if not quiet:
                    print(f"  [{idx:02d}/{len(codes):02d}] #{code} {pose.label:<10} ({pose.section}) ➔ {out_name}", end="", flush=True)

                # 1. 기존 파일 스킵
                if not params.overwrite and out_path.exists() and out_path.stat().st_size > 0:
                    if not quiet:
                        print(" [기존 파일 보존: 건너뜀]", end="")
                    if params.censor and is_nude:
                        c_target = out_path.with_name(f"{out_path.stem}_censored{out_path.suffix}")
                        if not c_target.exists():
                            targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
                            c_res = censor_file(out_path, dst_path=c_target, style=params.censor_style, targets=targets)
                            if c_res and c_res.exists() and not quiet:
                                print(f" [검열본 생성: {c_res.name}]", end="")
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
                        if params.censor and is_nude:
                            c_target = out_path.with_name(f"{out_path.stem}_censored{out_path.suffix}")
                            if not c_target.exists():
                                targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
                                c_res = censor_file(out_path, dst_path=c_target, style=params.censor_style, targets=targets)
                                if c_res and c_res.exists() and not quiet:
                                    print(f" [검열본 생성: {c_res.name}]", end="")
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
                            print(f" [사본 복제 실패({cpe}) ➔ 신규 생성 진행]", end="")

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
                    client.generate_image(workflow=workflow, output_path=out_path)
                    duration = time.time() - item_start
                    if not quiet:
                        print(f" [완료: {duration:.1f}초]", end="")
                    if params.censor and is_nude:
                        targets = [t.strip() for t in params.censor_targets.split(",") if t.strip()]
                        try:
                            c_path = censor_file(out_path, style=params.censor_style, targets=targets)
                            if c_path and c_path.exists() and not quiet:
                                print(f" [검열본 생성: {c_path.name}]", end="")
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

        return all_results


default_generation_service = GenerationService()
