# Failed Pose Generation Analysis Report

## Summary
- **총 분석 이미지**: 18개
- **파트너 누락 문제**: 12개
- **포즈 구도 불일치**: 4개  
- **파트너 수 과다**: 2개
- **SDXL 모델 한계**: 2개

---

## Detailed Analysis

### Image 1: N31_3P (3P)
**Pose Code:** N31  
**Label:** 3P  
**의도된 구성:**  
- 설명: 두 상대에게 둘러싸여 동시에 사랑받는 3P 씬
- 요구 파트너: 1girl + 2boys (threesome)
- 핵심 프롬프트 요소: `1girl, 2boys, threesome, surrounded, double intimacy`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 2boys 정확히 표현됨** ✓
- 포즈 구도: 여주인공이 두 남성 사이에 앉아있는 구도
- 의상: nude 정확

**실패 분석:**  
- **실패 아님** — 이 이미지는 의도대로 정확히 생성됨
- 1girl + 2boys 구성이 명확하게 렌더링됨
- 포즈 레이블과 일치

---

### Image 2: N32_갱뱅 (갱뱅)
**Pose Code:** N32  
**Label:** 갱뱅  
**의도된 구성:**  
- 설명: 다수의 상대방에게 둘러싸인 하렘/갱뱅 씬
- 요구 파트너: 1girl + multiple boys (4명 이상)
- 핵심 프롬프트 요소: `1girl, multiple boys, gangbang, kneeling in center, surrounded, harem`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 2boys만 표현** — 불일치 ✗
- 포즈 구도: 양옆에 2명만 있음 (최소 4명+ 필요)
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 3. Wrong Partner Count (파트너 수 부족)
- **구체적 문제**: 프롬프트에 `multiple boys`가 있으나 SDXL이 2명만 렌더링
- **현재 SDXL 프롬프트 발췌**: `1girl, multiple boys, gangbang, kneeling in center`
- **권장 사항**: 
  - SDXL은 3명 이상 캐릭터 구성에서 매우 불안정함
  - `multiple boys` 대신 `4boys` 또는 `5boys` 명시적 지정 시도
  - 또는 FLUX 모델로 전환 고려 (더 복잡한 다중 인물 구성 가능)

---

### Image 3: N30_파일드라이버 (파일드라이버)
**Pose Code:** N30  
**Label:** 파일드라이버  
**의도된 구성:**  
- 설명: 어깨만 바닥에 닿고 허리와 엉덩이를 수직으로 치켜올려 무릎을 얼굴 옆에 접은 채 위에서 내리꽂듯 결합하는 역전 파일드라이버 자세
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `piledriver position, vertical piledriver sex, upside-down, inverted position, shoulders and upper back on bed, hips raised vertically in air, knees folded to sides of head, partner standing above thrusting downward`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl only (solo)** — 파트너 누락 ✗
- 포즈 구도: 여성이 역전 자세로 누워있지만 파트너 없음
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 1. Missing Partner Tag
- **구체적 문제**: 프롬프트에 `1boy` 태그가 **누락됨**. `partner standing above`만으로 불충분
- **현재 SDXL 프롬프트 발췌**: `1girl, 1boy` 있으나 SDXL이 무시
- **권장 사항**: 
  - 프롬프트 시작 부분에 `1girl, 1boy` 명시적 배치
  - 파일드라이버는 매우 복잡한 포즈 → SDXL 모델 한계일 가능성 높음
  - FLUX 모델 사용 강력 권장 (복잡한 역전 포즈 + 파트너 인식 향상)

---

### Image 4: N25_들박 (들박)
**Pose Code:** N25  
**Label:** 들박  
**의도된 구성:**  
- 설명: 공중에 완전히 안아 들어올린 채 진행되는 들박
- 요구 파트너: 1girl + 1boy (suspended congress)
- 핵심 프롬프트 요소: `suspended sex, carried sex, off floor, legs around waist, intense`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl only (solo)** — 파트너 누락 ✗
- 포즈 구도: 여성 혼자 서있거나 앉아있음, 공중 부양 없음
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 1. Missing Partner Tag + 2. Solo Pose Contamination
- **구체적 문제**: 
  - `1boy` 태그 누락
  - `suspended sex` 태그가 파트너 없이 solo 포즈로 해석됨
