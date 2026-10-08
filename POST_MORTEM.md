# 🛡️ [PLEPA Post-Mortem Archive] 장애 및 버그 사후 분석 보고서

> **문서 목적**: 실전 개발 과정에서 발생했던 치명적인 버그 및 렌더링 결함의 **근본 원인(Root Cause)을 규명하고 영구적인 재발 방지 대책(Action Items)**을 문서화하여 동일한 실수의 반복을 차단합니다.  
> **현업 원칙**: 비난 없는 사후 분석(Blameless Post-Mortem) 원칙에 따라 시스템적, 프롬프트 엔지니어링적 원인과 해결책에 집중합니다.

---

## 📑 장애 및 결함 분석 색인 (Incident Index)

| 사건 번호 | 발생 일자 | 문제 요약 | 상태 |
| :---: | :---: | :--- | :---: |
| **INC-20261006-01** | 2026-10-06 | HEXMIX IP-Adapter 품질 저하 및 비호환 결정 | `[RESOLVED]` |
| **INC-20261006-02** | 2026-10-06 | oes 머리 상투 이탈/복수 변이 및 목 주위 점 분산 버그 | `[RESOLVED]` |
| **INC-20261006-03** | 2026-10-06 | xia/oes `clean pale skin` 창백한 얼굴 과렌더링 | `[RESOLVED]` |
| **INC-20261006-04** | 2026-10-06 | 포즈 #041 `cum pool` 태그로 초록 배경 생성 | `[RESOLVED]` |
| **INC-20261006-05** | 2026-10-06 | 포즈 #056 남성 2명 등장 | `[RESOLVED]` |
| **INC-20261004-01** | 2026-10-04 | 포즈 #014(유혹)의 메인 의상 탈의/노출 파손 버그 | `[RESOLVED]` |
| **INC-20261004-02** | 2026-10-04 | 포즈 #019(키스)의 입술 찌그러짐 및 앵글 불일치 버그 | `[RESOLVED]` |
| **INC-20261003-01** | 2026-10-03 | 젠잇 JSX 라이트 모드 글씨 증발(투명화) 버그 | `[RESOLVED]` |
| **INC-20261002-01** | 2026-10-02 | 파이프라인 T34b 네거티브 충돌 및 샤워 씬 삭제 버그 | `[RESOLVED]` |

---

---

## 5. [INC-20261006-01] HEXMIX IP-Adapter 품질 저하 및 비호환 결정

### 5.1 사건 개요
- **증상**: HEXMIX v5.0 체크포인트에서 IP-Adapter 활성화 시 이미지 품질이 급격히 저하되고 금빛 장식 프레임이 생성됨. 레퍼런스 해상도를 1024×1536으로 맞춰도 개선되지 않음.

### 5.2 근본 원인 분석
1. **방식 불일치**: Kiro(Forge WebUI)는 ControlNet 기반 IP-Adapter를 자동 최적화하는 반면, PLEPA(ComfyUI)는 IPAdapterPlus를 수동 설정함.
2. **프리셋 과포화**: ComfyUI IPAdapterPlus의 "PLUS (high strength)" 프리셋이 HEXMIX 모델의 특성에 과도하게 작용함.
3. **금빛 프레임 원인**: Illustrious 계열 모델이 `masterpiece` 품질 태그를 고급 일러스트로 해석하여 장식 테두리를 생성 (IP-Adapter 미사용 시에도 발생 가능).

### 5.3 영구 대책
- **HEXMIX 사용 시 `--no_ref` 기본 적용** (IP-Adapter 비활성화).
- 네거티브에 `(border:1.5), (frame:1.5), (ornate border:1.5), (decorative frame:1.5)` 추가.
- `캐릭터_포즈_제작_규칙.md` 체크포인트별 IP-Adapter 호환성 표 참조.

---

## 6. [INC-20261006-02] oes 머리 상투 이탈/복수 변이 및 목 주위 점 분산 버그

### 6.1 사건 개요
- **증상 1**: `single hair bun`이 두 개로 분리(double bun)되거나 뒷통수에서 정수리로 위치가 이동함.
- **증상 2**: `beauty mark under left eye near cheek`가 왼쪽 눈 아래가 아닌 목/턱 주위에 여러 개 분산 생성됨.

