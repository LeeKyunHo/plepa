# Phase 1 파트너 가시율 개선 계획 (SDXL 솔로 이미지 67% 억제)

## 배경 및 목표
- **현재 문제**: SDXL이 `1boy` 태그를 무시하고 solo 이미지를 67% 빈도로 생성
- **목표**: `(solo:1.4), (single person:1.4), (one person:1.3)` 네거티브 주입으로 파트너 가시율 80% 이상 달성
- **범위**: 13개 우선 포즈 프롬프트 개선 + 엔진 레벨 솔로 억제 자동화

## 핵심 제약
1. `PoseService.load_pose_db()`는 `sdxl_pose_database.json` 로드 후 `data/themes/adult.json`으로 덮어씀
   → 두 파일 모두 동기화 필수 (adult.json이 런타임 최상위 우선순위)
2. 현재 `assemble_sdxl_prompt()`의 `is_two_person` 변수 (라인 349-353)에서 이미 2인 판별 구현됨
3. 기존 네거티브 제거 로직(남성 차단, 멀티 차단)은 절대 손상 금지
4. 무협(wuxia) 세계관, 탈의, 체크포인트 분기 로직 보존

## 대상 파일 및 수정 위치

### 파일 1: `c:\Users\rbsgh\plepa\plepa_engine\prompt_builder.py`

**작업**: 2인 포즈 감지 시 네거티브에 솔로 억제 태그 자동 주입

**위치**: 라인 446-453 구간 (현재 `if is_two_person:` 2인 씬 네거티브 정제 블록)

**수정 로직**:
- 라인 446 `if is_two_person:` 블록 직후 (라인 454 경계)에 새 로직 추가
- 조건: `if is_two_person`이 참이면
- 동작: `negative_prompt` 문자열에 `(solo:1.4), (single person:1.4), (one person:1.3)` 추가

**구체적 패치**:
```python
# [패치 SOLO] 2인 씬에서 남성 누락(solo) 방지를 위한 네거티브 강제 주입
if is_two_person:
    # 기존 블록 (라인 448-453) - 그대로 유지
    negative_prompt = re.sub(...)
    # ... 기존 4줄 ...
    
    # 새 추가: 솔로 억제 태그 주입
    solo_inhibit = "(solo:1.4), (single person:1.4), (one person:1.3)"
    if solo_inhibit not in negative_prompt:
        negative_prompt = f"{negative_prompt}, {solo_inhibit}"
```

**검증**:
- 라인 라인 라인 번호 확인: `grep -n "if is_two_person:" c:\Users\rbsgh\plepa\plepa_engine\prompt_builder.py`
- 기존 정제 4줄(1boy, male, masculine, multiple characters 제거) 유지 확인
- 솔로 억제 태그 중복 방지 로직 검증

---

### 파일 2: `c:\Users\rbsgh\plepa\data\themes\adult.json`

**작업**: 13개 우선 포즈의 `sdxl_prompt_female` 개선 (파트너 상호작용, 시선, 앵글 3요소 강화)

**13개 포즈 및 개선 규칙**:

#### 그룹 A: 파트너 누락 심각 (8개) — 신체 접촉 + 시선 + 앵글 명시화
1. **N03 (후배위약)**: 
   - 현재: `looking back over shoulder at partner, heavy body blush, ...`
   - 개선: `partner gripping hips firmly from behind, looking back over shoulder at partner` 추가
   - 최종: `1girl, 1boy, ((doggystyle, on all fours:1.3)), ((arched back, hips raised:1.25)), ((partner gripping hips firmly from behind:1.2)), from side view, looking back over shoulder at partner, heavy body blush, intensely flushed cheeks, parted lips gasping, teary gentle pleasure gaze, soft bedding`

2. **N04 (후배위강)**:
   - 현재: `partner gripping hips firmly from behind` 이미 있음
   - 개선: 그대로 유지 (이미 충분함)

3. **N05 (기승위약)**:
   - 현재: `hands resting on partner's chest`
   - 개선: 시선과 앵글 명시화: `looking down at partner with seductive smile` 확인, `upright posture` 유지
   - 현재 프롬프트가 이미 충분하므로 유지

4. **N06 (기승위강)**:
   - 현재: `leaning back, head thrown back` 있음
   - 개선: 파트너 상호작용 명시: 자체 손으로 다리 만지기 → `hands resting on own thighs` 유지
   - 현재 충분함

