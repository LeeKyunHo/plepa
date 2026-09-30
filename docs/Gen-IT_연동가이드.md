# 플에파 (PLEPA) 젠잇(Gen-IT) 연동 가이드

> **문서 버전**: v1.0.0  
> **대상**: 젠잇(Gen-IT) AI 챗봇 빌더, 프롬프트 엔지니어  
> **연계 문서**: [`사용법.md`](사용법.md), [`포즈매핑.md`](포즈매핑.md)

---

## 1. 젠잇(Gen-IT) 연동 개요

플에파(PLEPA)에서 생성된 80종의 WebP 캐릭터 에셋은 젠잇(Gen-IT) 챗봇 플랫폼 규격에 맞춰 자동으로 마크다운 가이드 문서(`[prefix]_genit_guide.md`)로 조립됩니다.

각 캐릭터의 배치 생성이 끝나면 `projects/[roster]/assets/[prefix]/[prefix]_genit_guide.md` 파일이 자동 생성되며, 사용자는 이 파일의 내용을 복사하여 젠잇 챗봇 설정에 그대로 붙여넣을 수 있습니다.

---

## 2. 젠잇 가이드 4대 블록 구조

### 2.1 이미지 호출 코드 블록
챗봇이 대화 도중 동적으로 이미지를 불러올 수 있도록 정형화된 이미지 URL 목록입니다:

```markdown
### bjh 이미지 호출 코드
{{url}}bjh/bjh_00.webp
{{url}}bjh/bjh_01.webp
{{url}}bjh/bjh_02.webp
...
```

### 2.2 파일 목록 블록
사람이 한눈에 포즈 번호와 한글 라벨을 확인할 수 있는 마크다운 목록입니다:

```markdown
### bjh 파일 목록
- `{{url}}bjh/bjh_00.webp` (평상)
- `{{url}}bjh/bjh_01.webp` (미소)
- `{{url}}bjh/bjh_02.webp` (활짝웃음)
```

### 2.3 상태 매핑 가이드 블록
젠잇 챗봇의 **시스템 프롬프트(System Prompt)**에 주입하여, 대화 상황과 감정에 따라 챗봇이 정확한 이미지 URL을 출력하도록 유도하는 규칙표입니다:

```markdown
### bjh 상태 매핑 가이드
[emotions]
  평상                         -> bjh_00.webp
  미소                         -> bjh_01.webp
  활짝웃음                     -> bjh_02.webp
  홍조                         -> bjh_03.webp
[poses]
  윙크                         -> bjh_20.webp
  양손하트                     -> bjh_21.webp
[h_scenes]
  정상위                       -> bjh_40.webp
  후배위                       -> bjh_43.webp
```

### 2.4 상태창 템플릿 블록
대화 턴마다 캐릭터의 현재 상태를 시각화하는 젠잇 표준 상태창 템플릿입니다:

```markdown
### bjh 상태창 템플릿
[캐릭터이름: bjh]
[직책: 직책입력]
[호감도: 0/100]
[의상: 착의상태]
[현재위치: 장소입력]
[심리상태: 감정상태]
[외형특징: bjh 주요외형]
```

---

## 3. 실제 적용 방법 (3단계)

1. **에셋 생성**:
   ```bash
   python -u flux_batch_generator.py -r don -c bjh -p all
   ```
2. **가이드 파일 열기**:
   생성 완료 후 출력 폴더(`projects/don/assets/bjh/`)의 `bjh_genit_guide.md`를 엽니다.
3. **젠잇에 붙여넣기**:
   - `### bjh 상태 매핑 가이드` 블록을 복사하여 챗봇 시스템 지침에 추가.
   - `### bjh 이미지 호출 코드` 블록을 복사하여 챗봇 에셋 리스트에 등록.
