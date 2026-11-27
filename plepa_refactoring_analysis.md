# 🏗️ PLEPA 저사양 모델 대비 완성형 리팩토링 & 노트북 싱크로 마스터 플랜

> **작성일**: 2026-11-25  
> **기준 브랜치 / HEAD**: `main` @ `549db0f` (`docs: 젠잇 캐릭터채팅 제작법 v2.2 최신화 및 인트로 HTML 반응형·구버전 문서 정리`)  
> **설계 목표**: 향후 하위(다운그레이드) 모델로 전환되더라도 **① 350줄 이하 단일 책임 모듈, ② 다이어트된 Active SSOT 문서, ③ 기계적 계약 테스트 & Hook 하드블록, ④ `.agents/` 레일형 미니 에이전트 6종, ⑤ 외부 Gemini 노트북 두뇌 싱크로**를 통해 실수 0건으로 유지보수 가능한 자가 방어형 아키텍처 구축.  
> **감사 준수 사항**: `projects/*/assets/` 및 `*_origin/` 에셋 불변 원칙 100% 준수, `data/legacy/`·`plepa_engine/legacy/`·워크플로우 JSON 본문·미디어 미열람, 소스 코드 무수정·무커밋.

---

## 1. 기준선(Baseline) 잠금 진단 (`Pre-Flight`)

### 1.1 시점 차이 실증 교정 (`7f73b81` 과거 보고 vs `549db0f` 현재 디스크)
직전 세션(`HEAD = 7f73b81`, 미커밋 16건 + `test_genit_work_integrity.py` 실패 1건) 이후 타 세션에서 **4건의 커밋(`59987bb` → `11ad496` → `8174ca0` → `549db0f`)**이 반영되어 현재 실제 기준선은 다음과 같습니다.

| 점검 항목 | 과거 보고 시점 (`7f73b81`) | 현재 디스크 실측 (`549db0f` + 워킹트리) | 실증 진단 |
| :--- | :--- | :--- | :--- |
| **`pytest` 전체 스위트** | 204개 중 203 passed, **1 failed** | **209 passed, 0 failed**, 1 warning (`151.44s`) | 전 테스트 통과 (추가 테스트 5건 반영됨) |
| **`test_genit_work_integrity.py`** | **FAIL** (`v2`/`v2.1`의 `103_입위약`·`104_입위강`) | **PASS** (`validate_genit_work.py --force` 3건 전원 통과) | 커밋 `549db0f`에서 구 완성본 삭제 및 `v2.2_완성본.md`(`103_입위앞`·`104_입위뒤`) 동기화 완료 |
| **워킹트리 미커밋 항목** | 추적 수정 16건 | **총 30건** (추적 수정 `M` **25건** + 미추적 `??` **5건**) | SDXL v9 프로필, 하이브리드 종횡비, 모바일 뷰어 v2, `spy` 이벤트 작업분 누적 |
| **`plepa_engine.precheck` (12개 로스터)** | 주요 로스터 점검 | **7개 PASS** (`campus`, `spy`, `oto`, `sns`, `ykn`, `hey`, `school`) / **5개 FAIL** (`default`: 4, `maid`: 7, `man`: 16, `don`: 209, `murim`: 649) | 실패 5개는 구형 로스터 캐릭터 JSON의 `BREAK`·`sdxl_nude_positive` 미갱신 |

