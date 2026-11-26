"""
plepa_engine.censor
2D 애니메이션 일러스트 전용 자동 성기 검열(Censorship) 서브패키지 파사드.
Phase P2.5(ADR-99) 알고리즘·수치·공개 API 및 테스트 패치 호환성을 100% 보존합니다.
"""

from __future__ import annotations

from ._runtime import HAS_IMGUTILS, detect_censors, logger
from .constants import (
    DAILY_EXPOSURE_CODES,
    EXEMPT_DAILY_EVENT_CODES,
    EXEMPT_EMOTION_CODES,
    NON_EXPOSURE_H_POSES,
    POSE_EXACT_ANCHORS,
    POSE_SAFE_ANCHORS,
    ROMANCE_NON_EXPOSURE_CODES,
    _POSE_DB_CACHE,
    _POSE_DB_CACHE_LOCK,
    _get_cached_pose_db,
    _normalize_censor_targets,
)
from .policy import (
    _is_otokonoko_context,
    get_pose_anchor_box,
    get_pose_category,
    is_pose_censor_required,
)
from .detection import (
    _detect_target_candidates,
    _filter_bottom_edge_false_positives,
    _get_roi_specs_for_pose,
    _load_pil_image,
    detect_genitals,
)
from .geometry import (
    _BASE_RESOLUTION,
    _bbox_fallback_geometry,
    _box_iomin,
    _box_iou,
    _compute_scale_factor,
    _estimate_penis_axis_and_base,
    _extract_roi_foreground_mask,
    _has_hand_between_boxes,
    _normalize_censor_boxes,
    _odd_kernel,
    _restore_alpha,
    _rotated_rect_points,
    _scale_int,
    _slice_cross_width,
    _split_rgb_and_alpha,
    _to_rgb_ndarray,
    get_skin_mask,
)
from .hybrid import _resolve_hybrid_targets_and_mask, _resolve_hybrid_targets_with_priors
from .lineart import (
    _clamp_mask_by_lineart_and_base,
    _extract_lineart_barrier,
    _label_border_touch_ratio,
    _snap_seed_to_fillable,
    _snap_to_outer_lineart,
)
from .mask_refinement import (
    _build_oriented_core_guard,
    _build_rounded_box_guard,
    _classify_sam_mask_leak,
    _finalize_and_blend_silhouette,
    _is_sam_mask_leaky,
)
from .models import (
    _CENSOR_SEG_LOCK,
    _CENSOR_SEG_MODEL,
    _SAM_MODEL,
    _SAM_MODEL_LOCK,
    _extract_sam_mask_data,
    _infer_custom_censor_seg,
    _infer_custom_censor_seg_items,
    _render_seg_items_mask,
    get_custom_censor_seg_model,
    get_sam_model,
    unload_censor_models,
)
from .pipeline import (
    _atomic_replace_with_retry,
    censor_file,
    censor_image,
    run_batch_censor,
    verify_and_heal_censor,
)
from .protection import (
    _compute_mutually_exclusive_prompts,
    _extract_hand_occlusion_mask,
    _extract_hand_outer_skin_point,
)
from .segmentation import _compute_prior_extension_corridor, _extract_semantic_sam_prompts
from .silhouette import apply_silhouette
from .styles import (
    _render_censored_style,
    apply_debug_bbox,
    apply_manga_bar,
    apply_manga_glow,
)
from .styles_basic import (
    apply_black_silhouette,
    apply_mosaic,
    apply_shadow_silhouette,
    apply_slim_black_bar,
    apply_white_silhouette,
    apply_wide_solid_bar,
)

__all__ = [
    "DAILY_EXPOSURE_CODES",
    "EXEMPT_DAILY_EVENT_CODES",
    "EXEMPT_EMOTION_CODES",
    "HAS_IMGUTILS",
    "NON_EXPOSURE_H_POSES",
    "POSE_EXACT_ANCHORS",
    "POSE_SAFE_ANCHORS",
    "ROMANCE_NON_EXPOSURE_CODES",
    "apply_black_silhouette",
    "apply_debug_bbox",
    "apply_manga_bar",
    "apply_manga_glow",
    "apply_mosaic",
    "apply_shadow_silhouette",
    "apply_silhouette",
    "apply_slim_black_bar",
    "apply_white_silhouette",
    "apply_wide_solid_bar",
    "censor_file",
    "censor_image",
    "detect_censors",
    "detect_genitals",
    "get_custom_censor_seg_model",
    "get_pose_anchor_box",
    "get_pose_category",
    "get_sam_model",
    "get_skin_mask",
    "is_pose_censor_required",
    "logger",
    "run_batch_censor",
    "unload_censor_models",
    "verify_and_heal_censor",
]
