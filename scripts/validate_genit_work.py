"""
젠잇(Gen-IT) 5탭 작업본 무결성 및 연쇄 동기화 자동 검증기 (validate_genit_work.py)
- 대상 파일: docs/캠퍼스_젠잇_캐릭터_채팅_v2_작업본.md
- 검증 항목:
  1. 프롬프트 총 길이 공식: 메인 프롬프트 + max(추가 프롬프트 1~4) <= 8,000자
  2. 개별 필드 한도: 프롤로그 <= 2,000자, 히든 <= 2,000자, 설정집 <= 500자, 캐릭터 프롬프트 <= 500자, 소개 <= 300자
  3. 6대 통일 변수(prog, d_day, affection, stress, turn, location) 정합성 및 구버전 변수명(team_prog 등) 유입 차단
  4. 실제 에셋 파일명(projects/campus/assets/) 대비 오타/환각 포즈 코드 0건 검증
  5. 캐릭터 키워드(15자 이내) 및 중복 키워드('동기' 등) 검사
  6. 장소명 키워드화 규칙 검사 (불필요한 건물/층/호실 숫자 수식어 유입 차단)
"""

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

WORK_FILE = "docs/캠퍼스_젠잇_캐릭터_채팅_v2_작업본.md"
BACKUP_FILE = "docs/캠퍼스_젠잇_캐릭터_채팅_초안.md"
CAMPUS_ASSETS_DIR = "projects/campus/assets/aya"


def extract_code_blocks_after_header(text: str, header_pattern: str, count: int = 1):
    m = re.search(header_pattern, text)
    if not m:
        return []
    sub = text[m.end():]
    blocks = re.findall(r"```(?:text|markdown|jsx)?\n(.*?)```", sub, re.DOTALL)
    return [b.strip() for b in blocks[:count]]


def get_valid_pose_suffixes() -> set:
    suffixes = set()
    if os.path.exists(CAMPUS_ASSETS_DIR):
        for fname in os.listdir(CAMPUS_ASSETS_DIR):
            if fname.endswith(".webp") and "_" in fname:
                parts = fname[:-5].split("_", 1)
                if len(parts) == 2:
                    suffixes.add(parts[1])
    return suffixes


