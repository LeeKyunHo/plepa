"""
plepa_engine.services.generation
배치 이미지 생성 준비·실행·Auto-QC·검열·매니페스트 기록 하위 헬퍼 서브패키지.
"""

from plepa_engine.services.generation.manifest import (
    load_manifest_state,
    save_batch_manifest_atomic,
)
from plepa_engine.services.generation.plan import (
    BatchPlan,
    compute_deterministic_pose_seed,
    generate_mock_image,
    get_optimal_resolution_for_pose,
    is_portrait_emotion_pose,
    normalize_engine_params,
    prepare_batch_plan,
    resolve_effective_sdxl_params,
)
from plepa_engine.services.generation.prepare import (
    PoseWorkItem,
    build_pose_work_item,
    resolve_char_workspace_and_ref,
)
from plepa_engine.services.generation.qc_runner import execute_comfy_with_qc_and_censor
from plepa_engine.services.generation.runner import (
    apply_censor_to_asset_atomic,
    dispatch_pose_work_item,
    handle_censor_only_item,
    handle_existing_or_legacy_item,
    resolve_origin_path_compat,
)

__all__ = [
    "BatchPlan",
    "PoseWorkItem",
    "load_manifest_state",
    "save_batch_manifest_atomic",
    "is_portrait_emotion_pose",
    "get_optimal_resolution_for_pose",
    "generate_mock_image",
    "compute_deterministic_pose_seed",
    "resolve_effective_sdxl_params",
    "normalize_engine_params",
    "prepare_batch_plan",
    "resolve_char_workspace_and_ref",
    "build_pose_work_item",
    "resolve_origin_path_compat",
    "apply_censor_to_asset_atomic",
    "handle_censor_only_item",
    "handle_existing_or_legacy_item",
    "execute_comfy_with_qc_and_censor",
    "dispatch_pose_work_item",
]
