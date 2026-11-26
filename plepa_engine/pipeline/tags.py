"""
plepa_engine.pipeline.tags
SDXL 태그 정규화, 충돌 검출/제거, 괄호 보존 토큰 제거 및 캐릭터 표정 조화 유틸리티.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from plepa_engine.pipeline.constants import (
    _BRACKET_TABLE,
    _PROTECTED_CONTROL_TAGS,
    _WEIGHT_SUFFIX_PATTERN,
)


def _strip_tags_preserving_parens(text: str, inner_pattern: str) -> str:
    """중첩/가중치 괄호 균형을 훼손하지 않고 일치하는 태그 토큰만 안전하게 제거합니다."""
    cleaned = re.sub(inner_pattern, "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"(:\d+(?:\.\d+)?)\s*,\s*:\d+(?:\.\d+)?", r"\1", cleaned)
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = re.sub(r"\(\s*,\s*", "(", cleaned)
        cleaned = re.sub(r",\s*(?=[:\)])", "", cleaned)
        cleaned = re.sub(r"\(\s*(?::[0-9\.]+)?\s*\)", "", cleaned)
    cleaned = re.sub(r"(,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"\bBREAK\s*,\s*", "BREAK ", cleaned)
    cleaned = re.sub(r",\s*\bBREAK\b", " BREAK", cleaned)
    return cleaned.strip(" ,")


def harmonize_character_expression(char_part: str, pose_tag: str) -> str:
    """포즈에 구체적인 표정/감정 태그가 있을 경우, 캐릭터 기본 정의의 상반된 무표정/기본 표정 태그를 억제하여 표정 충돌을 방지한다."""
    has_explicit_pose_expression = any(
        kw in pose_tag.lower()
        for kw in (
            "smile", "smiling", "laugh", "grin", "happy", "blush", "flushed",
            "crying", "tears", "ecstasy", "screaming", "angry", "moaning",
            "pleasure", "winking", "embarrassed", "pout", "flustered", "intoxicated",
            "shock", "surprised", "panic", "comic", "wide eyes", "constricted pupils", "blank stare",
        )
    )
    if has_explicit_pose_expression:
        char_part = re.sub(
            r",?\s*\b(cool calm expression|stoic expression|calm expression|expressionless|emotionless|indifferent gaze|neutral expression)\b",
            "",
            char_part,
            flags=re.IGNORECASE,
        )
    return char_part


def normalize_tag(raw: str) -> str:
    """
    비교 및 매칭을 위해 태그를 정규화합니다.
    괄호 및 가중치 표기를 제거하고 소문자 및 공백을 정규화합니다.
    """
    tag = raw.strip().lower().translate(_BRACKET_TABLE)
    tag = _WEIGHT_SUFFIX_PATTERN.sub("", tag)
    return " ".join(tag.split())


def split_tags(text: str) -> List[str]:
    """쉼표 및 BREAK 구분자로 텍스트를 분리하여 정규화된 태그 리스트를 반환합니다."""
    cleaned = re.sub(r"\bBREAK\b", ",", text)
    return [normalize_tag(tag) for tag in cleaned.split(",") if normalize_tag(tag)]


def find_tag_conflicts(positive: str, negative: str) -> List[str]:
    """긍정과 부정 프롬프트에 동시에 존재하는 정규화 태그 목록을 반환합니다."""
    pos_tags = set(split_tags(positive))
    neg_tags = set(split_tags(negative))
    return sorted(pos_tags & neg_tags)


def remove_conflicting_tags_from_negative(positive: str, negative: str) -> Tuple[str, List[str]]:
    """
    긍정과 부정 사이에 충돌하는 태그를 감지하고, 네거티브 프롬프트에서 해당 태그를 안전하게 제거합니다.
    다중 태그 괄호 그룹(((tag1, tag2:1.5))) 내부 조각도 괄호 쌍을 완벽하게 보존하면서 충돌 태그를 정확히 정제합니다.
    구도/인원수 제어용 보호 태그(_PROTECTED_CONTROL_TAGS)는 가드 무력화를 막기 위해 보존합니다.
    """
    conflicts = [t for t in find_tag_conflicts(positive, negative) if t not in _PROTECTED_CONTROL_TAGS]
    if not conflicts:
        return negative, []

    conflict_set = set(conflicts)
    neg_chunks = [c.strip() for c in negative.split(",") if c.strip()]
    kept_chunks: List[str] = []
    removed_tags: List[str] = []
    pending_open_parens = ""

    for chunk in neg_chunks:
        norm = normalize_tag(chunk)
        open_parens = chunk.count("(")
        close_parens = chunk.count(")")

        if norm in conflict_set:
            removed_tags.append(norm)
            if open_parens > close_parens:
                pending_open_parens += "(" * (open_parens - close_parens)
            elif close_parens > open_parens:
                needed_close = ")" * (close_parens - open_parens)
                if pending_open_parens:
                    cancel_count = min(len(pending_open_parens), len(needed_close))
                    pending_open_parens = pending_open_parens[:-cancel_count] if cancel_count else ""
                    needed_close = needed_close[cancel_count:]
                if needed_close and kept_chunks:
                    open_balance = sum(c.count("(") - c.count(")") for c in kept_chunks)
                    if open_balance > 0:
                        kept_chunks[-1] = kept_chunks[-1] + needed_close[:open_balance]
            continue

        if pending_open_parens:
            chunk = pending_open_parens + chunk
            pending_open_parens = ""

        kept_chunks.append(chunk)

    new_neg = ", ".join(kept_chunks)
    return new_neg, sorted(set(removed_tags))