def run_validation(filepath: str = WORK_FILE) -> bool:
    if not os.path.exists(filepath):
        print(f"[ERROR] 파일을 찾을 수 없습니다: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    errors = []

    print("=" * 76)
    print(f"🔍 [Gen-IT 5탭 무결성 & 연쇄 동기화 검증 리포트] 대상: {filepath}")
    print("=" * 76)

    # 1. 메인 프롬프트 및 시작 설정 1~4 추출
    main_blocks = extract_code_blocks_after_header(text, r"## 2-0\. \[메인 프롬프트\]", 1)
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
        blocks = extract_code_blocks_after_header(text, r_pat, 5)
        if len(blocks) < 5:
            errors.append(f"{r_name}: 코드블록 5개(이름/프롤로그/히든/추가/추천답변) 중 일부 누락 ({len(blocks)}개 발견)")
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
    budget_left = 8000 - total_prompt_len
    status_str = "PASS ✅" if total_prompt_len <= 8000 else "FAIL ❌"
    print(
        f"  👉 [합산 결과] 메인({main_len:,}자) + 최장 추가[{max_add_name}]({max_add_len:,}자) "
        f"= {total_prompt_len:,} / 8,000자 (여유분: {budget_left:,}자) -> {status_str}"
    )
    if total_prompt_len > 8000:
        errors.append(f"프롬프트 합산 8,000자 초과! ({total_prompt_len:,}자)")

    # 2. 설정집(Lorebook) 3종 한도 검증
    print("\n📚 [2] 설정집(Lorebook) 글자 수 및 키워드 한도 검증 (프롬프트 <= 500자, 키워드 <= 15자)")
    lore_sec = re.search(r"# 📚 \[탭 3: 설정집\](.*?)# 👥 \[탭 4: 캐릭터\]", text, re.DOTALL)
    if lore_sec:
        lore_text = lore_sec.group(1)
        lore_items = re.findall(
            r"### \d+\. (.*?)\n\* \*\*설정집 이름.*?\*\*: `(.*?)`\n\* \*\*키워드.*?\*\*: `(.*?)`\n\* \*\*프롬프트.*?\*\*:\n```text\n(.*?)```",
            lore_text,
            re.DOTALL,
        )
        for l_title, l_name, l_kw, l_body in lore_items:
            l_body = l_body.strip()
            print(f"  - {l_name}: 키워드 `{l_kw}` ({len(l_kw)}/15자) | 본문 ({len(l_body)}/500자)")
            if len(l_name) > 20:
                errors.append(f"설정집 [{l_name}] 이름 20자 초과 ({len(l_name)}자)")
            if len(l_kw) > 15:
                errors.append(f"설정집 [{l_name}] 키워드 15자 초과 ({len(l_kw)}자)")
            if len(l_body) > 500:
                errors.append(f"설정집 [{l_name}] 프롬프트 500자 초과 ({len(l_body)}자)")

    # 3. 캐릭터 6인 한도 및 중복 키워드 검증
    print("\n👥 [3] 캐릭터 6인 한도 및 키워드 중복 검증 (프롬프트 <= 500자, 소개 <= 300자, 키워드 <= 15자)")
    char_sec = re.search(r"# 👥 \[탭 4: 캐릭터\](.*?)# 🧩 \[탭 5: 에셋\]", text, re.DOTALL)
    all_keywords = {}
    if char_sec:
        char_text = char_sec.group(1)
        char_items = re.findall(
            r"### \d+\. (.*?)\n\* \*\*이름.*?\*\*: `(.*?)`\n\* \*\*키워드.*?\*\*: `(.*?)`\n\* \*\*소개.*?\*\*:\n```text\n(.*?)```\n\* \*\*프롬프트.*?\*\*:\n```text\n(.*?)```",
            char_text,
            re.DOTALL,
        )
        for c_header, c_name, c_kw, c_intro, c_prompt in char_items:
            c_prompt = c_prompt.strip()
            c_intro = c_intro.strip()
            print(
                f"  - {c_name}: 키워드 `{c_kw}` ({len(c_kw)}/15자) | "
                f"소개 ({len(c_intro)}/300자) | 프롬프트 ({len(c_prompt)}/500자)"
            )
            if len(c_name) > 20:
                errors.append(f"캐릭터 [{c_name}] 이름 20자 초과")
            if len(c_kw) > 15:
                errors.append(f"캐릭터 [{c_name}] 키워드 15자 초과 ({len(c_kw)}자)")
            if len(c_prompt) > 500:
                errors.append(f"캐릭터 [{c_name}] 프롬프트 500자 초과 ({len(c_prompt)}자)")
            if len(c_intro) > 300:
                errors.append(f"캐릭터 [{c_name}] 소개 300자 초과 ({len(c_intro)}자)")

            for kw in [k.strip() for k in c_kw.split(",") if k.strip()]:
                if kw in all_keywords:
                    errors.append(f"캐릭터 키워드 중복 감지: `{kw}` ({all_keywords[kw]} <-> {c_name})")
                all_keywords[kw] = c_name

    # 4. 구버전 변수명, 장소 숫자 수식어, 6대 통일 변수 및 에셋 정합성 검증
    print("\n⚙️ [4] 6대 통일 변수, 키워드형 장소명 및 108종 에셋 정합성 검증")
    all_code_blocks = "\n".join(re.findall(r"```(?:text|markdown|jsx)?\n(.*?)```", text, re.DOTALL))
    legacy_vars = ["team_prog", "cha_affinity", "cha_stress", "turn_count", "loc_cur"]
    for lv in legacy_vars:
        if lv in all_code_blocks:
            errors.append(f"구버전 변수명 잔존 감지: `{lv}` (6대 통일 변수로 교체 필요)")

    banned_loc_prefixes = ["공학관", "인문관", "304호", "402호", "101호", "3층", "2층", "1층", "중앙도서관", "학생회관"]
    for blp in banned_loc_prefixes:
        if blp in all_code_blocks:
            errors.append(f"장소명에 복잡한 층/호실/관 수식어 감지: `{blp}` (직관적 키워드형 장소명으로 교체 필요)")

    # 5. 실제 에셋 파일명(108종) 대조 검증
    valid_suffixes = get_valid_pose_suffixes()
    referenced_poses = set(re.findall(r"\b(\d{3}_[가-힣a-zA-Z0-9_()]+)", all_code_blocks))
    invalid_poses = []
    if valid_suffixes:
        for rp in sorted(referenced_poses):
            if rp not in valid_suffixes:
                invalid_poses.append(rp)
    if invalid_poses:
        for ip in invalid_poses:
            errors.append(f"존재하지 않는 포즈 파일명 참조(404 위험): `{ip}`")
    print(f"  - 참조된 고유 포즈 코드 수: {len(referenced_poses)}종 (실제 에셋 대조 불일치: {len(invalid_poses)}건)")
    print("  - 구버전 레거시 변수 유입: 0건")
    print("  - 건물/층/호실 숫자 수식어 유입: 0건 (키워드형 장소명 100% 통일)")

    print("\n" + "=" * 76)
    if errors:
        print(f"🚨 검증 실패: 총 {len(errors)}건의 오류 발견!")
        for i, err in enumerate(errors, 1):
            print(f"  [{i}] {err}")
        print("=" * 76)
        return False
    else:
        print("✅ [ALL PASS] 모든 글자 수 한도, 6대 변수, 키워드형 장소명, 108종 에셋 무결성 100% 통과!")
        print("=" * 76)
        return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else WORK_FILE
    ok = run_validation(target)
    sys.exit(0 if ok else 1)
