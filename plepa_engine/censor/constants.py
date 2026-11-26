"""
plepa_engine.censor.constants
검열 안전 앵커 좌표, 면제 코드 대역, 비노출 H-씬 집합 및 로스터 포즈 DB 캐시 모듈.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Sequence

from ._runtime import facade_get

# 체위별 안전 앵커 바운딩 박스 (정규화 좌표: [x0, y0, x1, y1])
POSE_SAFE_ANCHORS = {
    "missionary":  [0.34, 0.58, 0.66, 0.84],   # 정상위/배위: 하단 중앙 영역
    "doggystyle":  [0.40, 0.60, 0.60, 0.74],   # 후배위: 결합 중심 슬림 앵커
    "cowgirl":     [0.34, 0.60, 0.66, 0.86],   # 기승위: 하단 기저부
    "fellatio":    [0.36, 0.38, 0.64, 0.60],   # 상반신·얼굴 밀착 구강: 중상단 입/접촉부
    "paizuri":     [0.34, 0.40, 0.66, 0.68],   # 상반신·바스트 밀착: 가슴 중심 결합부
    "piledriver":  [0.36, 0.08, 0.64, 0.38],   # 역전 파일드라이버: 상단 중앙 결합부
    "side":        [0.35, 0.55, 0.65, 0.82],   # 측와위: 측면 교차부
    "standing":    [0.34, 0.44, 0.66, 0.72],   # 입위(서서 하는 체위): 중앙 허리~골반 높이
    "shower":      [0.34, 0.48, 0.66, 0.76],   # 샤워실/수중 체위: 중앙 결합부
    "cunnilingus": [0.45, 0.65, 0.55, 0.75],   # 애무: 미사용 (검열 면제)
    "handjob":     [0.34, 0.48, 0.66, 0.74],   # 대딸/핸드잡: 중하단 손 위치
    "footjob":     [0.34, 0.52, 0.66, 0.80],   # 풋잡: 하단 발 위치
    "spanking":    [0.34, 0.48, 0.66, 0.78],   # 스팽킹: 둔부/엉덩이 중심
    "default_h":   [0.34, 0.56, 0.66, 0.84],   # 기본 성인 결합 씬
}

# 다중 표본(N>=9) 실측 벤치마크 기반 포즈별 고유 정밀 앵커 좌표 (x0, y0, x1, y1)
# 범용 카테고리 앵커보다 최우선 적용되어 미탐지 폴백 시에도 정확한 실제 결합 부위에 마스킹 안착
POSE_EXACT_ANCHORS: Dict[str, List[float]] = {
    # 088 후배위약: 좌측 측면 배면 결합 (N=9 실측 평균 X=0.14, Y=0.73 기반 정밀 바운딩)
    "067": [0.10, 0.20, 0.40, 0.65],  # 067 딥스로트: 좌측 구강 결합 (N=9 실측 X=0.25, Y=0.35)
    "072": [0.35, 0.55, 0.65, 0.90],  # 072 파이즈리: 정면 바스트 중앙 결합 (N=9 실측 X=0.50, Y=0.68)
    "088": [0.04, 0.66, 0.26, 0.88],
    "116": [0.38, 0.10, 0.66, 0.45],  # 116 파일드라이버: 상단 반전 결합 (N=9 실측 X=0.53, Y=0.25)
    "186": [0.38, 0.10, 0.66, 0.45],  # 186 오토코노코 파일드라이버 (+70)
    "158": [0.04, 0.66, 0.26, 0.88],  # 오토코노코 대칭 (+70)
}

# 100% 완전 착의 감정 표현 대역 (000~019)
EXEMPT_EMOTION_CODES = frozenset(f"{i:03d}" for i in range(0, 20))

# 100% 완전 착의 일상 이벤트 대역 (051~059)
EXEMPT_DAILY_EVENT_CODES = frozenset(f"{i:03d}" for i in range(51, 60))

# 일상 포즈(020~050) 중 남성 관련 노출 씬 (사용자 정책: 여성 단독 노출 씬 030,038,039,044,045는 검열 면제)
DAILY_EXPOSURE_CODES = frozenset({
    "037",  # 붓카케 (파트너 사정 흔적)
})

# 로맨스(060~079) 중 비노출/착의 씬 (성기 노출 없음)
ROMANCE_NON_EXPOSURE_CODES = frozenset({
    "060",  # 딥키스 (완전 착의 밀착 키스)
    "061",  # 알몸키스 (상체 밀착 키스)
})

# H씬(080~139, 150~209)은 모델 생성 편차로 인한 우발적 노출까지 100% 포착하기 위해 면제 없이 전수 YOLO 스캔 수행
# 남성 결합 부위가 일체 등장하지 않는 포즈 대역 (애무, 커닐링구스, 착의 전희, 사후 여운 등)
# 사용자 정책: 여성 신체 부위는 검열 대상에서 완전 제외하므로, 남성 결합 대상이 없는 포즈는 검열 원천 면제
NON_EXPOSURE_H_POSES: frozenset[str] = frozenset({
    "081",  # 대면좌위 (파트너 등 뒤 뷰 -> 결합 부위 가려짐/비노출)
    "082",  # 대면좌위절정 (클로즈업 비노출)
    "083",  # 누워절정여운 (여성 솔로 사후 여운 -> 남성 없음)
    "084",  # 엎드려절정여운 (여성 솔로 사후 여운 -> 남성 없음)
    "101",  # 펠라사후 (사후 여운)
    "109",  # 커닐링구스 (여성 대상 구강 애무 -> 남성 결합 부위 없음)
    "110",  # 보지애무약 (손가락 애무 -> 남성 결합 부위 없음)
    "111",  # 보지애무강 (손가락 애무 -> 남성 결합 부위 없음)
    "112",  # 착의섹스 전 (치마 걷기/전희 -> 결합 전 비노출)
    "114",  # 착의섹스 후 (사후 여운)
    "115",  # 필로우토크 (사후 대화)
    "123",  # 전라유혹 (여성 단독 포즈)
    # 주의: 오토코노코 대칭(151~193)은 주 캐릭터 본인에게 남성기가 존재하므로 면제하지 않고 전수 스캔함
})

_POSE_DB_CACHE: Dict[str, dict] = {}
_POSE_DB_CACHE_LOCK = threading.Lock()


def _normalize_censor_targets(targets: Sequence[str] = ("penis",)) -> set[str]:
    """검열 대상 라벨 시퀀스를 정규화된 소문자 집합으로 변환합니다 ('all' 지원)."""
    raw = {str(t).strip().lower() for t in (targets or ()) if str(t).strip()}
    if not raw:
        return {"penis"}
    if "all" in raw:
        return {"penis", "pussy"}
    return raw


def _get_cached_pose_db(roster: Optional[str] = None) -> dict:
    """로스터별 포즈 DB를 스레드 안전하게 지연 로드하여 체위 카테고리 동적 추론에 활용합니다."""
    from plepa_engine.config import DEFAULT_ROSTER

    eff_roster = (roster or DEFAULT_ROSTER).strip() or DEFAULT_ROSTER
    cache_lock = facade_get("_POSE_DB_CACHE_LOCK", _POSE_DB_CACHE_LOCK)
    cache_dict = facade_get("_POSE_DB_CACHE", _POSE_DB_CACHE)
    with cache_lock:
        cached = cache_dict.get(eff_roster)
    if cached is not None:
        return cached

    try:
        from plepa_engine.services.pose_service import default_pose_service
        loaded = default_pose_service.load_pose_db(engine="sdxl", roster=eff_roster)
    except Exception:
        loaded = {}

    with cache_lock:
        cache_dict.setdefault(eff_roster, loaded)
        return cache_dict[eff_roster]
