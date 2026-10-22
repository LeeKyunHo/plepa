"""
plepa_engine.workflow_templates
ComfyUI 로컬 API 전송용 플럭스(FLUX.1 [dev] GGUF) 워크플로우 템플릿 생성기.
"""

from __future__ import annotations

import random
from typing import Any, Dict, Optional
from plepa_engine.config import (
    DEFAULT_CLIP_1,
    DEFAULT_CLIP_2,
    DEFAULT_GUIDANCE,
    DEFAULT_HEIGHT,
    DEFAULT_SAMPLER,
    DEFAULT_SCHEDULER,
    DEFAULT_SDXL_CKPT,
    DEFAULT_SDXL_CFG,
    DEFAULT_SDXL_HEIGHT,
    DEFAULT_SDXL_SAMPLER,
    DEFAULT_SDXL_SCHEDULER,
    DEFAULT_SDXL_STEPS,
    DEFAULT_SDXL_WIDTH,
    DEFAULT_CLIP_SKIP,
    DEFAULT_REF_WEIGHT,
    DEFAULT_STEPS,
    DEFAULT_UNET_GGUF,
    DEFAULT_UPSCALER,
    DEFAULT_VAE,
    DEFAULT_WIDTH,
)


# ── 레거시 FLUX 워크플로우 (plepa_engine.legacy.flux_workflows로 분리 격리됨) ──
from plepa_engine.legacy.flux_workflows import build_flux_workflow



from plepa_engine.graph_builder import WorkflowGraph


