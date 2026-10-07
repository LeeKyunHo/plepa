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

## 3. 코드 및 프롬프트 무결성 (Integrity)
- 기존 주석 및 독스트링을 임의로 훼손하지 않습니다.
- 프롬프트 데이터는 `flux_pose_database.json`에, 파이프라인 로직은 `plepa_engine/`에 철저히 격리합니다.
- Danbooru 쉼표 태그/BREAK 문법은 키로(SDXL) 전용이므로, 플에파에서는 **플럭스 특화 영문 서술형 자연어(Descriptive Natural Language)** 규칙을 엄격히 준수합니다.

## 4. 인계 및 지식 연속성 (Handover & Continuity)
- 새로운 세션이나 다른 컴퓨터의 Antigravity 에이전트가 투입되었을 때:
  - 반드시 루트 디렉토리의 **[`AI_HANDOVER_GUIDE.md`](AI_HANDOVER_GUIDE.md)**를 최우선으로 정독하여 시스템 아키텍처, 하드웨어 결정 배경, 프롬프트 불변식을 숙지합니다.
  - 사용자의 의사결정 내역(ComfyUI 로컬 API 채택, RTX 4060 Ti 8GB + 48GB RAM 최적화 등)을 왜곡하거나 이전 논의와 상충되는 방향으로 되돌리지 않습니다.

## 5. 서류 작성 및 깃 푸시 프로토콜 (Documentation & Pre-push Protocol)
- 사용자가 **"일지 적어줘", "서류/문서 정리해줘", "푸시해줘"** 등을 명령하거나 작업 세션을 마무리할 때:
  - **가장 먼저 루트 디렉토리의 [`DOCUMENTATION_GUIDE.md`](DOCUMENTATION_GUIDE.md)를 열람**합니다.
  - 변경된 작업 유형(ADR/아키텍처, CLI 옵션, 포즈/프롬프트 DB, 일반 생성 등)에 따라 해당하는 문서들([`AI_HANDOVER_GUIDE.md`](AI_HANDOVER_GUIDE.md), [`RUNBOOK.md`](RUNBOOK.md), [`사용법.txt`](사용법.txt), [`개발일지.md`](개발일지.md) 등)을 누락 없이 순서대로 업데이트합니다.
  - `DOCUMENTATION_GUIDE.md`의 5단계 프로토콜(가이드 확인 ➔ 서류 갱신 ➔ git status 점검 및 민감어 배제 ➔ 분할 커밋 ➔ git push)을 철저히 준수합니다.