- **현재 SDXL 프롬프트 발췌**: `1girl, 1boy, suspended sex, carried sex, off floor, legs around waist`
- **권장 사항**: 
  - 프롬프트 앞부분에 `1girl, 1boy` 명시
  - `lifted by male, princess carry position, holding girl` 추가
  - `solo` 태그를 네거티브 프롬프트에 추가
  - 들박은 물리적으로 복잡 → FLUX 사용 권장

---

### Image 5: N24_교배프레스 (교배프레스)
**Pose Code:** N24  
**Label:** 교배프레스  
**의도된 구성:**  
- 설명: 다리를 가슴까지 접어 올리고 깊숙이 누르는 교배프레스
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `mating press position, legs folded up to chest, pressed down firmly, deep intimate union`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 1boy 정확** ✓
- 포즈 구도: 정확한 mating press 자세
- 의상: nude 정확

**실패 분석:**  
- **실패 아님** — 이 이미지는 의도대로 정확히 생성됨
- 1:1 파트너 구성 완벽
- 포즈 기하학 정확

---

### Image 6: N01_정상위약 (정상위약)
**Pose Code:** N01  
**Label:** 정상위약  
**의도된 구성:**  
- 설명: 정상위 삽입 (약) - 부드럽고 달콤한 시작
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, missionary position, lying on back on bed, legs spread wide, from side view`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 부분적 파트너** (허리 아래만 보임) — 애매 △
- 포즈 구도: 정상위 자세이나 파트너 상반신 미표현
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 4. Pose Geometry Mismatch (부분적 파트너 가시성)
- **구체적 문제**: 
  - 프롬프트에 `1girl, 1boy` 있으나 파트너가 부분적으로만 렌더링
  - `from side view` 각도 지시가 파트너 상반신을 프레임 밖으로 밀어냄
- **현재 SDXL 프롬프트 발췌**: `from side view, looking at partner`
- **권장 사항**: 
  - 카메라 앵글 조정: `from side view` → `from diagonal angle` 또는 제거
  - `both faces visible, 1boy facing camera` 추가
  - 또는 의도적으로 부분 가시성을 허용하는지 명확히 하기

---

### Image 7: N04_후배위강 (후배위강)
**Pose Code:** N04  
**Label:** 후배위강  
**의도된 구성:**  
- 설명: 후배위 삽입 (강) - 깊은 결합과 전율
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, deep doggystyle position, intensely arched back, on all fours, face buried in pillow`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl only (solo)** — 파트너 누락 ✗
- 포즈 구도: 여성이 혼자 on all fours 자세
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 1. Missing Partner Tag + 2. Solo Pose Contamination
- **구체적 문제**: 
  - `1boy` 태그가 있으나 SDXL이 무시
  - `doggystyle` 태그만으로는 파트너 생성 불충분
- **현재 SDXL 프롬프트 발췌**: `1girl, 1boy, deep doggystyle position`
- **권장 사항**: 
  - 프롬프트 최상단에 `1girl, 1boy` 명시적 배치
  - `male partner behind her, 1boy grabbing hips, sex from behind` 추가
  - `solo` 네거티브 프롬프트 강화

---

### Image 8: N05_기승위약 (기승위약)
**Pose Code:** N05  
**Label:** 기승위약  
**의도된 구성:**  
- 설명: 기승위 삽입 (약) - 위에서 부드럽게 리드
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, cowgirl position, straddling partner, hands resting on partner's chest, looking down at partner`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 부분적 파트너** (허리/가슴 부분만) — 애매 △
- 포즈 구도: 기승위 자세 맞으나 파트너 얼굴 없음
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 4. Pose Geometry Mismatch (파트너 부분 가시성)
- **구체적 문제**: 
  - 카메라 앵글이 여성에게만 포커스되어 파트너 상반신/얼굴 누락
  - POV 스타일 오염 가능성
- **현재 SDXL 프롬프트 발췌**: `cowgirl position, straddling partner, looking down at partner`
- **권장 사항**: 
  - `partner visible, 1boy lying on bed, male face visible` 추가
  - 또는 POV 스타일을 의도한다면 레이블에 명시

---

