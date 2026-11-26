"""
plepa_engine.censor.policy
오토코노코 컨텍스트 추론, 포즈 검열 의무 판정(is_pose_censor_required), 체위 분류 및 안전 앵커 계산 모듈.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Optional, Tuple, Union

from ._runtime import facade_get
from .constants import (
    DAILY_EXPOSURE_CODES,
    EXEMPT_DAILY_EVENT_CODES,
    EXEMPT_EMOTION_CODES,
    NON_EXPOSURE_H_POSES,
    POSE_EXACT_ANCHORS,
    POSE_SAFE_ANCHORS,
    ROMANCE_NON_EXPOSURE_CODES,
    _get_cached_pose_db,
)


def _is_otokonoko_context(
    roster: Optional[str] = None,
    file_path: Union[str, Path, None] = None,
    code_str: Optional[str] = None,
) -> bool:
    """로스터/경로/포즈코드/캐릭터 설정으로부터 오토코노코 대상 여부를 추론합니다."""
    if code_str and code_str.isdigit() and (150 <= int(code_str) <= 209):
        return True
    r_low = (roster or "").strip().lower()
    if r_low == "oto" or "otokonoko" in r_low:
        return True
    if file_path is not None:
        p_norm = str(file_path).replace("\\", "/").lower()
        if "/oto/" in p_norm or "otokonoko" in p_norm:
            return True
        m_prefix = re.match(r"^([a-z0-9]+)_(?:[a-z]\d{2,3}|\d{3})_", Path(file_path).name.lower())
        if m_prefix and roster:
            try:
                from plepa_engine.services.character_service import default_character_service
                char_cfg = default_character_service.load_character(m_prefix.group(1), roster=roster)
                if char_cfg is not None:
                    g = (getattr(char_cfg, "gender", "") or "").strip().lower()
                    sdxl_p = (getattr(char_cfg, "sdxl_positive", "") or "").lower()
                    if g == "otokonoko" or "otokonoko" in sdxl_p:
                        return True
            except Exception:
                pass
    return False


def is_pose_censor_required(
    pose_code: Union[str, int, None] = None,
    pose: Any = None,
    is_nude: bool = False,
    file_path: Union[str, Path, None] = None,
    roster: Optional[str] = None,
    is_otokonoko: Optional[bool] = None,
) -> bool:
    """
    2대 서브폴더 구조(01_normal, 02_h_scenes) 및 포즈 코드·성별에 기반하여 해당 포즈/에셋이 검열 대상인지 엄격히 판정합니다:
    - 01_normal (000~059):
      * 000~019 (감정표현): 완전 착의 -> False (절대 면제)
      * 051~059 (일상 이벤트): 완전 착의 -> False (절대 면제)
      * 020~050 (범용 일상): DAILY_EXPOSURE_CODES({"037"})만 True, 단 오토코노코 누드 씬(030,038,039,043,044,045,049 등)은 본인 남성기 검열을 위해 True
    - 02_h_scenes (060~209+):
      * 060~079 (로맨스/구강): 060(딥키스)은 False, 061(알몸키스)은 오토코노코 누드 시 True, 062~079는 True
      * 080~139 (여성 H씬): 여성 단독/비노출 NON_EXPOSURE_H_POSES는 False, 나머지 True
      * 150~209 (오토코노코 H씬): 본인 남성기 노출 가능성을 포착하기 위해 면제 없이 전수 True
    """
    if file_path is not None:
        p_str = str(file_path).replace("\\", "/")
        if "/01_emotions/" in p_str or "/03_events/" in p_str:
            return False

    code_str = None
    if pose_code is not None:
        try:
            code_str = str(int(str(pose_code).strip())).zfill(3)
        except (ValueError, TypeError):
            code_str = str(pose_code).strip()
    elif pose is not None and hasattr(pose, "code"):
        try:
            code_str = str(int(str(pose.code).strip())).zfill(3)
        except (ValueError, TypeError):
            code_str = str(pose.code).strip()
    elif file_path is not None:
        m = re.search(r"_([A-Za-z]\d{2,3}|\d{3})(?:_|\.)", Path(file_path).name)
        if m:
            code_str = m.group(1).upper()

    if not code_str:
        return False

    if len(code_str) >= 2 and code_str[0] == "N" and code_str[1:].isdigit():
        return True

    if pose is None:
        try:
            pose = facade_get("_get_cached_pose_db", _get_cached_pose_db)(roster=roster).get(code_str)
        except Exception:
            pose = None

    eff_nude = bool(is_nude) or (
        pose is not None and str(getattr(pose, "required_outfit", "") or "").strip().lower() == "nude"
    )
    eff_otokonoko = (
        bool(is_otokonoko)
        if is_otokonoko is not None
        else facade_get("_is_otokonoko_context", _is_otokonoko_context)(
            roster=roster, file_path=file_path, code_str=code_str
        )
    )

    if code_str in facade_get("EXEMPT_EMOTION_CODES", EXEMPT_EMOTION_CODES):
        return False
    if code_str in facade_get("EXEMPT_DAILY_EVENT_CODES", EXEMPT_DAILY_EVENT_CODES):
        return False
    if code_str in facade_get("ROMANCE_NON_EXPOSURE_CODES", ROMANCE_NON_EXPOSURE_CODES):
        return bool(eff_otokonoko and eff_nude)
    if (not eff_otokonoko) and (code_str in facade_get("NON_EXPOSURE_H_POSES", NON_EXPOSURE_H_POSES)):
        return False

    try:
        c_int = int(code_str)
    except ValueError:
        return False

    if 20 <= c_int <= 50:
        return (code_str in facade_get("DAILY_EXPOSURE_CODES", DAILY_EXPOSURE_CODES)) or bool(is_nude) or bool(eff_otokonoko and eff_nude)
    if 60 <= c_int <= 79:
        return c_int in (62, 63) or (64 <= c_int <= 79) or eff_nude
    if (80 <= c_int <= 139) or (150 <= c_int <= 209):
        return True
    return False


def get_pose_category(pose_code: Union[str, int], roster: Optional[str] = None) -> Optional[str]:
    """
    포즈 DB의 프롬프트 및 라벨 메타데이터를 기반으로 체위 카테고리를 동적으로 판정합니다.
    포즈 DB가 수정되면 별도 하드코딩 수정 없이 자동으로 연동됩니다.
    """
    code_str = str(pose_code).zfill(3)
    if code_str in facade_get("NON_EXPOSURE_H_POSES", NON_EXPOSURE_H_POSES):
        return None

    try:
        code_int = int(code_str)
    except ValueError:
        return None

    if not ((64 <= code_int <= 79) or (80 <= code_int <= 139) or (150 <= code_int <= 209)):
        return None

    db = facade_get("_get_cached_pose_db", _get_cached_pose_db)(roster=roster)
    entry = db.get(code_str)
    if entry is not None:
        label = (entry.label or "").lower()
        prompt = (entry.prompt or "").lower()
        combined = f"{label} {prompt}"

        if any(kw in combined for kw in ("piledriver", "upside-down", "inverted position", "파일드라이버")):
            return "piledriver"
        if ("paizuri" in combined or "titfuck" in combined or "파이즈리" in label or "가슴사정" in label) and "fellatio" not in combined and "펠라" not in label:
            return "paizuri"
        if any(kw in combined for kw in ("fellatio", "blowjob", "deepthroat", "licking shaft", "licking penis", "펠라", "딥스로트", "남근핥기", "수유대딸", "가슴애무대딸")):
            return "fellatio"
        if any(kw in combined for kw in ("doggystyle", "sex from behind", "anal doggystyle", "후배위", "교배프레스", "뒷스마타", "빈강의실")):
            return "doggystyle"
        if any(kw in combined for kw in ("cowgirl", "straddling", "riding partner", "기승위", "보건실")):
            return "cowgirl"
        if any(kw in combined for kw in ("side by side sex", "측위", "들박")):
            return "side"
        if any(kw in combined for kw in ("standing sex", "입위", "들박")):
            return "standing"
        if any(kw in combined for kw in ("shower sex", "샤워", "욕실")):
            return "shower"
        if any(kw in combined for kw in ("cunnilingus", "fingering", "보지애무", "구강애무", "후방애무", "커닐링구스")):
            return "cunnilingus"
        if any(kw in combined for kw in ("handjob", "대딸", "핸드잡", "백허그대딸")):
            return "handjob"
        if any(kw in combined for kw in ("footjob", "풋잡")):
            return "footjob"
        if any(kw in combined for kw in ("spanking", "스팽킹")):
            return "spanking"
        if any(kw in combined for kw in ("missionary", "정상위", "대면좌위", "삽입조르기", "웨딩섹스", "알몸섹스절정", "m자개각", "밀착절정")):
            return "missionary"

    return "default_h"


def get_pose_anchor_box(
    pose_code: Union[str, int],
    img_width: int,
    img_height: int,
    roster: Optional[str] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """
    포즈 코드에 해당하는 안전 앵커 픽셀 바운딩 박스 (x1, y1, x2, y2)를 계산하여 반환합니다.
    1순위: N>=9 실측 벤치마크 기반 포즈 고유 앵커 (POSE_EXACT_ANCHORS)
    2순위: 체위 카테고리 범용 안전 앵커 (POSE_SAFE_ANCHORS)
    """
    code_key = str(pose_code).strip().zfill(3)
    exact_anchors = facade_get("POSE_EXACT_ANCHORS", POSE_EXACT_ANCHORS)
    safe_anchors = facade_get("POSE_SAFE_ANCHORS", POSE_SAFE_ANCHORS)

    if code_key in exact_anchors:
        x0_pct, y0_pct, x1_pct, y1_pct = exact_anchors[code_key]
        return (
            int(round(x0_pct * img_width)),
            int(round(y0_pct * img_height)),
            int(round(x1_pct * img_width)),
            int(round(y1_pct * img_height)),
        )

    cat = facade_get("get_pose_category", get_pose_category)(pose_code, roster=roster)
    if not cat or cat not in safe_anchors:
        return None
    x0_pct, y0_pct, x1_pct, y1_pct = safe_anchors[cat]
    return (
        int(round(x0_pct * img_width)),
        int(round(y0_pct * img_height)),
        int(round(x1_pct * img_width)),
        int(round(y1_pct * img_height)),
    )
