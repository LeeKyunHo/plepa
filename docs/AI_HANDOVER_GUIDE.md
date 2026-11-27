# 🧠 플에파(PLEPA) 시스템 아키텍처 & 에이전트 인계 핵심 가이드 (Active SSOT)

> **역할**: 신규 에이전트·저사양 모델·외부 Gemini 노트북이 프로젝트의 **현재 골든 스테이트(15대 불변식)**와 **최근 주요 의사결정(ADR-80 ~ ADR-114)**을 200줄 이내로 즉시 숙지하는 최우선 인계 문서입니다.  
> **포즈 단일 매핑표**: [`POSE_MAPPING.md`](../POSE_MAPPING.md) · **제작 규칙**: [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md) · **운영 런북**: [`RUNBOOK.md`](RUNBOOK.md)  
> **과거 전체 아카이브 (`ADR-01 ~ ADR-107` 상세 원문 & FLUX/V1~V2 초기 이력)**: [`docs/archive/ADR_HISTORY_FULL.md`](archive/ADR_HISTORY_FULL.md)

---

## 💻 1. 표준 개발 하드웨어 & 런타임 환경
- **로컬 워크스테이션**: Windows 11 · **RTX 4060 Ti 8GB VRAM** · **48GB System RAM** · `.venv` Python 3.10.11
- **백엔드 추론기**: ComfyUI 로컬 API (`http://127.0.0.1:8188`)
- **기본 체크포인트**: `UnholyDesireMixSinisterAesthetic_V9_Illustrious.safetensors` (`Steps 28`, `CFG 4.0`, `dpmpp_2m`, `karras`, `CLIP Skip -2`, `FreeU` 활성)

---

## ⚡ 2. 현행 골든 스테이트 15대 핵심 불변식 (Golden State Invariants)