### 6.2 근본 원인 분석
1. **가중치 부족**: `((single hair bun...:1.3))`이 Illustrious 모델의 롱헤어 편향을 이기지 못함.
2. **모호한 위치 지시어**: `near cheek`가 얼굴 전체 넓은 영역으로 해석되어 점이 분산됨.
3. **네거티브 방어선 부재**: `hair bun on top of head`, `multiple beauty marks` 차단 태그 없음.

### 6.3 영구 대책
- 머리 가중치: `1.3` → `1.45` + 위치 명시 `positioned at nape of neck` 강화.
- 점 표현: `single beauty mark directly under left eye` (near cheek 제거, directly 추가).
- 네거티브 추가: `((hair bun on top of head, high hair bun, bun on crown:1.5))`, `((multiple beauty marks, beauty marks on neck, beauty mark on chin:1.5))`.

---

## 7. [INC-20261006-03] `clean pale skin` 창백한 얼굴 과렌더링

### 7.1 사건 개요
- **증상**: xia 및 oes 캐릭터에서 피부가 병적으로 창백하게 렌더링됨.

### 7.2 근본 원인 분석
- `clean pale skin`의 `pale`이 Illustrious 계열 모델에서 혈색 없는 창백함으로 과해석됨.

### 7.3 영구 대책
- `clean pale skin` → `fair skin with healthy complexion` 교체.
- `캐릭터제작규칙.md` 권장 표현 목록에 `fair skin with healthy complexion` 추가.

---

## 8. [INC-20261006-04] 포즈 #041 `cum pool` 태그 초록 배경 생성

### 8.1 사건 개요
- **증상**: 포즈 #041 정상위절정 생성 시 배경이 초록색으로 렌더링됨.

### 8.2 근본 원인 분석
- `cum pool` 태그의 `pool`이 Illustrious 계열에서 수영장/물웅덩이로 오해석 → 초록 배경(수초/풀밭) 생성.

### 8.3 영구 대책
- `cum pool` → `cum puddle on sheets, cum stain on bedsheets` 교체.
- `캐릭터제작규칙.md` 2.4항에 `pool` 어휘 금지 및 `puddle`, `stain` 대체어 규칙 명문화 (기존 등재 확인).

---

## 9. [INC-20261006-05] 포즈 #056 남성 2명 등장

### 9.1 사건 개요
- **증상**: 포즈 #056 스탠딩섹스에서 여성 1명 + 남성 1명이 정상인데, 남성이 2명 생성됨.

### 9.2 근본 원인 분석
- 모브 주입 로직이 포즈 프롬프트의 `1girl` 태그 없이 실행되어 2명의 남성 모브를 생성.

### 9.3 영구 대책
- 포즈 DB #056에 `1girl` 명시 및 네거티브에 `(2boys:1.5), (multiple boys:1.5)` 추가.

1. [INC-20261004-01] 포즈 #014(유혹) 메인 의상 탈의 파손

### 1.1 사건 개요 (Summary)
- **증상**: 감정/상호작용 씬 #014(유혹) 에셋 생성 시, 캐릭터가 입고 있던 기본 메인 의상(스웨터, 교복, 원피스 등)이 의도치 않게 완전히 벗겨져 속옷이나 피부가 노출되는 결함 발생.
- **영향 범위**: `projects/man/` 로스터의 여성 캐릭터 5인 전체.

### 1.2 근본 원인 분석 (Root Cause Analysis - 5 Whys)
1. *왜 옷이 벗겨졌는가?* ➔ 포즈 DB 014번에 가슴골과 쇄골을 지나치게 강조하는 노출 태그가 포함되어 있었음.
2. *왜 캐릭터의 메인 의상이 버티지 못했는가?* ➔ 캐릭터 JSON의 메인 의상 태그 가중치가 낮거나, 포즈 DB의 노출 프롬프트가 의상 속성을 덮어씌움(Overriding).
3. *왜 이런 프롬프트가 들어갔는가?* ➔ '유혹'의 연출 의도를 '양손을 가슴에 모으는 여성스러운 포즈'가 아니라 '신체 노출'로 모델이 잘못 해석함.

