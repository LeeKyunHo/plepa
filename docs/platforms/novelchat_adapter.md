# 🟡 노벨챗(NovelChat) 플랫폼 어댑터 (`novelchat_adapter`)

> **역할**: [`CORE_SPEC.md`](CORE_SPEC.md)의 공통 코어를 **노벨챗(NovelChat) 6탭 커스텀 모드 규격**에 매핑하는 공식 어댑터입니다.  
> **상세 기술 SSOT**: [`docs/노벨챗_캐릭터채팅_제작법.md`](../%EB%85%B8%EB%B2%A8%EC%B1%97_%EC%BA%90%EB%A6%AD%ED%84%B0%EC%B1%84%ED%8C%85_%EC%A0%9C%EC%9E%91%EB%B2%95.md) · [`docs/novelchat/NOVELCHAT_MULTI_THEME_TEMPLATE_v1.0.md`](../novelchat/NOVELCHAT_MULTI_THEME_TEMPLATE_v1.0.md)

---

## 1. 플랫폼 슬롯 및 글자수 한도 매핑

| 코어 개념 | 노벨챗 6탭 입력 필드 | 최대 한도 | AI 주입 |
| :--- | :--- | :--- | :---: |
| 작품 소개 | 탭 1 프로필 → `콘텐츠 소개` | `<= 1,000자` (한줄 `<= 200자`, 이름 `<= 20자` 특수문자X) | X |
| 공통 헌법 | 탭 2 배경 설정 → `공통 프롬프트` | `<= 7,000자` | O (상시) |
| 캐릭터 인격/외형 | 탭 2 배경 설정 → `캐릭터 설명` | **`<= 1,000자`** (`{{char_...}}` **금지**) | O |
| 캐릭터 수치 스탯 | 탭 2 배경 설정 → `종속 변수` | 스탯 설명 `<= 200자` (`{{char_...}}` **금지**) | O |
| 루트 분기 (최대 3) | 탭 3 도입부 → `도입부` (1~3) | 제목 `<= 30자`(특수문자X), 일반 블록 `<= 500자`(커스텀 `""` 2자 가산), INFO `<= 300자`, 이벤트 `<= 2,000자`, 전용 프롬프트 `<= 7,000자` | O |
| 에셋 풀 | 탭 4 캐릭터 에셋 | **총 `<= 500개`**, 개당 `<= 5MB`, `_` 금지, `Bronze` 고정 | O (호출어) |
| 로어북 | 탭 5 메모리북 | 키워드 `<= 5개` × `<= 30자`(**Exact Match**), 내용 `<= 450자` | O (조건부) |
| 등급/코멘트 | 탭 6 기타 설정 | 일반 / **성인모드(비가역)**, 코멘트 `<= 1,000자` | X |

---

## 2. 이미지 · 에셋 · 경로 규격

- **본문 호출 문법**: `![char_이름](호출명)` (접두어 중복 기재 금지)
- **업로드 파일명 규칙**: `{호출어}_{코드}.webp` (`_` 앞 문자열이 호출어로 자동 파싱됨)
- **자동 패키징 CLI**:
  ```powershell
  .\.venv\Scripts\python.exe scripts/novelchat_asset_mapper.py --roster {roster} --include-adult --trim-to-limit
  ```

---

## 3. 자동 검증 게이트

```powershell
.\.venv\Scripts\python.exe scripts/validate_novelchat_work.py docs/novelchat/{work}.md --manifest dist/novelchat/{roster}/upload_manifest.json
```
