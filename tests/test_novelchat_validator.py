"""tests/test_novelchat_validator.py — 노벨챗 원고 검증기 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path

from plepa_engine.services.novelchat_validator import validate_novelchat_markdown

ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT_DIR / "docs" / "novelchat" / "NOVELCHAT_MULTI_THEME_TEMPLATE_v1.0.md"


def _minimal_valid_doc(
    name: str = "테스트 작품",
    char_desc: str = "아야메는 차분하다.",
    stat_desc: str = "{{user}}가 아야메를 칭찬하면 +3",
    custom_block: str = "대사입니다",
    intro_title: str = "첫번째 도입부",
    common_extra: str = "",
) -> str:
    return f"""---
status: active
roster: campus
---
## 1. [탭 1: 프로필]
### 1-1. 콘텐츠 이름
```text
{name}
```
### 1-2. 한줄 소개
```text
짧은 소개입니다.
```
### 1-3. 콘텐츠 소개
```text
작품 소개입니다.
```
### 1-4. 해시태그
```text
캠퍼스, 로맨스
```

## 2. [탭 2: 배경 설정]
### 2-1. 공통 프롬프트
```text
![char_아야메](평상)
{{{{char_아야메}}}}는 도서관에 있다.
{common_extra}
```
### 2-2. 캐릭터 설정
#### [캐릭터: 아야메]
##### 한줄 소개
```text
문학부 동기
```
##### 캐릭터 설명
```text
{char_desc}
```
##### 종속 변수
###### 변수: 호감도
```text
{stat_desc}
```

## 3. [탭 3: 도입부]
### 3-1. [도입부 1: {intro_title}]
#### 도입부 제목
```text
{intro_title}
```
#### 도입부 내용
##### [블록: 커스텀 캐릭터]
```text
{custom_block}
```
#### 추천답변
```text
인사한다
```

## 5. [탭 5: 메모리북]
### 5-1. [메모리북: 도서관]
#### 키워드
```text
도서관, 열람실
```
#### 내용
```text
조용한 도서관이다.
```

## 6. [탭 6: 기타 설정]
### 6-1. 연령 등급
```text
일반모드
```
### 6-2. 크리에이터 코멘트
```text
코멘트
```
"""


def test_master_template_passes_validation() -> None:
    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    res = validate_novelchat_markdown(content)
    assert res.passed, f"템플릿 검증 실패: {res.errors}"


def test_custom_character_quotes_overhead_boundary() -> None:
    ok_doc = _minimal_valid_doc(custom_block="가" * 498)
    assert validate_novelchat_markdown(ok_doc).passed

    bad_doc = _minimal_valid_doc(custom_block="가" * 499)
    res = validate_novelchat_markdown(bad_doc)
    assert not res.passed
    assert any("커스텀 캐릭터 블록" in e for e in res.errors)


def test_title_special_char_and_emoji_blocked() -> None:
    bad_name = _minimal_valid_doc(name="캠퍼스: 사랑!")
    res1 = validate_novelchat_markdown(bad_name)
    assert not res1.passed and any("콘텐츠 이름" in e for e in res1.errors)

    bad_intro = _minimal_valid_doc(intro_title="도입부 😀")
    res2 = validate_novelchat_markdown(bad_intro)
    assert not res2.passed and any("도입부 1 제목" in e for e in res2.errors)


def test_char_token_forbidden_and_allowed_zones() -> None:
    bad_desc = _minimal_valid_doc(char_desc="{{char_아야메}}는 차분하다.")
    res1 = validate_novelchat_markdown(bad_desc)
    assert not res1.passed and any("금지 구역" in e for e in res1.errors)

    bad_stat = _minimal_valid_doc(stat_desc="{{char_아야메}} 칭찬 +3")
    res2 = validate_novelchat_markdown(bad_stat)
    assert not res2.passed and any("금지 구역" in e for e in res2.errors)

    unreg = _minimal_valid_doc(common_extra="{{char_미등록}} 등장")
    res3 = validate_novelchat_markdown(unreg)
    assert not res3.passed and any("미등록 캐릭터 토큰" in e for e in res3.errors)


def test_genit_legacy_and_manifest_cross_check(tmp_path: Path) -> None:
    legacy = _minimal_valid_doc(common_extra="{{url}}aya/aya_000_평상.webp [@id=Status|turn=1]")
    res1 = validate_novelchat_markdown(legacy)
    assert not res1.passed and len(res1.errors) >= 2

    manifest = tmp_path / "upload_manifest.json"
    manifest.write_text(
        json.dumps({"characters": {"아야메": {"pools": {"미소": 1}}}}),
        encoding="utf-8",
    )
    res2 = validate_novelchat_markdown(_minimal_valid_doc(), manifest_path=manifest)
    assert not res2.passed
    assert any("미등록 호출어" in e for e in res2.errors)
