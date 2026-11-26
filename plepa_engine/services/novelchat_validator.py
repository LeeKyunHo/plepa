"""
plepa_engine.services.novelchat_validator
노벨챗(NovelChat) 6탭 표준 마크다운 원고 파서 및 정합성 검증 엔진.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

NOVELCHAT_LIMITS: Dict[str, int] = {
    "CONTENT_NAME_MAX": 20,
    "ONE_LINE_INTRO_MAX": 200,
    "CONTENT_INTRO_MAX": 1000,
    "HASHTAG_MAX_COUNT": 10,
    "HASHTAG_MAX_LEN": 10,
    "COMMON_PROMPT_MAX": 7000,
    "CHAR_NAME_MAX": 20,
    "CHAR_ONE_LINE_MAX": 200,
    "CHAR_DESC_MAX": 1000,
    "STAT_DESC_MAX": 200,
    "INTRO_MAX_COUNT": 3,
    "INTRO_TITLE_MAX": 30,
    "INTRO_BLOCK_MAX": 500,
    "INTRO_INFO_MAX": 300,
    "INTRO_REC_MAX_COUNT": 3,
    "INTRO_REC_MAX_LEN": 50,
    "INTRO_EVENT_MAX": 2000,
    "INTRO_CUSTOM_PROMPT_MAX": 7000,  # UNVERIFIED: 도입부 전용 프롬프트 상한, 공통 프롬프트 기준 추정
    "MEMORY_KW_MAX_COUNT": 5,
    "MEMORY_KW_MAX_LEN": 30,
    "MEMORY_CONTENT_MAX": 450,
    "CREATOR_COMMENT_MAX": 1000,
    "ASSET_TRIGGER_MAX_LEN": 30,  # UNVERIFIED: 개별 호출어 최대 길이 방어 경고선
}

_TITLE_ALLOWED_RE = re.compile(r"^[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ\s]+$")
_GENIT_LEGACY_PATTERNS = [
    (r"\{\{url\}\}", "젠잇 매크로 '{{url}}' 잔재"),
    (r"\[@id=", "젠잇 상태창/라인 태그 '[@id=' 잔재"),
    (r"useTemplateValue|setReturnValue", "젠잇 JSX 훅 잔재"),
    (r"\{\{random\(", "젠잇 난수 매크로 '{{random(' 잔재"),
    (r"@[가-힣A-Za-z0-9_?]+@", "젠잇 화자 표기 '@캐릭터@' 잔재"),
]
_POSTPOSITION_ENDINGS = ("에서", "으로", "에게", "한테", "하면", "할때", "이다", "였다", "이다.")


@dataclass
class ValidationResult:
    """원고 검증 결과."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """YAML Frontmatter 파싱."""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not m:
        return {}, text
    meta: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if line and ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, text[m.end():]


def _extract_section(text: str, heading_regex: str, next_level: int) -> str:
    m = re.search(heading_regex, text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end():]
    stop = re.search(rf"^#{{1,{next_level}}}\s+", rest, re.MULTILINE)
    return rest[: stop.start()] if stop else rest


def _extract_first_code_block(section_text: str) -> Optional[str]:
    m = re.search(r"```[^\n]*\n(.*?)```", section_text, re.DOTALL)
    return m.group(1).strip() if m else None


def _check_len(label: str, val: Optional[str], limit: int, errors: List[str], required: bool = False) -> None:
    if val is None:
        if required:
            errors.append(f"[{label}] 필수 항목이 누락되었습니다.")
        return
    if len(val) > limit:
        errors.append(f"[{label}] 글자 수 초과 ({len(val)}/{limit}자)")


def _check_char_tokens(
    zone: str,
    text: str,
    registered_chars: Set[str],
    allow_char_token: bool,
    errors: List[str],
) -> None:
    tokens = re.findall(r"\{\{char_([^}]+)\}\}", text)
    if not allow_char_token and tokens:
        errors.append(f"[{zone}] '{{{{char_...}}}}' 토큰 사용 금지 구역입니다 (발견: {tokens}). 실명을 직접 기재하세요.")
        return
    for name in tokens:
        if registered_chars and name.strip() not in registered_chars:
            errors.append(f"[{zone}] 미등록 캐릭터 토큰 '{{{{char_{name}}}}}' 사용 (등록 목록: {sorted(registered_chars)})")


def _check_image_calls(
    zone: str,
    text: str,
    manifest_chars: Optional[Dict[str, Set[str]]],
    errors: List[str],
    warnings: List[str],
) -> None:
    for bad in re.findall(r"!\[char[^_\]\n]*\]\([^)]*\)", text):
        if not bad.startswith("![char_"):
            errors.append(f"[{zone}] 이미지 호출 문법 오류: {bad} ('![char_이름](호출명)' 필수)")
    for char_name, trigger in re.findall(r"!\[char_([^\]]+)\]\(([^)]*)\)", text):
        if "_" in trigger:
            errors.append(f"[{zone}] 이미지 호출어에 '_' 사용 금지: ![char_{char_name}]({trigger})")
        if len(trigger) > NOVELCHAT_LIMITS["ASSET_TRIGGER_MAX_LEN"]:
            warnings.append(f"[{zone}] 호출어 길이 경고({len(trigger)}자): {trigger}")
        if re.match(r"^[a-z]{2,4}\s+", trigger):
            warnings.append(f"[{zone}] 호출어에 캐릭터 접두어 중복 의심(토큰 낭비): {trigger}")
        if manifest_chars is not None:
            valid_pools = manifest_chars.get(char_name)
            if valid_pools is None:
                errors.append(f"[{zone}] 매니페스트에 없는 캐릭터 이미지 호출: char_{char_name}")
            elif trigger not in valid_pools:
                errors.append(f"[{zone}] 매니페스트 미등록 호출어: ![char_{char_name}]({trigger})")


def _load_manifest_pools(manifest_path: Optional[Path]) -> Optional[Dict[str, Set[str]]]:
    if not manifest_path:
        return None
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    chars_raw = data.get("characters", {})
    return {k: set(v.get("pools", {}).keys()) for k, v in chars_raw.items()}


def _validate_intros(
    tab3: str,
    registered_chars: Set[str],
    manifest_pools: Optional[Dict[str, Set[str]]],
    res: ValidationResult,
) -> int:
    intro_headers = list(re.finditer(r"^### 3-\d+\.\s*\[도입부[^\]]*\]", tab3, re.MULTILINE))
    if len(intro_headers) > NOVELCHAT_LIMITS["INTRO_MAX_COUNT"]:
        res.errors.append(f"[도입부] 최대 개수 초과 ({len(intro_headers)}/{NOVELCHAT_LIMITS['INTRO_MAX_COUNT']}개)")

    for idx, im in enumerate(intro_headers):
        end_pos = intro_headers[idx + 1].start() if idx + 1 < len(intro_headers) else len(tab3)
        i_sec = tab3[im.end():end_pos]
        i_title = _extract_first_code_block(_extract_section(i_sec, r"^#### 도입부 제목", 4))
        _check_len(f"도입부 {idx+1} 제목", i_title, NOVELCHAT_LIMITS["INTRO_TITLE_MAX"], res.errors, required=True)
        if i_title and not _TITLE_ALLOWED_RE.match(i_title):
            res.errors.append(f"[도입부 {idx+1} 제목] 특수문자 또는 이모지 제외 필수: {i_title}")

        content_sec = _extract_section(i_sec, r"^#### 도입부 내용", 4)
        for bm in re.finditer(r"^##### \[블록:\s*([^\]]+)\]", content_sec, re.MULTILINE):
            btype = bm.group(1).strip()
            btext = _extract_first_code_block(content_sec[bm.end():]) or ""
            if btype == "INFO":
                _check_len(f"도입부 {idx+1} INFO 블록", btext, NOVELCHAT_LIMITS["INTRO_INFO_MAX"], res.errors)
            elif btype in ("캐릭터", "커스텀 캐릭터", "나레이션", "사용자"):
                eff_len = len(btext) + (2 if btype == "커스텀 캐릭터" else 0)
                if eff_len > NOVELCHAT_LIMITS["INTRO_BLOCK_MAX"]:
                    res.errors.append(
                        f"[도입부 {idx+1} {btype} 블록] 글자 수 초과 ({eff_len}/{NOVELCHAT_LIMITS['INTRO_BLOCK_MAX']}자, 커스텀 \"\" 포함)"
                    )
                if re.search(r"^[가-힣A-Za-z0-9_]+\s*:\s*\"", btext, re.MULTILINE):
                    res.warnings.append(f"[도입부 {idx+1} {btype} 블록] 본문 내 화자명 중복 표기 의심")
                _check_char_tokens(f"도입부 {idx+1} 블록", btext, registered_chars, True, res.errors)
                _check_image_calls(f"도입부 {idx+1} 블록", btext, manifest_pools, res.errors, res.warnings)

        rec_raw = _extract_first_code_block(_extract_section(i_sec, r"^#### 추천답변", 4))
        if rec_raw:
            recs = [r.strip() for r in rec_raw.splitlines() if r.strip()]
            if len(recs) > NOVELCHAT_LIMITS["INTRO_REC_MAX_COUNT"]:
                res.errors.append(f"[도입부 {idx+1} 추천답변] 개수 초과 ({len(recs)}/3개)")
            for r in recs:
                if len(r) > NOVELCHAT_LIMITS["INTRO_REC_MAX_LEN"]:
                    res.errors.append(f"[도입부 {idx+1} 추천답변] 항목 길이 초과 ({len(r)}/50자)")

        ev = _extract_first_code_block(_extract_section(i_sec, r"^#### 도입부 이벤트", 4))
        _check_len(f"도입부 {idx+1} 이벤트", ev, NOVELCHAT_LIMITS["INTRO_EVENT_MAX"], res.errors)
        if ev:
            _check_char_tokens(f"도입부 {idx+1} 이벤트", ev, registered_chars, True, res.errors)
        cp = _extract_first_code_block(_extract_section(i_sec, r"^#### 도입부 전용 프롬프트", 4))
        _check_len(f"도입부 {idx+1} 전용 프롬프트", cp, NOVELCHAT_LIMITS["INTRO_CUSTOM_PROMPT_MAX"], res.errors)
        if cp:
            _check_char_tokens(f"도입부 {idx+1} 전용 프롬프트", cp, registered_chars, True, res.errors)
            _check_image_calls(f"도입부 {idx+1} 전용 프롬프트", cp, manifest_pools, res.errors, res.warnings)
    return len(intro_headers)


def _validate_memorybooks(tab5: str, registered_chars: Set[str], res: ValidationResult) -> int:
    mem_blocks = list(re.finditer(r"^### 5-\d+\.\s*\[메모리북:\s*([^\]]+)\]", tab5, re.MULTILINE))
    for idx, mm in enumerate(mem_blocks):
        mtitle = mm.group(1).strip()
        end_pos = mem_blocks[idx + 1].start() if idx + 1 < len(mem_blocks) else len(tab5)
        m_sec = tab5[mm.end():end_pos]
        kw_raw = _extract_first_code_block(_extract_section(m_sec, r"^#### 키워드", 4)) or ""
        kws = [k.strip() for k in re.split(r"[,\n]+", kw_raw) if k.strip()]
        if len(kws) > NOVELCHAT_LIMITS["MEMORY_KW_MAX_COUNT"]:
            res.errors.append(f"[메모리북:{mtitle}] 키워드 개수 초과 ({len(kws)}/5개)")
        for kw in kws:
            if len(kw) > NOVELCHAT_LIMITS["MEMORY_KW_MAX_LEN"]:
                res.errors.append(f"[메모리북:{mtitle}] 키워드 '{kw}' 길이 초과 ({len(kw)}/30자)")
            if " " in kw or kw.endswith(_POSTPOSITION_ENDINGS):
                res.warnings.append(f"[메모리북:{mtitle}] Exact Match 불발 위험 키워드(공백/조사): '{kw}'")
        m_content = _extract_first_code_block(_extract_section(m_sec, r"^#### 내용", 4))
        _check_len(f"메모리북:{mtitle} 내용", m_content, NOVELCHAT_LIMITS["MEMORY_CONTENT_MAX"], res.errors, required=True)
        if m_content:
            _check_char_tokens(f"메모리북:{mtitle}", m_content, registered_chars, True, res.errors)
    return len(mem_blocks)


def _validate_tab1_profile(body: str, res: ValidationResult) -> None:
    """탭 1(프로필/해시태그) 글자 수 및 특수문자 규칙을 검증합니다."""
    tab1 = _extract_section(body, r"^## 1\.\s*\[탭 1:\s*프로필\]", 2)
    name = _extract_first_code_block(_extract_section(tab1, r"^### 1-1\.", 3))
    one_line = _extract_first_code_block(_extract_section(tab1, r"^### 1-2\.", 3))
    intro = _extract_first_code_block(_extract_section(tab1, r"^### 1-3\.", 3))
    tags_raw = _extract_first_code_block(_extract_section(tab1, r"^### 1-4\.", 3))

    _check_len("콘텐츠 이름", name, NOVELCHAT_LIMITS["CONTENT_NAME_MAX"], res.errors, required=True)
    if name and not _TITLE_ALLOWED_RE.match(name):
        res.errors.append(f"[콘텐츠 이름] 특수문자 또는 이모지 사용 불가: {name}")
    _check_len("한줄 소개", one_line, NOVELCHAT_LIMITS["ONE_LINE_INTRO_MAX"], res.errors, required=True)
    _check_len("콘텐츠 소개", intro, NOVELCHAT_LIMITS["CONTENT_INTRO_MAX"], res.errors, required=True)

    if tags_raw:
        tags = [t.strip().lstrip("#") for t in re.split(r"[,\n]+", tags_raw) if t.strip()]
        if len(tags) > NOVELCHAT_LIMITS["HASHTAG_MAX_COUNT"]:
            res.errors.append(f"[해시태그] 개수 초과 ({len(tags)}/{NOVELCHAT_LIMITS['HASHTAG_MAX_COUNT']}개)")
        for t in tags:
            if len(t) > NOVELCHAT_LIMITS["HASHTAG_MAX_LEN"]:
                res.errors.append(f"[해시태그] '{t}' 길이 초과 ({len(t)}/{NOVELCHAT_LIMITS['HASHTAG_MAX_LEN']}자)")


def _validate_tab2_background(
    body: str,
    manifest_pools: Optional[Dict[str, Set[str]]],
    res: ValidationResult,
) -> Tuple[Optional[str], Set[str]]:
    """탭 2(배경/공통 프롬프트/캐릭터 블록·종속 변수) 정합성을 검증합니다."""
    tab2 = _extract_section(body, r"^## 2\.\s*\[탭 2:\s*배경 설정\]", 2)
    common_prompt = _extract_first_code_block(_extract_section(tab2, r"^### 2-1\.", 3))
    _check_len("공통 프롬프트", common_prompt, NOVELCHAT_LIMITS["COMMON_PROMPT_MAX"], res.errors, required=True)

    char_blocks = list(re.finditer(r"^#### \[캐릭터:\s*([^\]]+)\]", tab2, re.MULTILINE))
    registered_chars = {m.group(1).strip() for m in char_blocks}
    for idx, cm in enumerate(char_blocks):
        cname = cm.group(1).strip()
        end_pos = char_blocks[idx + 1].start() if idx + 1 < len(char_blocks) else len(tab2)
        c_sec = tab2[cm.end():end_pos]
        if len(cname) > NOVELCHAT_LIMITS["CHAR_NAME_MAX"]:
            res.errors.append(f"[캐릭터:{cname}] 이름 길이 초과 ({len(cname)}/{NOVELCHAT_LIMITS['CHAR_NAME_MAX']}자)")
        c_one = _extract_first_code_block(_extract_section(c_sec, r"^##### 한줄 소개", 5))
        c_desc = _extract_first_code_block(_extract_section(c_sec, r"^##### 캐릭터 설명", 5))
        _check_len(f"캐릭터:{cname} 한줄 소개", c_one, NOVELCHAT_LIMITS["CHAR_ONE_LINE_MAX"], res.errors)
        _check_len(f"캐릭터:{cname} 설명", c_desc, NOVELCHAT_LIMITS["CHAR_DESC_MAX"], res.errors, required=True)
        if c_desc:
            _check_char_tokens(f"캐릭터:{cname} 설명", c_desc, registered_chars, False, res.errors)

        stat_sec = _extract_section(c_sec, r"^##### 종속 변수", 5)
        for sm in re.finditer(r"^######\s+([^\n]+)", stat_sec, re.MULTILINE):
            s_body = _extract_first_code_block(stat_sec[sm.end():])
            _check_len(f"캐릭터:{cname} 스탯({sm.group(1).strip()})", s_body, NOVELCHAT_LIMITS["STAT_DESC_MAX"], res.errors)
            if s_body:
                _check_char_tokens(f"캐릭터:{cname} 스탯", s_body, registered_chars, False, res.errors)

    if common_prompt:
        _check_char_tokens("공통 프롬프트", common_prompt, registered_chars, True, res.errors)
        _check_image_calls("공통 프롬프트", common_prompt, manifest_pools, res.errors, res.warnings)
    return common_prompt, registered_chars


def validate_novelchat_markdown(
    content: str,
    manifest_path: Optional[Path] = None,
    strict: bool = False,
) -> ValidationResult:
    """노벨챗 6탭 표준 마크다운 원고를 파싱하고 전 규칙을 검증한다."""
    res = ValidationResult()
    _, body = parse_frontmatter(content)
    manifest_pools = _load_manifest_pools(manifest_path)

    _validate_tab1_profile(body, res)
    common_prompt, registered_chars = _validate_tab2_background(body, manifest_pools, res)

    tab3 = _extract_section(body, r"^## 3\.\s*\[탭 3:\s*도입부\]", 2)
    intro_count = _validate_intros(tab3, registered_chars, manifest_pools, res)

    tab5 = _extract_section(body, r"^## 5\.\s*\[탭 5:\s*메모리북\]", 2)
    mem_count = _validate_memorybooks(tab5, registered_chars, res)

    tab6 = _extract_section(body, r"^## 6\.\s*\[탭 6:\s*기타 설정\]", 2)
    age = _extract_first_code_block(_extract_section(tab6, r"^### 6-1\.", 3))
    comment = _extract_first_code_block(_extract_section(tab6, r"^### 6-2\.", 3))
    _check_len("크리에이터 코멘트", comment, NOVELCHAT_LIMITS["CREATOR_COMMENT_MAX"], res.errors)
    if age and "성인" in age:
        res.warnings.append("[기타 설정] 연령 등급 '성인모드' 선택됨: 설정 후 일반모드로 되돌리기 불가(비가역) 확인!")

    for pat, desc in _GENIT_LEGACY_PATTERNS:
        if re.search(pat, body):
            res.errors.append(f"[레거시 잔재] {desc} 발견")

    if strict and res.warnings:
        res.errors.extend([f"[STRICT] {w}" for w in res.warnings])

    res.stats = {
        "common_prompt_len": len(common_prompt or ""),
        "characters": len(registered_chars),
        "intros": intro_count,
        "memorybooks": mem_count,
    }
    return res