1. **SDXL 단일 파이프라인 일원화**: 플에파는 SDXL(Illustrious 계열, Danbooru 쉼표 태그, `BREAK` 청크, 7단계 Mutator 체인)로 영구 일원화되었습니다. 구 FLUX 경로(`plepa_engine/legacy/`, `data/legacy/`)는 참조·수정 금지입니다.
2. **하이브리드 최적 해상도 (`get_optimal_resolution_for_pose`)**: `--width`/`--height` 미지정 시 `000~024`(감정·초반 단독)은 세로형 `832×1216`, `025+`(일상·로맨스·H-씬)는 가로형 `1216×832`로 자동 분기합니다. (`GenitExporter` 상용 패키징 시 `1024×1536` Lanczos 중앙 크롭 통일)
3. **7단계 프롬프트 Mutator 체인 & 가중치 상한**: [`plepa_engine/pipeline/`](../plepa_engine/pipeline/__init__.py) 11모듈(`<=285L`)과 [`prompt_pipeline.py`](../plepa_engine/prompt_pipeline.py) 78L 파사드가 `PoseTagPreparation` ➔ `PositiveAssembly` ➔ `NegativeBase` ➔ `DefectDefense` ➔ `TwoPersonMob` ➔ `CompositionAntiDrift` ➔ `Sanitizer` 순으로 실행되며, `clamp_sdxl_weights`로 긍정 `<= 1.15`, 부정 `<= 1.25` 상한을 강제합니다.
4. **V3 포즈 DB(`data/sdxl_pose_database.json`) & 단일 매핑 SSOT**: 코어 DB는 `175`개 키(활성 `151`종 + `status="deprecated"` 보존 `24`종)이며, 로스터 전용 `projects/{roster}/events.json` (`051~055`, `130~132`/`200~202`)이 세계관 슬롯을 오버라이드합니다. 포즈 추가·수정 시 루트 [`POSE_MAPPING.md`](../POSE_MAPPING.md) 단일 SSOT를 즉시 동기화합니다.
5. **에셋 2대 서브폴더 & 원본 무손실 보존 불변식**: 모든 에셋은 `01_normal/`(`000~059`) · `02_h_scenes/`(`060~209+`)에 저장되며(`3-Track` 하위 호환 탐색), 무검열 원본은 `{char}_origin/`에 영구 보존됩니다. 이미 생성된 `projects/*/assets/` 파일은 절대 임의 읽기·수정·삭제하지 않습니다.
6. **화풍(`legacy`), `signature_accessories`, H-씬 수분광·무드 라이팅**: `PromptContext.style_mode` 기본값은 `"legacy"`입니다. `signature_accessories`는 2차 청크 선두(CLIP 75토큰 이내)에 우선 배치되며, `is_steamy_h_scene`(`>= 060`, `038/039`)에서는 땀/수분광 부스터 + 중립 심야 조명(`clean ambient occlusion`, 황변 네거티브 방어 유지)이 가동됩니다.
7. **2인 모브 4-Tier(`mob_tier 0~3`), `partner_pos` 및 상안부 그림자 음영**: 마네킹(`bald`/`faceless`) 및 앞머리 가림(`male hair over eyes`)을 영구 퇴출하고 `_MOB_SHADOW_EYES_POS`(뒤통수·상안부 그림자 음영) + 여성 한정 `(clear visible female eyes:1.15)`을 적용합니다. (`mob_tier 1/3` 등 미주입 포즈는 DB 엔트리에 직접 3종 세트 명기)
8. **검열 엔진 `Phase P2.5` 동결(`ADR-99`) & 터치 협업**: [`plepa_engine/censor/`](../plepa_engine/censor/__init__.py) 서브패키지(19모듈 `<=322L`)는 `deepghs` + `models/censor_seg.pt` (`YOLO11s-seg`) + `sam2.1_s.pt` 하이브리드 및 `white_silhouette` 기본(총 11종, `enable_anchor_fallback=False`)으로 프로덕션 동결되었습니다. 미세 보정은 웹/모바일 `✏️ 터치 덧칠`(`retouch_editor.py`)로 처리합니다.
9. **오토코노코(`oto`) 검열 & 톤 동기화**: `150~209` H-씬 전수 스캔 + 탈의 일상(`030,038,039,043~045,049`) `is_nude` 컨텍스트 전파를 강제하며, `oto` 배경·네거티브는 `campus` 중립 색감에 동기화됩니다.
10. **Auto-QC 딥러닝 자동 검증 (`qa_validator.py` + `qa_checks.py`)**: 인원·얼굴·머리·손·눈·Color Burn·상반신 화각 드리프트(`_check_closeup_aspect_drift`)·Laplacian 흐림 검사를 수행하며 `strict_censor_qc`는 `mob_tier not in (0, 1, 2)`에서만 작동합니다.
11. **CLI · Engine · GUI 삼위일체 동기화 (`Trinity Sync`)**: 생성 옵션 추가 시 [`generation_options.py`](../plepa_engine/services/generation_options.py) `GENERATION_OPTION_SPECS`(29종) ↔ `GenerationParams` ↔ `batch_generator.py` CLI ↔ `plepa_gui` (`option_controls.py`) ↔ `tests/test_cli_gui_sync.py` + `tests/test_contract_guards.py`를 1세트로 유지합니다.
12. **비동기 FIFO 대기열 & 원격 토큰 보안**: 8080 스튜디오(`/generate`, `/gallery`, `/api`)는 `GlobalJobManager`(`enqueue_job`/`enqueue_censor_only`), 8085 벤치마크 서버는 `RerollQueueManager`가 단일 워커 FIFO로 GPU 경합을 차단하며, `start_remote.py` 원격 구동 시 `PLEPA_MOBILE_TOKEN` 쿠키·Origin 검증이 활성화됩니다.
13. **원자적 I/O & 안전 백업**: 모든 JSON·이미지 덮어쓰기는 임시 파일 생성 + `os.replace` 원자적 교체를 사용하며(선행 `unlink()` 금지), 수정·삭제 시 `.plepa_backup/`(20개 순환) 및 `_trash/`를 활용합니다.
14. **Antigravity 레일형 거버넌스 & AST 래칫**: `.agents/hooks.json`(`plepa_guard.py`)이 에셋 직접 접근·레거시·`sync_to_kiro`·민감 커밋을 물리 차단하고, `.agents/skills/` 6종이 작업 레일을 안내합니다. `plepa_engine/` 전 74모듈은 `<= 350줄` / 전 함수 `<= 120줄` 및 역방향 레이어 Allowlist 0건을 달성했습니다.
15. **레거시 `kiro` 브릿지 차단 & 문서 규율**: `scripts/sync_to_kiro.py`는 `--force-unsafe` 없이 차단(`exit 2`)됩니다. 통계 과장 금지(Rule 8), 질문 후 승인 게이트(Rule 9), 비민감 한국어 커밋(Rule 2)을 상시 준수합니다.

---

## 📋 3. Active ADR 핵심 요약 (`ADR-80 ~ ADR-114`, 상세 원문은 Archive 참조)

