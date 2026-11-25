# PLEPA ➔ KIRO 양방향 시너지 전파 및 무결성 확정 리포트

> **작성 일자**: 2026-10-16  
> **동기화 주체**: `plepa` (`c:\Users\rbsgh\plepa`) ➔ `kiro` (`C:\Users\rbsgh\kiro`)  
> **상태**: 완료 (전체 테스트 35건 100% PASS)

---

## 1. 전파 전 `plepa` 골든 스테이트(Golden State) 무결성 고정

1. **색감 과포화(Color Burn) 및 뷰파인더(`⌜ ⌝`) 완전 차단**:
   - `clamp_sdxl_weights()`: 긍정 프롬프트 상한선 `1.15`, 부정 프롬프트 상한선 `1.25`, 다중 괄호 단일화(`((...))` ➔ `(...)`) 적용 유지.
   - 단일 `CLIPTextEncode` 그래프 구조 유지 (듀얼 인코딩/중복 조건화 방지).
   - `PositiveAssemblyMutator`: `base_pos.split(" BREAK ", 1)` 구조로 캐릭터 JSON의 기본 품질 태그가 2중으로 중복 주입되지 않도록 격리 조립 보장.
   - `040`(덮쳐짐): 프롬프트 내 `camera`를 `viewer`로 안전 치환하고, `negative_add`에 `(camera frame, viewfinder, border, HUD, screen corners:1.4)`를 고정 주입하여 뷰파인더 아티팩트 원천 차단.

2. **`060`(딥키스) & `061`(알몸키스) 원본 프롬프트 복원**:
   - `060`: 구 `099`(딥키스, `required_outfit: "default"`) 및 구 `199`(오토코노코) 원본 프롬프트로 복원.
   - `061`: 구 `098`(알몸키스, `required_outfit: "nude"`) 및 구 `198`(오토코노코) 원본 프롬프트로 복원하되, 밀착 키스 씬에서 파트너를 화면 밖으로 밀어내는 구도 충돌 태그인 `(partner off-screen:1.15)`를 완벽히 제거.
   - 두 포즈 모두 성기 노출/오랄 결합 모순 차단 및 키스 분리 방지용 `negative_add` 유지.

---

## 2. `plepa` ➔ `kiro` 자동 전파 브릿지 (`scripts/sync_to_kiro.py`)

언제든 단 한 줄의 명령어로 최신 데이터와 코어 모듈을 전파할 수 있도록 브릿지 스크립트를 구현 및 실행 완료했습니다.

### [2-1] 전파 완료 항목
| 구분 | 소스 (`plepa`) | 타겟 (`kiro`) | 전파 상태 |
| :--- | :--- | :--- | :---: |
| **포즈 데이터베이스** | `data/sdxl_pose_database.json` | `pose_database.json` | **동기화 완료** (기존 DB 백업 생성) |
| **검열 엔진** | `plepa_engine/censor.py` | `generator/censor.py` | **전파 완료** (독립 실행 가능) |
| **Auto-QC 검증기** | `plepa_engine/qa_validator.py` | `generator/qa_validator.py` | **전파 완료** (독립 실행 가능) |
| **프로젝트 설정 (13개)** | `projects/*/pose_overrides.json`, `background.json` 등 | `projects/*/` | **동기화 완료** |

### [2-2] V2 에셋 2-Pass 안전 리네임 유틸리티
- `docs/POSE_MAPPING_V2.md`의 새 번호 ➔ 기존 번호 1:1 매핑을 자동 파싱.
- `{char}_{pose_code}{rest}` 및 `{pose_code}_{char}{rest}` 패턴을 모두 감지하여 총 **2,389개 에셋 리네임 대상** 식별.
- `__tmp_v2_*` 임시 접두사를 경유하는 **2-Pass 알고리즘**을 적용하여 연쇄 번호 덮어쓰기(Cascade Overwrite) 방지 보장.
- 실행 명령어:
  ```powershell
  # 시뮬레이션 모드
  python scripts/sync_to_kiro.py --dry-run
  # 실제 에셋 리네임 실행
  python scripts/sync_to_kiro.py --rename-assets
  ```

---

## 3. `kiro` ➔ `plepa` 강점 역수입 (양방향 시너지)

1. **프롬프트 태그 충돌 감지기 (`find_tag_conflicts`) 탑재**:
   - `kiro/generator/prompt.py`의 아이디어를 계승하여 `plepa_engine/prompt_pipeline.py`에 `normalize_tag`, `split_tags`, `find_tag_conflicts`, `remove_conflicting_tags_from_negative` 구현.
   - `SanitizerMutator`(파이프라인 6단계)에서 긍정 프롬프트와 부정 프롬프트에 동시 존재하는 태그(예: `1girl`, `blue hair` 등)를 자동 감지하고, 네거티브에서 즉시 제거하여 긍정 프롬프트의 의도가 억제되지 않도록 보호.
   - `[WARN] 프롬프트 태그 충돌 감지` 로깅 기능 탑재.

2. **검열 미탐지 폴백 안전 앵커 (`POSE_SAFE_ANCHORS`) 도입**:
   - `kiro/auto_censor.py`의 체위별 앵커 바운딩 박스를 계승하여 `plepa_engine/censor.py`에 탑재.
   - `missionary`, `doggystyle`, `cowgirl`, `fellatio`, `side`, `default_h` 6대 체위 앵커 정의 및 V2 번호(`080~130`, `150~200`) 매핑.
   - 비노출 여운 씬(`101`, `102`, `104`, `105`, `171`, `172`, `174`, `175`)은 앵커 대상에서 제외하여 불필요한 마스킹 방지.
   - 성인 결합 씬에서 딥러닝 탐지 0건 시 경고 로그 및 폴백 박스 적용 지원.

3. **신규 로스터 전수 호환성 점검**:
   - `kiro/projects/` 내 15개 프로젝트, 85명 캐릭터 JSON 파일을 대상으로 `CharacterSchema` 검증 및 `SDXLPromptPipeline` 렌더링 전수 조사 완료.
   - **85명 캐릭터 전원 100% 정상 로드 및 프롬프트 조합 통과 (오류 0건)**.

---

## 4. 검증 결과

- **PLEPA 단위 테스트**: `35/35 통과 (100% OK)`
  - `tests/test_prompt_conflict.py`: 태그 정규화, 충돌 감지, 네거티브 자동 정제 테스트 (통과)
  - `tests/test_censor_anchor.py`: 체위 분류, 앵커 박스 계산, 폴백 마스킹 테스트 (통과)
  - 기존 33개 코어/서비스/파이프라인 테스트: 100% 통과 유지.
- **KIRO 환경 모듈 Import 검증**:
  - `from generator.censor import POSE_SAFE_ANCHORS, get_pose_category` 정상 동작.
  - `from generator.qa_validator import validate_generated_image` 정상 동작.
