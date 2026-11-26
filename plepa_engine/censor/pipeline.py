"""
plepa_engine.censor.pipeline
단건 이미지 검열(censor_image), 사후 치유(verify_and_heal_censor), 원자적 파일 저장(censor_file) 및 일괄 처리 모듈.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import time
from typing import List, Optional, Sequence, Tuple, Union
import uuid

import numpy as np
from PIL import Image

from ._runtime import HAS_IMGUTILS, _restore_alpha, _split_rgb_and_alpha, detect_censors, facade_get, logger
from .constants import _normalize_censor_targets
from .detection import _load_pil_image
from .geometry import get_skin_mask
from .hybrid import _resolve_hybrid_targets_with_priors
from .policy import get_pose_anchor_box, get_pose_category, is_pose_censor_required
from .styles import _render_censored_style


def _atomic_replace_with_retry(
    temp_dst: Path,
    target_dst: Path,
    retries: int = 5,
    delay: float = 0.08,
) -> None:
    """Windows 파일 락 일시 충돌 시 지수/선형 백오프로 os.replace를 재시도합니다."""
    last_err: Optional[OSError] = None
    for attempt in range(max(1, retries)):
        try:
            os.replace(temp_dst, target_dst)
            return
        except PermissionError as err:
            last_err = err
            if attempt + 1 < retries:
                time.sleep(delay * (attempt + 1))
        except OSError as err:
            last_err = err
            if attempt + 1 < retries:
                time.sleep(delay * (attempt + 1))
    if last_err is not None:
        raise last_err


def censor_image(
    image: Union[Image.Image, Path, str],
    style: str = "white_silhouette",
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.16,
    pose_code: Optional[Union[str, int]] = None,
    enable_anchor_fallback: bool = False,
    roster: Optional[str] = None,
    is_nude: bool = False,
    is_otokonoko: Optional[bool] = None,
) -> Tuple[Image.Image, int]:
    """
    이미지 내 성기 및 결합 접점 부위를 다중 스케일(전체 + 체위별 줌인 ROI)로 정밀 감지하여 검열을 적용합니다.
    - 기본 스타일: 'white_silhouette' (매끈한 소프트 화이트 실루엣 - 젠잇 심의 규정 표준)
    - 기본 대상: 남성기+고환 ('penis'), 옵션으로 'pussy'/'all' 등 targets 인수를 존중
    - RGBA 입력 시 알파 채널을 무손실 보존합니다.
    - 반환값: (검열된 PIL 이미지, 감지된 부위 개수)
    """
    src_img = _load_pil_image(image)
    img_rgb, alpha_ch = _split_rgb_and_alpha(src_img)

    req_fn = facade_get("is_pose_censor_required", is_pose_censor_required)
    cat_fn = facade_get("get_pose_category", get_pose_category)
    skin_fn = facade_get("get_skin_mask", get_skin_mask)
    hybrid_fn = facade_get("_resolve_hybrid_targets_with_priors", _resolve_hybrid_targets_with_priors)
    anchor_fn = facade_get("get_pose_anchor_box", get_pose_anchor_box)
    render_fn = facade_get("_render_censored_style", _render_censored_style)

    # V3 오검열 원천 방어 가드: 비검열 대상(감정표현, 일상 스킨십, 착의 이벤트 등)은 즉시 원본 반환
    if pose_code is not None and not req_fn(
        pose_code=pose_code,
        is_nude=is_nude,
        file_path=image if isinstance(image, (str, Path)) else None,
        roster=roster,
        is_otokonoko=is_otokonoko,
    ):
        return _restore_alpha(img_rgb, alpha_ch), 0

    pose_cat = cat_fn(pose_code, roster=roster) if pose_code is not None else None
    skin_check_np = skin_fn(np.array(img_rgb))

    # P2 Semantic-Guided Hybrid Gating (YOLO 타이트 박스 + distanceTransform 코어 투영 + SAM 2.1)
    detected_boxes_with_labels, custom_seg_mask, fallback_boxes, yolo_prior_masks, context_boxes = hybrid_fn(
        img_rgb,
        targets=targets,
        min_confidence=min_confidence,
        pose_code=pose_code,
        roster=roster,
        skin_np=skin_check_np,
        pose_cat=pose_cat,
    )

    # 검열 미탐지 시 체위별 안전 앵커 폴백 점검 (기본 False: 신체 오검열 아티팩트 방지)
    if not detected_boxes_with_labels and pose_code is not None and pose_cat:
        if enable_anchor_fallback:
            anchor_box = anchor_fn(pose_code, img_rgb.width, img_rgb.height, roster=roster)
            if anchor_box:
                anchor_item = (anchor_box, "anchor", 1.0)
                detected_boxes_with_labels.append(anchor_item)
                if fallback_boxes is not None:
                    fallback_boxes.append(anchor_item)
                if yolo_prior_masks is not None:
                    yolo_prior_masks.append(None)
                if context_boxes is not None:
                    context_boxes.append(None)
                logger.info(
                    f"[Censor] 포즈 {pose_code}: 성기 미탐지 ➔ 안전 앵커({pose_cat}) 폴백 적용: {anchor_box}"
                )
        else:
            logger.warning(
                f"[WARN] [Censor] 포즈 {pose_code}: 성기 미탐지! 안전 앵커 영역({pose_cat}) 폴백 점검 대상입니다."
            )

    if not detected_boxes_with_labels:
        return _restore_alpha(img_rgb, alpha_ch), 0

    censored_rgb = render_fn(
        img_rgb,
        detected_boxes_with_labels,
        style=style,
        skin_np=skin_check_np,
        pose_cat=pose_cat,
        custom_seg_mask=custom_seg_mask,
        fallback_boxes=fallback_boxes,
        yolo_prior_masks=yolo_prior_masks,
        context_boxes=context_boxes,
    )
    return _restore_alpha(censored_rgb, alpha_ch), len(detected_boxes_with_labels)


def verify_and_heal_censor(
    censored_img: Image.Image,
    style: str = "white_silhouette",
    min_confidence: float = 0.32,
    targets: Sequence[str] = ("penis",),
) -> Tuple[Image.Image, bool]:
    """
    검열이 완료된 이미지를 대상으로 성기 검출기를 다시 돌려 잔여 노출 여부를 2차 검증합니다.
    과도한 2중 팽창을 방지하기 위해 신뢰도 임계값 0.32 이상의 명백한 잔여 노출에만 2차 보정을 발동합니다.
    반환값: (최종 안전 이미지, 추가 보정 발생 여부)
    """
    if not facade_get("HAS_IMGUTILS", HAS_IMGUTILS):
        return censored_img, False

    try:
        rgb_img, alpha_ch = _split_rgb_and_alpha(censored_img)
        target_labels = _normalize_censor_targets(targets)
        eff_min_conf = max(0.05, float(min_confidence))
        detect_fn = facade_get("detect_censors", detect_censors)
        render_fn = facade_get("_render_censored_style", _render_censored_style)
        results = detect_fn(rgb_img, conf_threshold=eff_min_conf)
        leaks = [
            ((int(b[0]), int(b[1]), int(b[2]), int(b[3])), str(label).strip().lower())
            for b, label, score in results
            if str(label).strip().lower() in target_labels and float(score) >= eff_min_conf
        ]
        if not leaks:
            return censored_img, False

        logger.warning(
            f"[Censor Gate] 2차 사후 검증에서 명백한 잔여 노출 {len(leaks)}건 감지! 즉시 2차 안전 보정을 수행합니다."
        )
        healed_rgb = render_fn(rgb_img, leaks, style=style)
        return _restore_alpha(healed_rgb, alpha_ch), True
    except Exception as e:
        logger.debug(f"[Censor Gate] 사후 검증 예외: {e}")
        return censored_img, False


def censor_file(
    src_path: Union[Path, str],
    dst_path: Optional[Union[Path, str]] = None,
    style: str = "white_silhouette",
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.16,
    quality: int = 95,
    pose_code: Optional[Union[str, int]] = None,
    enable_anchor_fallback: bool = False,
    backup_dir: Optional[Union[Path, str]] = None,
    roster: Optional[str] = None,
    is_nude: bool = False,
    is_otokonoko: Optional[bool] = None,
) -> Optional[Path]:
    """
    파일 경로를 입력받아 검열본을 생성하고 저장합니다.
    - dst_path 미지정 시 'stem_censored.webp'로 자동 저장.
    - backup_dir 지정 시 감지 성공 여부와 무관하게 원본 파일을 해당 폴더로 안전하게 선제 복사 백업.
    - 감지된 검열 대상이 없는 경우 검열본을 생성하지 않고 None 반환.
    """
    src = Path(src_path)
    if not src.exists():
        return None

    req_fn = facade_get("is_pose_censor_required", is_pose_censor_required)
    censor_img_fn = facade_get("censor_image", censor_image)
    replace_fn = facade_get("_atomic_replace_with_retry", _atomic_replace_with_retry)

    # V3 오검열 원천 방어 가드: 비검열 대역(01_emotions, 03_events, 착의 일상 등)은 100% 면제
    if not req_fn(
        pose_code=pose_code,
        is_nude=is_nude,
        file_path=src,
        roster=roster,
        is_otokonoko=is_otokonoko,
    ):
        return None

    if backup_dir:
        b_dir = Path(backup_dir)
        b_dir.mkdir(parents=True, exist_ok=True)
        b_path = b_dir / src.name
        if not b_path.exists():
            shutil.copy2(src, b_path)

    with Image.open(src) as opened:
        img = opened.copy()
    censored_img, count = censor_img_fn(
        img,
        style=style,
        targets=targets,
        min_confidence=min_confidence,
        pose_code=pose_code,
        enable_anchor_fallback=enable_anchor_fallback,
        roster=roster,
        is_nude=is_nude,
        is_otokonoko=is_otokonoko,
    )

    if count == 0:
        return None

    if dst_path is None:
        target_dst = src.with_name(f"{src.stem}_censored{src.suffix}")
    else:
        target_dst = Path(dst_path)

    target_dst.parent.mkdir(parents=True, exist_ok=True)
    ext_map = {".webp": "WEBP", ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
    save_fmt = ext_map.get(target_dst.suffix.lower(), "WEBP")
    if save_fmt == "JPEG" and censored_img.mode != "RGB":
        censored_img = censored_img.convert("RGB")
    temp_dst = target_dst.with_name(f".{target_dst.stem}_{uuid.uuid4().hex[:8]}.tmp{target_dst.suffix or '.webp'}")
    try:
        save_kwargs = {"quality": quality} if save_fmt in ("WEBP", "JPEG") else {"optimize": True}
        censored_img.save(temp_dst, save_fmt, **save_kwargs)
        replace_fn(temp_dst, target_dst)
    finally:
        if temp_dst.exists():
            temp_dst.unlink(missing_ok=True)
    return target_dst


def run_batch_censor(
    folder_path: Union[Path, str],
    style: str = "white_silhouette",
    overwrite: bool = True,
    recursive: bool = True,
    targets: Sequence[str] = ("penis",),
    min_confidence: float = 0.22,
    enable_anchor_fallback: bool = False,
) -> int:
    """폴더 내의 모든 일러스트 에셋을 스캔하여 일괄 검열을 수행합니다."""
    base_dir = Path(folder_path).resolve()
    if not base_dir.exists():
        logger.error(f"[오류] 대상 폴더를 찾을 수 없습니다: {base_dir}")
        return 0

    req_fn = facade_get("is_pose_censor_required", is_pose_censor_required)
    censor_file_fn = facade_get("censor_file", censor_file)

    extensions = ["*.webp", "*.png", "*.jpg", "*.jpeg"]
    image_files: List[Path] = []
    for ext in extensions:
        image_files.extend(base_dir.rglob(ext) if recursive else base_dir.glob(ext))

    target_files = [f for f in image_files if not f.stem.endswith("_censored")]
    processed_count = 0

    for file_path in target_files:
        # 1. _origin 폴더 내부 파일은 원본이므로 배치 검열 대상에서 원천 제외
        if "_origin" in file_path.parts:
            continue

        # 2. V3 정밀 정규식: 하이브리드 파일명(prefix_000_label.webp), 영숫자 코드(prefix_N01_label.webp) 및 코드 파일명 지원
        match = re.search(r"_([A-Za-z]\d{2,3}|\d{3})(?:_|\.)", file_path.name)
        pose_code: Union[str, int, None] = None
        if match:
            raw_code = match.group(1)
            pose_code = int(raw_code) if raw_code.isdigit() else raw_code.upper()

        # 3. V3 대역 체계 기반 검열 대상 여부 엄격 판정: 비검열 대역은 100% 바이패스
        if not req_fn(pose_code=pose_code, file_path=file_path):
            continue

        try:
            dst = file_path if overwrite else file_path.with_name(f"{file_path.stem}_censored{file_path.suffix}")
            saved = censor_file_fn(
                src_path=file_path,
                dst_path=dst,
                style=style,
                targets=targets,
                min_confidence=min_confidence,
                pose_code=pose_code,
                enable_anchor_fallback=enable_anchor_fallback,
            )
            if saved is not None:
                processed_count += 1
        except Exception as e:
            logger.warning(f"[Censor] 배치 검열 실패: {file_path.name} ({e})")

    return processed_count
