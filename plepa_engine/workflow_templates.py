"""
plepa_engine.workflow_templates
ComfyUI 로컬 API 전송용 SDXL 단일 파이프라인 워크플로우 템플릿 생성기.
"""

from __future__ import annotations

import random
from typing import Any, Dict, Optional
from plepa_engine.config import (
    DEFAULT_CLIP_SKIP,
    DEFAULT_REF_WEIGHT,
    DEFAULT_SDXL_CFG,
    DEFAULT_SDXL_CKPT,
    DEFAULT_SDXL_HEIGHT,
    DEFAULT_SDXL_SAMPLER,
    DEFAULT_SDXL_SCHEDULER,
    DEFAULT_SDXL_STEPS,
    DEFAULT_SDXL_WIDTH,
    DEFAULT_UPSCALER,
)


from plepa_engine.graph_builder import WorkflowGraph
from plepa_engine.workflow_nodes import (
    add_ipadapter_nodes,
    append_detailers_and_upscale,
    append_sampler_and_decode,
)


def build_flux_workflow(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """[DEPRECATED] 레거시 FLUX 워크플로우 빌더 (plepa_engine.legacy로 격리됨)."""
    from plepa_engine.legacy.flux_workflows import build_flux_workflow as _legacy_build
    return _legacy_build(*args, **kwargs)


# ComfyUI 파이프라인 구동에 필수적인 외부 커스텀 노드 및 해당 확장 팩 매핑
REQUIRED_CUSTOM_NODES: Dict[str, str] = {
    # ComfyUI-Impact-Pack (얼굴/손 정밀 보정 및 세그먼트 디텍터)
    "FaceDetailer": "ComfyUI-Impact-Pack",
    "UltralyticsDetectorProvider": "ComfyUI-Impact-Pack",
    "SEGSOrderedFilterDetailerHookProvider": "ComfyUI-Impact-Pack",
    # ComfyUI_IPAdapter_plus (캐릭터 레퍼런스 스타일 주입)
    "IPAdapterUnifiedLoader": "ComfyUI_IPAdapter_plus",
    "PrepImageForClipVision": "ComfyUI_IPAdapter_plus",
    "IPAdapterAdvanced": "ComfyUI_IPAdapter_plus",
}


def _normalize_lora_specs(
    loras: Optional[Any] = None,
    lora_name: Optional[str] = None,
    lora_weight: float = 0.8,
) -> list[tuple[str, float]]:
    """단일·복수 LoRA 입력을 유효한 (파일명, 강도) 튜플 목록으로 정규화합니다."""
    specs: list[tuple[str, float]] = []
    candidates: list[Any] = list(loras) if loras is not None else []
    if lora_name is not None:
        candidates.insert(0, (lora_name, lora_weight))
    seen: set[str] = set()
    for item in candidates:
        name, weight = "", 0.8
        if isinstance(item, (tuple, list)) and item:
            name = str(item[0] or "").strip()
            weight = float(item[1]) if len(item) > 1 and item[1] is not None else 0.8
        elif isinstance(item, dict):
            name, weight = str(item.get("name") or "").strip(), float(item.get("weight", 0.8))
        elif hasattr(item, "name"):
            name = str(getattr(item, "name") or "").strip()
            weight = float(getattr(item, "weight", 0.8) or 0.8)
        elif isinstance(item, str):
            name, weight = item.strip(), float(lora_weight)
        if not name or name.lower() in {"none", "null", "off", "false"}:
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            specs.append((name, weight))
    return specs


def _apply_lora_chain(
    graph: WorkflowGraph,
    base_model: Any,
    clip_ref: Any,
    loras: list[tuple[str, float]],
) -> tuple[Any, Any]:
    """활성 LoRA가 있을 때만 LoraLoader 노드를 직렬 체이닝합니다."""
    for name, weight in loras:
        lora_id = graph.add_node(
            "LoraLoader",
            model=base_model,
            clip=clip_ref,
            lora_name=name,
            strength_model=float(weight),
            strength_clip=float(weight),
        )
        base_model, clip_ref = graph.out(lora_id, 0), graph.out(lora_id, 1)
    return base_model, clip_ref


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
    use_freeu: bool = True,
    use_upscale: bool = False,
    ref_image_name: Optional[str] = None,
    ref_weight: float = DEFAULT_REF_WEIGHT,
    ref_mode: str = "full",
    ipadapter_model: str = "ip-adapter-plus_sdxl_vit-h.safetensors",
    clip_vision_model: str = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
    hand_detector_model: str = "bbox/hand_yolov8s.pt",
    loras: Optional[Any] = None,
    lora_name: Optional[str] = None,
    lora_weight: float = 0.8,
) -> Dict[str, Any]:
    """ComfyUI SDXL 워크플로우 그래프 생성 (LoRA 미지정 시 바이패스, IP-Adapter 2-Track 지원)."""
    if seed < 0:
        seed = random.randint(1, 999999999999999)

    graph = WorkflowGraph()
    ckpt_id = graph.add_node("CheckpointLoaderSimple", ckpt_name=ckpt_name)
    base_model, clip_ref, vae_ref = graph.out(ckpt_id, 0), graph.out(ckpt_id, 1), graph.out(ckpt_id, 2)

    active_loras = _normalize_lora_specs(loras=loras, lora_name=lora_name, lora_weight=lora_weight)
    if active_loras:
        base_model, clip_ref = _apply_lora_chain(graph, base_model, clip_ref, active_loras)
    if clip_skip > 1:
        skip_id = graph.add_node("CLIPSetLastLayer", clip=clip_ref, stop_at_clip_layer=-clip_skip)
        clip_ref = graph.out(skip_id, 0)
    if use_freeu:
        freeu_id = graph.add_node("FreeU", model=base_model, b1=1.02, b2=1.03, s1=0.95, s2=0.2)
        base_model = graph.out(freeu_id, 0)

    ipa_model = (
        add_ipadapter_nodes(graph, base_model, ref_image_name, ref_weight, ref_mode)
        if ref_image_name else None
    )
    pos_id, neg_id, current_image_output = append_sampler_and_decode(
        graph=graph, base_model=base_model, ipa_model=ipa_model, clip_ref=clip_ref, vae_ref=vae_ref,
        positive_prompt=positive_prompt, negative_prompt=negative_prompt,
        ref_image_name=ref_image_name, ref_mode=ref_mode, width=width, height=height,
        seed=seed, steps=steps, cfg=cfg, sampler=sampler, scheduler=scheduler,
    )
    detailer_model = ipa_model if ref_image_name else base_model
    current_image_output = append_detailers_and_upscale(
        graph=graph, current_image_output=current_image_output, detailer_model=detailer_model,
        clip_ref=clip_ref, vae_ref=vae_ref, pos_id=pos_id, neg_id=neg_id, seed=seed,
        steps=steps, cfg=cfg, sampler=sampler, scheduler=scheduler,
        use_face_detailer=use_face_detailer, use_hand_detailer=use_hand_detailer,
        hand_detector_model=hand_detector_model, use_upscale=use_upscale,
        default_upscaler=DEFAULT_UPSCALER, ref_image_name=ref_image_name, ref_mode=ref_mode,
    )
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