5. **N12 (펠라치오약)**:
   - 현재: `kneeling between partner's legs, fellatio, looking up submissively with devoted gaze`
   - 개선: `looking up submissively` 강화 및 앵글 명시 추가
   - 최종: `1girl, 1boy, ((kneeling between partner's legs, fellatio:1.35)), ((looking up submissively with deeply devoted affectionate gaze:1.3)), open mouth, licking tip, saliva trail, heavy facial blush, teary eyes, intimate tender bedroom atmosphere`

6. **N16 (젖꼭지핥음)**:
   - 현재: `licking nipple, sucking nipple, breast play, hands in hair, shivering`
   - 개선: 파트너의 손이나 입이 명시되어야 함 → `partner's mouth`/`partner's tongue` 강조
   - 최종: `1girl, 1boy, ((partner's mouth licking and sucking nipple:1.35)), ((partner's tongue teasing sensitive nipple:1.3)), ((hands tangled in partner's hair:1.25)), arched back, shivering with pleasure, moaning, heavy blush, bed`

7. **N25 (들박)**:
   - 현재: `suspended sex, carried sex, off floor, legs around waist`
   - 개선: 앵글 명시 및 상호작용 강화
   - 최종: `1girl, 1boy, ((suspended sex, carried off floor:1.3)), ((legs wrapped tightly around partner's waist:1.25)), ((partner gripping thighs firmly:1.2)), intense breathless gasps, open mouth, heavy full body blush, tears of pleasure, from front angle showing intimate union, disheveled`

8. **N34 (수유대딘)**:
   - 현재: `nursing handjob, breastfeeding and handjob simultaneously...` (이미 매우 상세함)
   - 개선: 약간의 앵글 명시 추가
   - 최종: 현재 프롬프트 유지 (이미 충분)

#### 그룹 B: 구도 불일치 (4개) — 앵글 및 시선 명시화
9. **N01 (정상위약)**:
   - 현재: `lying on back on bed, legs spread wide, from side view, looking at partner, heavy body blush`
   - 개선: `from side view` 명시 + 앵글 각도 재강조
   - 최종: `1girl, 1boy, ((missionary position:1.3)), ((lying on back on bed, legs spread wide:1.25)), ((from side view angle:1.2)), looking up at partner with soft loving gaze, heavy body blush, flushed cheeks, soft parted lips, breathless gentle expression, disheveled sheets, soft ambient bedroom light`

10. **N02 (정상위강)**:
    - 현재: `lying on back on bed, female on bottom... single male partner on top between her thighs`
    - 개선: 앵글과 응시 강화
    - 최종: `1girl, 1boy, ((missionary position:1.35)), ((lying on back on bed, female on bottom:1.35)), ((single male partner on top between her thighs:1.25)), ((from front-center view angle:1.2)), legs spread wide, completely nude, intense pleasure, arched back, open mouth, looking up intensely at partner, heavy blush, bed, disheveled sheets`

11. **N05 (기승위약)** — (다시 확인):
    - 현재 프롬프트: `cowgirl position, straddling partner... upright posture, looking down at partner`
    - 개선: 충분함 (유지)

12. **N19 (딥키스)**:
    - 현재: `deep kiss, french kiss, tongues entangled, saliva trail, completely nude, embrace`
    - 개선: 앵글 및 상호작용 명시 강화
    - 최종: `1girl, 1boy, ((passionate deep french kiss:1.35)), ((intertwined tongues, saliva trail between lips:1.3)), ((tight intimate embrace, arms wrapped around partner's neck:1.25)), completely nude, closed eyes in bliss, heavy body blush, kissing lips together, disheveled bedsheets, soft intimate lighting`

#### 그룹 C: 복합 문제 (1개) — FLUX 전환 권장
13. **N32 (갱뱅)**:
    - **주의**: 현재 SDXL 단일 패스로 다중 인물 인체 접촉 계산 매우 어려움
    - 개선 방향: FLUX 서술형으로 분리 (구현 시 FLUX 엔진으로 생성)
    - SDXL용 현재 프롬프트 유지: `1girl, multiple boys, gangbang, kneeling in center, dazed expression, heavy blush, surrounded, harem`

## 최종 개선된 프롬프트 목록

### adult.json 수정 대상 (sdxl_prompt_female 필드)