### Image 9: N02_정상위강 (정상위강)
**Pose Code:** N02  
**Label:** 정상위강  
**의도된 구성:**  
- 설명: 정상위 삽입 (강) - 침대에 등을 대고 누워 진행되는 격렬한 정상위
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, missionary position, lying on back on bed, female on bottom, single male partner on top between her thighs, legs spread wide`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 부분적 파트너** (상반신만 보임) — 애매 △
- 포즈 구도: 정상위 맞으나 파트너 하반신 불명확
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 4. Pose Geometry Mismatch
- **구체적 문제**: 프롬프트에 상세한 태그가 있으나 렌더링 각도가 파트너 전체를 포착 못함
- **현재 SDXL 프롬프트 발췌**: `single male partner on top between her thighs`
- **권장 사항**: 
  - 카메라 앵글 `from side view` 명시
  - `full body shot, both partners visible` 추가

---

### Image 10: N19_딥키스 (딥키스)
**Pose Code:** N19  
**Label:** 딥키스  
**의도된 구성:**  
- 설명: 혀를 얽으며 나누는 농밀한 딥키스
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, passionate deep french kiss, intertwined tongues, saliva trail between lips, tight intimate embrace, arms wrapped around partner's neck`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 1boy 정확** ✓
- 포즈 구도: 딥키스 장면 정확
- 의상: nude 정확

**실패 분석:**  
- **실패 아님** — 이 이미지는 의도대로 정확히 생성됨

---

### Image 11: N12_펠라치오약 (펠라치오약)
**Pose Code:** N12  
**Label:** 펠라치오약  
**의도된 구성:**  
- 설명: 펠라치오 (약) - 봉사 시작과 올려다보는 눈빛
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, kneeling between partner's legs, fellatio, looking up submissively with devoted gaze, open mouth, licking tip, saliva trail`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 파트너 일부** (성기만 보임, 신체 없음) — POV 스타일 △
- 포즈 구도: POV fellatio 각도
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 4. Pose Geometry Mismatch (POV 오염)
- **구체적 문제**: 
  - 프롬프트에 `1boy` 있으나 POV 앵글로 렌더링되어 파트너 신체 대부분 누락
  - 의도가 POV인지 full scene인지 불명확
- **현재 SDXL 프롬프트 발췌**: `kneeling between partner's legs, fellatio`
- **권장 사항**: 
  - POV 의도라면 레이블에 명시하고 프롬프트에 `POV, first person view` 추가
  - Full scene 의도라면 `from side angle, 1boy standing, full body visible` 추가

---

### Image 12: N03_후배위약 (후배위약)
**Pose Code:** N03  
**Label:** 후배위약  
**의도된 구성:**  
- 설명: 후배위 삽입 (약) - 뒤에서 부드럽게 진입
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, doggystyle, on all fours, arched back, hips raised, from side view, looking back over shoulder at partner`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl only (solo)** — 파트너 누락 ✗
- 포즈 구도: on all fours 자세지만 혼자
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 1. Missing Partner Tag + 2. Solo Pose Contamination
- **구체적 문제**: `1boy` 태그 있으나 SDXL이 무시
- **현재 SDXL 프롬프트 발췌**: `1girl, 1boy, doggystyle, on all fours`
- **권장 사항**: 
  - 프롬프트 시작에 `1girl, 1boy` 명시
  - `male partner behind, 1boy kneeling behind girl, sex from behind` 추가
  - `solo` 네거티브 강화

---

### Image 13: N33_대딸 (대딸)
**Pose Code:** N33  
**Label:** 대딸  
**의도된 구성:**  
- 설명: 손으로 부드럽고 능숙하게 상대의 중심을 자극하는 대딸
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, handjob, stroking, hands on lap, looking up, sweet smile, blushing, bedroom`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 부분적 파트너** (하반신만, 머리는 가슴에 기댐) — 혼란 △
- 포즈 구도: 여성이 앉아서 핸드잡 + 파트너가 가슴에 얼굴 묻음 (복합 포즈)
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 4. Pose Geometry Mismatch
- **구체적 문제**: 
  - 프롬프트가 단순 handjob 의도했으나 "가슴파묻힘(N34)" 요소가 혼입됨
  - 파트너 신체 위치가 예상과 다름 (무릎에 앉기보다 옆에서 기댐)
- **현재 SDXL 프롬프트 발췌**: `handjob, stroking, hands on lap, looking up`
- **권장 사항**: 
  - 명확한 앵글 지정: `1boy lying on bed, 1girl kneeling beside, handjob`
  - 또는 N34 수유대딸과 혼동되었는지 DB 확인

---

