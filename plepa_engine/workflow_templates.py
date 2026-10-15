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
    use_face_detailer: bool = False,
    use_upscale: bool = False,
    ref_image_name: Optional[str] = None,
    ref_weight: float = DEFAULT_REF_WEIGHT,
    ipadapter_model: str = "ip-adapter-plus_sdxl_vit-h.safetensors",
    clip_vision_model: str = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
) -> Dict[str, Any]:
    """
    ComfyUI 로컬 API 전송용 SDXL(Illustrious-XL / NTR MIX XIII 등) 단독 체크포인트 워크플로우 템플릿.
    - ref_image_name 지정 시 IP-Adapter-Plus(SDXL) 노드 그래프를 자동 결합합니다.
    - clip_skip=2 기본 적용 (Illustrious 공식 표준: CLIPSetLastLayer -2).
    """
    if seed < 0:
        seed = random.randint(1, 999999999999999)

    workflow: Dict[str, Any] = {}

    # 1. Checkpoint 로더 (Node 1)
    workflow["1"] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": ckpt_name
        }
    }

    current_model = ["1", 0]
    clip_ref = ["1", 1]

    # Illustrious 공식 표준: CLIP Skip 2 노드 연결 (Node 14)
    if clip_skip > 1:
        workflow["14"] = {
            "class_type": "CLIPSetLastLayer",
            "inputs": {
                "clip": ["1", 1],
                "stop_at_clip_layer": -clip_skip
            }
        }
        clip_ref = ["14", 0]

    # IP-Adapter 결합 (Node 30, 32, 33)
    if ref_image_name:
        workflow["30"] = {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {
                "model": current_model,
                "preset": "PLUS (high strength)"
            }
        }
        workflow["32"] = {
            "class_type": "LoadImage",
            "inputs": {
                "image": ref_image_name
            }
        }
        workflow["33"] = {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": ["30", 0],
                "ipadapter": ["30", 1],
                "image": ["32", 0],
                "weight": ref_weight,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 0.8,
                "embeds_scaling": "K+V",
            }
        }
        current_model = ["33", 0]

    # 2. 긍정 프롬프트 인코딩 (Node 2)
    workflow["2"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": clip_ref,
            "text": positive_prompt
        }
    }

    # 3. 부정 프롬프트 인코딩 (Node 3)
    workflow["3"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": clip_ref,
            "text": negative_prompt
        }
    }

    # 4. 빈 잠재 공간 생성 (Node 4)
    workflow["4"] = {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": width,
            "height": height,
            "batch_size": 1
        }
    }

    # 5. KSampler (Node 5)
    workflow["5"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": current_model,
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["4", 0],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler,
            "scheduler": scheduler,
            "denoise": 1.0
        }
    }

    # 6. VAE 디코딩 (Node 6)
    workflow["6"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["5", 0],
            "vae": ["1", 2]
        }
    }

    current_image_output = ["6", 0]

    # 7. (선택) Face Detailer 노드 (Node 9, 10)
    if use_face_detailer:
        workflow["9"] = {
            "class_type": "UltralyticsDetectorProvider",
            "inputs": {
                "model_name": "bbox/face_yolov8m.pt"
            }
        }
        workflow["10"] = {
            "class_type": "FaceDetailer",
            "inputs": {
                "image": current_image_output,
                "model": current_model,
                "clip": clip_ref,
                "vae": ["1", 2],
                "guide_size": 512,
                "guide_size_for": True,
                "max_size": 1024,
                "seed": seed + 1,
                "steps": steps,
                "cfg": min(cfg, 4.5),
                "sampler_name": sampler,
                "scheduler": scheduler,
                "positive": ["2", 0],
                "negative": ["3", 0],
                "denoise": 0.35,
                "feather": 5,
                "noise_mask": True,
                "force_inpaint": True,
                "bbox_threshold": 0.5,
                "bbox_dilation": 10,
                "bbox_crop_factor": 3.0,
                "sam_detection_hint": "center-1",
                "sam_dilation": 0,
                "sam_threshold": 0.93,
                "sam_bbox_expansion": 0,
                "sam_mask_hint_threshold": 0.7,
                "sam_mask_hint_use_negative": "False",
                "drop_size": 10,
                "wildcard": "",
                "cycle": 1,
                "bbox_detector": ["9", 0]
            }
        }
        current_image_output = ["10", 0]

    # 8. (선택) AI 업스케일 노드 (Node 11, 12)
    if use_upscale:
        workflow["11"] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {
                "model_name": DEFAULT_UPSCALER
            }
        }
        workflow["12"] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": ["11", 0],
                "image": current_image_output
            }
        }
        current_image_output = ["12", 0]

    # 9. 최종 이미지 저장 노드 (Node 20)
    workflow["20"] = {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": output_prefix,
            "images": current_image_output
        }
    }

    return workflow


def build_standalone_upscale_workflow(
    image_name: str,
    output_prefix: str = "upscale_4k",
    upscale_model: str = DEFAULT_UPSCALER,
) -> Dict[str, Any]:
    """
    이미 생성 완료된 이미지를 ComfyUI에 업로드하여 AI 모델(4x-UltraSharp 등)로 단독 초고화질 업스케일하는 워크플로우.
    - 디퓨전(KSampler) 없이 순수 초해상화 모델만 실행하므로 장당 2~3초 초고속 처리 및 형태 변형 0%.
    """
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": image_name
            }
        },
        "2": {
            "class_type": "UpscaleModelLoader",
            "inputs": {
                "model_name": upscale_model
            }
        },
        "3": {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": ["2", 0],
                "image": ["1", 0]
            }
        },
        "4": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": output_prefix,
                "images": ["3", 0]
            }
        }
    }


