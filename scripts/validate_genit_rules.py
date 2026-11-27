"""
scripts/validate_genit_rules.py
validate_genit_work.py의 Frontmatter/해시/에셋 수집 및 섹션별 5탭 검증 규칙 헬퍼.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple


GENIT_PROMPT_COMBINED_LIMIT = 12000
GENIT_PROLOGUE_LIMIT = 2000
GENIT_HIDDEN_LIMIT = 2000


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """문서 상단 YAML Frontmatter(--- ... ---) 파싱."""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not m:
        return {}, text

    fm_text = m.group(1)
    body = text[m.end():]
    meta: Dict[str, str] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if line and ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, body


def compute_sha256(path: Path) -> str:
    """파일 SHA-256 해시 계산."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_asset_info(projects_dir: Path, roster: str) -> Tuple[int, float, Set[str]]:
    """로스터의 실제 에셋 수량, 최신 mtime, 유효한 포즈 서픽스 집합 추출."""
    assets_dir = projects_dir / roster / "assets"
    if not assets_dir.exists():
        return 0, 0.0, set()

    count = 0
    max_mtime = 0.0
    suffixes: Set[str] = set()
    for p in assets_dir.rglob("*.webp"):
        if any(skip in p.parts for skip in ("_origin", "_trash", "legacy_backups")):
            continue
        count += 1
        m = p.stat().st_mtime
        if m > max_mtime:
            max_mtime = m
        fname = p.name
        if "_" in fname:
            parts = fname[:-5].split("_", 1)
            if len(parts) == 2:
                suffixes.add(parts[1])
    return count, max_mtime, suffixes


def extract_code_blocks_after_header(text: str, header_pattern: str, count: int = 1) -> List[str]:
    m = re.search(header_pattern, text)
    if not m:
        return []
    sub = text[m.end():]
    blocks = re.findall(r"```(?:text|markdown|jsx)?\n(.*?)```", sub, re.DOTALL)
    return [b.strip() for b in blocks[:count]]


def validate_prompts_section(body: str, errors: List[str]) -> None:
    """[1] 메인 프롬프트 + 최장 시작 설정 추가 프롬프트(<=12,000자) 및 Status 호출을 검증합니다."""
    main_blocks = extract_code_blocks_after_header(body, r"## 2-0\. \[메인 프롬프트\]", 1)
    main_prompt = main_blocks[0] if main_blocks else ""
    main_len = len(main_prompt)

    route_headers = re.findall(r"^(## 2-([1-9]\d*)\.\s*\[([^\]]+)\])", body, re.MULTILINE)
    routes = [(label.strip(), re.escape(header_line.strip())) for header_line, _, label in route_headers]
    if not routes:
        errors.append("시작 설정 루트 헤더(## 2-1. [...])를 찾을 수 없습니다.")

    max_add_len, max_add_name = 0, ""
    print(f"\n📊 [1] 프롬프트 글자 수 한도 검증 (메인 + max(추가) <= {GENIT_PROMPT_COMBINED_LIMIT:,}자)")
    print(f"  - 메인 프롬프트 길이: {main_len:,}자")

    for r_name, r_pat in routes:
        blocks = extract_code_blocks_after_header(body, r_pat, 5)
        if len(blocks) < 5:
            errors.append(f"{r_name}: 코드블록 5개 중 일부 누락 ({len(blocks)}개 발견)")
            continue
        title_b, prol_b, hid_b, add_b, _ = blocks
        if len(title_b) > 20:
            errors.append(f"{r_name} 이름 20자 초과: {len(title_b)}자 ({title_b})")
        if len(prol_b) > GENIT_PROLOGUE_LIMIT:
            errors.append(f"{r_name} 프롤로그 {GENIT_PROLOGUE_LIMIT:,}자 초과: {len(prol_b):,}자")
        if len(hid_b) > GENIT_HIDDEN_LIMIT:
            errors.append(f"{r_name} 히든 프롬프트 {GENIT_HIDDEN_LIMIT:,}자 초과: {len(hid_b):,}자")
        if len(add_b) > max_add_len:
            max_add_len, max_add_name = len(add_b), r_name
        if "[@id=Status|" not in prol_b:
            errors.append(f"{r_name} 프롤로그 말미에 [@id=Status|...] 호출문 누락")
        print(
            f"  - {r_name}: 이름({len(title_b)}/20자) | 프롤로그({len(prol_b):,}/{GENIT_PROLOGUE_LIMIT:,}자) "
            f"| 히든({len(hid_b):,}/{GENIT_HIDDEN_LIMIT:,}자) | 추가({len(add_b):,}자)"
        )

    total_prompt_len = main_len + max_add_len
    if total_prompt_len > GENIT_PROMPT_COMBINED_LIMIT:
        errors.append(f"메인 + {max_add_name} 합산 글자 수 {GENIT_PROMPT_COMBINED_LIMIT:,}자 초과: {total_prompt_len:,}자")
        print(
            f"  👉 [합산 결과] 메인 + 최장 추가 = {total_prompt_len:,} / {GENIT_PROMPT_COMBINED_LIMIT:,}자 "
            f"(초과: {total_prompt_len - GENIT_PROMPT_COMBINED_LIMIT:,}자) -> FAIL ❌"
        )
    else:
        print(
            f"  👉 [합산 결과] 메인({main_len:,}자) + 최장 추가[{max_add_name}]({max_add_len:,}자) = "
            f"{total_prompt_len:,} / {GENIT_PROMPT_COMBINED_LIMIT:,}자 (여유분: {GENIT_PROMPT_COMBINED_LIMIT - total_prompt_len:,}자) -> PASS ✅"
        )


