# 플에파(PLEPA) 에이전트 규칙 (Agent Rules)

## 1. 기본 언어 및 커뮤니케이션 (Language & Communication)
- **응답 언어**: 사용자와의 모든 대화, 코드 설명, 계획 수립, 터미널 실행 결과 보고는 **항상 한국어**로 작성합니다.
- **용어 표기**: 코드 심볼, 파일명, CLI 명령어, 파이썬 식별자, 기술 전문 용어(ComfyUI, GGUF, NF4, LoRA, VRAM, Face Detailer 등)는 원래의 영문 표기를 유지하되 설명은 한국어로 진행합니다.
- **원클릭 하이퍼링크 의무화 (Hyperlink over Raw Text/Codeblock)**:
  - 사용자가 모바일 및 PC 브라우저에서 번거로운 복사·붙여넣기 없이 즉시 원클릭(원터치)으로 접속할 수 있도록, **모든 웹/터널/로컬 URL은 절대 백틱 인라인 코드(``)나 일반 텍스트로 노출하지 않고 반드시 클릭 가능한 마크다운 하이퍼링크(`[링크 라벨](URL)`) 형태로 제공**합니다.
  - 예시: `[📱 모바일 검수 갤러리 바로가기](https://representation-renew-exercise-medicaid.trycloudflare.com/inspect)`