def build_sdxl_workflow(
    positive_prompt: str,
    negative_prompt: str,
    output_prefix: str,
    seed: int = -1,
    width: int = DEFAULT_SDXL_WIDTH,
    height: int = DEFAULT_SDXL_HEIGHT,
    steps: int = DEFAULT_SDXL_STEPS,
    cfg: float = DEFAULT_SDXL_CFG,
    sampler: str = DEFAULT_SDXL_SAMPLER,
    scheduler: str = DEFAULT_SDXL_SCHEDULER,
    ckpt_name: str = DEFAULT_SDXL_CKPT,
    clip_skip: int = DEFAULT_CLIP_SKIP,
    use_face_detailer: Optional[bool] = None,
    use_hand_detailer: bool = False,
    use_upscale: bool = False,
    ref_image_name: Optional[str] = None,
    ref_weight: float = DEFAULT_REF_WEIGHT,
    ref_mode: str = "full",
    ipadapter_model: str = "ip-adapter-plus_sdxl_vit-h.safetensors",
    clip_vision_model: str = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
    hand_detector_model: str = "bbox/hand_yolov8s.pt",
) -> Dict[str, Any]:
    """
    ComfyUI 로컬 API 전송용 SDXL(Illustrious-XL / NTR MIX XIII 등) 단독 체크포인트 워크플로우 템플릿.
    - WorkflowGraph 동적 노드 ID 할당 및 자동 배선을 사용합니다.
    - ref_image_name 지정 시 IP-Adapter-Plus(SDXL) 노드 그래프를 동적으로 체이닝합니다.
    - ref_mode:
        - "full": 정적 1인 착의 씬(000~019 등), 1차 KSampler와 2차 FaceDetailer 모두 IP-Adapter 연결
        - "face_only": 역동적 포즈/H씬/2인씬, 1차 KSampler는 순수 base_model(포즈/의상 파괴 차단), 2차 FaceDetailer에만 IP-Adapter 연결
    - clip_skip=2 기본 적용 (Illustrious 공식 표준: CLIPSetLastLayer -2).
    """
    if seed < 0:
        seed = random.randint(1, 999999999999999)

    graph = WorkflowGraph()

    # 1. Checkpoint 로더
    ckpt_id = graph.add_node("CheckpointLoaderSimple", ckpt_name=ckpt_name)
    base_model = graph.out(ckpt_id, 0)
    clip_ref = graph.out(ckpt_id, 1)
    vae_ref = graph.out(ckpt_id, 2)

    # 2. Illustrious 공식 표준: CLIP Skip 노드 연결
    if clip_skip > 1:
        skip_id = graph.add_node("CLIPSetLastLayer", clip=clip_ref, stop_at_clip_layer=-clip_skip)
        clip_ref = graph.out(skip_id, 0)

    # 3. IP-Adapter 결합 (PrepImageForClipVision + 2-Track 하이브리드)
    ipa_model = None
    if ref_image_name:
        ipa_loader_id = graph.add_node("IPAdapterUnifiedLoader", model=base_model, preset="PLUS (high strength)")
        load_img_id = graph.add_node("LoadImage", image=ref_image_name)
        prep_img_id = graph.add_node(
            "PrepImageForClipVision",
            image=graph.out(load_img_id, 0),
            interpolation="LANCZOS",
            crop_position="top",
            sharpening=0.05,
        )

        if ref_mode == "face_only":
            start_at = 0.0
            end_at = 1.0
            weight_type = "linear"
        else:  # full
            start_at = 0.25
            end_at = 0.75
            weight_type = "ease out"

        ipa_adv_id = graph.add_node(
            "IPAdapterAdvanced",
            model=graph.out(ipa_loader_id, 0),
            ipadapter=graph.out(ipa_loader_id, 1),
            image=graph.out(prep_img_id, 0),
            weight=ref_weight,
            weight_type=weight_type,
            combine_embeds="concat",
            start_at=start_at,
            end_at=end_at,
            embeds_scaling="K+V w/ C penalty",
        )
        ipa_model = graph.out(ipa_adv_id, 0)

    # 4. 프롬프트 인코딩
    pos_id = graph.add_node("CLIPTextEncode", clip=clip_ref, text=positive_prompt)
    neg_id = graph.add_node("CLIPTextEncode", clip=clip_ref, text=negative_prompt)

    # 5. 빈 잠재 공간 생성
    latent_id = graph.add_node("EmptyLatentImage", width=width, height=height, batch_size=1)

    # 6. KSampler 모델 결정: full 모드는 IP-Adapter 적용, face_only 모드는 순수 base_model 적용
    if ref_image_name and ref_mode == "full":
        ksampler_model = ipa_model
    else:
        ksampler_model = base_model

    ksampler_id = graph.add_node(
        "KSampler",
        model=ksampler_model,
        positive=graph.out(pos_id, 0),
        negative=graph.out(neg_id, 0),
        latent_image=graph.out(latent_id, 0),
        seed=seed,
        steps=steps,
        cfg=cfg,
        sampler_name=sampler,
        scheduler=scheduler,
        denoise=1.0,
    )

    # 7. VAE 디코딩
    decode_id = graph.add_node("VAEDecode", samples=graph.out(ksampler_id, 0), vae=vae_ref)
    current_image_output = graph.out(decode_id, 0)

    # 8. (기본 활성화: None이거나 True이면 Face Detailer 활성화, 명시적 False 시 비활성화)
    if use_face_detailer is None:
        should_use_face_detailer = True
    else:
        should_use_face_detailer = bool(use_face_detailer)
    if should_use_face_detailer:
        detector_id = graph.add_node("UltralyticsDetectorProvider", model_name="bbox/face_yolov8m.pt")
        fd_model = ipa_model if ref_image_name else base_model
        fd_denoise = 0.40 if (ref_image_name and ref_mode == "face_only") else 0.35
        hook_id = graph.add_node(
            "SEGSOrderedFilterDetailerHookProvider",
            target="area(=w*h)",
            order=True,
            take_start=0,
            take_count=1,
        )
        fd_id = graph.add_node(
            "FaceDetailer",
            image=current_image_output,
            model=fd_model,
            clip=clip_ref,
            vae=vae_ref,
            guide_size=512,
            guide_size_for=True,
            max_size=1024,
            seed=seed + 1,
            steps=steps,
            cfg=min(cfg, 4.5),
            sampler_name=sampler,
            scheduler=scheduler,
            positive=graph.out(pos_id, 0),
            negative=graph.out(neg_id, 0),
            denoise=fd_denoise,
            feather=5,
            noise_mask=True,
            force_inpaint=True,
            bbox_threshold=0.68,
            bbox_dilation=10,
            bbox_crop_factor=3.0,
            sam_detection_hint="center-1",
            sam_dilation=0,
            sam_threshold=0.93,
            sam_bbox_expansion=0,
            sam_mask_hint_threshold=0.7,
            sam_mask_hint_use_negative="False",
            drop_size=10,
            wildcard="",
            cycle=1,
            bbox_detector=graph.out(detector_id, 0),
            detailer_hook=graph.out(hook_id, 0),
        )
        current_image_output = graph.out(fd_id, 0)

    # 8.1. (선택) Hand Detailer 체이닝 (Face Detailer 직후 손 보정)
    if use_hand_detailer:
        hand_detector_id = graph.add_node("UltralyticsDetectorProvider", model_name=hand_detector_model)
        hd_model = ipa_model if ref_image_name else base_model
        hd_id = graph.add_node(
            "FaceDetailer",
            image=current_image_output,
            model=hd_model,
            clip=clip_ref,
            vae=vae_ref,
            guide_size=512,
            guide_size_for=True,
            max_size=1024,
            seed=seed + 2,
            steps=steps,
            cfg=min(cfg, 4.5),
            sampler_name=sampler,
            scheduler=scheduler,
            positive=graph.out(pos_id, 0),
            negative=graph.out(neg_id, 0),
            denoise=0.35,
            feather=5,
            noise_mask=True,
            force_inpaint=True,
            bbox_threshold=0.60,
            bbox_dilation=10,
            bbox_crop_factor=2.0,
            sam_detection_hint="center-1",
            sam_dilation=0,
            sam_threshold=0.90,
            sam_bbox_expansion=0,
            sam_mask_hint_threshold=0.7,
            sam_mask_hint_use_negative="False",
            drop_size=10,
            wildcard="",
            cycle=1,
            bbox_detector=graph.out(hand_detector_id, 0),
        )
        current_image_output = graph.out(hd_id, 0)

    # 9. (선택) AI 업스케일 노드
    if use_upscale:
        upscale_loader_id = graph.add_node("UpscaleModelLoader", model_name=DEFAULT_UPSCALER)
        upscale_id = graph.add_node(
            "ImageUpscaleWithModel",
            upscale_model=graph.out(upscale_loader_id, 0),
            image=current_image_output,
        )
        current_image_output = graph.out(upscale_id, 0)

    # 10. 최종 이미지 저장 노드
    graph.add_node("SaveImage", filename_prefix=output_prefix, images=current_image_output)

    return graph.to_dict()



def build_standalone_upscale_workflow(
    image_name: str,
    output_prefix: str = "upscale_4k",
    upscale_model: str = DEFAULT_UPSCALER,
) -> Dict[str, Any]:
    """
    이미 생성 완료된 이미지를 ComfyUI에 업로드하여 AI 모델(4x-UltraSharp 등)로 단독 초고화질 업스케일하는 워크플로우.
    - 디퓨전(KSampler) 없이 순수 초해상화 모델만 실행하므로 장당 2~3초 초고속 처리 및 형태 변형 0%.
    """
    graph = WorkflowGraph()
    load_img_id = graph.add_node("LoadImage", image=image_name)
    model_loader_id = graph.add_node("UpscaleModelLoader", model_name=upscale_model)
    upscale_id = graph.add_node(
        "ImageUpscaleWithModel",
        upscale_model=graph.out(model_loader_id, 0),
        image=graph.out(load_img_id, 0),
    )
    graph.add_node("SaveImage", filename_prefix=output_prefix, images=graph.out(upscale_id, 0))
    return graph.to_dict()