### 1.2 `test_genit_work_integrity.py` 해소 확인 및 향후 생애주기 선택지
- **실측 상태**: 과거 실패 원인이었던 `캠퍼스_젠잇_캐릭터_채팅_v2_완성본.md` 및 `v2.1_완성본.md`는 커밋 `549db0f`에서 삭제되었고, 현행 [`캠퍼스_젠잇_캐릭터_채팅_v2.2_완성본.md`](docs/genit/캠퍼스_젠잇_캐릭터_채팅_v2.2_완성본.md)와 신규 미추적 [`스파이_젠잇_캐릭터_채팅_v2.2_완성본.md`](docs/genit/스파이_젠잇_캐릭터_채팅_v2.2_완성본.md) 모두 실존 에셋 114종(`103_입위앞`, `104_입위뒤`)과 **100% 일치하여 즉시 PASS**합니다.
- **남은 정합성 선택지**: [`docs/DOCUMENTATION_GUIDE.md`](docs/DOCUMENTATION_GUIDE.md#L24)는 구 완성본을 `docs/archive/genit/`에 `status: frozen`으로 봉인한다고 서술하나 실제로는 `git rm`이 사용되었고, [`scripts/validate_genit_work.py`](scripts/validate_genit_work.py#L8-L9) 출력문에는 구 규격(`6대 통일 변수 / 108종`)이 남아 있습니다.
  - **(Recommended) 선택지 A**: 현행 `v2.2` 단일 활성 구조 유지 + 향후 `v2.3` 등 업그레이드 시 구본을 `docs/archive/genit/` 이동 및 Frontmatter `status: frozen`으로 표준화 + `validate_genit_work.py` 출력 문구를 현행(`8대 통일 변수 / 실존 에셋 전수 대조`)으로 갱신.
  - **선택지 B**: Git 히스토리(`8174ca0`)에서 구 `v2`·`v2.1` 문서를 `docs/archive/genit/`로 복원하고 상단에 `status: frozen`을 부여해 보관.

### 1.3 기준선 커밋 전 필수 해결 Blocker 2건
1. **🚨 [Blocker 1 — 런타임 크래시] [`plepa_gui/pages/gallery.py`](plepa_gui/pages/gallery.py#L1285-L1294)**:
   - `_save_batch_manifest()`([`generation_service.py`](plepa_engine/services/generation_service.py#L1095-L1108))는 `"items"`를 `list[dict]`(키: `"code": "000"`)로 기록합니다.
   - 그러나 현재 미커밋 코드 `gallery.py:1289-1293`은 `loaded_m = json.load(f).get("items", {}) or {}`로 `list`를 받은 뒤 `try` 블록 바깥(`L1293`)에서 `manifest_cache[manifest_p].get(f"{prefix_val}_{code_val}", {})`를 호출하여, 라이트박스 진입 즉시 **`AttributeError: 'list' object has no attribute 'get'` 크래시** 및 키 불일치(`aya_000` vs `000`)가 발생합니다. (커밋 전 4줄 인덱싱 변환 필수)
2. **🚨 [Blocker 2 — 204.4MB 바이너리 오커밋 위험] [`.gitignore`](.gitignore)**:
   - 미추적 폴더 `benchmarks/` (38파일, **`6.47 MB`**) 및 `projects/spy/assets_archive_v1/` (854파일, **`197.94 MB`**) 총 **`204.41 MB`**가 `.gitignore`에 누락되어 있습니다. 커밋 전 최우선으로 `.gitignore`에 격리해야 합니다.

### 1.4 현행 워킹트리 미커밋 30건(`M` 25 + `??` 5) 논리적 5단 분할 커밋 초안

| 순서 | 권장 커밋 메시지 (민감어 배제 사무적 한국어) | 포함 대상 파일 (총 30건 해소) | 작업 성격 요약 |
| :---: | :--- | :--- | :--- |
| **0 (선행)** | `chore: 벤치마크 산출물 및 구형 에셋 백업 폴더 gitignore 격리` | `.gitignore` (`benchmarks/`, `projects/*/assets_archive*/` 추가) | `204.4MB` 바이너리 미추적 폴더 오커밋 원천 차단 |
| **1** | `feat: SDXL v9 기본 프로필 승격, 하이브리드 종횡비 및 2인 구도 음영·QC 개선` | `plepa_engine/config.py`, `plepa_engine/checkpoint_profiles.json`, `plepa_engine/models.py`, `plepa_engine/precheck.py`, `plepa_engine/prompt_pipeline.py`, `plepa_engine/qa_validator.py`, `plepa_engine/services/generation_service.py`, `plepa_engine/services/pose_service.py`, `tests/test_comfy_and_job_queue.py`, `tests/test_dynamic_aspect_ratio.py`, `tests/test_prompt_pipeline.py`, `tests/test_qa_validator.py` **(12파일)** | v9 Illustrious(28스텝) 기본 승격, `000~024` 세로 / `025+` 가로 하이브리드 해상도, `mob_shadow`·`allow_partner_head` QC 확장, 공용 포즈 배경 하드코딩 `precheck` 가드 |
| **2** | `feat: Genit 내보내기 방향 자동 매칭 및 갤러리 라이트박스 캐싱 개선` | `plepa_engine/services/genit_exporter.py`, `plepa_gui/pages/gallery.py` *(L1289 핫픽스 반영)*, `tests/test_genit_exporter.py` **(3파일)** | 가로/세로 비율 자동 감지 리사이즈(`1024x1536` / `1536x1024`), 라이트박스 메모리 캐시 및 프리로드 |
| **3** | `feat: 모바일 검수 뷰어 v2 순차 그리드 개편 및 실시간 로스터 전환 API 구현` | `plepa_gui/app.py`, `plepa_gui/pages/mobile_viewer.py`, `scripts/start_remote.ps1`, `tests/test_mobile_inspection_api.py` **(4파일)** | `/api/mobile/gallery` 신설, 상단 로스터 무리로드 전환, 동시 3장 순차 청크 3열 그리드 및 하단 5분할 액션 바 |
| **4** | `refactor: 포즈 DB 음영 플래그·배경 분리 정비 및 spy 로스터 이벤트·문서 동기화` | `data/sdxl_pose_database.json`, `projects/spy/events.json` *(신규)*, `projects/spy/background.json`, `projects/spy/pose_background_mapping.json`, `POSE_MAPPING.md`, `docs/POSE_MAPPING_V2.md`, `docs/캐릭터_포즈_제작_규칙.md`, `docs/genit/스파이_젠잇_캐릭터_채팅_v2.2_완성본.md` *(신규)* **(8파일)** | 2인 근접 포즈 10종 `mob_shadow` 반영, `#033` 배경 분리, `spy` 이벤트(`051~055`, `130~132`, `200~202`)·배경·매핑 문서 및 v2.2 완성본 동기화 *(※ `plepa_feature_audit_for_kiro.md`는 `docs/archive/` 이동)* |

---

## 2. 저사양 모델 대비 코드·문서·안전망 전수 감사

### 2.1 전체 모듈 인벤토리 및 `350줄 이상` 비대 파일 분해 설계

#### A. 레이어별 전체 모듈 현황 요약 (총 65개 활성 `.py`, `30,480`줄)
- **CLI & `plepa_engine/` 코어 (14파일, `7,993L`)**: `batch_generator.py`(392), `__init__.py`(6), `config.py`(110), `models.py`(256), `graph_builder.py`(56), `workflow_templates.py`(296 — **LoRA 노드 미구현**), `comfy_client.py`(462), `checkpoint_service.py`(288), `prompt_builder.py`(239 — 포즈 번호 10종 하드코딩), `prompt_pipeline.py`(**1,381**), `censor.py`(**3,787**), `qa_validator.py`(404), `precheck.py`(392 — 캐릭터 20명 prefix 하드코딩), `reporter.py`(220).
- **`plepa_engine/services/` 서비스 (14파일, `4,671L`)**: `__init__.py`(35), `schemas.py`(155 — `PoseFlags` 유령 스키마, `bury_chest`/`carry` 누락), `repository.py`(129), `config_service.py`(109 — 전역 변수 런타임 변이), `character_service.py`(213 — **`clone_character` 확장 필드 유실**), `pose_service.py`(**646**), `background_service.py`(173), `pose_background_service.py`(120), `asset_service.py`(438 — `_origin` 탐색 6곳 파편화), `generation_service.py`(**1,126** — **`L418-424` `/settings` 설정값 무시 버그**), `job_manager.py`(360), `upscale_service.py`(158), `genit_exporter.py`(296), `health_service.py`(**712** — 상위 `plepa_gui` 역방향 import 위반).
- **`plepa_gui/` 웹 스튜디오 (14파일, `6,525L`)**: `__init__.py`(4), `app.py`(232), `api_routes.py`(456), `header.py`(209 — 동기 3초 헬스체크 지연), `prompt_inspector.py`(53), `retouch_editor.py`(**563**), `backgrounds.py`(184), `characters.py`(367 — **저장 시 `sdxl_nude_positive`·`outfits`·`signature_accessories` 증발 버그**), `poses.py`(260 — 유령 `flags` 편집), `pose_sets.py`(201 — 영숫자 코드 `ValueError`), `settings.py`(194 — **원클릭 프리셋 미저장 리로드 버그**), `generate.py`(**544**), `gallery.py`(**1,618** — 라이트박스 크래시 & `GlobalJobManager` 우회 스레드 실행), `mobile_viewer.py`(**1,640**).
- **`scripts/` 유틸·벤치마크 (현역 23파일, `11,291L`)**: 코어 운영/ML 도구 7종 외에 `:8080` NiceGUI와 중복되는 `:8085` 서버/뷰어 4종(`3,714L`), 일회성 벤치마크 러너 10종(`3,209L`), 런타임 크래시 보유 `plepa_upscaler.py`(128L, `load_db` 미존재 호출), **실행 시 최신 Kiro(Wave 0~4)를 파손시키는 위험 스크립트 `sync_to_kiro.py`(324L)** 공존.

#### B. 저사양 모델 컨텍스트 보호를 위한 `350줄 이상` 비대 파일 전수 목록 (총 30개) 및 분해안
하위 모델은 350줄을 넘는 다중 책임 파일이나 인라인 HTML/JS 거대 문자열을 편집할 때 줄 번호 밀림·괄호 파손·이웃 로직 누락 사고를 자주 일으킵니다. **목표 상한(`<= 300~350L`)** 기준 분해 대상 30개 전수 설계는 다음과 같습니다.

| 순위 | 파일 경로 | 현행 줄 수 | 주요 비대화 원인 | 저사양 모델 친화적 분해 / 정리 처방 (목표 `<= 350L`) |
| :---: | :--- | ---: | :--- | :--- |
| 1 | [`plepa_engine/censor.py`](plepa_engine/censor.py) | **3,787** | 모델 로더 + 기하/선화 + 11종 렌더러(`apply_silhouette` 534L) + 포즈 정책 + P2.5 앙상블(373L) + 배치 I/O 결합 | **`plepa_engine/censor/` 7모듈 패키지 분해** (`runtime.py`, `detectors.py`, `geometry_span.py`, `render_silhouette.py`, `render_styles.py`, `policy.py`, `pipeline.py` + 하위 호환 `__init__.py` — **ADR-99 수치 100% 무변경**) |
| 2 | [`plepa_gui/pages/mobile_viewer.py`](plepa_gui/pages/mobile_viewer.py) | **1,640** | `1,456L` 분량 HTML/CSS/JS SPA가 파이썬 f-string으로 내장 | 프론트엔드 에셋을 `plepa_gui/static/mobile_viewer.{css,js}` + HTML 템플릿으로 외부화 ➔ 파이썬 데이터 빌더 `<= 220L` |
| 3 | [`plepa_gui/pages/gallery.py`](plepa_gui/pages/gallery.py) | **1,618** | 단일 함수 내 20개 중첩 클로저(매트릭스·단일뷰·라이트박스 397L·감사·내보내기) | `plepa_gui/components/gallery_matrix.py`, `gallery_lightbox.py`, `gallery_dialogs.py` 4분할 (각 `<= 350L`) |
| 4 | [`scripts/generate_inspection_viewer.py`](scripts/generate_inspection_viewer.py) | **1,408** | `1,347L` 정적 HTML/JS 내장 (구 검수 뷰어, `mobile_viewer`와 중복) | `scripts/archive/` 격리 (현역 `:8080/mobile`로 일원화) |
| 5 | [`scripts/serve_benchmark_mobile.py`](scripts/serve_benchmark_mobile.py) | **1,401** | `:8085` 독자 FastAPI·리롤큐·터널 서버 (`plepa_gui`와 이중화) | GT 정답 저장 2줄만 `plepa_gui/api_routes.py`에 옵션 흡수 후 `scripts/benchmarks/` 격리 |
| 6 | [`plepa_engine/prompt_pipeline.py`](plepa_engine/prompt_pipeline.py) | **1,381** | 7개 Mutator 클래스 + 대형 키워드 사전 + 포즈 코드 분기 단일 파일 밀집 | `plepa_engine/pipeline/` 패키지 분해 (`context.py`, `lexicon.py`, `assembly_mutators.py`, `defense_mutators.py`, `mob_mutator.py`, `sanitizer.py` + 호환 re-export) |
| 7 | [`plepa_engine/services/generation_service.py`](plepa_engine/services/generation_service.py) | **1,126** | 옵션 스펙 + `run_batch()` 단일 **663줄** God Method + 매니페스트 I/O | `option_specs.py`(SSOT 스펙), `manifest_store.py`, `batch_runner.py`, `generation_service.py`(파사드) 4분할 |
| 8 | [`scripts/extract_censor_seg_dataset.py`](scripts/extract_censor_seg_dataset.py) | **956** | GT 차분 추출 + 폴리곤 변환 + 하드 네거티브 샘플링 + 분할 통계 단일 파일 | ML 학습 전용 비핵심 도구이므로 `scripts/ml_censor/` 하위로 격리 (일반 유지보수 열람 제외) |
| 9 | [`scripts/evaluate_h1_pilot.py`](scripts/evaluate_h1_pilot.py) | **857** | ADR-100 파일럿 일회성 평가 + 460L HTML 생성기 | `scripts/archive/` 이동 |
| 10 | [`plepa_engine/services/health_service.py`](plepa_engine/services/health_service.py) | **712** | 10단계 진단 로직 + `plepa_gui` 역방향 스캔 + 콘솔 테이블 포매터 | 코어 진단(`health_checks.py`, `<= 320L`) + 포매터 분리 + GUI 진단은 `plepa_gui` 콜백으로 의존성 역전 |
| 11 | [`scripts/export_context.py`](scripts/export_context.py) | **687** | AST 파서 + Tier 1~3 마크다운 빌더 + 해시/드리프트 단일 스크립트 | v2 개편 시 `scripts/context_exporter/` (`ast_extract.py`, `builders.py`, `telemetry.py`, CLI 진입점 `export_context.py` `<= 180L`) 모듈화 |
| 12 | [`scripts/benchmark_spy_batch.py`](scripts/benchmark_spy_batch.py) | **674** | P2.5 일회성 배치 평가 + 500L HTML 빌더 | `scripts/benchmarks/` 이동 |
| 13 | [`plepa_engine/services/pose_service.py`](plepa_engine/services/pose_service.py) | **646** | 포즈 DB/테마 로더 + 코드 해석기 + 에셋 리네임 + 포즈 세트 CRUD + 문서 검증 | `pose_loader.py`, `pose_set_service.py`, `pose_rename.py`, `pose_service.py`(파사드, 각 `<= 250L`) 분할 |
| 14 | [`scripts/mobile_gallery.py`](scripts/mobile_gallery.py) | **574** | 구버전 무인증 읽기 전용 뷰어 (`:8080` 포트 충돌) | `scripts/archive/` 이동 |
| 15 | [`plepa_gui/components/retouch_editor.py`](plepa_gui/components/retouch_editor.py) | **563** | `550L` CSS/HTML/JS 문자열 상수 내장 | `plepa_gui/static/retouch_editor.{css,js}` 정적 파일 분리 ➔ 파이썬 로더 `<= 60L` |
| 16 | [`plepa_gui/pages/generate.py`](plepa_gui/pages/generate.py) | **544** | 503L 단일 페이지 클로저 + 세트 퀵버튼 하드코딩 + 진행률 폴러 | 폼/세트 선택기(`generate_controls.py`)와 실시간 모니터(`generate_monitor.py`) 분리 |
| 17~19 | `run_artist_benchmark_v2.py`(507), `audit_asset_alignment.py`(506), `run_artist_benchmark.py`(505) | **505~507** | 작가 벤치마크 복제본 2종 + 독자 포즈 로더 내장 감사기 | 작가 벤치마크 2종은 `scripts/benchmarks/` 이동; `audit_asset_alignment.py`는 `PoseService`/`AssetService` 재사용으로 `<= 280L` 축소 |
| 20 | [`plepa_engine/comfy_client.py`](plepa_engine/comfy_client.py) | **462** | HTTP/WS 통신 + WS 재연결 루프(196L) + 레거시 GGUF 조회 + 원자적 저장 | 공용 `fs_utils.py`로 원자적 저장 이관 + WS 실행기와 메타 조회 분리(`<= 320L`) |
| 21 | [`plepa_gui/api_routes.py`](plepa_gui/api_routes.py) | **456** | 9개 REST 엔드포인트 + 자체 `_origin`/원자적 WebP 헬퍼 중복 | 파일/원본 탐색 헬퍼를 `AssetService`·`fs_utils.py`로 위임해 순수 라우터 `<= 280L` 슬림화 |
| 22 | [`plepa_engine/services/asset_service.py`](plepa_engine/services/asset_service.py) | **438** | 에셋 인덱싱 + `_origin` 탐색 3중 구현 + 휴지통 번들 + 로스터 감사 | `_origin` 단일 해석기 통합 및 감사 리포트 로직 분리(`<= 300L`) |
| 23 | [`scripts/validate_genit_work.py`](scripts/validate_genit_work.py) | **419** | Frontmatter/캐시 + 5탭 정규식 파서 + 콘솔 리포터 | 파서·규칙 검증부 모듈 정리(`<= 320L`) |
| 24 | [`plepa_engine/qa_validator.py`](plepa_engine/qa_validator.py) | **404** | 런타임 설정 + Color Burn/화각 + 구문 휴리스틱 + `validate_generated_image`(195L) | Lazy ML 로더 도입 + 프롬프트 구문 규칙을 `PoseEntry` 메타데이터로 이관해 `<= 280L` 경량화 |
| 25~26 | [`batch_generator.py`](batch_generator.py)(392), [`plepa_engine/precheck.py`](plepa_engine/precheck.py)(392) | **392** | CLI 내 `-r all` 루프·직접 JSON 파싱 / `precheck` 내 캐릭터 20명 하드코딩 | `-r all` 및 출력을 서비스로 위임(`<= 240L`); `precheck` 하드코딩을 캐릭터 JSON 메타로 이관(`<= 280L`) |
| 27~30 | `train_censor_seg.py`(386), `benchmark_censor_metrics.py`(372), [`characters.py`](plepa_gui/pages/characters.py)(367), [`job_manager.py`](plepa_engine/services/job_manager.py)(360) | **360~386** | ML 학습/평가 스크립트 2종 + 캐릭터 복제 모달 혼재 + `start_job`/`enqueue_job` 중복 | ML/벤치마크는 전용 서브폴더 격리; `characters.py` 복제 다이얼로그 분리(`<= 260L`); `job_manager.py` 단일 큐 API 통합(`<= 280L`) |

---

### 2.2 문서 · ADR 250건 컨텍스트 다이어트 & SSOT 통폐합안

#### A. `AI_HANDOVER_GUIDE.md` ("ADR 250건") 및 문서 혼란의 실측 원인
- [`docs/AI_HANDOVER_GUIDE.md`](docs/AI_HANDOVER_GUIDE.md)는 현재 **`1,932`줄 (`251 KB`)**에 달하며, `export_context.py` 파서 기준 **번호 매김된 굵은 항목이 정확히 250건**(섹션 2의 번호 항목 + 섹션 7의 `### ADR-XX` 헤더 66건, 누적 ADR-1~107) 수록되어 있습니다.
- 치명적 문제는 상단 0장은 최신 V3·SDXL 단일 원칙인데, **본문 중간 3~5장(`L729~798`)에 초기 FLUX 시절 규칙("Danbooru 태그 및 `BREAK` 철폐")이 현행 불변식처럼 방치**되어 있고, [`docs/POSE_CATALOG.md`](docs/POSE_CATALOG.md)는 현행 DB와 번호가 정반대인 구 V2 표이며, [`docs/개발일지.md`](docs/개발일지.md)(`3,787`줄, `495 KB`)는 최하단(`L3675~3787`)에 `22차, 56~59차`가 역순 규칙을 깨고 잘못 덧붙여져 있습니다. 하위 모델이 이 문서들을 열면 컨텍스트 창이 즉시 포화되고 구버전 규칙을 환각 적용하게 됩니다.

#### B. Active SSOT (경량 현역 8종) vs Cold Archive (`docs/archive/` 열람 금지 구역) 재편안

| 구분 | 대상 문서 | 목표 분량 | 재편 및 컨텍스트 다이어트 내용 |
| :---: | :--- | :---: | :--- |
| **Active SSOT 1** | [`GEMINI.md`](GEMINI.md) | `<= 100L` | 전사 불변 헌법 + 작업 유형별 **`.agents/skills/` 미니 에이전트 1:1 호출 라우팅 표** (`7단계 Mutator`, 단일 `POSE_MAPPING.md` 반영) |
| **Active SSOT 2** | [`docs/AI_HANDOVER_GUIDE.md`](docs/AI_HANDOVER_GUIDE.md) | **`1,932L` ➔ `<= 220L`** | **90% 다이어트**: ① 현행 골든 스테이트 15대 불변식 + ② **현재 코드에 살아있는 Active 핵심 ADR 요약표(ADR-82, 87, 89, 94, 99, 101, 102, 104, 105, 106, 107 등 15건)**만 남기고, 초기 역사·구 FLUX 3~5장·과거 250건 상세 이력은 `docs/archive/ADR_HISTORY_FULL.md`로 완전 분리 |
| **Active SSOT 3** | [`POSE_MAPPING.md`](POSE_MAPPING.md) *(루트 단일)* | `<= 180L` | **유일한 포즈 매핑 SSOT**: `POSE_MAPPING_V2.md`(85% 중복)의 대역 표·deprecated 표기를 흡수하고 캠퍼스/스파이 배경 매핑 오기를 정정. `docs/POSE_CATALOG.md` 및 `docs/POSE_MAPPING_V2.md`는 `docs/archive/`로 퇴출 |
| **Active SSOT 4** | [`docs/캐릭터_포즈_제작_규칙.md`](docs/캐릭터_포즈_제작_규칙.md) | `<= 200L` | `L22` 제어문자 깨짐(` are ass`) 복구, `events.json` 예시를 구 `133~135`에서 현행 V3 `200~202`(`special_otokonoko_h`)로 교정, `precheck` 7단계 반영 |
| **Active SSOT 5** | [`docs/DOCUMENTATION_GUIDE.md`](docs/DOCUMENTATION_GUIDE.md) | `<= 120L` | 단일화된 Active SSOT 지도, `export_context.py` 실행 포함 푸시 5단계 프로토콜 반영 |
| **Active SSOT 6** | [`docs/RUNBOOK.md`](docs/RUNBOOK.md) + [`사용법.txt`](사용법.txt) | 각 `<= 160L` | `사용법.txt`는 순수 복붙용 최신 CLI 원라이너(`12개` 로스터, `11종` 검열 스타일, `sync_to_kiro` 제거), `RUNBOOK.md`는 10초 진단 + 6계층 장애 복구 SOP + 원격 접속(`:8080/mobile` 토큰 인증 중심)으로 중복 제거 |
| **Active SSOT 7** | [`docs/GUI_GUIDE.md`](docs/GUI_GUIDE.md) + [`docs/플에파_기능명세.md`](docs/플에파_기능명세.md) | 각 `<= 170L` | 누락된 8번째 탭(`/mobile`) 추가, `/pose_sets` ➔ `/pose-sets` 라우트 오타 정정, 업스케일 해상도(`3328×4864`) 및 V3 스키마(`events.json`, `mob_shadow`) 반영 |
| **Active SSOT 8** | [`docs/젠잇_캐릭터채팅_제작법.md`](docs/젠잇_캐릭터채팅_제작법.md) + `docs/genit/*.md` | 현행 유지 | v2.2 최신 정합 상태 유지 (`README.md`도 V3 온보딩 요약 `<= 90L`로 정정) |
| **Cold Archive**<br>*(열람 금지)* | `docs/archive/*` | 격리 보관 | `ADR_HISTORY_FULL.md`, `개발일지` 구 회차(`docs/개발일지.md`는 최상단 색인표 + **최근 10회차(`<= 400L`)만 유지**하고 구 회차 월별 롤링 아카이빙 + 최하단 오정렬 5개 회차 복구), `POSE_CATALOG.md`, `POSE_MAPPING_V2.md`, `KIRO_SYNC_REPORT.md`, `ykn_production_benchmark_and_time_analysis.md`, `plepa_feature_audit_for_kiro.md` |

---

### 2.3 기계적 안전망(Contract Tests & Automated Guardrails) 공백 진단

하위 모델이 프롬프트 지시를 잊더라도 **`pytest`와 `precheck`가 1초 내에 실패(Fail-Fast)시켜 잘못된 수정을 물리적으로 거부**하도록 아래 **9종의 기계적 계약 테스트**를 보강합니다.

| # | 신규/보강 계약 테스트 파일 | 차단 대상 휴먼·저사양 모델 실수 (Fail-Fast 불변식) | 현행 상태 |
| :---: | :--- | :--- | :---: |
| **1** | `tests/test_ast_size_and_layer_guard.py` *(신규)* | ① 리팩토링 완료 모듈이 **350줄(최대 하드캡 400줄)**을 초과하거나 단일 함수가 **120줄**을 초과하면 즉시 FAIL<br>② `plepa_engine`이 상위 `plepa_gui`·`scripts`를 역방향 import하거나 비레거시 모듈이 `legacy`를 import하면 즉시 FAIL | **공백** (`health_service` 역방향 결합 방치 중) |
| **2** | `tests/test_character_lossless_roundtrip.py` *(신규)* | `CharacterService.save_character()`, `clone_character()`, `/characters` GUI 저장 핸들러가 `sdxl_nude_positive`, `outfits`, `pose_restrictions`, `signature_accessories` 및 미지 확장 JSON 키를 단 1개라도 유실하면 즉시 FAIL | **공백** (실제 유실 버그 존재) |
| **3** | `tests/test_config_priority_contract.py` *(신규)* | `GenerationService.run_batch()`에서 `명시적 CLI/API 인자 > .plepa_state/config.json(/settings) > CheckpointProfile > 코드 기본값` 4단 우선순위가 깨지면 즉시 FAIL + `/settings` 프리셋 버튼 저장 검증 | **공백** (`/settings` 무시 버그 존재) |
| **4** | `tests/test_schema_model_parity.py` *(신규)* | `models.PoseEntry` 필드와 `schemas.PoseItemSchema`(`partner_pos`의 `bury_chest`·`carry` 포함, `mob_shadow`, `required_outfit`) 및 `PoseService.update_pose()`가 1:1 일치하지 않으면 즉시 FAIL | **공백** (`PoseFlags` 유령 스키마 방치) |
| **5** | `tests/test_cli_gui_sync.py` *(고도화)* | ① 원문 문자열 검색 대신 실제 `create_parser()._actions` 대조<br>② `mobile_viewer.py` 검열 스타일 드롭다운과 `GENERATION_OPTION_SPECS` 일치 단언<br>③ GUI 모듈에서 `GlobalJobManager`를 우회해 `run_batch()`를 스레드로 직접 호출하면 AST 검사로 즉시 FAIL | 반쪽 검증 (예외 하드코딩 존재) |
| **6** | `tests/test_gui_state_handlers.py` *(신규)* | `gallery.py` 라이트박스의 `_batch_manifest.json`(`items: list`) 파싱, `pose_sets.py`의 영숫자 테마 코드(`D01`, `S01`) 정렬 저장 등 핵심 GUI 핸들러 헤드리스 단위 검증 | **공백** (함수 존재 여부만 검사 중) |
| **7** | `tests/test_pose_doc_sync.py` *(단일 SSOT 개편)* | 루트 `POSE_MAPPING.md` 단일 SSOT와 `sdxl_pose_database.json` + 각 로스터 `events.json`의 코드·라벨·개수 합계·배경 매핑표 일치 검증 | 2중 문서 강제, 개수/배경 오기 미검출 |
| **8** | `tests/test_asset_immutability_guard.py` *(신규 + 마커 분리)* | 전체 `pytest` 세션 전후 `projects/*/assets/` 및 `*_origin/`의 파일 목록·크기·mtime 해시가 **단 1바이트라도 변하면 즉시 FAIL**; 로컬 에셋 보유 전제 테스트는 `@pytest.mark.local_assets`로 분리 | 에셋 수량만 고정 단언 |
| **9** | `plepa_engine/precheck.py` *(계약 확장)* | ① 로스터 메타(`status: active | legacy`) 인식<br>② 코어 파이프라인/포즈 DB 내 특정 캐릭터명·로스터 종속 배경 하드코딩 검사<br>③ `background.json` 플랫/중첩 스키마 호환 검증 | 캐릭터 20명 하드코딩 내장 |

---

### 2.4 안전한 단계별 실행 로드맵 (Wave 0 ~ Wave 5)

```mermaid
flowchart LR
    W0["Wave 0<br>기준선 5단 커밋 &<br>치명 버그 4종 핫픽스"] --> W1["Wave 1<br>미니 에이전트 6종·Hook &<br>기계적 계약 테스트 구축"]
    W1 --> W2["Wave 2<br>문서/ADR 90% 다이어트 &<br>Gemini 노트북 링크 v2"]
    W2 --> W3["Wave 3<br>스키마·설정·작업큐 &<br>Trinity Sync 일원화"]
    W3 --> W4["Wave 4<br>엔진 거대 파일 분해<br>(censor·pipeline·service)"]
    W4 --> W5["Wave 5<br>GUI 정적 에셋 분리 &<br>scripts/ 계층 정리"]
```

> **왜 Wave 1~2에 미니 에이전트·안전망·문서 다이어트·노트북 링크를 앞당겼는가?**  
> `Gemini 4 Carbon High` 사용 가능 기간 내에 **안전 레일(Hooks + 계약 테스트 + `.agents/skills/` + `export_context.py` v2)**과 **치명 버그 핫픽스**를 가장 먼저 완공해 두면, 설령 도중에 모델 등급이 내려가더라도 Wave 3~5(모듈 분해)를 외부 Gemini 노트북의 설계 지령과 로컬 기계적 가드레일 아래 무사고로 완주할 수 있기 때문입니다.

| 단계 | 핵심 작업 내용 | 완료 게이트 (Verification Gate) |
| :---: | :--- | :--- |
| **Wave 0**<br>*(기준선 잠금 & 치명 핫픽스)* | 1. `.gitignore`에 `benchmarks/`·`projects/*/assets_archive*/`(204MB) 격리 + `gallery.py:1289` 라이트박스 핫픽스 후 **미커밋 30건 5단 클린 분할 커밋**<br>2. 치명 버그 수정: `characters.py`·`clone_character` 필드 유실 차단, `settings.py` 프리셋 저장, `generation_service.py` 설정 우선순위(`params > config > profile`) 복구, `sync_to_kiro.py` 실행 차단 가드 장착 | `git status` Clean + `pytest` 전수 PASS + 에셋 불변 확인 |
| **Wave 1**<br>*(미니 에이전트 · Hook · 안전망)* | 1. `.agents/tasks/` 구 임시파일(23개) `docs/archive/legacy_agent_tasks/` 이관 후 **`.agents/hooks.json`(에셋·레거시·민감커밋 물리 차단) + `.agents/skills/` 미니 에이전트 6종** 탑재<br>2. **2.3절 신규 기계적 계약 테스트(무손실 저장, 설정 우선순위, 에셋 불변, 레이어/크기 가드)** 선행 구축 | Hook 차단 시뮬레이션 PASS + 신규 계약 테스트 100% PASS |
| **Wave 2**<br>*(문서 다이어트 & 노트북 링크 v2)* | 1. `AI_HANDOVER_GUIDE.md`(`1,932L` ➔ `<= 220L`), `개발일지.md`(`3,787L` ➔ 최근 10회차 + 오정렬 복구), 루트 `POSE_MAPPING.md` 단일 SSOT 통합 및 구 문서 `docs/archive/` 격리, 운영/GUI 문서 현행화<br>2. **`scripts/export_context.py` v2 구현** (`context_snapshot/` 구버전 4파일 자동 청소 + `50_REFACTORING_PLAN.md` 포함 고정 5파일 체제 개통) | 깨진 문서 링크 0건 + `context_snapshot/` 용량 상한(`<= 160KB`) 및 `test_export_context.py` PASS |
| **Wave 3**<br>*(스키마 · 큐 · Trinity 일원화)* | 1. `PoseEntry` ↔ `PoseItemSchema` 단일화(`/poses` 실제 필드 편집, `pose_sets.py` 영숫자 정렬)<br>2. `gallery.py`·`generate.py`를 `GlobalJobManager.enqueue_job()` 단일 큐로 통합 + `GENERATION_OPTION_SPECS` 확장 + SDXL `LoraLoader` 워크플로우 노드 연결<br>3. 로스터 `active / legacy` 메타 도입 및 잔여 FLUX 상수/테스트 정리 | 전 활성 로스터 `precheck` PASS + `test_cli_gui_sync.py` 무예외 PASS |
| **Wave 4**<br>*(엔진 `>=350L` 거대 파일 분해)* | 동작 무변경 순수 모듈 분해: `censor.py`(`3,787L` ➔ `plepa_engine/censor/` 7모듈, **ADR-99 동결 보존**), `prompt_pipeline.py`(`1,381L` ➔ `pipeline/` 패키지 + 포즈/체크포인트 하드코딩 JSON 데이터화), `generation_service.py`(`1,126L`), `pose_service.py`(`646L`), `health_service.py`(`712L`), 공용 `fs_utils.py` 통합 | `test_smart_censor.py`·`test_prompt_pipeline.py` 무수정 100% PASS + `test_ast_size_and_layer_guard` 전면 활성화 |
| **Wave 5**<br>*(GUI 정적 분리 & `scripts/` 정리)* | `mobile_viewer.py`(`1,640L`)·`retouch_editor.py`(`563L`) 정적 `.css/.js` 외부화, `gallery.py`(`1,618L`) 4분할, `api_routes.py`에 GT 아카이빙 흡수 후 `:8085` 중복 서버·일회성 벤치마크 스크립트 `scripts/benchmarks/`·`archive/` 계층화, `plepa_upscaler.py` 수리 | 웹/모바일 통합 테스트 전수 PASS + 전 활성 모듈 `<= 350~400L` 달성 |

---

## 3. Antigravity 미니 에이전트(`Customizations`) 구축 설계안

### 3.1 현행 워크스페이스 Customizations 점검 결과
- `.agent/`, `.antigravity/` 디렉토리는 존재하지 않으며, 표준 루트인 `.agents/` 내부에는 정식 `skills/`, `rules/`, `hooks.json`이 **0건**입니다.
- 대신 `.agents/tasks/` 하위에 과거 일회성 스크립트·리포트·로그 **23개 파일(`152 KB`, `add_campus_poses.py`, `phase1_plan.md` 등)**이 방치되어 있습니다 ➔ 이를 `docs/archive/legacy_agent_tasks/`로 깔끔히 이관하고, Antigravity 공식 스펙(`Progressive Disclosure Skills` + `Lifecycle Hooks` + `Directory Rules`)으로 `.agents/`를 구축합니다.

### 3.2 3중 레일 아키텍처 (Hooks 물리 차단 + 초경량 `GEMINI.md` + 온디맨드 미니 에이전트 6종)

#### 계층 A. 추론 불신 기반 물리적 가드레일 (`.agents/hooks.json` + `.agents/hooks/plepa_guard.py`)
저사양 모델이 규칙을 망각하더라도 도구 실행 직전(`PreToolUse`)에 **0.02초 만에 `{"decision": "deny"}`로 강제 차단**합니다.
- **에셋 불가침 하드블록**: `write_file`, `edit_file`, `read_file`의 `Path` 또는 `run_command`의 삭제/이동 명령이 `projects/*/assets/` 및 `*_origin/`을 직접 겨냥하면 즉시 `deny` (정식 `batch_generator.py` CLI 실행만 허용).
- **토큰 세이빙 & 위험 스크립트 하드블록**: `data/legacy/`, `plepa_engine/legacy/`, `docs/archive/`, ComfyUI 워크플로우 `.json` 직접 열람 및 `scripts/sync_to_kiro.py` 실행 시도 시 즉시 `deny`.
- **커밋 메시지 민감어 필터**: `git commit` 실행 시 커밋 메시지에 민감 어휘 정규식이 매칭되면 즉시 `deny` 및 사무적 표현 교정 안내 반환.

#### 계층 B. 온디맨드 레일형 미니 에이전트 6종 (`.agents/skills/<name>/SKILL.md`)
평소에는 스킬당 이름·설명(~60토큰)만 노출되어 컨텍스트를 전혀 소모하지 않으며, 해당 작업 발생 시에만 활성화되어 **허용 파일·금지 구역·고정 절차·복붙 검증 커맨드**를 강제합니다.

| 미니 에이전트 ID (`.agents/skills/*/SKILL.md`) | 전담 도메인 | 허용 파일 (Whitelist) | 절대 금지 (Blacklist) | 필수 종료 검증 커맨드 (Gate) |
| :--- | :--- | :--- | :--- | :--- |
| **1. `plepa-pose-curator`**<br>*(포즈·프롬프트 DB 전담)* | 신규 포즈 추가, 프롬프트·라벨·음영·의상 슬롯 튜닝 | `data/sdxl_pose_database.json`, `data/themes/*.json`, `projects/*/events.json`, `POSE_MAPPING.md` | `plepa_engine/` 파이프라인 코드 수정, 가중치 상한(`1.15/1.25`) 초과, `bald/faceless` 사용, 기존 에셋 파일 리네임 | `pytest tests/test_pose_db_contracts.py tests/test_pose_doc_sync.py tests/test_prompt_pipeline.py` && `python -m plepa_engine.precheck -r campus` |
| **2. `plepa-roster-character`**<br>*(캐릭터·로스터·Gen-IT 전담)* | 캐릭터 JSON·배경 매핑·`genit_map.json`·5탭 완성본 편집 | `projects/{roster}/*.json`, `projects/{roster}/characters/*.json`, `docs/genit/*.md` | `assets/` 이미지 조작, `precheck.py`에 캐릭터명 하드코딩 추가, 확장 필드(`sdxl_nude_positive` 등) 누락 | `python -m plepa_engine.precheck -r {roster}` && `python scripts/validate_genit_work.py -r {roster} --force` |
| **3. `plepa-pipeline-qc-tuner`**<br>*(파이프라인·QA·검열 전담)* | Mutator 체인, Auto-QC 판정식, 검열 렌더러 유지보수 | `plepa_engine/pipeline/*`, `prompt_builder.py`, `qa_validator.py`, `plepa_engine/censor/*` | 포즈 번호 숫자 분기 하드코딩, 승인 및 `benchmark_censor_metrics.py` 비교 없는 ADR-99 임계치 변경 | `pytest tests/test_prompt_pipeline.py tests/test_prompt_conflict.py tests/test_qa_validator.py tests/test_smart_censor.py` |
| **4. `plepa-trinity-gui-sync`**<br>*(CLI·서비스·GUI 삼위일체 전담)* | 생성 옵션 추가, 서비스/REST API/웹 스튜디오 UI 수정 | `plepa_engine/services/*`, `batch_generator.py`, `plepa_gui/*`, `tests/test_cli_gui_sync.py` | `GENERATION_OPTION_SPECS` 우회 위젯 하드코딩, `GlobalJobManager` 우회 `run_batch` 호출, `engine -> gui` 역방향 import | `pytest tests/test_cli_gui_sync.py tests/test_gui_all_features.py tests/test_mobile_inspection_api.py` |
| **5. `plepa-batch-operator`**<br>*(배치 생성·검열·검수 운영 전담)* | 에셋 배치 생성, 소급 검열, 모바일 원격 서버 기동 | CLI 실행 전용 (`batch_generator.py`, `scripts/start_remote.py`, `audit_asset_alignment.py`) | 미승인 `-f/--overwrite` 실행, 백그라운드 완료 전 중간 수치 보고, 1~2장 표본 과장 보고 | ComfyUI `:8188` 사전 체크 ➔ `--dry-run` 확인 ➔ `Task DONE` 후 탐지/폴백 분리 집계 |
| **6. `plepa-doc-notebook-sync`**<br>*(문서·커밋·노트북 링크 전담)* | 작업 후 Active SSOT 문서 갱신, 스냅샷 추출, 분할 커밋 | Active SSOT 문서 8종, `docs/개발일지.md`, `scripts/export_context.py`, `context_snapshot/*` | `docs/archive/` 구 문서 열람, 민감어 커밋 메시지, 테스트 미통과 상태 커밋/푸시 | `python scripts/export_context.py` && `pytest -q` ➔ `git status` 점검 후 분할 커밋 |

---

## 4. Gemini 노트북 상시 협업 링크 (`scripts/export_context.py` v2) 설계안

다운그레이드 이후 **외부 Gemini 노트북(설계·리뷰 두뇌)**이 `plepa` 전체를 환각 없이 100% 조망하고, 로컬의 **저사양 Antigravity 모델(레일 실행자)**에게 정확한 작업 지시서를 내려줄 수 있도록 `context_snapshot/` 구조를 다음과 같이 업그레이드합니다.

### 4.1 현행 `context_snapshot/`의 문제점과 해결 원칙
- **현행 문제**: ① 폴더 내에 구버전 4파일(`00_README_SYNC.md` 등)과 신버전 4파일(`00_README_FOR_AI.md` 등) 총 **8개 파일이 혼재**하여 노트북 업로드 시 신·구 정보 충돌 발생, ② `DEPRECATION_LEDGER`가 구 V2 기준(`133~135`)으로 오기재, ③ `ADR-80~107` 마크다운 헤더 파싱 누락 및 250건 무차별 나열, ④ `plepa_gui/`·문서 맵·미니 에이전트·리팩토링 현황 부재.
- **해결 원칙**: 실행 시 **허용된 고정 5개 파일만 덮어쓰기(Strict Overwrite)**하고 그 외 잔여 `.md` 파일은 즉시 자동 `unlink()` 제거하며, 파일별 바이트 상한(`enforce_budget`, **총합 `<= 160 KB`**)을 강제합니다.

### 4.2 고정 5파일 스펙 및 용량 예산 (Total Budget `<= 160 KB`)

| 고정 파일명 (항상 덮어쓰기) | 수록 콘텐츠 (코드 AST · Git · 메타데이터 100% 자동 추출) | 용량 상한 |
| :--- | :--- | :---: |
| **`00_README_FOR_AI.md`**<br>*(두뇌 지휘 규칙 · 미니 에이전트 · 문서 맵)* | • `snapshot_id`, Git HEAD/dirty, 직전 대비 변경 파일(`A/M/D`) 해시 Delta<br>• 무환각 리뷰 규칙 + V3 최신 `DEPRECATION_LEDGER` (`sync_to_kiro.py` 금지 포함)<br>• **`.agents/skills/` 미니 에이전트 6종 카탈로그 & 허용 파일 표** *(노트북이 로컬 하위 모델용 지시서를 쓸 때 정확한 스킬명을 지정하도록 연결)*<br>• **Active SSOT 문서 8종 역할·줄수·SHA-8 요약표** | **<= 20 KB** |
| **`10_TIER1_CONSTITUTION.md`**<br>*(불변 헌법 · 전체 기능 맵 · 핵심 ADR)* | • `GEMINI.md` 핵심 원칙 + 다이어트된 골든 스테이트 15대 불변식 + V3 포즈/폴더 규격<br>• **전체 모듈 아키텍처 맵** (`batch_generator.py` + `plepa_engine/` + `plepa_gui/` + 핵심 `scripts/` + `tests/` 전 파일 줄수·SHA-8·역할·`350L` 초과 배지 자동 표기)<br>• **Active 핵심 ADR 요약표** (`### ADR-XX` 통합 파서 적용, 현역 유효 결정 중심 수록) | **<= 35 KB** |
| **`20_TIER2_CORE_LOGIC.md`**<br>*(파이프라인 · API · Trinity 계약)* | • 7단계 `SDXLPromptPipeline` 체인 및 데이터 모델(`PoseEntry`, `CharacterSchema`)<br>• **`GenerationParams`(42) ↔ `GENERATION_OPTION_SPECS` ↔ CLI ↔ GUI 실시간 Trinity Sync 감사표**<br>• 코어·서비스 전체 공개 시그니처 & 상수 + `plepa_gui` FastAPI REST 엔드포인트(`/api/assets/*`, `/api/mobile/*`) 목록<br>• Auto-QC & P2.5 검열 동결 파라미터, 체크포인트 프로필, 포즈 DB 섹션/`events.json`/테마팩 라벨 요약 | **<= 50 KB** |
| **`30_TIER3_RUNTIME.md`**<br>*(런타임 · 로스터 에셋 · Gen-IT · 테스트)* | • 12개 로스터(`active` 7 / `legacy` 5) 에셋 완비율 매트릭스<br>• `docs/genit/*.md` 활성 완성본 글자수·에셋 무결성 요약<br>• Auto-QC 실패 상위 30건 트렁케이션 요약 및 `plepa` ↔ `kiro` 공유 모듈 해시 비교<br>• (`--run-tests` 시) `pytest` 및 `precheck` 최신 실행 결과 | **<= 25 KB** |
| **`50_REFACTORING_PLAN.md`** *(신규)*<br>*(리팩토링 현황 & 로컬 에이전트 지령 규격)* | • Wave 0~5 체크리스트 진척도 및 기술 부채 해결 현황<br>• **실시간 코드 건강도 계측기 (AST Live Telemetry)**: ① `>=350L` 비대 파일 수/목록, ② `>=120L` 함수 수, ③ Trinity 미동기화 수, ④ 계약 테스트 파일 수 자동 계측<br>• **[노트북 ➔ 로컬 하위 모델 작업 지시서 표준 템플릿]**: `호출 스킬` / `수정 허용 파일(sha 포함)` / `절대 금지 사항` / `종료 검증 원라이너` 4칸 규격 내장 | **<= 30 KB** |
| *(선택)* **`40_CORE_CODE.md`** | `--full-code` 또는 `--focus <모듈경로>` 실행 시에만 타겟 코드 원문 번들 생성 (`<= 80 KB` 상한, 일반 실행 시 자동 삭제하여 구 코드 잔류 차단) | *(선택)* **<= 80 KB** |

---

## 5. 착수 전 핵심 의사결정 확정 결과 (`2026-11-25` 승인 완료)

`GEMINI.md` 7조·9조 승인 게이트에 따라 질의한 5대 설계 방향이 전원 권장안(`Recommended`)으로 최종 확정되었습니다.

| 항목 | 확정된 의사결정 (Confirmed Architecture Decision) | 집행 대상 Wave |
| :---: | :--- | :---: |
| **Q1. 기준선 잠금 & Gen-IT** | `.gitignore`(`benchmarks/`·`projects/*/assets_archive*/` 204.4MB 격리) + `gallery.py:1289` 라이트박스 4줄 핫픽스 선반영 후 **5단 논리적 분할 커밋으로 기준선 잠금** + `docs/genit/`은 현행 `v2.2` 단일 활성 체제 유지(`validate_genit_work.py` 문구만 현행화, 향후 구본은 `docs/archive/genit/` `status: frozen` 봉인 표준화) | **Wave 0** |
| **Q2. 문서·ADR 250건 다이어트** | `AI_HANDOVER_GUIDE.md`(`1,932L` ➔ `<= 220L`, 구 FLUX 섹션 및 과거 250건 상세 이력은 `docs/archive/ADR_HISTORY_FULL.md`로 분리) + `개발일지.md`(`3,787L` ➔ 최근 10회차만 현역 유지·최하단 오정렬 복구·구 회차 월별 아카이빙) + **루트 `POSE_MAPPING.md` 단일 SSOT 통합**(`POSE_CATALOG.md`·`POSE_MAPPING_V2.md` 아카이브 이동) | **Wave 2** |
| **Q3. 미니 에이전트 & Hook** | `.agents/tasks/` 구 임시파일(23개)을 `docs/archive/legacy_agent_tasks/`로 이관한 뒤, **`.agents/hooks.json`(에셋·레거시·`sync_to_kiro`·민감커밋 `PreToolUse` 자동 차단) + `.agents/skills/` 온디맨드 레일형 미니 에이전트 6종** 풀세트 구축 | **Wave 1** |
| **Q4. `>=350L` 분해 & 구형 로스터** | `censor.py`(`3,787L`)를 ADR-99 알고리즘·수치 **100% 무변경** 조건으로 `plepa_engine/censor/` 서브패키지(하위 호환 `__init__.py`)로 분해 + `:8085` 중복 스크립트 계층 정리 + 구형 5개 로스터(`default`, `maid`, `man`, `don`, `murim`) `status: legacy` 분리 관리 + SDXL 워크플로우 정식 `LoraLoader` 노드 연결 | **Wave 3 ~ 5** |
| **Q5. 실행 순서** | **Wave 0(기준선 잠금 + 치명 버그 4종 핫픽스) ➔ Wave 1(미니 에이전트 6종 + Hook + 9대 기계적 계약 테스트) ➔ Wave 2(문서 90% 다이어트 + `export_context.py` v2 노트북 링크)** 최우선 완공 후 Wave 3~5 모듈 분해 순차 진행 | **마스터 실행 순서** |

### 5.1 전 Wave 공통 보완 지침 (실행 불변식)
1. **Wave 1 Hook 오탐 방지 & 공식 스펙 검증**: `.agents/hooks.json` 및 `.agents/skills/` 구축 시 Antigravity 실제 로드 경로·포맷을 검증하고, `projects/*/assets/`·`*_origin/` 직접 읽기·수정·삭제는 차단하되 `pytest`, `plepa_engine.precheck`, `scripts/export_context.py`, `scripts/audit_asset_alignment.py`, `scripts/validate_genit_work.py` 등 읽기 전용 검증·감사 스크립트 실행은 오탐 차단하지 않도록 설계한다.
2. **Wave 1 AST 줄수 가드 래칫(Ratchet) 적용**: 아직 분해 전인 기존 30개 비대 파일은 현행 줄수를 상한으로 Allowlist에 등록하여 줄수 증가만 차단하고, 신규 파일 및 Wave 3~5 분해 완료 파일에 `<= 350~400L` 상한을 강제하여 전 구간 `pytest` 100% PASS를 유지한다.
3. **Wave 2 포즈 SSOT 일괄 참조 동기화**: `docs/POSE_MAPPING_V2.md` 아카이브 시 `GEMINI.md`, `docs/DOCUMENTATION_GUIDE.md`, `tests/test_pose_doc_sync.py`, `scripts/export_context.py`의 참조를 단일 트랜잭션으로 동시 갱신한다.
4. **구형 로스터 에셋 절대 무접촉**: 구형 5개 로스터(`default`, `maid`, `man`, `don`, `murim`)는 로스터 메타데이터(`status: legacy`)로만 분리하며 기존 `assets/` 및 `*_origin/` 폴더는 단 1장도 접촉하지 않는다.

### 5.2 실행 진척도 추적 (Execution Tracker)
- [x] **Wave 0 완료 (`8ea43b4`)**: 기준선 5단 분할 커밋, `.gitignore`(204.4MB 격리), 라이트박스 매니페스트 핫픽스(`gallery.py`), 캐릭터 무손실 저장(`schemas.py`, `character_service.py`, `characters.py`), 설정 우선순위(`generation_service.py`, `settings.py`), `sync_to_kiro.py` 차단 가드 및 회귀 테스트(`test_wave0_hotfixes.py`).
- [x] **Wave 1 완료**: `.agents/tasks/`(23건) 아카이브 이관, `.agents/hooks.json`(`plepa_guard.py` `PreToolUse`), `.agents/skills/` 미니 에이전트 6종, `GEMINI.md` 11장 라우팅, 세션 에셋 불변 가드(`conftest.py`), AST 줄수/레이어/큐/파서/스키마 계약 테스트(`test_contract_guards.py`, `test_agent_hooks_and_skills.py`).
- [x] **Wave 2 완료**: 포즈 SSOT 단일화(`POSE_MAPPING.md` 통합 + `POSE_CATALOG`/`POSE_MAPPING_V2`/`KIRO_SYNC_REPORT`/`ykn_*` `docs/archive/` 이관), Active 문서 90% 다이어트(`AI_HANDOVER_GUIDE.md` 64L + `ADR_HISTORY_FULL.md`, `개발일지.md` 246L+ + 중기 아카이브, `README`/`사용법`/`RUNBOOK`/`GUI_GUIDE`/`기능명세`/`제작규칙`/`REMOTE` 최신화) 및 `scripts/export_context.py` v2 (`context_exporter/` 5모듈 · 고정 5파일 `34KB` · `50_REFACTORING_PLAN.md`) 개통.
- [x] **Wave 3 완료**: `PoseEntry`/`PoseItemSchema` 양방향 단일화, `GlobalJobManager` GUI 전체 FIFO 큐 통합(`enqueue_censor_only` + 직접 `run_batch` 우회 0건), `GENERATION_OPTION_SPECS` 29종(`generation_options.py`·`option_controls.py`·`batch_generator.py`) 삼위일체 확장, `LoraLoader` 직렬 체이닝(미지정 시 그래프 무변경 바이패스), 구형 5종 로스터 `roster.json` `status: legacy` 분리 & `pytest 252 passed`.
- [x] **Wave 4-A 완료**: `plepa_engine/censor.py`(3,787L)를 `plepa_engine/censor/` 19개 단일 책임 모듈(`<=322L`/`<=117L`)로 Phase P2.5(ADR-99) 알고리즘·수치·공개 API·테스트 패치 100% 무변경 분해 완료 및 `test_contract_guards.py` AST 래칫 Allowlist 제거(`test_wave4a_censor_package.py` 추가).
- [x] **Wave 4-B1 완료**: 코어 4대 영역(`pipeline/` 11모듈 + `prompt_pipeline.py` 78L 파사드, `comfy_client`/`comfy_transport`, `qa_validator`/`qa_checks`, `precheck`/`precheck_rules`) 무손실 구조 분해 (전 모듈 `<=316L` · 전 함수 `<=105L`), `test_contract_guards.py` Wave 4-B1 AST 래칫 Allowlist 제거 및 `test_wave4b1_core_modules.py` 포함 `pytest 271 passed`.
- [x] **Wave 4-B2 완료 (Wave 4 전체 완결)**: 서비스 레이어 4모듈(`generation_service` ➔ `generation/` 6모듈 + `238L` 파사드, `health_service` ➔ `health_checks_core/ops`, `pose_service` ➔ `pose_resolver/storage`, `asset_service` ➔ `asset_helpers`), `workflow_templates`(`workflow_nodes.py`) 및 `novelchat_validator` 분해 + `health_service` 역방향 레이어 import 해소 완료 — **`plepa_engine/` 전 74모듈 `<=350L`/`<=120L` 및 AST·역방향 레이어 Allowlist 0건**, `test_wave4b2_service_modules.py` 포함 `pytest 276 passed`.
- [x] **Wave 5-A 완료**: `plepa_gui/` 인라인 CSS/HTML/JS를 `plepa_gui/static/` 6파일(`retouch_editor.*`, `mobile_viewer.*`)로 분리하고 `api_routes` (`api_schemas`/`api_security`/`api_file_ops`), `gallery` (`gallery_parts/` 7모듈), `generate` (`generate_sections`), `characters` (`characters_form`) 및 4대 페이지(`poses`, `pose_sets`, `backgrounds`, `settings`) 분해 완료 — **`plepa_gui/` 전 28개 파이썬 모듈 `<=350L` · 전 함수 `<=120L` · Allowlist 0건 · `run_batch` 우회 0건**, `test_wave5a_gui_refactor.py` 포함 `pytest 279 passed` (ADR-114).
- [ ] **Wave 5-B 대기**: `scripts/` 대형 스크립트(`generate_inspection_viewer`, `serve_benchmark_mobile`, `extract_censor_seg_dataset`, `evaluate_h1_pilot` 등) 계층 정리 및 잔여 AST Allowlist 0건 마감.
