"""
plepa_engine.qa_checks
Auto-QC 이미지 품질(블러/미적/과포화) 및 4대 검출(인원/머리/얼굴/손) 세부 판정 규칙 헬퍼 모듈.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image

_HEADLESS_LOCAL_KEYWORDS = (
    "crotch focus", "ass focus", "foot focus", "feet focus",
    "pussy focus", "penis focus", "anal focus", "lower body",
    "pov crotch", "headless", "head out of frame", "cropped head",
    "eye focus", "mouth focus", "hand focus",
)

_CLOSEUP_ASPECT_KEYWORDS = (
    "face focus", "bust shot", "chest focus", "upper body",
    "tight bust", "intimate close-up", "portrait", "cowboy shot",
)

_HEADPAT_PHRASES = (
    "headpat", "patting head", "patting her head", "stroking hair", "hand on head",
)

_MULTI_HAND_PHRASES = (
    "hands pressed on mattress", "pov hands", "paizuri", "breast grab",
    "grabbing", "hands cupping", "handjob", "caressing",
    "massage", "groping", "two hands",
)

_NIGHT_LIGHTING_KEYWORDS = (
    "night", "evening", "dark", "starry", "neon", "moonlight", "nighttime", "city lights",
)

_HEAD_CONTACT_KEYWORDS = (
    "back of male head", "back of dark-haired male head", "head between thighs",
    "burying face", "face buried", "head buried", "buried in her chest",
    "princess carry", "carried in dark-haired male", "carried in male partner",
    "back hug", "hugging partner", "hug from behind", "grabbing from behind",
    "washing partner", "spooning position", "intimate embrace",
    "dark-haired male mob",
)


def is_headless_closeup_prompt(p_text: str) -> bool:
    """하반신/국소 클로즈업 등 머리가 프레임 밖에 있을 수 있는 프롬프트인지 판별합니다."""
    if any(kw in p_text for kw in _HEADLESS_LOCAL_KEYWORDS):
        return True
    if "close-up" in p_text and not any(
        kw in p_text for kw in ("face focus", "upper body", "bust shot", "portrait", "cowboy shot")
    ):
        return True
    return False


def compute_color_burn_ratio(img: Image.Image) -> float:
    """
    256x256 다운샘플링 기반으로 극단적 고채도 네온 과포화 및 RGB 채널 클리핑(Color Burn) 비율을 측정합니다.
    순백 배경(S=0)과 어두운 밤 배경(low V / low delta)은 오탐에서 배제합니다.
    """
    small = img.resize((256, 256), Image.Resampling.BILINEAR)
    try:
        import numpy as np

        arr = np.asarray(small, dtype=np.uint8)
        max_c = arr.max(axis=2)
        min_c = arr.min(axis=2)
        delta = max_c.astype(np.int16) - min_c.astype(np.int16)

        sat = np.zeros_like(max_c, dtype=np.float32)
        nz = max_c > 0
        sat[nz] = delta[nz].astype(np.float32) / max_c[nz].astype(np.float32)
        val = max_c.astype(np.float32) / 255.0

        # 극단적 네온 과포화(S > 0.94 & V >= 0.35) 또는 유채색 채널 극단 클리핑(>=254 & <=1 동시 존재)
        neon_mask = (sat > 0.94) & (val >= 0.35)
        clip_mask = (arr.max(axis=2) >= 254) & (arr.min(axis=2) <= 1) & (delta >= 200)
        return float((neon_mask | clip_mask).mean())
    except ImportError:
        pixels = list(small.getdata())
        if not pixels:
            return 0.0
        burned = 0
        for r, g, b in pixels:
            mx = max(r, g, b)
            mn = min(r, g, b)
            d = mx - mn
            sat = (d / mx) if mx > 0 else 0.0
            val = mx / 255.0
            if (sat > 0.94 and val >= 0.35) or (mx >= 254 and mn <= 1 and d >= 200):
                burned += 1
        return burned / len(pixels)


def check_closeup_aspect_drift(
    img_h: int,
    valid_faces: list,
    p_text: str,
    metrics: Dict[str, Any],
    min_face_ratio: float = 0.08,
) -> Optional[str]:
    """1인/2인 상반신·포트레이트 씬에서 전신 롱샷으로 이탈하는 화각 드리프트를 검사합니다."""
    if not valid_faces or not any(kw in p_text for kw in _CLOSEUP_ASPECT_KEYWORDS):
        return None
    max_face_h = max((f[0][3] - f[0][1]) for f in valid_faces)
    face_ratio = max_face_h / max(1, img_h)
    metrics["face_height_ratio"] = round(face_ratio, 3)
    if face_ratio < min_face_ratio:
        return (
            f"상반신/클로즈업 씬 화각 드리프트(전신 롱샷 이탈) 감지 "
            f"(얼굴 비율: {face_ratio * 100:.1f}% < {min_face_ratio * 100:.1f}%)"
        )
    return None


def check_blur_aesthetic_and_burn(
    *,
    img: Image.Image,
    p_text: str,
    metrics: Dict[str, Any],
    check_blur: bool,
    min_blur_score: float,
    laplacian_fn: Optional[Callable[..., Any]],
    check_aesthetic: bool,
    min_aesthetic_score: float,
    aesthetic_fn: Optional[Callable[..., Any]],
    check_color_burn: bool,
    max_color_burn_ratio: float,
    burn_ratio_fn: Callable[[Image.Image], float],
    logger: logging.Logger,
) -> Optional[str]:
    """선명도(Laplacian), 미적 점수(Aesthetic), 색감 과포화(Color Burn) 선행 Short-Circuit 검사를 수행합니다."""
    if check_blur and laplacian_fn is not None:
        try:
            b_score = float(laplacian_fn(img))
            metrics["blur_score"] = round(b_score, 2)
            if b_score < min_blur_score:
                return f"이미지 블러/초점 이탈 감지 (선명도: {b_score:.1f} < 임계치 {min_blur_score})"
        except Exception as e:
            logger.debug(f"[Auto-QC] 선명도 계산 예외: {e}")

    if check_aesthetic and aesthetic_fn is not None:
        try:
            a_score = float(aesthetic_fn(img))
            metrics["aesthetic_score"] = round(a_score, 2)
            if a_score < min_aesthetic_score:
                return f"이미지 미적 완성도 미달 감지 (점수: {a_score:.2f} < 임계치 {min_aesthetic_score})"
        except Exception as e:
            logger.debug(f"[Auto-QC] 미적 점수 계산 예외: {e}")

    if check_color_burn:
        burn_ratio = burn_ratio_fn(img)
        metrics["color_burn_ratio"] = round(burn_ratio, 4)
        is_night_scene = any(kw in p_text for kw in _NIGHT_LIGHTING_KEYWORDS)
        eff_max_burn = 0.35 if (is_night_scene and max_color_burn_ratio <= 0.22) else max_color_burn_ratio
        if burn_ratio >= eff_max_burn:
            return (
                f"색감 과포화(Color Burn) 감지 "
                f"(과포화/클리핑 비율: {burn_ratio * 100:.1f}% >= {eff_max_burn * 100:.1f}%)"
            )
    return None


def check_person_count(
    *,
    detect_person_fn: Callable[..., list],
    img: Image.Image,
    conf_threshold: float,
    is_solo: bool,
    eff_require_subject: bool,
    headless_allowed: bool,
    metrics: Dict[str, Any],
) -> Optional[str]:
    """1단계: 인원수 초과 및 피사체 증발 여부를 판정합니다."""
    raw_persons = detect_person_fn(img)
    valid_persons = [p for p in raw_persons if p[2] >= conf_threshold]
    metrics["persons"] = len(valid_persons)

    if is_solo and metrics["persons"] > 1:
        return f"1인 씬 인원 초과 감지 (인원: {metrics['persons']}명)"
    if not is_solo and metrics["persons"] > 2:
        return f"2인 씬 제3자/모브 증식(3명 이상) 감지 (인원: {metrics['persons']}명)"
    if eff_require_subject and not headless_allowed and metrics["persons"] == 0:
        return "피사체 증발/구도 붕괴 감지 (인원 미검출)"
    return None


def check_head_count(
    *,
    detect_heads_fn: Callable[..., list],
    img: Image.Image,
    conf_threshold: float,
    is_solo: bool,
    is_two_person: bool,
    is_offscreen_partner: bool,
    allow_partner_head: bool,
    is_kiss: bool,
    is_nursing: bool,
    is_close_up_focus: bool,
    p_text: str,
    metrics: Dict[str, Any],
) -> Optional[str]:
    """2단계: 머리 검출 수 및 오프스크린/밀착 구도 침범 여부를 판정합니다."""
    raw_heads = detect_heads_fn(img)
    valid_heads = [h for h in raw_heads if h[2] >= conf_threshold]
    metrics["heads"] = len(valid_heads)

    is_head_contact_allowed = (
        bool(allow_partner_head)
        or is_kiss
        or is_nursing
        or any(kw in p_text for kw in _HEAD_CONTACT_KEYWORDS)
    )

    if is_solo:
        if metrics["heads"] > 1:
            return f"1인 씬 머리 초과 감지 (인원: {metrics['persons']}명, 머리: {metrics['heads']}개)"
    elif is_two_person and is_offscreen_partner:
        max_offscreen_heads = 2 if is_head_contact_allowed else 1
        if metrics["heads"] > max_offscreen_heads:
            return f"오프스크린 파트너 씬 머리 초과 감지 (머리: {metrics['heads']}개, 최대 {max_offscreen_heads}개 허용)"
    else:
        if is_close_up_focus and not is_kiss and not is_nursing and metrics["heads"] > 1:
            return f"상반신 밀착 씬 모브 머리 침범 감지 (머리: {metrics['heads']}개, 단독 1인 머리만 허용)"
        if metrics["heads"] > 2:
            return f"2인 씬 머리 초과(3개 이상) 감지 (인원: {metrics['persons']}명, 머리: {metrics['heads']}개)"
    return None


def check_face_count(
    *,
    detect_faces_fn: Callable[..., list],
    img: Image.Image,
    is_solo: bool,
    is_two_person: bool,
    is_offscreen_partner: bool,
    is_kiss: bool,
    is_nursing: bool,
    is_close_up_focus: bool,
    eff_require_subject: bool,
    headless_allowed: bool,
    p_text: str,
    metrics: Dict[str, Any],
    allow_partner_shadow_face: bool = False,
) -> Tuple[Optional[str], list]:
    """3단계: 얼굴 검출 수 및 faceless·모브 얼굴 노출 위반 여부를 판정합니다."""
    raw_faces = detect_faces_fn(img)
    valid_faces = [f for f in raw_faces if f[2] >= 0.65]
    metrics["faces"] = len(valid_faces)

    if eff_require_subject and not headless_allowed and metrics["heads"] == 0 and metrics["faces"] == 0:
        return "피사체 증발/구도 붕괴 감지 (머리·얼굴 동시 미검출)", valid_faces

    if is_solo:
        if metrics["faces"] > 1:
            return f"1인 씬 얼굴 초과 감지 (얼굴: {metrics['faces']}개)", valid_faces
    elif is_two_person and is_offscreen_partner:
        max_offscreen_faces = 2 if (is_kiss or is_nursing or allow_partner_shadow_face) else 1
        if metrics["faces"] > max_offscreen_faces:
            return (
                f"오프스크린 파트너 씬 모브 얼굴 노출 감지 (얼굴: {metrics['faces']}개, 단독 {max_offscreen_faces}인 얼굴만 허용)",
                valid_faces,
            )
    elif not is_solo:
        if is_close_up_focus and not is_kiss and not is_nursing and metrics["faces"] > 1:
            return f"상반신 밀착 씬 모브 얼굴 침범 감지 (얼굴: {metrics['faces']}개, 단독 1인 얼굴만 허용)", valid_faces

        is_faceless_prompt = ("faceless male" in p_text) or ("faceless" in p_text)
        max_faces = 1 if (is_faceless_prompt and not is_kiss) else 2
        if metrics["faces"] > max_faces:
            if max_faces == 1:
                return f"2인 씬 모브/파트너 얼굴 노출(faceless 위반) 감지 (얼굴: {metrics['faces']}개)", valid_faces
            return f"2인 씬 얼굴 과다 노출 감지 (얼굴: {metrics['faces']}개, 3인 이상 위반)", valid_faces
    return None, valid_faces


def check_hand_count(
    *,
    detect_hands_fn: Callable[..., list],
    img: Image.Image,
    is_solo: bool,
    p_text: str,
    metrics: Dict[str, Any],
) -> Optional[str]:
    """4단계: 손 검출 수(신뢰도 0.60 이상) 기반 기형 손 증식 여부를 판정합니다."""
    raw_hands = detect_hands_fn(img)
    valid_hands = [h for h in raw_hands if h[2] >= 0.60]
    metrics["hands"] = len(valid_hands)

    if is_solo:
        is_headpat_scene = any(kw in p_text for kw in _HEADPAT_PHRASES)
        is_multi_hand_scene = any(kw in p_text for kw in _MULTI_HAND_PHRASES)
        if is_multi_hand_scene:
            max_hands = 4
        elif is_headpat_scene:
            max_hands = 3
        else:
            max_hands = 2
        if metrics["hands"] > max_hands:
            return f"1인 씬 손 증식({max_hands + 1}개 이상) 감지 (손: {metrics['hands']}개)"
    elif metrics["hands"] > 4:
        return f"2인 씬 손 증식(5개 이상) 감지 (손: {metrics['hands']}개)"
    return None