### ADR-80 ~ ADR-89: 2섹터 통합 · 공통 봉사 대역 · 콤팩트 언더마스킹 & FIFO 큐
- **ADR-80 (2026-10-28)**: 80인 작가 화풍 벤치마크(`art_*`, `.gitignore` 격리) & 웹 갤러리 마운트.
- **ADR-81 (2026-11-05)**: 에셋 `01_normal`(000~059) · `02_h_scenes`(060~209+) 2대 통합 + 3-Track 탐색기.
- **ADR-82 (2026-11-08)**: Gen-IT 심의 기준 **`white_silhouette`** 기본 채택, `Skin Density Gate`(18%), `debug_bbox` 시각화.
- **ADR-83 (2026-11-08)**: 공통 봉사 대역 `064~079` 일원화, 구 코드 24종 `status="deprecated"` 2-Track 보존, 얼굴 상단 `protection_mask` 38% 축소.
- **ADR-84 / ADR-85 (2026-11-09~10)**: 전역 결함 감사(`POSE_SAFE_ANCHORS` 확장) 및 Blueprint 88종 무단 확장 롤백, **실증·승인 헌법(Rule 8·9)** 제정.
- **ADR-86 / ADR-87 (2026-11-10)**: 내측 콤팩트 언더마스킹 + 모바일 인라인 터치 덧칠 협업 확정, H-씬 3단계 표준 시퀀스(`시작/절정/사후`) 및 동적 다중 캐릭터 갤러리 구축.
- **ADR-88 / ADR-89 (2026-11-11)**: 검수 갤러리 Sticky 상단바·원클릭 `_origin` 복원(`/api/restore_origin`) & ComfyUI FIFO 리롤 큐(`RerollQueueManager`) 구축.

### ADR-90 ~ ADR-99: 공간/명칭 정규화 · 보안/원자 I/O & 검열 Phase P2.5 동결
- **ADR-90 ~ ADR-93 (2026-11-11~13)**: `#049` 무배경/`#050` 야경테라스 정규화, `#126/#127` 언더데스크 공간·착의 파트너 정립, 봉사 7종 간결 명칭 & 3단계 언더바(`_`) 통일.
- **ADR-94 (2026-11-13)**: 원격 `ACCESS_TOKEN`·경로·Origin 보안 가드, 전역 원자적 파일 교체(`_atomic_replace_with_retry`), `checkpoint_service` 실시간 config 동기화, `GlobalJobManager` FIFO 직렬화 완비.
- **ADR-95 ~ ADR-98 (2026-11-15)**: 4중 수축 해제 & 외곽 선화 스냅(P0) ➔ 손 분할 Sub-BBox + Hold-out 클린 `YOLO11s-seg`(P0.5/P1) ➔ Semantic SAM 2.1 투영 + `0.92` Fast-Path(P2) ➔ Residual Span 2-Way 복원 & 리콜 회복 재학습(P2.5, `02_h_scenes` IoU `0.7351` / `spy_holdout` `0.7494`).
- **ADR-99 (2026-11-15)**: `spy` 10인 510장 실전 검증(핵심 노출 9포즈 `10/10`, 과검열 `2장 0.39%`)으로 **`censor.py` Phase P2.5 최종 프로덕션 동결**.