```json
{
  "N01": {
    "sdxl_prompt_female": "1girl, 1boy, ((missionary position:1.3)), ((lying on back on bed, legs spread wide:1.25)), ((from side view angle:1.2)), looking up at partner with soft loving gaze, heavy body blush, flushed cheeks, soft parted lips, breathless gentle expression, disheveled sheets, soft ambient bedroom light"
  },
  "N02": {
    "sdxl_prompt_female": "1girl, 1boy, ((missionary position:1.35)), ((lying on back on bed, female on bottom:1.35)), ((single male partner on top between her thighs:1.25)), ((from front-center view angle:1.2)), legs spread wide, completely nude, intense pleasure, arched back, open mouth, looking up intensely at partner, heavy blush, bed, disheveled sheets"
  },
  "N03": {
    "sdxl_prompt_female": "1girl, 1boy, ((doggystyle, on all fours:1.3)), ((arched back, hips raised:1.25)), ((partner gripping hips firmly from behind:1.2)), from side view, looking back over shoulder at partner, heavy body blush, intensely flushed cheeks, parted lips gasping, teary gentle pleasure gaze, soft bedding"
  },
  "N12": {
    "sdxl_prompt_female": "1girl, 1boy, ((kneeling between partner's legs, fellatio:1.35)), ((looking up submissively with deeply devoted affectionate gaze:1.3)), open mouth, licking tip, saliva trail, heavy facial blush, teary eyes, intimate tender bedroom atmosphere"
  },
  "N16": {
    "sdxl_prompt_female": "1girl, 1boy, ((partner's mouth licking and sucking nipple:1.35)), ((partner's tongue teasing sensitive nipple:1.3)), ((hands tangled in partner's hair:1.25)), arched back, shivering with pleasure, moaning, heavy blush, bed"
  },
  "N19": {
    "sdxl_prompt_female": "1girl, 1boy, ((passionate deep french kiss:1.35)), ((intertwined tongues, saliva trail between lips:1.3)), ((tight intimate embrace, arms wrapped around partner's neck:1.25)), completely nude, closed eyes in bliss, heavy body blush, kissing lips together, disheveled bedsheets, soft intimate lighting"
  },
  "N25": {
    "sdxl_prompt_female": "1girl, 1boy, ((suspended sex, carried off floor:1.3)), ((legs wrapped tightly around partner's waist:1.25)), ((partner gripping thighs firmly:1.2)), intense breathless gasps, open mouth, heavy full body blush, tears of pleasure, from front angle showing intimate union, disheveled"
  },
  "N33": {
    "sdxl_prompt_female": "1girl, 1boy, ((handjob, stroking delicately:1.3)), ((hands gripping partner firmly:1.25)), looking up with sweet bashful smile, rhythmic motion, heavy blush, bedroom, from front angle, teary blushing eyes"
  },
  "N34": {
    "sdxl_prompt_female": "1girl, 1boy, ((nursing handjob, breastfeeding and handjob simultaneously:1.35)), ((partner sucking on nipple, mouth on breast:1.3)), ((one hand stroking partner penis with delicate grip:1.35)), ((handjob while nursing:1.3)), sitting, partner lying with head on lap, completely nude, looking down with sweet maternal affectionate smile, gentle loving blush, tender bedroom intimacy"
  },
  "N35": {
    "sdxl_prompt_female": "1girl, 1boy, ((rear sumata, back thigh sex:1.35)), ((lying on stomach, hips raised slightly, legs squeezed tight:1.3)), ((partner rubbing between her thighs from behind:1.3)), thigh friction without insertion, looking back over shoulder, completely nude, flushed cheeks, heavy blush, bed"
  },
  "N42": {
    "sdxl_prompt_female": "1girl, 1boy, ((doggystyle anal, on hands and knees on bed:1.3)), ((partner gripping hips firmly from behind:1.25)), looking back over shoulder, completely nude, teary gasping face, heavy blush, bed"
  }
}
```

## 실행 순서 및 검증

### Step 1: prompt_builder.py 수정 (5분)
**파일**: `c:\Users\rbsgh\plepa\plepa_engine\prompt_builder.py`

**작업**:
1. 라인 446 `if is_two_person:` 블록 찾기
2. 라인 453 (블록 마지막) 다음에 새로운 코드 추가:
   ```python
   # [패치 SOLO] 2인 씬에서 남성 누락(solo) 방지를 위한 네거티브 강제 주입
   solo_inhibit = "(solo:1.4), (single person:1.4), (one person:1.3)"
   if solo_inhibit not in negative_prompt:
       negative_prompt = f"{negative_prompt}, {solo_inhibit}"
   ```

**검증**:
```bash
cd c:\Users\rbsgh\plepa
python -m pytest tests/ -k "test_sdxl_negative" -v  # 테스트 코드가 있으면 실행
# 또는 python 스크립트 수동 테스트로 프롬프트 생성 확인
```

