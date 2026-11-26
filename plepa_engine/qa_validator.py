"""
plepa_engine.qa_validator
생성된 일러스트 이미지의 품질 및 구도 불량(인원수 오류, 머리 복제, 손 증식, 모브 얼굴 노출)을
전문 애니메이션 딥러닝 감지기(imgutils.detect)로 자동 판정하는 Auto-QC 모듈.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from PIL import Image

from plepa_engine.qa_checks import (
    _CLOSEUP_ASPECT_KEYWORDS,
    _HEADLESS_LOCAL_KEYWORDS,
    _HEADPAT_PHRASES,
    _MULTI_HAND_PHRASES,
    _NIGHT_LIGHTING_KEYWORDS,
    check_blur_aesthetic_and_burn,
    check_closeup_aspect_drift,
    check_face_count,
    check_hand_count,
    check_head_count,
    check_person_count,
    compute_color_burn_ratio,
    is_headless_closeup_prompt,
)

_RUNTIME_CONFIGURED = False


def configure_qa_runtime(force: bool = False, low_priority: bool = False) -> int:
    """
    딥러닝 감지기 추론 중 CPU 스레드 자동 제한 설정.
    모듈 import 시점이 아닌 최초 검증 시점에 지연 적용해 웹 GUI/테스트 프로세스 간섭을 방지합니다.
    OS 프로세스 우선순위 하향은 low_priority=True가 명시된 경우에만 적용합니다.
    """
    global _RUNTIME_CONFIGURED
    usable_threads = max(2, (os.cpu_count() or 4) - 2)
    if _RUNTIME_CONFIGURED and not force:
        return usable_threads

    os.environ["OMP_NUM_THREADS"] = str(usable_threads)
    os.environ["MKL_NUM_THREADS"] = str(usable_threads)

    try:
        import torch
        torch.set_num_threads(usable_threads)
    except Exception:
        pass

    if low_priority:
        try:
            import psutil
            p = psutil.Process(os.getpid())
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except Exception:
            pass

    _RUNTIME_CONFIGURED = True
    return usable_threads


try:
    from imgutils.detect import (
        detect_faces,
        detect_hands,
        detect_heads,
        detect_person,
    )
    HAS_IMGUTILS = True
except ImportError:
    HAS_IMGUTILS = False

try:
    from imgutils.metrics import laplacian_score
    HAS_LAPLACIAN = True
except ImportError:
    laplacian_score = None
    HAS_LAPLACIAN = False

try:
    from imgutils.metrics import anime_dbaesthetic
    HAS_AESTHETIC = True
except ImportError:
    anime_dbaesthetic = None
    HAS_AESTHETIC = False

logger = logging.getLogger(__name__)

_is_headless_closeup_prompt = is_headless_closeup_prompt
_compute_color_burn_ratio = compute_color_burn_ratio
_check_closeup_aspect_drift = check_closeup_aspect_drift


def _load_rgb_image(image: Union[Path, str, Image.Image]) -> Image.Image:
    if isinstance(image, (str, Path)):
        with Image.open(str(image)) as raw_im:
            return raw_im.convert("RGB")
    return image.convert("RGB")


def validate_generated_image(
    image: Union[Path, str, Image.Image],
    is_solo_scene: bool = True,
    is_two_person: bool = False,
    is_offscreen_partner: bool = False,
    is_kiss_scene: bool = False,
    allow_partner_head: bool = False,
    section: Optional[str] = None,
    conf_threshold: float = 0.55,
    prompt: Optional[str] = None,
    check_blur: bool = False,
    min_blur_score: float = 60.0,
    check_aesthetic: bool = False,
    min_aesthetic_score: float = 4.0,
    check_color_burn: bool = True,
    max_color_burn_ratio: float = 0.22,
    require_subject: Optional[bool] = None,
    **kwargs: Any,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    생성된 이미지를 정밀 분석하여 불량(Reject) 여부와 사유를 판정합니다.

    Returns:
        (is_valid, reject_reason, metrics)
        - is_valid: True(합격), False(불량 판정)
        - reject_reason: 불량 판정 사유 (합격 시 빈 문자열)
        - metrics: 감지된 인원/머리/손/얼굴 카운트 및 세부 정보
    """
    metrics: Dict[str, Any] = {
        "persons": 0, "heads": 0, "hands": 0, "faces": 0,
        "blur_score": 0.0, "color_burn_ratio": 0.0,
    }
    configure_qa_runtime()
    if not HAS_IMGUTILS:
        return True, "", metrics

    try:
        img = _load_rgb_image(image)
        p_text = (prompt or "").lower()
        eff_require_subject = bool(p_text.strip()) if require_subject is None else bool(require_subject)
        headless_allowed = _is_headless_closeup_prompt(p_text)

        quality_err = check_blur_aesthetic_and_burn(
            img=img, p_text=p_text, metrics=metrics,
            check_blur=check_blur, min_blur_score=min_blur_score,
            laplacian_fn=laplacian_score if HAS_LAPLACIAN else None,
            check_aesthetic=check_aesthetic, min_aesthetic_score=min_aesthetic_score,
            aesthetic_fn=anime_dbaesthetic if HAS_AESTHETIC else None,
            check_color_burn=check_color_burn, max_color_burn_ratio=max_color_burn_ratio,
            burn_ratio_fn=_compute_color_burn_ratio, logger=logger,
        )
        if quality_err:
            return False, quality_err, metrics

        is_solo = is_solo_scene or (not is_two_person)
        is_kiss = bool(is_kiss_scene) or any(kw in p_text for kw in ("kiss", "french kiss", "deep kiss"))
        is_nursing = any(kw in p_text for kw in ("nursing handjob", "breastfeeding", "sucking on nipple", "mouth on breast"))
        is_close_up_focus = any(
            kw in p_text
            for kw in ("face focus", "bust shot", "chest focus", "upper body close-up", "tight bust", "intimate close-up", "close-up upper body")
        )

        person_err = check_person_count(
            detect_person_fn=detect_person, img=img, conf_threshold=conf_threshold,
            is_solo=is_solo, eff_require_subject=eff_require_subject,
            headless_allowed=headless_allowed, metrics=metrics,
        )
        if person_err:
            return False, person_err, metrics

        head_err = check_head_count(
            detect_heads_fn=detect_heads, img=img, conf_threshold=conf_threshold,
            is_solo=is_solo, is_two_person=is_two_person, is_offscreen_partner=is_offscreen_partner,
            allow_partner_head=allow_partner_head, is_kiss=is_kiss, is_nursing=is_nursing,
            is_close_up_focus=is_close_up_focus, p_text=p_text, metrics=metrics,
        )
        if head_err:
            return False, head_err, metrics

        face_err, valid_faces = check_face_count(
            detect_faces_fn=detect_faces, img=img, is_solo=is_solo, is_two_person=is_two_person,
            is_offscreen_partner=is_offscreen_partner, is_kiss=is_kiss, is_nursing=is_nursing,
            is_close_up_focus=is_close_up_focus, eff_require_subject=eff_require_subject,
            headless_allowed=headless_allowed, p_text=p_text, metrics=metrics,
        )
        if face_err:
            return False, face_err, metrics

        if not headless_allowed:
            aspect_err = _check_closeup_aspect_drift(img.size[1], valid_faces, p_text, metrics)
            if aspect_err:
                return False, aspect_err, metrics

        hand_err = check_hand_count(
            detect_hands_fn=detect_hands, img=img, is_solo=is_solo, p_text=p_text, metrics=metrics,
        )
        if hand_err:
            return False, hand_err, metrics

        return True, "", metrics
    except Exception as e:
        logger.warning(f"[Auto-QC 판정 예외] {e}")
        metrics["error"] = str(e)
        metrics["qc_bypassed"] = True
        return True, "", metrics