### ADR-100 ~ ADR-107: V3 여캐 집중 · 상안부 음영 모브 · 소품/구도 락 & Wave 리팩토링
- **ADR-100 / ADR-101 (2026-11-15~16)**: 2인 모브 `mob_tier 0~3` & 방향성 인라인 `partner_pos` 전환, `bald`/`faceless`·이중화각 영구 퇴출, 여성 H-씬 70종(`060~132`) 전량 매핑 & Auto-QC 야간 Color Burn(`0.35`)·쓰다듬기(`max_hands=3`) 보정.
- **ADR-102 / ADR-103 (2026-11-16~17)**: 일상 `style_mode="legacy"` 확정 + H-씬 수분광 부스터, `oto` `151~193` 검열 면제 해제 및 `is_nude`/`is_otokonoko` 컨텍스트 전파 복원(`oto` 검열률 `71.4%→95.2%`).
- **ADR-104 / ADR-105 (2026-11-17)**: 체위 4종(`087/090/093/105`) `mob_tier: 2` 밀착 포옹 승격 및 H-씬 무드 조명 중립화(`clean ambient occlusion`), `oto` 일상 중립 톤 동기화 및 모브 **상안부 그림자 음영(`_MOB_SHADOW_EYES_POS`)** 전면 전환.
- **ADR-106 / ADR-107 (2026-11-17~20)**: `signature_accessories` 2차 청크 전단 고정 + `CompositionAntiDriftMutator` + `--deterministic-pose-seed` 삼위일체 도입, `#128`/`#198` 복합 봉사 포즈 공식 폐기 및 ControlNet 향후 로드맵 수립.
- **ADR-108 (2026-11-26, Wave 3)**: `PoseEntry`/`PoseItemSchema` 양방향 통일, `GlobalJobManager` GUI 전체 FIFO 큐 일원화, `GENERATION_OPTION_SPECS` 29종 삼위일체(`generation_options.py`·`option_controls.py`·CLI), `LoraLoader` 조건부 직렬 체이닝(미지정 시 무변경 바이패스) 및 구형 5종 로스터 `status: legacy` 분리.
- **ADR-109 (2026-11-26)**: 노벨챗(NovelChat) 6탭 커스텀 모드 제작법([`노벨챗_캐릭터채팅_제작법.md`](%EB%85%B8%EB%B2%A8%EC%B1%97_%EC%BA%90%EB%A6%AD%ED%84%B0%EC%B1%84%ED%8C%85_%EC%A0%9C%EC%9E%91%EB%B2%95.md))·멀티플랫폼 이식 구조(`docs/platforms/`)·34종 호출어 풀(`novelchat_pose_pools.json`)·500장 예산 패키저(`novelchat_exporter.py`)·6탭 원고 검증기(`novelchat_validator.py`) 구축.
- **ADR-110 (2026-11-27)**: `#109` 정면 백헤드·양손 허벅지 파지 2인 구도(`partner_pos="between_thighs"`, `mob_tier=2`, `Auto-QC` 허용 연동) 및 `#179` 상반신~아랫배 줌아웃 단독 절정 컷(`mob_tier=0`, `cropped at lower belly`) 확정, `DefectDefenseMutator` 상체 크롭 하반신 태그 주입 제외 분기(`is_upper_torso_crop`) 신설.
- **ADR-111 (2026-11-27, Wave 4-A)**: 단일 거대 모듈 `plepa_engine/censor.py`(3,787L)를 `plepa_engine/censor/` 19개 단일 책임 모듈(`<=322L`, 전 함수 `<=117L`)로 Phase P2.5 수치·공개 API·테스트 패치 호환성(`facade_get`/`facade_set`) 100% 무변경 분해 완료 및 `test_contract_guards.py` AST 래칫 Allowlist 제거.
- **ADR-112 (2026-11-27, Wave 4-B1)**: 코어 4대 영역(`prompt_pipeline.py` 1,381L ➔ `pipeline/` 11모듈 + `78L` 파사드, `comfy_client`+`comfy_transport`, `qa_validator`+`qa_checks`, `precheck`+`precheck_rules`) 순수 구조 분해 완료 (전 모듈 `<=316L` · 전 함수 `<=105L`, Short-Circuit 및 패치 호환성 100% 유지, `test_contract_guards.py` Wave 4-B1 래칫 Allowlist 4모듈·4함수 제거).
- **ADR-113 (2026-11-27, Wave 4-B2 / Wave 4 완결)**: 서비스 레이어 4대 모듈(`generation_service` ➔ `generation/` 6모듈 + `238L` 파사드, `health_service` ➔ `health_checks_core/ops`, `pose_service` ➔ `pose_resolver/storage`, `asset_service` ➔ `asset_helpers`) 및 `workflow_templates`(`workflow_nodes.py`)·`novelchat_validator` 분해를 완료하고 `health_service` 정적 GUI 역방향 import를 `importlib` 동적 검증으로 전환해 **`plepa_engine/` 전 74모듈 `<=350L` · 전 함수 `<=120L` · AST/역방향 레이어 Allowlist 0건** 달성 (`pytest 276 passed`).
- **ADR-114 (2026-11-27, Wave 5-A)**: `plepa_gui/` 내 인라인 CSS/HTML/JS를 [`plepa_gui/static/`](../plepa_gui/static/mobile_viewer.html) 6파일(`retouch_editor.{css,html,js}`, `mobile_viewer.{css,html,js}`)로 분리하고, [`api_routes.py`](../plepa_gui/api_routes.py)(`api_schemas`/`api_security`/`api_file_ops`), [`gallery.py`](../plepa_gui/pages/gallery.py)(`gallery_parts/` 7모듈), [`generate.py`](../plepa_gui/pages/generate.py)(`generate_sections.py`), [`characters.py`](../plepa_gui/pages/characters.py)(`characters_form.py`) 및 4대 설정/포즈 페이지를 분해해 **`plepa_gui/` 전 28개 파이썬 모듈 `<=350L` · 전 함수 `<=120L` · Allowlist 0건 · `run_batch` 우회 0건** 달성 (`pytest 279 passed`).