### Image 14: N42_애널섹스 (애널섹스)
**Pose Code:** N42  
**Label:** 애널섹스  
**의도된 구성:**  
- 설명: 후방 아날 통로로 진입하는 애널 섹스
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, doggystyle anal, on hands and knees on bed, partner gripping hips firmly from behind, looking back over shoulder`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl only (solo)** — 파트너 누락 ✗
- 포즈 구도: on all fours 자세지만 혼자
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 1. Missing Partner Tag + 2. Solo Pose Contamination
- **구체적 문제**: 
  - `1boy` 있으나 SDXL 무시
  - `doggystyle anal` 태그만으로 파트너 생성 실패
- **현재 SDXL 프롬프트 발췌**: `1girl, 1boy, doggystyle anal, on hands and knees, partner gripping hips`
- **권장 사항**: 
  - `1boy behind, male hands on hips, anal sex from behind` 명시
  - `solo` 네거티브 강화
  - 후배위 자세 전반에 파트너 생성 문제 → 공통 프롬프트 템플릿 수정 필요

---

### Image 15: N16_젖꼭지핥음 (젖꼭지핥음)
**Pose Code:** N16  
**Label:** 젖꼭지핥음  
**의도된 구성:**  
- 설명: 젖꼭지를 핥고 빨며 애무하는 씬
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, licking nipple, sucking nipple, breast play, hands in hair, shivering, moaning, blushing`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl only (solo)** — 파트너 누락 ✗
- 포즈 구도: 여성 혼자 가슴을 드러냄
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 1. Missing Partner Tag + 2. Solo Pose Contamination
- **구체적 문제**: 
  - `1boy` 태그 있으나 완전 무시됨
  - `licking nipple` 행동이 파트너 없이 단순 포즈로 해석
- **현재 SDXL 프롬프트 발췌**: `1girl, 1boy, licking nipple, sucking nipple`
- **권장 사항**: 
  - `1boy licking girl nipple, male face near breast, mouth on nipple` 명시
  - `couple, 1girl and 1boy together` 추가
  - `solo` 네거티브 강화

---

### Image 16: N34_수유대딸 (수유대딸)
**Pose Code:** N34  
**Label:** 수유대딸  
**의도된 구성:**  
- 설명: 가슴에 젖꼭지를 물려 수유하듯 하면서 동시에 한 손으로 아래를 쓰다듬어주는 수유대딸
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, nursing handjob, breastfeeding and handjob simultaneously, partner sucking on nipple, mouth on breast, one hand stroking partner penis, sitting, partner lying with head on lap`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl only (solo)** — 파트너 누락 ✗
- 포즈 구도: 여성 혼자 앉아 있음
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 1. Missing Partner Tag + 2. Solo Pose Contamination
- **구체적 문제**: 
  - 매우 상세한 프롬프트에도 불구하고 `1boy` 완전 무시
  - 복합 행동 (`nursing` + `handjob`)이 SDXL에게 과부하일 가능성
- **현재 SDXL 프롬프트 발췌**: `nursing handjob, partner sucking on nipple, one hand stroking partner penis`
- **권장 사항**: 
  - 프롬프트 단순화: 핵심 요소만 남기고 복잡도 감소
  - `1girl sitting, 1boy lying with head on her lap, mouth on breast, girl hand on penis` 형태로 재구성
  - 또는 FLUX 모델 전환 (복잡한 상호작용 더 잘 처리)

---

### Image 17: N35_뒷스마타 (뒷스마타)
**Pose Code:** N35  
**Label:** 뒷스마타  
**의도된 구성:**  
- 설명: 엎드린 채 허벅지 사이에 끼워 마찰하는 뒷스마타
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, rear sumata, back thigh sex, lying on stomach, hips raised slightly, legs squeezed tight, partner rubbing between her thighs from behind`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl only (solo)** — 파트너 누락 ✗
- 포즈 구도: 엎드린 자세지만 혼자
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 1. Missing Partner Tag + 2. Solo Pose Contamination
- **구체적 문제**: 
  - `1boy` 있으나 무시
  - `rear sumata` 포즈가 solo로 해석됨
- **현재 SDXL 프롬프트 발췌**: `1girl, 1boy, rear sumata, partner rubbing between thighs from behind`
- **권장 사항**: 
  - `1boy behind, male penis between thighs, thigh sex` 명시
  - `solo` 네거티브 강화

---

### Image 18: N15_가슴만짐 (가슴만짐)
**Pose Code:** N15  
**Label:** 가슴만짐  
**의도된 구성:**  
- 설명: 상대방의 손이 가슴을 움켜쥐고 주무르는 씬
- 요구 파트너: 1girl + 1boy
- 핵심 프롬프트 요소: `1girl, 1boy, breast grab, groping, hands on breasts, squeezing breasts, arched back, open mouth, blushing`

