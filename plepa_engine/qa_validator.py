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

# ──────────────────────────────────────────────────────────────────────────────
# 1. CPU 스레드 자동 제한 (전체 스레드 수 - 2) & 2. 프로세스 우선순위 하향 (Below Normal)
# 딥러닝 감지기 추론 중 CPU 100% 점유로 인한 윈도우 UI/마우스/브라우저 버벅임을 원천 방지합니다.
# ──────────────────────────────────────────────────────────────────────────────
usable_threads = max(2, (os.cpu_count() or 4) - 2)
os.environ["OMP_NUM_THREADS"] = str(usable_threads)
os.environ["MKL_NUM_THREADS"] = str(usable_threads)

try:
    import torch
    torch.set_num_threads(usable_threads)
except Exception:
    pass

try:
    import psutil
    p = psutil.Process(os.getpid())
    p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass

from PIL import Image

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
    HAS_LAPLACIAN = False

try:
    from imgutils.metrics import anime_dbaesthetic
    HAS_AESTHETIC = True
except ImportError:
    HAS_AESTHETIC = False

logger = logging.getLogger(__name__)


def validate_generated_image(
    image: Union[Path, str, Image.Image],
    is_solo_scene: bool = True,
    is_two_person: bool = False,
    is_offscreen_partner: bool = False,
    is_kiss_scene: bool = False,
    section: Optional[str] = None,
    conf_threshold: float = 0.55,
    prompt: Optional[str] = None,
    check_blur: bool = False,
    min_blur_score: float = 60.0,
    check_aesthetic: bool = False,
    min_aesthetic_score: float = 4.0,
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
        "persons": 0,
        "heads": 0,
        "hands": 0,
        "faces": 0,
        "blur_score": 0.0,
    }

    if not HAS_IMGUTILS:
        # 감지기가 없으면 안전 통과
        return True, "", metrics

    try:
        if isinstance(image, (str, Path)):
            img = Image.open(str(image)).convert("RGB")
        else:
            img = image.convert("RGB")

        # 0. 선명도(Laplacian) 및 미적 점수(Aesthetic) 측정
        if HAS_LAPLACIAN:
            try:
                b_score = float(laplacian_score(img))
                metrics["blur_score"] = round(b_score, 2)
                if check_blur and b_score < min_blur_score:
                    reason = f"이미지 블러/초점 이탈 감지 (선명도: {b_score:.1f} < 임계치 {min_blur_score})"
                    return False, reason, metrics
            except Exception as e:
                logger.debug(f"[Auto-QC] 선명도 계산 예외: {e}")

        if check_aesthetic and HAS_AESTHETIC:
            try:
                a_score = float(anime_dbaesthetic(img))
                metrics["aesthetic_score"] = round(a_score, 2)
                if a_score < min_aesthetic_score:
                    reason = f"이미지 미적 완성도 미달 감지 (점수: {a_score:.2f} < 임계치 {min_aesthetic_score})"
                    return False, reason, metrics
            except Exception as e:
                logger.debug(f"[Auto-QC] 미적 점수 계산 예외: {e}")

        # 1. 인원수 검출 (Person Detection)
        raw_persons = detect_person(img)
        valid_persons = [p for p in raw_persons if p[2] >= conf_threshold]
        metrics["persons"] = len(valid_persons)

        # 2. 머리 검출 (Head Detection)
        raw_heads = detect_heads(img)
        valid_heads = [h for h in raw_heads if h[2] >= conf_threshold]
        metrics["heads"] = len(valid_heads)

        # 3. 손 검출 (Hand Detection: 신뢰도 0.60 이상)
        raw_hands = detect_hands(img)
        valid_hands = [h for h in raw_hands if h[2] >= 0.60]
        metrics["hands"] = len(valid_hands)

        # 4. 얼굴 검출 (Face Detection: 신뢰도 0.65 이상)
        raw_faces = detect_faces(img)
        valid_faces = [f for f in raw_faces if f[2] >= 0.65]
        metrics["faces"] = len(valid_faces)

        # ── 1인 단독 씬 판정 규칙 ──
        if is_solo_scene or (not is_two_person):
            if metrics["persons"] > 1 or metrics["heads"] > 1:
                reason = f"1인 씬 인원/머리 초과 감지 (인원: {metrics['persons']}명, 머리: {metrics['heads']}개)"
                return False, reason, metrics

            # 1인칭 손 개입 씬(쓰다듬기 047, 덮쳐짐 040 등 유저 손 개입) 및 스킨십/파이즈리 씬 허용치 완화
            p_text = (prompt or "").lower()
            multi_hand_keywords = (
                "headpat", "patting head", "hand on head", "hands pressed on mattress", "pov",
                "paizuri", "breast grab", "grabbing breast", "hands cupping", "handjob", "caressing", "massage", "groping", "touching"
            )
            is_multi_hand_scene = any(kw in p_text for kw in multi_hand_keywords)
            max_hands = 4 if is_multi_hand_scene else 2

            if metrics["hands"] > max_hands:
                reason = f"1인 씬 손 증식({max_hands + 1}개 이상) 감지 (손: {metrics['hands']}개)"
                return False, reason, metrics

        # ── 2인 상호작용 씬 판정 규칙 (오프스크린 제외) ──
        elif is_two_person and not is_offscreen_partner:
            p_text = (prompt or "").lower()
            # 상반신·바스트 밀착 클로즈업 씬에서는 모브/파트너 얼굴 및 머리 노출을 엄격 차단 (여주인공 1인 집중)
            is_close_up_focus = any(kw in p_text for kw in ("face focus", "bust shot", "chest focus", "upper body close-up", "tight bust", "intimate close-up", "close-up upper body"))
            is_kiss_scene = any(kw in p_text for kw in ("kiss", "french kiss", "deep kiss"))
            if is_close_up_focus and not is_kiss_scene:
                if metrics["faces"] > 1:
                    reason = f"상반신 밀착 씬 모브 얼굴 침범 감지 (얼굴: {metrics['faces']}개, 단독 1인 얼굴만 허용)"
                    return False, reason, metrics
                if metrics["heads"] > 1:
                    reason = f"상반신 밀착 씬 모브 머리 침범 감지 (머리: {metrics['heads']}개, 단독 1인 머리만 허용)"
                    return False, reason, metrics

                # ── 기하학적 화각 검증: 얼굴 높이 비율 측정 (전신 롱샷 이탈 방지) ──
                if valid_faces:
                    img_w, img_h = img.size
                    max_face_h = max((f[0][3] - f[0][1]) for f in valid_faces)
                    face_ratio = max_face_h / max(1, img_h)
                    metrics["face_height_ratio"] = round(face_ratio, 3)
                    if face_ratio < 0.08:
                        reason = f"상반신/클로즈업 씬 화각 드리프트(전신 롱샷 이탈) 감지 (얼굴 비율: {face_ratio * 100:.1f}% < 8.0%)"
                        return False, reason, metrics

            if metrics["persons"] > 2 or metrics["heads"] > 2:
                reason = f"2인 씬 제3자/모브 증식(3명 이상) 감지 (인원: {metrics['persons']}명, 머리: {metrics['heads']}개)"
                return False, reason, metrics

            if metrics["hands"] > 4:
                reason = f"2인 씬 손 증식(5개 이상) 감지 (손: {metrics['hands']}개)"
                return False, reason, metrics

            # 2인 씬에서 제3자의 얼굴까지 노출되는 것을 방지 (2명 씬이므로 faces <= 2 허용)
            max_faces = 2
            if metrics["faces"] > max_faces:
                reason = f"2인 씬 얼굴 과다 노출 감지 (얼굴: {metrics['faces']}개, 3인 이상 위반)"
                return False, reason, metrics

        return True, "", metrics

    except Exception as e:
        logger.warning(f"[Auto-QC 판정 예외] {e}")
        metrics["error"] = str(e)
        metrics["qc_bypassed"] = True
        return True, "", metrics