### 1.3 긴급 조치 및 영구 대책 (Mitigation & Prevention)
- **긴급 조치**: 포즈 014의 프롬프트를 `hands gently clasping together near chest, softly resting fingers against clothes, modest seductive gesture, keeping outfit intact`로 전면 교체 후 5개 캐릭터 에셋 강제 재생성(`--overwrite`).
- **영구 방지책**: [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md) 3.4.2항에 **#014 유혹 연출 황금 공식 (양손 가슴 모으기 & 의상 보존 불변식)** 명문화.

---

## 2. [INC-20261004-02] 포즈 #019(키스) 입술 왜곡 및 구도 불일치

### 2.1 사건 개요 (Summary)
- **증상**: 키스/뽀뽀를 요청하는 포즈 #019에서 입술이 부자연스럽게 비틀리거나, 눈을 번쩍 뜨고 정면을 응시하여 몰입도를 심각하게 해치는 렌더링 결과 발생.
- **영향 범위**: `projects/man/assets/*_019.webp` 전체.

### 2.2 근본 원인 분석
- 단순한 `kiss, closed mouth, blush` 키워드만으로는 모델이 2D 애니메이션 특유의 '상체를 앞으로 기울이고 눈을 감은 채 입술을 살짝 오므리는 뽀뽀 표정'을 이해하지 못함.
- 카메라 앵글이 수평 정면 샷으로 고정되어 레퍼런스 구도(살짝 위에서 내려다보는 밀착 각도)와 불일치.

### 2.3 영구 방지책
- 레퍼런스 이미지 기반 황금 태그 세트 확립:
  - `(closed eyes:1.15), (pucker lips:1.15), softly protruding lips for a kiss, leaning forward towards viewer, intimate close-up, warm blush across cheeks and nose bridge`.
- [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md) 3.4.1항에 수록 완료.

---

## 3. [INC-20261003-01] 젠잇 JSX 라이트 모드 글씨 가시성 파손

### 3.1 사건 개요 (Summary)
- **증상**: 젠잇 웹 플랫폼에서 다크 모드에서는 정상 보이던 상태창 UI가, 라이트 모드(흰색 배경)로 전환 시 턴 숫자, 호감도 수치, 속마음 텍스트가 연두색/파스텔톤으로 표기되어 완전히 투명해지는 현상 발생.

### 3.2 근본 원인 분석
- CSS `@media (prefers-color-scheme)`나 클래스 분기가 젠잇 샌드박스 보안 정책상 차단됨.
- 단순 고정 컬러(`#80ffaa` 등)를 사용하여 흰색 배경(`#ffffff`)과의 명도 대비(Contrast Ratio)가 1.2:1 수준으로 붕괴됨.

### 3.3 영구 방지책
- 젠잇 공식 색상 함수인 `light-dark(라이트색, 다크색)` 도입.
- 모든 핵심 수치와 라벨의 텍스트 색상을 **`color: "light-dark(#000000, #ffffff)"`** 및 `fontWeight: "700~800"`으로 검정색 강제 고정.
- [`frameworks/genit/UNIVERSAL_STATUS.jsx`](frameworks/genit/UNIVERSAL_STATUS.jsx)에 표준 코드로 내장 완료.

---

## 4. [INC-20261002-01] 파이프라인 T34b 금지 네거티브 충돌 버그

### 4.1 사건 개요 (Summary)
- **증상**: 후반부 샤워 씬 및 스킨십 씬에서 물방울이나 땀, 액체 연출이 완전히 삭제되어 건조한 마네킹처럼 렌더링되거나 파이프라인 자체 진단(`T34b`)에서 오류 반환.

### 4.2 근본 원인 분석
- 캐릭터 JSON의 `negative` 프롬프트에 관습적으로 들어간 **`sweat`, `perspiration`, `liquid`, `splatter`** 4개 단어가 포즈 DB의 물방울/체액 연출을 강제로 지워버림.

### 4.3 영구 방지책
- 4개 단어를 네거티브 금지어로 지정하고, 원치 않는 요소는 포지티브 프롬프트에서 조절하도록 룰 제정.
- 파이프라인 자동 진단기(`--test`)에 네거티브 금지어 검출 로직 내장 완료.
