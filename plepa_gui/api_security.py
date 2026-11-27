"""
plepa_gui.api_security
선택적 토큰 인증, Origin/Referer 검증 및 프로젝트 경로 탐색 방지 보안 유틸리티.
"""

from __future__ import annotations

import hmac
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from plepa_engine.config import PROJECTS_DIR

_SAFE_ROSTER_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_COOKIE_NAME = "plepa_token"


def get_optional_mobile_token() -> str:
    """환경변수 PLEPA_MOBILE_TOKEN 반환 (미설정 시 빈 문자열 — 로컬 무인증 호환)."""
    return os.environ.get("PLEPA_MOBILE_TOKEN", "").strip()


def verify_optional_request_auth(request: Request, *, check_origin: bool = False) -> None:
    """
    PLEPA_MOBILE_TOKEN이 설정된 경우에만 토큰 및 Origin을 검증합니다.
    미설정(로컬 PC 단독 구동·오프라인 단위 테스트) 시에는 즉시 통과합니다.
    """
    expected = get_optional_mobile_token()
    if not expected:
        return

    token = request.headers.get("X-Plepa-Token", "").strip()
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    if not token:
        token = (request.cookies.get(_COOKIE_NAME) or "").strip()
    if not token:
        token = (request.query_params.get("token") or "").strip()

    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="유효하지 않은 모바일 인증 토큰입니다.")

    if check_origin:
        host = (request.headers.get("Host") or "").strip().lower()
        origin = (request.headers.get("Origin") or "").strip()
        if origin:
            origin_host = urlparse(origin).netloc.lower()
            if not host or origin_host != host:
                raise HTTPException(status_code=403, detail="허용되지 않은 Origin 요청입니다.")
        else:
            referer = (request.headers.get("Referer") or "").strip()
            if referer:
                ref_host = urlparse(referer).netloc.lower()
                if not host or ref_host != host:
                    raise HTTPException(status_code=403, detail="허용되지 않은 Referer 요청입니다.")


async def require_optional_api_auth(request: Request) -> None:
    """FastAPI router dependency: 상태 변경(POST 등) 요청 시 Origin까지 검증합니다."""
    is_mutating = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
    verify_optional_request_auth(request, check_origin=is_mutating)


def validate_roster_name(roster: str) -> str:
    """로스터 이름 허용 문자 집합을 검증해 경로 인젝션을 차단합니다."""
    clean = (roster or "").strip()
    if not clean or not _SAFE_ROSTER_PATTERN.match(clean):
        raise HTTPException(status_code=400, detail=f"유효하지 않은 로스터 이름입니다: {roster!r}")
    return clean


def resolve_safe_project_file(rel_path: str, projects_dir: Optional[Path] = None) -> Path:
    """PROJECTS_DIR 하위 상대 경로만 허용하며 경로 탈출 시 400을 발생시킵니다."""
    projects_root = (projects_dir or PROJECTS_DIR).resolve()
    clean_rel = (rel_path or "").strip().lstrip("/\\")
    if not clean_rel:
        raise HTTPException(status_code=400, detail="유효하지 않은 경로입니다.")
    candidate = (projects_root / clean_rel).resolve()
    try:
        is_inside = candidate.is_relative_to(projects_root)
    except AttributeError:
        is_inside = projects_root in candidate.parents
    if not is_inside or candidate == projects_root:
        raise HTTPException(status_code=400, detail="허용되지 않은 경로 접근입니다.")
    return candidate


def ensure_not_origin_target(target_path: Path) -> None:
    """무검열 원본(_origin) 경로 직접 덮어쓰기를 403으로 차단합니다."""
    if any(part == "_origin" or part.endswith("_origin") for part in target_path.parts):
        raise HTTPException(status_code=403, detail="무검열 원본(_origin) 경로는 직접 덮어쓸 수 없습니다.")


def find_project_origin_for_asset(target_path: Path, projects_dir: Optional[Path] = None) -> Optional[Path]:
    """2-Track(_origin) 구조에서 본체 에셋에 대응하는 무검열 원본 파일을 탐색합니다."""
    projects_root = (projects_dir or PROJECTS_DIR).resolve()
    resolved_target = target_path.resolve()
    parts = resolved_target.parts
    if "assets" not in parts:
        return None

    assets_idx = parts.index("assets")
    if assets_idx + 1 >= len(parts):
        return None

    assets_base = Path(*parts[: assets_idx + 1])
    sub_parts = parts[assets_idx + 1 :]
    char_code = sub_parts[0]
    rel_in_char = Path(*sub_parts[1:]) if len(sub_parts) > 1 else Path(resolved_target.name)

    for cand in (
        (assets_base / f"{char_code}_origin" / rel_in_char).resolve(),
        (assets_base / char_code / "_origin" / rel_in_char).resolve(),
        (assets_base / f"{char_code}_origin" / resolved_target.name).resolve(),
    ):
        if cand.is_relative_to(projects_root) and cand.is_file():
            return cand
    return None


def extract_pose_code_from_name(filename: str) -> str:
    """파일명에서 3자리 숫자 또는 영숫자 포즈 코드를 추출합니다."""
    m = re.search(r"_([A-Za-z]\d{2,3}|\d{3})(?:_|\.)", filename or "")
    if not m:
        return ""
    raw = m.group(1)
    return raw.zfill(3) if raw.isdigit() else raw.upper()