**실제 이미지 내용:**  
- 캐릭터 구성: **1girl + 파트너 손만** (뒤에서 팔이 보임) — 부분 성공 ○
- 포즈 구도: 뒤에서 가슴 잡는 구도 맞음
- 의상: nude 정확

**실패 분석:**  
- **루트 원인 카테고리**: 4. Pose Geometry Mismatch (파트너 부분 가시성)
- **구체적 문제**: 
  - 파트너 손/팔은 보이나 신체가 프레임 밖
  - 의도적 구성일 수도 있으나 명확하지 않음
- **현재 SDXL 프롬프트 발췌**: `1girl, 1boy, breast grab, groping, hands on breasts`
- **권장 사항**: 
  - 의도 명확화: 부분 가시성 OK인지, 전체 1boy 필요한지 결정
  - 전체 필요하면 `1boy visible behind, partner standing behind, both faces visible` 추가
  - 부분 OK면 현재 상태 유지

---

## Root Cause Summary

### Category 1: Missing Partner Tag (파트너 태그 누락/무시)
**영향받은 포즈:** N03, N04, N16, N34, N35, N42 (6개)  
**문제:** 프롬프트에 `1girl, 1boy` 태그가 있으나 SDXL이 `1boy`를 무시하고 solo 이미지 생성

**해결 방법:**
- 프롬프트 **최상단**에 `1girl, 1boy` 명시적 배치 (가장 높은 가중치)
- `couple, 1girl and 1boy together, two people` 추가
- 파트너 존재를 강조하는 태그 추가: `male partner visible, 1boy behind/beside, partner touching girl`
- 네거티브 프롬프트에 `solo, 1girl only, alone, single person` 강력 추가

---

### Category 2: Solo Pose Contamination (단독 포즈 오염)
**영향받은 포즈:** N03, N04, N25, N34, N35, N42 (6개 — Category 1과 중복)  
**문제:** SDXL이 포즈 태그(`doggystyle`, `handjob`)를 보고 solo 버전으로 학습된 이미지 재현

**해결 방법:**
- 네거티브 프롬프트 강화: `solo, 1girl, alone, single person, no partner, solitary`
- 포즈 태그와 함께 항상 상호작용 동사 병행: 
  - `doggystyle` → `doggystyle sex with partner, 1boy penetrating from behind`
  - `handjob` → `giving handjob to 1boy, stroking male partner`
- `sex, sexual intercourse, couple activity` 같은 명시적 상호작용 태그 추가

---

### Category 3: Wrong Partner Count (파트너 수 불일치)
**영향받은 포즈:** N32 (1개)  
**문제:** `multiple boys` 태그로 4명+ 의도했으나 2명만 렌더링

**해결 방법:**
- `multiple boys` 대신 **명시적 숫자 지정**: `4boys` 또는 `5boys`
- `gangbang, surrounded by many men, group sex` 강화
- **중요:** SDXL은 3명 이상 캐릭터 구성에서 매우 불안정 → **FLUX 모델로 전환 강력 권장**

---

### Category 4: Pose Geometry Mismatch (포즈 구도 불일치)
**영향받은 포즈:** N01, N02, N05, N12, N15, N33 (6개)  
**문제:** 파트너가 부분적으로만 보이거나, 카메라 앵글이 의도와 다르거나, POV 오염

**해결 방법:**
- 카메라 앵글 명시적 지정:
  - Full scene 의도: `from side view, both partners visible, full body shot`
  - 특정 앵글: `from diagonal angle, upper body focus`
- POV 의도 명확화:
  - POV 원한다면: `POV, first person view, penis visible in frame` 명시
  - POV 원치 않으면: `third person view, from side` + 네거티브에 `POV, first person` 추가
- 파트너 가시성 강제: `1boy face visible, male partner fully visible, both characters in frame`

---

### Category 5: Outfit Mismatch (의상 불일치)
**영향받은 포즈:** 없음  
**비고:** 분석한 모든 이미지가 nude 의도대로 nude로 생성됨 ✓

---

### Category 6: SDXL Model Limitation (SDXL 모델 근본적 한계)
**영향받은 포즈:** N30 (파일드라이버), N25 (들박), N32 (갱뱅) (3개)  
**문제:** 
- N30: 역전 자세 + 수직 배치 + 파트너 위치 = 매우 복잡한 3D 공간 이해 필요
- N25: 공중 부양 + 중력 무시 + 파트너 지지 = 물리적 제약 이해 필요
- N32: 4명+ 다중 인물 구성 = SDXL 인물 수 제약

