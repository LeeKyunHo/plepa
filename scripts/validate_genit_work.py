"""
젠잇(Gen-IT) 5탭 완성본 무결성 및 연쇄 동기화 스마트 검증기 (validate_genit_work.py)

[주요 기능]
1. 디렉토리 기반 다각화: docs/genit/ 내 모든 완성본 마크다운(*.md) 자동 탐색
2. 생애주기 관리 (Frontmatter): status: active(상시 검사) vs frozen/archived(스킵)
3. 스마트 해시 캐싱 (.cache/genit_cache.json): 변경 없는 문서는 0.001초 만에 [Cached PASS] 스킵
4. 에셋 연쇄 동기화: 실제 디스크 에셋(108종) 대비 오타/환각/404 포즈 실시간 검출
5. 6대 통일 변수, 글자수 한도(8,000자), 설정집/캐릭터 키워드 한도 전수 검증
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
GENIT_DIR = ROOT_DIR / "docs" / "genit"
PROJECTS_DIR = ROOT_DIR / "projects"
CACHE_DIR = ROOT_DIR / ".cache"
CACHE_FILE = CACHE_DIR / "genit_cache.json"


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


def get_asset_info(roster: str) -> Tuple[int, float, Set[str]]:
    """로스터의 실제 에셋 수량, 최신 mtime, 유효한 포즈 서픽스 집합 추출."""
    assets_dir = PROJECTS_DIR / roster / "assets"
    if not assets_dir.exists():
        return 0, 0.0, set()

    count = 0
    max_mtime = 0.0
    suffixes: Set[str] = set()

    for p in assets_dir.rglob("*.webp"):
        if "_origin" in p.parts:
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


def load_cache() -> Dict[str, Any]:
    """캐시 로드."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache: Dict[str, Any]) -> None:
    """캐시 저장."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 캐시 저장 실패: {e}")


def extract_code_blocks_after_header(text: str, header_pattern: str, count: int = 1) -> List[str]:
    m = re.search(header_pattern, text)
    if not m:
        return []
    sub = text[m.end():]
    blocks = re.findall(r"```(?:text|markdown|jsx)?\n(.*?)```", sub, re.DOTALL)
    return [b.strip() for b in blocks[:count]]


def validate_document(
    file_path: Path,
    use_cache: bool = True,
    force_all: bool = False,
) -> Tuple[bool, List[str], bool]:
    """
    단일 완성본 마크다운 검증 실행.
    Returns:
        (is_passed, errors, is_cached)
    """
    if not file_path.exists():
        return False, [f"파일을 찾을 수 없습니다: {file_path}"], False

    content = file_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)

    roster = meta.get("roster", "campus")
    status = meta.get("status", "active").lower()

    # frozen/archived 상태이고 force_all이 아니면 스킵
    if status in ("frozen", "archived") and not force_all:
        print(f"⏩ [SKIP] 봉인된 완성본 검사 스킵: {file_path.name} (status: {status})")
        return True, [], True

    # 스마트 캐시 검사
    file_hash = compute_sha256(file_path)
    asset_count, asset_mtime, valid_suffixes = get_asset_info(roster)

    cache = load_cache()
    cache_key = str(file_path.resolve())
    cached_entry = cache.get(cache_key)

    if use_cache and cached_entry:
        if (
            cached_entry.get("file_hash") == file_hash
            and cached_entry.get("asset_count") == asset_count
            and cached_entry.get("asset_mtime") == asset_mtime
            and cached_entry.get("passed") is True
        ):
            print(f"⚡ [Cached PASS] 내용 및 에셋 변경 없음: {file_path.name} (0.001s)")
            return True, [], True

    errors: List[str] = []
    print("=" * 76)
    print(f"🔍 [Gen-IT 5탭 정합성 검증] 대상: {file_path.name} (로스터: {roster})")
    print("=" * 76)

    # 1. 메인 프롬프트 및 시작 설정 1~4 추출
    main_blocks = extract_code_blocks_after_header(body, r"## 2-0\. \[메인 프롬프트\]", 1)
    main_prompt = main_blocks[0] if main_blocks else ""
    main_len = len(main_prompt)

    routes = [
        ("시작 설정 1 (아야메)", r"## 2-1\. \[시작 설정 1: 아야메 루트\]"),
        ("시작 설정 2 (유리카)", r"## 2-2\. \[시작 설정 2: 유리카 루트\]"),
        ("시작 설정 3 (카오루)", r"## 2-3\. \[시작 설정 3: 카오루 루트\]"),
        ("시작 설정 4 (올스타)", r"## 2-4\. \[시작 설정 4: 올스타 조별과제 루트\]"),
    ]

    max_add_len = 0
    max_add_name = ""

    print("\n📊 [1] 프롬프트 글자 수 한도 검증 (메인 + max(추가) <= 8,000자)")
    print(f"  - 메인 프롬프트 길이: {main_len:,}자")

    for r_name, r_pat in routes:
        blocks = extract_code_blocks_after_header(body, r_pat, 5)
        if len(blocks) < 5:
            errors.append(f"{r_name}: 코드블록 5개 중 일부 누락 ({len(blocks)}개 발견)")
            continue
        title_b, prol_b, hid_b, add_b, rec_b = blocks
        if len(title_b) > 20:
            errors.append(f"{r_name} 이름 20자 초과: {len(title_b)}자 ({title_b})")
        if len(prol_b) > 2000:
            errors.append(f"{r_name} 프롤로그 2,000자 초과: {len(prol_b):,}자")
        if len(hid_b) > 2000:
            errors.append(f"{r_name} 히든 프롬프트 2,000자 초과: {len(hid_b):,}자")
        if len(add_b) > max_add_len:
            max_add_len = len(add_b)
            max_add_name = r_name

        if "[@id=Status|" not in prol_b:
            errors.append(f"{r_name} 프롤로그 말미에 [@id=Status|...] 호출문 누락")

        print(
            f"  - {r_name}: 이름({len(title_b)}/20자) | 프롤로그({len(prol_b):,}/2,000자) | "
            f"히든({len(hid_b):,}/2,000자) | 추가({len(add_b):,}자)"
        )

    total_prompt_len = main_len + max_add_len
    if total_prompt_len > 8000:
        errors.append(f"메인 + {max_add_name} 합산 글자 수 8,000자 초과: {total_prompt_len:,}자")
        print(f"  👉 [합산 결과] 메인 + 최장 추가 = {total_prompt_len:,} / 8,000자 (초과: {total_prompt_len - 8000}자) -> FAIL ❌")
    else:
        print(f"  👉 [합산 결과] 메인({main_len:,}자) + 최장 추가[{max_add_name}]({max_add_len:,}자) = {total_prompt_len:,} / 8,000자 (여유분: {8000 - total_prompt_len:,}자) -> PASS ✅")

    # 2. 설정집 글자 수 검증
    lorebook_matches = re.findall(
        r"### \d+\. 설정집 \d+: (.*?)\n.*?\* \*\*키워드 \(15자 이내\)\*\*: `(.*?)`\n.*?\* \*\*프롬프트 \(500자 이내\)\*\*:\n```text\n(.*?)```",
        body,
        re.DOTALL
    )

    print("\n📚 [2] 설정집(Lorebook) 글자 수 및 키워드 한도 검증 (프롬프트 <= 500자, 키워드 <= 15자)")
    if len(lorebook_matches) < 6:
        errors.append(f"설정집 6개 항목 중 일부 파싱 실패 (발견: {len(lorebook_matches)}개)")

    for l_title, kw_b, prompt_b in lorebook_matches:
        l_title = l_title.strip()
        kw_b = kw_b.strip()
        prompt_b = prompt_b.strip()
        if len(kw_b) > 15:
            errors.append(f"설정집 '{l_title}' 키워드 15자 초과: {len(kw_b)}자 (`{kw_b}`)")
        if len(prompt_b) > 500:
            errors.append(f"설정집 '{l_title}' 프롬프트 500자 초과: {len(prompt_b)}자")
        print(f"  - {l_title}: 키워드 `{kw_b}` ({len(kw_b)}/15자) | 본문 ({len(prompt_b)}/500자)")

    # 3. 캐릭터 6인 한도 검증
    char_match = re.search(r"# 👥 \[탭 4: 캐릭터\].*?(?=# 🧩 \[탭 5: 에셋\]|$)", body, re.DOTALL)
    char_text = char_match.group(0) if char_match else body

    char_matches = re.findall(
        r"### \d+\. (.*?) \([`a-zA-Z가-힣\s]+\)\n.*?\* \*\*이름 \(20자 이내\)\*\*: `(.*?)`\n.*?\* \*\*키워드 \(15자 이내\)\*\*: `(.*?)`\n.*?\* \*\*소개 \(.*?300자 이내\)\*\*:\n```text\n(.*?)```\n.*?\* \*\*프롬프트 \(.*?500자 이내\)\*\*:\n```text\n(.*?)```",
        char_text,
        re.DOTALL
    )

    print("\n👥 [3] 캐릭터 6인 한도 및 키워드 중복 검증 (프롬프트 <= 500자, 소개 <= 300자, 키워드 <= 15자)")
    if len(char_matches) < 6:
        errors.append(f"캐릭터 6인 중 일부 파싱 실패 (발견: {len(char_matches)}명)")

    all_char_kws: List[str] = []
    for c_title, name_b, kw_b, intro_b, prompt_b in char_matches:
        c_title = c_title.strip()
        kw_b = kw_b.strip()
        intro_b = intro_b.strip()
        prompt_b = prompt_b.strip()

        if len(kw_b) > 15:
            errors.append(f"캐릭터 '{c_title}' 키워드 15자 초과: {len(kw_b)}자 (`{kw_b}`)")
        if len(intro_b) > 300:
            errors.append(f"캐릭터 '{c_title}' 소개 300자 초과: {len(intro_b)}자")
        if len(prompt_b) > 500:
            errors.append(f"캐릭터 '{c_title}' 프롬프트 500자 초과: {len(prompt_b)}자")

        kws = [k.strip() for k in kw_b.split(",") if k.strip()]
        for kw in kws:
            if kw in all_char_kws:
                errors.append(f"캐릭터 키워드 중복 발견: `{kw}` (타 히로인 호출 간섭 유발)")
            all_char_kws.append(kw)

        print(f"  - {c_title}: 키워드 `{kw_b}` ({len(kw_b)}/15자) | 소개 ({len(intro_b)}/300자) | 프롬프트 ({len(prompt_b)}/500자)")

    # 4. 6대 통일 변수 및 장소명 키워드 검증
    print("\n⚙️ [4] 6대 통일 변수, 키워드형 장소명 및 실제 에셋 정합성 검증")
    all_code_blocks = "\n".join(re.findall(r"```(?:text|markdown|jsx)?\n(.*?)```", body, re.DOTALL))

    legacy_vars = ["team_prog", "cha_affinity", "cha_stress", "heroine_affinity", "heroine_stress"]
    for lv in legacy_vars:
        if re.search(r"\b" + re.escape(lv) + r"\b", all_code_blocks):
            errors.append(f"구버전 레거시 변수 감지: `{lv}` (6대 통일 변수로 교체 필요)")

    banned_loc_prefixes = ["공학관", "인문관", "304호", "402호", "101호", "3층", "2층", "1층", "중앙도서관", "학생회관"]
    for blp in banned_loc_prefixes:
        if blp in all_code_blocks:
            errors.append(f"장소명에 복잡한 층/호실/관 수식어 감지: `{blp}` (직관적 키워드형 장소명 필요)")

    # 5. 실제 에셋 파일명 대조 검증
    referenced_poses: Set[str] = set()

    m_table = re.search(r"\[5\. 캠퍼스 6인 전수 포즈 매핑 테이블 \(108종 SSOT\)\](.*?)\[6\.", body, re.DOTALL)
    if m_table:
        for token in re.findall(r"\b(\d{3}_[^\s\|\]\n\r]+)", m_table.group(1)):
            referenced_poses.add(token.strip())

    for url_match in re.findall(r"\{\{url\}\}[a-z]{3}_(\d{3}_[^\s\.\n\r\t\"\'\`]+)\.webp", body):
        referenced_poses.add(url_match.strip())

    invalid_poses = []
    if valid_suffixes:
        for rp in sorted(referenced_poses):
            if rp not in valid_suffixes:
                invalid_poses.append(rp)

    if invalid_poses:
        for ip in invalid_poses:
            errors.append(f"존재하지 않는 포즈 파일명 참조(404 위험): `{ip}`")

    print(f"  - 실제 에셋 서픽스 수집 수량: {len(valid_suffixes)}종")
    print(f"  - 완성본에서 검증된 고유 포즈 수량: {len(referenced_poses)}종 (불일치: {len(invalid_poses)}건)")

    is_passed = len(errors) == 0
    print("\n" + "=" * 76)
    if is_passed:
        print(f"✅ [PASS] {file_path.name} 무결성 100% 통과!")
        # 캐시 갱신
        cache[cache_key] = {
            "file_hash": file_hash,
            "asset_count": asset_count,
            "asset_mtime": asset_mtime,
            "passed": True,
        }
        save_cache(cache)
    else:
        print(f"🚨 [FAIL] {file_path.name} 총 {len(errors)}건의 오류 감지:")
        for i, err in enumerate(errors, 1):
            print(f"  [{i}] {err}")

    print("=" * 76)
    return is_passed, errors, False


def run_all_validations(
    target_roster: Optional[str] = None,
    specific_file: Optional[str] = None,
    force_all: bool = False,
    no_cache: bool = False,
) -> bool:
    """전체 활성 완성본 문서 일괄 순회 검증."""
    files_to_check: List[Path] = []

    if specific_file:
        p = Path(specific_file)
        if not p.is_absolute():
            p = ROOT_DIR / p
        files_to_check.append(p)
    else:
        if not GENIT_DIR.exists():
            print(f"[WARN] 젠잇 완성본 디렉토리가 존재하지 않습니다: {GENIT_DIR}")
            return True

        for p in sorted(GENIT_DIR.glob("*.md")):
            # 아카이브 폴더는 glob에서 자연스럽게 제외됨
            if target_roster:
                content = p.read_text(encoding="utf-8")
                meta, _ = parse_frontmatter(content)
                if meta.get("roster") != target_roster:
                    continue
            files_to_check.append(p)

    if not files_to_check:
        print("점검할 젠잇 완성본 문서가 없습니다.")
        return True

    all_passed = True
    total_checked = 0
    cached_count = 0

    for fpath in files_to_check:
        passed, errors, is_cached = validate_document(
            fpath,
            use_cache=(not no_cache),
            force_all=force_all,
        )
        total_checked += 1
        if is_cached:
            cached_count += 1
        if not passed:
            all_passed = False

    print(f"\n📋 [검증 집계] 총 {total_checked}개 문서 중 {cached_count}개 캐시 스킵, 최종 결과: {'ALL PASS ✅' if all_passed else 'FAIL ❌'}")
    return all_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="젠잇(Gen-IT) 완성본 5탭 스마트 검증기")
    parser.add_argument("-r", "--roster", default=None, help="특정 로스터의 완성본만 점검 (예: campus)")
    parser.add_argument("-f", "--file", default=None, help="특정 단일 마크다운 파일만 지정 점검")
    parser.add_argument("--force", action="store_true", help="캐시를 무시하고 강제 전수 검증")
    parser.add_argument("--all", action="store_true", help="frozen/archived 봉인 문서까지 모두 포함하여 검증")
    args = parser.parse_args()

    ok = run_all_validations(
        target_roster=args.roster,
        specific_file=args.file,
        force_all=args.all,
        no_cache=args.force,
    )
    sys.exit(0 if ok else 1)
