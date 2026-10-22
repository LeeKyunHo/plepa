# 플에파(PLEPA) 에이전트 규칙 (Agent Rules)

## 1. 기본 언어 및 커뮤니케이션 (Language & Communication)
- **응답 언어**: 사용자와의 모든 대화, 코드 설명, 계획 수립, 터미널 실행 결과 보고는 **항상 한국어**로 작성합니다.
- **용어 표기**: 코드 심볼, 파일명, CLI 명령어, 파이썬 식별자, 기술 전문 용어(ComfyUI, GGUF, NF4, LoRA, VRAM, Face Detailer 등)는 원래의 영문 표기를 유지하되 설명은 한국어로 진행합니다.

## 2. 깃 커밋 가이드라인 (Git Commit Guidelines)
- 커밋 메시지는 **민감한 세부 내용을 배제하고 무엇을 어떻게 수정했는지 사무적이고 기술적인 한국어 서술**(`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)을 사용합니다.
- 성인물 관련 표현, 신체 부위, 성적 행동 묘사 등 민감한 세부 내용은 절대 커밋 메시지에 포함하지 않습니다.
- 예시:
  - `feat: ComfyUI GGUF + Face Detailer 연동 비동기 워크플로우 클라이언트 구현`
  - `refactor: 플럭스 전용 영문 서술형 포즈 프롬프트 80종 데이터베이스 구조화`
  - `fix: ComfyUI 웹소켓 응답 파싱 및 이미지 저장 예외 처리 개선`
  - `docs: 다중 PC 이식 및 모델 다운로드 체크리스트 문서화`

## 3. 코드 및 프롬프트 무결성 (Integrity & Token Optimization)
- 기존 주석 및 독스트링을 임의로 훼손하지 않습니다.
- 프롬프트 데이터는 `data/` (`data/sdxl_pose_database.json`, `data/themes/`)에, 파이프라인 로직은 `plepa_engine/`에 철저히 격리합니다.
- **FLUX 완전 배제 및 SDXL 단일화 원칙 (Token Optimization)**:
  - 플에파는 SDXL 단일 파이프라인(Danbooru 쉼표 태그, BREAK 문법, 6대 Mutator 체인)으로 확정되었습니다.
  - FLUX는 `data/legacy/` 및 `plepa_engine/legacy/`로 완전 격리·아카이브되었습니다.
  - **포즈 추가/수정, 캐릭터 프롬프트 튜닝, 기능 수정 시 FLUX 관련 파일(`data/legacy/flux_pose_database.json`, `flux_*.py`)을 일체 열람·수정하거나 동기화하지 마십시오.** (토큰 낭비 및 불필요한 이중 작업 엄격 금지)
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