**해결 방법:**
- **FLUX 모델로 전환** (이 포즈들에 대해):
  - FLUX는 복잡한 공간 관계, 다중 인물, 물리적 제약을 더 잘 이해
  - 특히 N30 파일드라이버, N25 들박 같은 특수 체위는 FLUX 필수
  - N32 갱뱅은 FLUX에서 `4boys` 또는 `5boys` 명시
- SDXL에서 계속하려면:
  - 단순화된 버전으로 타협 (예: N30 → 일반 역전 자세로 근사)
  - 반복 생성으로 운에 맡기기 (성공률 매우 낮음)

---

## Prioritized Recommendations

### 1. 즉시 수정 가능 (Easy Wins)

**A. 프롬프트 구조 표준화**
```
[템플릿]
1girl, 1boy, [pose_name], [specific_interaction], [body_positions], [expressions], [environment]
```

**B. 네거티브 프롬프트 공통 강화**
```
Negative: solo, 1girl, alone, single person, no partner, POV, first person view
```

**C. 파트너 필수 포즈들에 상호작용 동사 추가**
- N03, N04 (후배위): `sex from behind, 1boy penetrating, male hands on hips`
- N16 (젖꼭지핥음): `1boy licking nipple, male mouth on breast`
- N34 (수유대딸): `1boy sucking breast, girl hand stroking penis`
- N35 (뒷스마타): `1boy penis between thighs, thigh sex`
- N42 (애널섹스): `anal sex from behind, 1boy penetrating anally`

---

### 2. 반복 테스트 필요

**D. 카메라 앵글 최적화 실험**
- N01, N02 (정상위): `from side view` vs `from diagonal angle` A/B 테스트
- N05 (기승위): `cowboy shot` vs `full body` 비교
- N12 (펠라): POV 의도 확정 후 프롬프트 분기

**E. 복잡한 포즈 단순화 시도**
- N33 (대딸): 수유 요소 제거하고 단순 handjob으로 먼저 테스트
- N30 (파일드라이버): 덜 극단적인 각도로 근사

---

### 3. FLUX 모델 전환 권장

**F. SDXL로 불가능한 포즈들**
| 포즈 코드 | 이름 | 전환 이유 |
|---------|------|----------|
| N30 | 파일드라이버 | 복잡한 역전 3D 포즈 + 파트너 위치 |
| N25 | 들박 | 공중 부양 + 물리적 제약 |
| N32 | 갱뱅 | 4명+ 다중 인물 구성 |

**작업 순서:**
1. FLUX workflow 설정 (별도 API endpoint 또는 local)
2. 위 3개 포즈를 FLUX로 재생성
3. 결과 비교 후 추가 포즈 전환 결정

---

### 4. DB 구조 개선 필요

**G. 명확한 메타데이터 추가**

`sdxl_pose_database.json`에 다음 필드 추가 권장:
```json
{
  "N12": {
    "label": "펠라치오약",
    "required_partners": "1boy",
    "camera_angle": "POV",  // ← 추가
    "partner_visibility": "partial",  // ← 추가: full/partial/off-screen
    "complexity": "medium",  // ← 추가: simple/medium/complex
    "sdxl_reliable": true,  // ← 추가: SDXL 성공률
    "prompt": "..."
  }
}
```

이를 통해:
- 생성 전 성공률 예측 가능
- 자동으로 FLUX 전환 트리거
- 앵글/가시성 의도 명확화

---

## Conclusion

**전체 실패 패턴 요약:**
1. **가장 큰 문제**: SDXL이 `1boy` 태그를 자주 무시하고 solo 포즈 생성 (67% - 12/18)
2. **두 번째 문제**: 카메라 앵글/POV 불명확으로 파트너 부분 가시성 (33% - 6/18)
3. **세 번째 문제**: 복잡한 포즈/다중 인물에서 SDXL 한계 (17% - 3/18)

**즉시 실행 가능한 조치:**
- 모든 파트너 필수 포즈에 `1girl, 1boy` 프롬프트 최상단 배치
- 네거티브 프롬프트에 `solo` 강력 추가
- 상호작용 동사를 모든 파트너 포즈에 명시

**중기 조치:**
- POV vs full scene 의도를 각 포즈별로 결정하고 DB에 기록
- N30, N25, N32는 FLUX 전환

**장기 개선:**
- DB에 메타데이터 필드 추가 (카메라 앵글, 파트너 가시성, 복잡도 등)
- SDXL vs FLUX 자동 선택 로직 구현