def validate_lorebooks_section(body: str, meta: Dict[str, str], roster: str, errors: List[str]) -> None:
    """[2] 설정집(Lorebook) 최소 개수, 키워드 개수/길이(<=15자, <=5개) 및 본문(<=500자)을 검증합니다."""
    lorebook_matches = re.findall(
        r"### \d+\. 설정집 \d+: (.*?)\n.*?\* \*\*키워드 \([^)]*\)\*\*: `(.*?)`\n.*?\* \*\*프롬프트 \(500자 이내\)\*\*:\n```text\n(.*?)```",
        body, re.DOTALL,
    )
    min_lorebooks = int(meta.get("min_lorebooks", 0) or (6 if roster == "campus" else 1))
    print("\n📚 [2] 설정집(Lorebook) 글자 수 및 키워드 한도 검증 (프롬프트 <= 500자, 키워드 각 15자 이내 · 최대 5개)")
    if len(lorebook_matches) < min_lorebooks:
        errors.append(f"설정집 최소 기준({min_lorebooks}개) 미달 (발견: {len(lorebook_matches)}개)")

    for l_title, kw_b, prompt_b in lorebook_matches:
        l_title, kw_b, prompt_b = l_title.strip(), kw_b.strip(), prompt_b.strip()
        kw_tags = [k.strip() for k in kw_b.split(",") if k.strip()]
        if len(kw_tags) > 5:
            errors.append(f"설정집 '{l_title}' 키워드 5개 초과: {len(kw_tags)}개 (`{kw_b}`)")
        for kt in kw_tags:
            if len(kt) > 15:
                errors.append(f"설정집 '{l_title}' 개별 키워드 15자 초과: `{kt}` ({len(kt)}자)")
        if len(prompt_b) > 500:
            errors.append(f"설정집 '{l_title}' 프롬프트 500자 초과: {len(prompt_b)}자")
        print(f"  - {l_title}: 키워드 `{kw_b}` ({len(kw_tags)}/5개) | 본문 ({len(prompt_b)}/500자)")


