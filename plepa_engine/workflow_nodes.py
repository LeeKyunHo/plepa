"""
plepa_engine.workflow_nodes
SDXL 워크플로우 그래프 조립용 IP-Adapter, Face/Hand Detailer, Upscale 노드 빌더 헬퍼.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from plepa_engine.graph_builder import WorkflowGraph


def add_ipadapter_nodes(
    graph: WorkflowGraph,
    base_model: Any,
    ref_image_name: str,
    ref_weight: float,
    ref_mode: str,
) -> Any:
    """IP-Adapter-Plus (SDXL) 로더·이미지 전처리·적용 노드를 순서대로 추가하고 모델 출력을 반환합니다."""
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
        start_at, end_at, weight_type = 0.0, 1.0, "linear"
    else:
        start_at, end_at, weight_type = 0.25, 0.75, "ease out"

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
    return graph.out(ipa_adv_id, 0)


def add_detailer_pass(
    graph: WorkflowGraph,
    image_ref: Any,
    model_ref: Any,
    clip_ref: Any,
    vae_ref: Any,
    pos_id: str,
    neg_id: str,
    detector_model: str,
    pass_seed: int,
    steps: int,
    cfg: float,
    sampler: str,
    scheduler: str,
    denoise: float,
    bbox_threshold: float,
    bbox_crop_factor: float,
    sam_threshold: float,
    detailer_hook: Any = None,
) -> Any:
    """UltralyticsDetectorProvider + FaceDetailer 패스 1회를 그래프에 추가합니다."""
    detector_id = graph.add_node("UltralyticsDetectorProvider", model_name=detector_model)
    kwargs: Dict[str, Any] = dict(
        image=image_ref,
        model=model_ref,
        clip=clip_ref,
        vae=vae_ref,
        guide_size=512,
        guide_size_for=True,
        max_size=1024,
        seed=pass_seed,
        steps=steps,
        cfg=min(cfg, 4.5),
        sampler_name=sampler,
        scheduler=scheduler,
        positive=graph.out(pos_id, 0),
        negative=graph.out(neg_id, 0),
        denoise=denoise,
        feather=5,
        noise_mask=True,
        force_inpaint=True,
        bbox_threshold=bbox_threshold,
        bbox_dilation=10,
        bbox_crop_factor=bbox_crop_factor,
        sam_detection_hint="center-1",
        sam_dilation=0,
        sam_threshold=sam_threshold,
        sam_bbox_expansion=0,
        sam_mask_hint_threshold=0.7,
        sam_mask_hint_use_negative="False",
        drop_size=10,
        wildcard="",
        cycle=1,
        bbox_detector=graph.out(detector_id, 0),
    )
    if detailer_hook is not None:
        kwargs["detailer_hook"] = detailer_hook
    node_id = graph.add_node("FaceDetailer", **kwargs)
    return graph.out(node_id, 0)


def append_sampler_and_decode(
    graph: WorkflowGraph,
    base_model: Any,
    ipa_model: Any,
    clip_ref: Any,
    vae_ref: Any,
    positive_prompt: str,
    negative_prompt: str,
    ref_image_name: Optional[str],
    ref_mode: str,
    width: int,
    height: int,
    seed: int,
    steps: int,
    cfg: float,
    sampler: str,
    scheduler: str,
) -> tuple[str, str, Any]:
    """CLIPTextEncode · EmptyLatentImage · KSampler · VAEDecode 노드를 순서대로 추가합니다."""
    pos_id = graph.add_node("CLIPTextEncode", clip=clip_ref, text=positive_prompt)
    neg_id = graph.add_node("CLIPTextEncode", clip=clip_ref, text=negative_prompt)
    latent_id = graph.add_node("EmptyLatentImage", width=width, height=height, batch_size=1)
    ksampler_model = ipa_model if (ref_image_name and ref_mode == "full") else base_model
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
    decode_id = graph.add_node("VAEDecode", samples=graph.out(ksampler_id, 0), vae=vae_ref)
    return pos_id, neg_id, graph.out(decode_id, 0)


def append_detailers_and_upscale(
    graph: WorkflowGraph,
    current_image_output: Any,
    detailer_model: Any,
    clip_ref: Any,
    vae_ref: Any,
    pos_id: str,
    neg_id: str,
    seed: int,
    steps: int,
    cfg: float,
    sampler: str,
    scheduler: str,
    use_face_detailer: Optional[bool],
    use_hand_detailer: bool,
    hand_detector_model: str,
    use_upscale: bool,
    default_upscaler: str,
    ref_image_name: Optional[str],
    ref_mode: str,
) -> Any:
    """FaceDetailer · HandDetailer · Upscale nodes 를 순서대로 체이닝합니다."""
    should_use_face_detailer = True if use_face_detailer is None else bool(use_face_detailer)
    if should_use_face_detailer:
        fd_denoise = 0.40 if (ref_image_name and ref_mode == "face_only") else 0.35
        hook_id = graph.add_node(
            "SEGSOrderedFilterDetailerHookProvider",
            target="area(=w*h)",
            order=True,
            take_start=0,
            take_count=1,
        )
        current_image_output = add_detailer_pass(
            graph=graph,
            image_ref=current_image_output,
            model_ref=detailer_model,
            clip_ref=clip_ref,
            vae_ref=vae_ref,
            pos_id=pos_id,
            neg_id=neg_id,
            detector_model="bbox/face_yolov8m.pt",
            pass_seed=seed + 1,
            steps=steps,
            cfg=cfg,
            sampler=sampler,
            scheduler=scheduler,
            denoise=fd_denoise,
            bbox_threshold=0.68,
            bbox_crop_factor=3.0,
            sam_threshold=0.93,
            detailer_hook=graph.out(hook_id, 0),
        )

    if use_hand_detailer:
        current_image_output = add_detailer_pass(
            graph=graph,
            image_ref=current_image_output,
            model_ref=detailer_model,
            clip_ref=clip_ref,
            vae_ref=vae_ref,
            pos_id=pos_id,
            neg_id=neg_id,
            detector_model=hand_detector_model,
            pass_seed=seed + 2,
            steps=steps,
            cfg=cfg,
            sampler=sampler,
            scheduler=scheduler,
            denoise=0.35,
            bbox_threshold=0.60,
            bbox_crop_factor=2.0,
            sam_threshold=0.90,
        )

    if use_upscale:
        upscale_loader_id = graph.add_node("UpscaleModelLoader", model_name=default_upscaler)
        upscale_id = graph.add_node(
            "ImageUpscaleWithModel",
            upscale_model=graph.out(upscale_loader_id, 0),
            image=current_image_output,
        )
        current_image_output = graph.out(upscale_id, 0)

    return current_image_output
