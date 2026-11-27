"""
젠잇(Gen-IT) 5탭 완성본 무결성 및 연쇄 동기화 스마트 검증기 (validate_genit_work.py)

[주요 기능]
1. 디렉토리 기반 다각화: docs/genit/ 내 모든 완성본 마크다운(*.md) 자동 탐색
2. 생애주기 관리 (Frontmatter): status: active(상시 검사) vs frozen/archived(스킵)
3. 스마트 해시 캐싱 (.cache/genit_cache.json): 변경 없는 문서는 0.001초 만에 [Cached PASS] 스킵
4. 에셋 연쇄 동기화: 로스터 실제 디스크 에셋 대비 오타/환각/404 포즈 실시간 전수 검출
5. 8대 통일 변수, 글자수 한도(12,000자), 설정집/캐릭터 키워드 한도 전수 검증
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from scripts.validate_genit_rules import (
    compute_sha256,
    extract_code_blocks_after_header,
    get_asset_info,
    parse_frontmatter,
    validate_characters_section,
    validate_lorebooks_section,
    validate_prompts_section,
    validate_vars_and_assets,
)

GENIT_DIR = ROOT_DIR / "docs" / "genit"
PROJECTS_DIR = ROOT_DIR / "projects"
CACHE_DIR = ROOT_DIR / ".cache"
CACHE_FILE = CACHE_DIR / "genit_cache.json"


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
    """캐시 원자적 저장."""
    temp_file: Optional[Path] = None
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = CACHE_DIR / f".{CACHE_FILE.name}.{uuid.uuid4().hex[:8]}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, CACHE_FILE)
    except Exception as exc:
        print(f"[WARN] 캐시 저장 실패: {exc}")
    finally:
        if temp_file and temp_file.exists():
            temp_file.unlink(missing_ok=True)


def validate_document(
    file_path: Path,
    use_cache: bool = True,
    force_all: bool = False,
) -> Tuple[bool, List[str], bool]:
    """단일 완성본 마크다운 검증 실행. 반환값: (is_passed, errors, is_cached)."""
    if not file_path.exists():
        return False, [f"파일을 찾을 수 없습니다: {file_path}"], False

    content = file_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    roster = meta.get("roster", "campus")
    status = meta.get("status", "active").lower()

    if status == "template":
        print(f"⏩ [SKIP] 다테마 청사진 템플릿 스킵: {file_path.name} (status: template)")
        return True, [], True
    if status in ("frozen", "archived") and not force_all:
        print(f"⏩ [SKIP] 봉인된 완성본 검사 스킵: {file_path.name} (status: {status})")
        return True, [], True

    file_hash = compute_sha256(file_path)
    asset_count, asset_mtime, valid_suffixes = get_asset_info(PROJECTS_DIR, roster)

    cache = load_cache()
    cache_key = str(file_path.resolve())
    cached_entry = cache.get(cache_key)
    if (
        use_cache
        and cached_entry
        and cached_entry.get("file_hash") == file_hash
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

    validate_prompts_section(body, errors)
    validate_lorebooks_section(body, meta, roster, errors)
    validate_characters_section(body, meta, roster, PROJECTS_DIR, errors)
    validate_vars_and_assets(body, valid_suffixes, errors)

    is_passed = len(errors) == 0
    print("\n" + "=" * 76)
    if is_passed:
        print(f"✅ [PASS] {file_path.name} 무결성 100% 통과!")
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
            if target_roster:
                meta, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
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
        passed, _, is_cached = validate_document(fpath, use_cache=(not no_cache), force_all=force_all)
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