## 2. 깃 커밋 가이드라인 (Git Commit Guidelines)
- 커밋 메시지는 **민감한 세부 내용을 배제하고 무엇을 어떻게 수정했는지 사무적이고 기술적인 한국어 서술**(`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)을 사용합니다.
- 성인물 관련 표현, 신체 부위, 성적 행동 묘사 등 민감한 세부 내용은 절대 커밋 메시지에 포함하지 않습니다.
- 예시:
  - `feat: ComfyUI GGUF + Face Detailer 연동 비동기 워크플로우 클라이언트 구현`
  - `refactor: 3단계 표준 시퀀스(시작/절정/사후) 포즈 데이터베이스 정비`
  - `feat: 콤팩트 언더마스킹(ADR-86) 및 모바일 1초 덧칠 캔버스 에디터 연동`
  - `fix: ComfyUI 웹소켓 응답 파싱 및 이미지 저장 예외 처리 개선`
  - `docs: 다중 PC 이식 및 모델 다운로드 체크리스트 문서화`

## 3. 코드 및 프롬프트 무결성 (Integrity & Token Optimization)
- 기존 주석 및 독스트링을 임의로 훼손하지 않습니다.
- 프롬프트 데이터는 `data/` (`data/sdxl_pose_database.json`, `data/themes/`)에, 파이프라인 로직은 `plepa_engine/`에 철저히 격리합니다.
- **FLUX 완전 배제 및 SDXL 단일화 원칙 (Token Optimization)**:
  - 플에파는 SDXL 단일 파이프라인(Danbooru 쉼표 태그, BREAK 문법, 6대 Mutator 체인)으로 영구 일원화되었습니다.
  - FLUX 관련 파일(`data/legacy/`, `plepa_engine/legacy/`)은 일체 열람·수정하거나 동기화하지 마십시오. (토큰 낭비 및 불필요한 이중 작업 엄격 금지)
  - 모든 포즈 작업의 단일 진실 공급원(SSOT)은 오직 **`data/sdxl_pose_database.json`** 하나입니다.
- **CLI · Engine · GUI 삼위일체 동기화 원칙 (Trinity Sync Rule)**:
  - `plepa_engine/services/`에 새로운 파라미터나 생성 옵션을 추가·수정할 때는 반드시 **① `plepa_engine` (`GENERATION_OPTION_SPECS` / `GenerationParams`) ➔ ② `batch_generator.py` (CLI 옵션) ➔ ③ `plepa_gui` (Web UI 자동 렌더링) ➔ ④ `tests/test_cli_gui_sync.py`** 4곳을 한 세트로 묶어 동기화하며, 어느 한쪽에만 기능을 방치하지 않습니다.
- **포즈 매핑 문서 실시간 동기화 원칙 (Pose Mapping Sync Rule)**:
  - 포즈가 신규 추가되거나 라벨·프롬프트가 수정될 때는 단일 진실 공급원(SSOT)인 `data/sdxl_pose_database.json`뿐만 아니라, **루트의 [`POSE_MAPPING.md`](POSE_MAPPING.md) 및 [`docs/POSE_MAPPING_V2.md`](docs/POSE_MAPPING_V2.md)를 반드시 세트로 함께 업데이트**하여 포즈 매핑 현황의 단일 정합성을 유지합니다.

## 4. 인계 및 지식 연속성 (Handover & Continuity)
- 새로운 세션이나 다른 컴퓨터의 Antigravity 에이전트가 투입되었을 때:
  - 반드시 **[`docs/AI_HANDOVER_GUIDE.md`](docs/AI_HANDOVER_GUIDE.md)**를 최우선으로 정독하여 시스템 아키텍처, 하드웨어 결정 배경, 프롬프트 불변식을 숙지합니다.
  - 사용자의 의사결정 내역(ComfyUI 로컬 API 채택, RTX 4060 Ti 8GB + 48GB RAM 최적화 등)을 왜곡하거나 이전 논의와 상충되는 방향으로 되돌리지 않습니다.

## 5. 서류 작성 및 깃 푸시 프로토콜 (Documentation & Pre-push Protocol)
- 사용자가 **"일지 적어줘", "서류/문서 정리해줘", "푸시해줘"** 등을 명령하거나 작업 세션을 마무리할 때:
  - **가장 먼저 [`docs/DOCUMENTATION_GUIDE.md`](docs/DOCUMENTATION_GUIDE.md)를 열람**합니다.
  - 변경된 작업 유형(ADR/아키텍처, CLI 옵션, 포즈/프롬프트 DB, 일반 생성 등)에 따라 해당하는 문서들([`docs/AI_HANDOVER_GUIDE.md`](docs/AI_HANDOVER_GUIDE.md), [`docs/RUNBOOK.md`](docs/RUNBOOK.md), [`사용법.txt`](사용법.txt), [`docs/개발일지.md`](docs/개발일지.md) 등)을 누락 없이 순서대로 업데이트합니다.
  - `docs/DOCUMENTATION_GUIDE.md`의 5단계 프로토콜(가이드 확인 ➔ 서류 갱신 ➔ git status 점검 및 민감어 배제 ➔ 분할 커밋 ➔ git push)을 철저히 준수합니다.

## 6. 유연한 확장과 지속적 콘텐츠 유입 원칙 (Extensibility & Content Evolution)
- **콘텐츠 진화 기본 전제**: 플에파는 고정된 정적 소프트웨어가 아니라, **새로운 캐릭터, 포즈, 로스터(세계관), 챗봇 시나리오, 최신 AI 생성 기술이 지속적으로 추가·수정·유입되는 '살아있는 콘텐츠 파이프라인'**임을 항상 기본 전제로 삼고 개발을 진행합니다.
- **하드코딩 금지 및 데이터 주도형 아키텍처 (Data-Driven & Contract over Hardcoding)**:
  - 파이썬 엔진 코드 내부에 특정 포즈 번호, 파일명, 로스터 이름을 하드코딩하지 않습니다.
  - 새 포즈나 로스터는 데이터(JSON/MD) 파일 추가만으로 엔진 수정 없이 즉시 작동해야 합니다.
  - 테스트 코드는 특정 시점의 임시 '값'을 고정 단언하는 대신, 상위 규격과 계약(Contract: 모든 포즈는 실존 배경에 매핑될 것 등)을 검증하여 콘텐츠 확장이 테스트를 깨뜨리지 않도록 방어합니다.
- **기존 완성 에셋 영구 무손실 보존 원칙 (Lossless Asset Preservation)**:
  - 이미 대규모로 완성되어 서비스 중인 프로덕션 에셋(예: 캠퍼스 648장 등)은 새로운 기획이나 기능이 도입되더라도 **파일명 변경·임의 삭제·불필요한 재생성을 일체 금지하며 100% 무손실 보존**합니다.
  - 새로운 구조가 도입될 때는 반드시 2-Track 탐색기(신규 우선 + 구버전 폴백)로 하위 호환성을 영구 보장합니다.
- **메타데이터 기반 스마트 생애주기 관리 (Metadata-Driven Lifecycle)**:
  - 문서나 데이터 스스로가 Frontmatter(`status: active / frozen / draft`)를 통해 자신의 상태를 선언하고, 검증기(`validate_genit_work.py` 등)는 스마트 해시 캐시를 통해 과거 완성본의 불필요한 누적 재검사나 버전 충돌을 0.001초 만에 스킵하도록 설계합니다.

## 7. 선제적 세부 질문 및 선택지 제시 원칙 (Proactive Clarification & Choice Alignment Rule)
- **지시 착수 전 디테일 선제 확인 (Pre-execution Clarification)**:
  - 구조 변경(폴더명, 파일명 규격 등), 데이터/에셋 마이그레이션 범위, 파이프라인 생성 옵션, 대규모 코드 개편 등 사용자의 지시에 여러 구현 경로가 있거나 세부 결정(디테일)이 필요한 경우, 에이전트가 독단적으로 임의 결정하여 바로 작업을 진행하지 않습니다.
  - 반드시 실제 변경 작업에 착수하기 전에, **가장 권장하는 최적안(`(Recommended)`)과 대안들을 정돈된 객관식 선택지(`ask_question`)로 구성하여 사용자에게 먼저 제시하고, 사용자의 명확한 승인과 선택을 확인한 후 작업**을 개시합니다.
- **선택지 설계 가이드라인**:
  - 선택지는 사용자가 직관적으로 이해할 수 있는 2~3개의 핵심 옵션으로 압축하고, 각 안의 차이점과 이점을 명확히 설명합니다.
  - 기존 에셋/데이터의 소급 적용 여부(예: 기존 에셋 통합 마이그레이션 vs 신규 생성분부터 적용 등)와 같은 영향 범위도 분리하여 함께 질문함으로써 사용자 의도와의 100% 정합성을 보장합니다.

## 8. 객관적 실증 및 허위·과장 보고 엄격 금지 (Empirical Rigor & Zero Exaggeration Rule)
- **표본 기반 통계적 실증 의무화**:
  - 단 1~2개 표본이나 단일 시드 결과만으로 "완벽 수렴", "100% 방어", "기적적 수렴" 등의 과장된 결론을 도출하거나 보고하지 않습니다.
  - 개선 효과를 보고할 때는 반드시 표본 수(N), 대상 캐릭터, 시드 고정 여부, 평균 오차 및 표준편차를 정직하게 명시합니다.
- **실제 탐지와 폴백 앵커의 분리 보고 의무화**:
  - 탐지 모델(YOLO/SAM)이 실제로 객체를 검출하여 마스킹한 것과, 모델 탐지 실패로 앵커 좌표가 사후 주입(Fallback)된 건을 명확하게 분리하여 통계에 집계합니다.
  - 앵커 폴백이 실행된 건을 "모델이 정상 탐지했다"고 왜곡 보고하지 않으며, 폴백 마스크가 실제 대상을 정확히 가렸는지는 A4 육안 검수(컨택트시트)를 거치기 전까지 "완전 방어"로 단언하지 않습니다.
- **파이프라인 제약식(Constraint) 검증 불변식**:
  - 프롬프트 파이프라인의 가중치 상한(`clamp_sdxl_weights`: 긍정 1.15 / 부정 1.25)이나 태그 정제 규칙을 사전에 확인하여, 실제 엔진에서 클램핑되거나 무효화되는 수치를 마치 모델에 온전히 들어간 것처럼 착각하거나 과장하지 않습니다.
- **비동기 작업 완료 전 성급한 중간 측정 금지**:
  - 배치가 백그라운드에서 실행 중이거나 디스크 플러시가 진행 중일 때 중간 상태를 측정하여 왜곡된 수치를 보고하지 않으며, 반드시 작업 완료(`Task Status: DONE`) 및 디스크 기록 완결을 확인한 후 수치 분석을 수행합니다.

## 9. 절차적 무결성 및 단계별 승인 게이트 의무화 (Procedural Integrity & Approval Gate Rule)
- **질문 후 임의 선행 작업 엄격 금지 (Strict Approval Gate)**:
  - 다음 단계 진행 방향이나 선택지를 사용자에게 질문(`ask_question` 또는 텍스트)한 후에는, **사용자의 명시적 승인 응답("진행해", "ㄱ" 등)이 도착하기 전까지 절대로 다음 단계의 코드/DB를 임의로 수정하거나 푸시하지 않습니다.**
- **포즈 라벨/프롬프트 수정 시 문서 실시간 동기화 의무화**:
  - `data/sdxl_pose_database.json`의 프롬프트나 라벨이 변경될 때는 반드시 루트의 [`POSE_MAPPING.md`](POSE_MAPPING.md) 및 [`docs/POSE_MAPPING_V2.md`](docs/POSE_MAPPING_V2.md)를 세트로 함께 업데이트하며, 미동기화 상태로 커밋/푸시하지 않습니다.
- **포즈 의미 훼손 및 충돌 주입 금지 (Semantic Preservation)**:
  - 포즈 프롬프트를 보강할 때는 해당 포즈의 원래 의도(사후 여운, 전희, 특정 체위, 단독/파트너 구도)를 반드시 먼저 정독하고 확인해야 하며, 카테고리 일괄 스크립트로 엉뚱한 자세나 충돌하는 모순 태그(예: 사후 씬에 결합 태그 주입 등)를 무차별 주입하지 않습니다.