def validate_characters_section(body: str, meta: Dict[str, str], roster: str, projects_dir: Path, errors: List[str]) -> None:
    """[3] 캐릭터 최소 수, 키워드 중복/길이 및 소개(<=300자)/프롬프트(<=500자) 한도를 검증합니다."""
    char_match = re.search(r"# 👥 \[탭 4: 캐릭터\].*?(?=# 🧩 \[탭 5: 에셋\]|$)", body, re.DOTALL)
    char_text = char_match.group(0) if char_match else body
    char_matches = re.findall(
        r"### \d+\. (.*?) \([`a-zA-Z가-힣\s]+\)\n.*?\* \*\*이름 \(20자 이내\)\*\*: `(.*?)`\n(?:\* \*\*별명 \([^)]*\)\*\*: `.*?`\n)?.*?\* \*\*키워드 \([^)]*\)\*\*: `(.*?)`\n.*?\* \*\*소개 \(.*?300자 이내\)\*\*:\n```text\n(.*?)```\n.*?\* \*\*프롬프트 \(.*?500자 이내\)\*\*:\n```text\n(.*?)```",
        char_text, re.DOTALL,
    )

    roster_chars_dir = projects_dir / roster / "characters"
    expected_char_count = (
        len([p for p in roster_chars_dir.glob("*.json") if not p.name.startswith("_")])
        if roster_chars_dir.is_dir() else 1
    )
    min_chars = int(meta.get("min_characters", 0) or max(1, expected_char_count))
    print(f"\n👥 [3] 캐릭터 ({len(char_matches)}/{min_chars}명) 한도 및 키워드 중복 검증 (프롬프트 <= 500자, 소개 <= 300자, 키워드 각 15자 이내 · 최대 5개)")
    if len(char_matches) < min_chars:
        errors.append(f"캐릭터 최소 기준({min_chars}명) 중 일부 파싱 실패 (발견: {len(char_matches)}명)")

    all_char_kws: List[str] = []
    for c_title, _, kw_b, intro_b, prompt_b in char_matches:
        c_title, kw_b, intro_b, prompt_b = c_title.strip(), kw_b.strip(), intro_b.strip(), prompt_b.strip()
        kws = [k.strip() for k in kw_b.split(",") if k.strip()]
        if len(kws) > 5:
            errors.append(f"캐릭터 '{c_title}' 키워드 5개 초과: {len(kws)}개 (`{kw_b}`)")
        for kw in kws:
            if len(kw) > 15:
                errors.append(f"캐릭터 '{c_title}' 개별 키워드 15자 초과: `{kw}` ({len(kw)}자)")
            if kw in all_char_kws:
                errors.append(f"캐릭터 키워드 중복 발견: `{kw}` (타 히로인 호출 간섭 유발)")
            all_char_kws.append(kw)
        if len(intro_b) > 300:
            errors.append(f"캐릭터 '{c_title}' 소개 300자 초과: {len(intro_b)}자")
        if len(prompt_b) > 500:
            errors.append(f"캐릭터 '{c_title}' 프롬프트 500자 초과: {len(prompt_b)}자")
        print(f"  - {c_title}: 키워드 `{kw_b}` ({len(kws)}/5개) | 소개 ({len(intro_b)}/300자) | 프롬프트 ({len(prompt_b)}/500자)")


def validate_vars_and_assets(body: str, valid_suffixes: Set[str], errors: List[str]) -> None:
    """[4~5] 8대 통일 변수, 금지 장소명 및 실제 디스크 에셋 서픽스 일치를 검증합니다."""
    print("\n⚙️ [4] 8대 통일 변수, 키워드형 장소명 및 실제 에셋 정합성 검증")
    all_code_blocks = "\n".join(re.findall(r"```(?:text|markdown|jsx)?\n(.*?)```", body, re.DOTALL))

    for lv in ("team_prog", "cha_affinity", "cha_stress", "heroine_affinity", "heroine_stress"):
        if re.search(r"\b" + re.escape(lv) + r"\b", all_code_blocks):
            errors.append(f"구버전 레거시 변수 감지: `{lv}` (8대 통일 변수로 교체 필요)")

    for blp in ("공학관", "인문관", "304호", "402호", "101호", "3층", "2층", "1층", "중앙도서관", "학생회관"):
        if blp in all_code_blocks:
            errors.append(f"장소명에 복잡한 층/호실/관 수식어 감지: `{blp}` (직관적 키워드형 장소명 필요)")

    referenced_poses: Set[str] = set()
    for token in re.findall(r"(?<![a-zA-Z0-9_])(\d{3}_[가-힣a-zA-Z0-9_\(\)]+)", all_code_blocks):
        referenced_poses.add(token.strip())
    for url_match in re.findall(r"\{\{url\}\}(?:[a-z]{3}/)?[a-z]{3}_(\d{3}_[^\s\.\n\r\t\"\'\`]+)\.webp", body):
        referenced_poses.add(url_match.strip())

    invalid_poses = [rp for rp in sorted(referenced_poses) if valid_suffixes and rp not in valid_suffixes]
    for ip in invalid_poses:
        errors.append(f"존재하지 않는 포즈 파일명 참조(404 위험): `{ip}`")

    print(f"  - 실제 에셋 서픽스 수집 수량: {len(valid_suffixes)}종")
    print(f"  - 완성본에서 검증된 고유 포즈 수량: {len(referenced_poses)}종 (불일치: {len(invalid_poses)}건)")