### Step 2: adult.json 업데이트 (5분)
**파일**: `c:\Users\rbsgh\plepa\data\themes\adult.json`

**작업**:
1. 각 포즈(N01, N02, N03, N12, N16, N19, N25, N33, N34, N35, N42)의 `sdxl_prompt_female` 필드 교체
2. 문법 검증: JSON 괄호/따옴표 일치 확인

**검증**:
```bash
python -m json.tool c:\Users\rbsgh\plepa\data\themes\adult.json > /dev/null && echo "JSON valid"
```

### Step 3: sdxl_pose_database.json 대응 (필요시)
**확인**: `PoseService.load_pose_db()`가 adult.json으로 덮어쓰므로 별도 수정 불필요
- 단, adult.json에 없는 포즈만 sdxl_pose_database.json 참조
- 13개 대상 포즈는 모두 adult.json에 존재하므로 데이터베이스 파일 수정 불필요

### Step 4: 파일 동기화 검증
**작업**:
1. `grep -A2 '"N01"' c:\Users\rbsgh\plepa\data\themes\adult.json` 실행하여 N01 포즈 로드 확인
2. `grep -A2 '"N01"' c:\Users\rbsgh\plepa\data\sdxl_pose_database.json` 실행하여 데이터베이스 버전 확인
3. 두 파일 모두 존재하는 포즈는 adult.json 값이 우선 (런타임 덮어쓰기)

### Step 5: 통합 테스트 (10분)
**테스트 프롬프트 생성**:
```bash
cd c:\Users\rbsgh\plepa
# 스파이 프로젝트의 특정 캐릭터로 N01, N03, N12, N25 포즈 프롬프트 생성
python -c "from plepa_engine.pose_service import PoseService; from plepa_engine.prompt_builder import assemble_sdxl_prompt; print('Prompt generation test')"
```

**기대 결과**:
- `assemble_sdxl_prompt()` 2인 포즈 호출 시 `negative_prompt`에 `(solo:1.4), (single person:1.4), (one person:1.3)` 포함 확인
- adult.json 포즈 로드 시 업데이트된 `sdxl_prompt_female` 값 사용 확인

---

## 참고: 이후 Phase 2~4 준비

**Phase 2 (DB 적용)**: 개선된 13개 포즈만 `-p N01,N03,N12,N16,N19,N25,N33,N34,N35,N42 --overwrite` 재생성
**Phase 3 (테스트)**: 3그룹 × 3포즈 A/B/C 샘플 생성, 파트너 가시율 80% 검증
**Phase 4 (전체 적용)**: 모든 포즈 업데이트 및 메타데이터 문서화

---

## 실행 커맨드 요약

```bash
# 1. prompt_builder.py 수정
# (텍스트 에디터 또는 sed/patch로 라인 453 다음 삽입)

# 2. adult.json JSON 유효성 검증
python -m json.tool "c:\Users\rbsgh\plepa\data\themes\adult.json" > nul && echo "JSON valid" || echo "JSON error"

# 3. 포즈 데이터 로드 테스트
cd c:\Users\rbsgh\plepa
python -c "import json; f=open('data/themes/adult.json'); d=json.load(f); print('N01 prompt:', d['adult']['N01'].get('sdxl_prompt_female', 'NOT FOUND')[:80])"

# 4. 프롬프트 생성 시뮬레이션 (선택)
python -m pytest tests/ -v -k "prompt" 2>/dev/null || echo "No test framework found, manual test recommended"
```

---

## 예상 영향도

| 항목 | 영향 |
|------|------|
| 파트너 가시율 | 67% → 80%+ (목표) |
| 기존 solo 포즈 | 영향 없음 (is_two_person=False일 때 미적용) |
| 무협 세계관 | 영향 없음 (is_wuxia 로직 독립) |
| 성능 | 무시할 수준 (정규식 치환 1회 추가) |
| 호환성 | 100% 하위 호환성 유지 |

---

## 위험 요소 및 대응

| 위험 | 대응 |
|------|------|
| JSON 문법 오류 | `python -m json.tool` 검증 필수 |
| 기존 네거티브 로직 충돌 | solo 억제 태그 중복 확인 조건 추가 |
| 런타임 덮어쓰기 미반영 | PoseService 코드 동작 확인 (이미 검증됨) |
| 정규식 오류 | 기존 정규식 수정 금지 (새 로직만 추가) |

