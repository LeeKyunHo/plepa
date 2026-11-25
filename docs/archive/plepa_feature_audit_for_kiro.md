# PLEPA → KIRO 기능 전수 감사 및 이식성 평가 리포트

> **작성일**: 2026-11-20  
> **대상 저장소**:
> - Source: `plepa` (`C:\Users\rbsgh\plepa`, branch `main`, HEAD `7f73b81`)
> - Target: `kiro` (`C:\Users\rbsgh\kiro`, Wave 0~4 리팩토링 완료 기준 `a3bb763`)
> - **감사 원칙**: 읽기 전용 전수 감사 (FLUX 레거시 `data/legacy/`, `plepa_engine/legacy/` 완전 배제, `scripts/sync_to_kiro.py` 미실행, 소스 코드 무수정)

---

## 1. `plepa` 최신 기준선 & 헬스 체크 (실측)

### 1.1 Git 기준선 및 `51a29ca` 이후 누적 변경 요약
- **Branch**: `main`
- **HEAD**: `7f73b81` (`docs: V3 GUI 포즈 세트 정비 및 수동 편집 에디터 문서·개발일지 동기화`)
- **워킹 트리 상태**: 미커밋 수정 파일 16건 존재 (`GEMINI.md`, `POSE_MAPPING.md`, `data/sdxl_pose_database.json`, `docs/AI_HANDOVER_GUIDE.md`, `docs/POSE_MAPPING_V2.md`, `docs/캐릭터_포즈_제작_규칙.md`, `plepa_engine/services/job_manager.py`, `plepa_gui/api_routes.py`, `plepa_gui/components/header.py`, `plepa_gui/components/retouch_editor.py`, `plepa_gui/pages/gallery.py`, `plepa_gui/pages/mobile_viewer.py`, `tests/test_comfy_and_job_queue.py`, `tests/test_gui_all_features.py`, `tests/test_mobile_inspection_api.py`, `tests/test_prompt_pipeline.py`) — 본 감사에서는 일체 수정·커밋하지 않음.
- **`51a29ca` (2026-10-27) 이후 누적 주요 마일스톤 & ADR (ADR-80 ~ ADR-106)**:
  - **ADR-80 ~ 83**: 80인 작가 화풍 벤치마크(400장), 2대 서브폴더(`01_normal`, `02_h_scenes`) 무손실 통합, `debug_bbox` 진단 모드, 공통 봉사 대역(`064~079`) 일원화 및 2-Track 탐색기.
  - **ADR-84 ~ 88**: 콤팩트 언더마스킹 정책 확정 + 모바일 인라인 터치 캔버스 덧칠 협업 검수(ADR-86), 체위 3단계 표준 시퀀스(시작→절정→사후, ADR-87), 무검열 원본 원클릭 복원(ADR-88).
  - **ADR-89 ~ 94**: ComfyUI 비동기 FIFO 리롤 큐(`GlobalJobManager`, ADR-89), 언더데스크 기하학 개편(ADR-91/93), 보안·원자적 I/O·CLI/Engine/GUI 삼위일체 동기화(ADR-94), Phase C1/C2 검열 코어 최적화(`_SAM_MODEL_LOCK`, `unload_censor_models()`, 동적 해상도 스케일 커널, `strict_censor_qc` 정상화, `censor_style`/`censor_targets` GUI·API 통합).
  - **ADR-95 ~ 99**: Phase P2.5 하이브리드 검열 엔진 동결(외곽 선화 스냅, 손 가로질림 Sub-BBox 분할, 커스텀 YOLO11s-seg + Semantic-Guided SAM 2.1, Residual Span 2-Way 복원, SPY 10인 510장 실전 검증).
  - **ADR-100 ~ 106**: 4-Tier 여캐 집중(Female-Centric/POV) 모브 파이프라인(`mob_tier` 0~3, `partner_pos` 방향성 인라인, `bald`/`faceless` 마네킹 태그 퇴출, 상안부 그림자 음영 + 여성 눈 한정 보호), H-씬 전용 Wet & Steamy Skin 부스터(ADR-102), 중립 무드 라이팅(ADR-104), `signature_accessories` 소품 우선 배치 + `CompositionAntiDriftMutator` + 결정론적 포즈 시드(ADR-106), PC/모바일 공용 수동 리터치 캔버스 에디터(`retouch_editor.py`).

### 1.2 `pytest` 전체 실행 결과 (실측)
- **실행 명령**: `.\.venv\Scripts\pytest.exe`
- **결과**: **204 collected → 203 passed, 1 failed, 0 skipped, 1 warning (117.39s)**
- **실패 1건 상세**:
  - `tests/test_genit_work_integrity.py::test_genit_active_works_integrity`
  - 원인: `docs/genit/캠퍼스_젠잇_캐릭터_채팅_v2.1_완성본.md` 및 `v2_완성본.md`에서 실제 에셋에 존재하지 않는 포즈 서픽스 2건(`103_입위약`, `104_입위강`) 참조 감지(404 위험). 코드 결함이 아닌 완성본 마크다운 ↔ 에셋 동기화 이슈.
- **경고 1건 상세**:
  - `ultralytics/models/sam/modules/blocks.py:538` — PyTorch Flash Attention 미컴파일 `UserWarning` (외부 라이브러리 경고).
- **비교 (Kiro 테스트 현황)**: Kiro는 Wave 0~4 테스트 5개 파일 총 **34개** 단위 테스트 보유(`plepa` 204개 대비 약 1/6 수준).

### 1.3 `python -m plepa_engine.precheck` 주요 로스터 실측 결과
| 로스터 | 점검 캐릭터 수 | 로드 포즈 수 (DB+테마+이벤트) | 조립 시뮬레이션 조합 | 결과 | 비고 |
|---|---:|---:|---:|---|---|
| `campus` | 6명 | 334종 | 2,004개 | **PASS (0건)** | 프로덕션 완료 로스터 |
| `spy` | 10명 | 329종 | 3,290개 | **PASS (0건)** | 프로덕션 완료 로스터 |
| `oto` | 3명 | 329종 | 987개 | **PASS (0건)** | 오토코노코 전용 로스터 |
| `ykn` | 4명 | 329종 | 1,316개 | **PASS (0건)** | 프로덕션 로스터 |
| `default` | 3명 | 329종 | 987개 | **FAIL (4건)** | `oes`/`sample`/`xia`의 `BREAK`/`sdxl_nude_positive` 누락 |
| `murim` | 12명 | 329종 | 3,948개 | **FAIL (633건)** | 구 캐릭터 JSON(`aa` 등)의 `BREAK`/`sdxl_nude_positive` 미갱신 |

### 1.4 포즈 DB · 로스터 · 아키텍처 실측 대조 (`plepa` vs `kiro`)
| 항목 | `plepa` (실측) | `kiro` (실측) | 비고 |
|---|---|---|---|
| 포즈 DB 스키마 버전 | `4.0.0` (`data/sdxl_pose_database.json`) | `4.0.0` (`pose_database.json`) | 메타 `_total_poses` 선언치와 실측 합계 차이 존재 |
| 기본 포즈 DB 실측 합계 | **175종** (선언 183종) | **159종** (선언 148종) | `plepa`는 `data/themes/` 8개 팩 병합 시 **329~334종** |
| 섹션별 분포 | `emotions`: 20, `poses`: 31, `romance`: 20, `h_scenes`: 47, `special_h`: 3, `scenes_otokonoko`: 48, `special_otokonoko`: 6 (`events` 섹션 없음) | `emotions`: 20, `poses`: 20, `events`: 13, `romance`: 4, `h_scenes`: 48, `special_h`: 3, `scenes_otokonoko`: 48, `special_otokonoko`: 3 | **구조 분기점**: `plepa`는 V3(공통봉사 064~079, `events`→`poses` 통합), `kiro`는 V2(`events` 040~059 유지) |
| 테마팩 (`data/themes/`) | **8종** (`adult`, `bdsm`, `bunny`, `genit_actions`, `genit_emotions`, `spy_actions`, `swimsuit`, `wuxia_actions`) | 없음 (로스터별 `events.json` 3개 / `pose_overrides.json` 3개) | `plepa`는 공용 테마팩 모듈화 |
| 포즈 세트 (`pose_sets.json`) | **21종** | 없음 (`V2_FEMALE_SECTIONS` 등 모드 확장) | GUI/CLI 프리셋 실행 지원 |
| 등록 로스터 수 | **12개** (`campus`, `default`, `don`, `hey`, `maid`, `man`, `murim`, `oto`, `school`, `sns`, `spy`, `ykn`) | **20개** (`bani`, `bin`, `cafe`, `campus`, `dark_generals`, `default`, `don`, `hey`, `home`, `maid`, `man`, `murim`, `oto`, `school`, `sea`, `sfk`, `sns`, `spy`, `ykn`, `zip`) | Kiro는 8개 추가 로스터 에셋 보유 (무손실 보존 필수) |

---

## 2. 전체 기능 인벤토리 & 완성도/이식성 마스터 매트릭스

> **등급 기준**: `S` (실전 대규모 검증 + 높은 테스트 커버리지 + 낮은 결합도), `A` (안정 동작 + 테스트 구비, 경미한 정리/어댑팅 필요), `B` (유용하나 결합도·특수 의존성 또는 미완성 요소 존재), `C` (특정 백엔드/프로젝트 전용이거나 Kiro가 더 최신/단순).  
> **총 인벤토리 수**: 7개 영역 **39개 핵심 기능**

### 영역 1. 프롬프트 파이프라인 (7개 기능)
| 모듈 / 핵심 심볼 (줄 수 / SHA-256) | 기능 요약 | 완성도 등급 + 근거 | 백엔드 의존성 | Kiro 현황 대조 | 이식 판정 |
|---|---|---|---|---|---|
| `plepa_engine/prompt_pipeline.py` (`SDXLPromptPipeline`, 7대 `PromptMutator`, `PromptContext`) — `1,358L` / `4ada174552a7` | 7단계 미들웨어 체인 기반 SDXL 프롬프트 조립(포즈 준비→긍정 조립→부정 기본→결함 방어→4-Tier 모브→구도 이탈 방지→정제) | **S** — `test_prompt_pipeline.py` 25건 + `test_prompt_conflict.py` 5건 등 30건+ 전수 통과, SPY/Campus 수천 장 실전 검증 | 순수 Python (엔진 독립) | **Kiro에 부분 존재**: `generator/scene_composer.py`(`547L`, `bdc8b3de2bdb`)가 단일 순수 함수 `compose_scene_prompt()`로 유사 분기 수행하나 Mutator 분리·최신 패치 미반영 | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/prompt_pipeline.py` (`harmonize_character_expression`) — `1,358L` / `4ada174552a7` | 포즈에 표정 태그가 있을 때 캐릭터 기본 외형의 고정 표정(`smile`, `stoic` 등) 충돌을 자동 치환·조화 | **S** — 단위 테스트 검증 완료, 전 로스터 표정 왜곡 방지 실전 검증 | 순수 Python (엔진 독립) | **Kiro 미보유** | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/prompt_pipeline.py` (`find_tag_conflicts`, `remove_conflicting_tags_from_negative`, `_strip_tags_preserving_parens`) — `1,358L` / `4ada174552a7` | 포지티브-네거티브 중복/충돌 태그를 중첩 가중치 괄호 균형을 유지하면서 네거티브에서 자동 제거 (모브 BREAK 블록 격리) | **S** — `test_prompt_conflict.py` 5건 + `test_censor_and_pipeline_fixes.py` 괄호 균형 회귀 테스트 통과 | 순수 Python (엔진 독립) | **Kiro에 부분 존재**: `generator/prompt.py`에 `find_tag_conflicts()` 검출만 있고 자동 제거/괄호 보존 함수 없음 | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/prompt_pipeline.py` (`TwoPersonMobMutator`, `_resolve_mob_tier`, `_inject_partner_pos_inline`, `_apply_gaze_direction_negatives`) — `1,358L` / `4ada174552a7` | 4-Tier(`mob_tier` 0~3) 모브 노출 제어, 방향성 인라인 파트너(`partner_pos`), 상안부 그림자 음영 + 여성 눈 보호(ADR-100/101/105), `bald`/`faceless` 마네킹 태그 퇴출 | **S** — ADR-100~105 실전 검증, `test_prompt_pipeline.py` 다수 케이스 통과 | 데이터 스키마 확장 수반 (`mob_tier`, `partner_pos` 선택 필드) | **Kiro에 부분 존재**: `scene_composer.py`가 구형 `faceless male` 일괄 주입 및 `male_face_suppression` 고정 문자열 사용 | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/prompt_pipeline.py` (`CompositionAntiDriftMutator`) — `1,358L` / `4ada174552a7` | 샷 사이즈(`tight bust portrait`, `cowboy shot`, `full body`)별 반대 구도 이탈 방지 네거티브 자동 주입 (ADR-106) | **S** — 순수 규칙 테이블(20줄 내외), `test_prompt_pipeline.py` 통과 | 순수 Python (엔진 독립) | **Kiro 미보유** | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/prompt_pipeline.py` (`_inject_signature_accessories`, `_strip_accessory_negative_conflicts`) — `1,358L` / `4ada174552a7` | 캐릭터 `signature_accessories`(안경, 리본 등) 우선 배치 및 네거티브 충돌 자동 해제 (ADR-106) | **A** — `test_prompt_pipeline.py` 검증 완료, 캐릭터 JSON에 선택 필드 추가 필요 | 순수 Python (선택적 스키마 확장) | **Kiro 미보유** | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/prompt_builder.py` (`clamp_sdxl_weights`) + `SanitizerMutator` — `239L` / `dcf944558c9b` | 포지티브 `<= 1.15`, 네거티브 `<= 1.25` 상시 가중치 클램핑 및 이중 괄호·빈 쉼표·BREAK 정규화 | **S** — 전 파이프라인 기본 적용, 과포화/번아웃 방어 실증 | 순수 Python (엔진 독립) | **Kiro에 부분 존재**: `generator/prompt.py:clamp_weights()` 존재하나 `scene_composer.py` 기본 `enable_clamp_weights=False`이고 네거티브 미클램핑 | **즉시 이식 추천 (Tier 1)** |

### 영역 2. 의상·테마팩·배경 자동화 (5개 기능)
| 모듈 / 핵심 심볼 (줄 수 / SHA-256) | 기능 요약 | 완성도 등급 + 근거 | 백엔드 의존성 | Kiro 현황 대조 | 이식 판정 |
|---|---|---|---|---|---|
| `plepa_engine/prompt_builder.py` (`resolve_pose_outfit_slot`, `get_character_outfit_prompt`, `strip_sdxl_outfit_tags`, `DEFAULT_THEME_OUTFITS`) — `239L` / `dcf944558c9b` | 포즈 요구 의상 슬롯(`default`/`nude`/`swimsuit`/`bunny`/`maid`/`bdsm`/`wedding` 등) 해석, 캐릭터 `outfits` 미정의 시 공용 기본 의상 폴백, 확장 의상 키워드(110개+) 스트리핑 | **S** — `test_outfit_swap.py` 6건 통과, `precheck` 수천 조합 검증 | 순수 Python (엔진 독립) | **Kiro에 부분 존재**: `scene_composer.py`에 `required_outfit` 분기와 `strip_outfit_tags()` 존재하나 공용 `DEFAULT_THEME_OUTFITS` 폴백 부재 및 의상 키워드 목록이 Plepa 대비 축소됨 | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/services/pose_background_service.py` (`PoseBackgroundService`) — `120L` / `bc77be60330a` | 로스터별 `pose_background_mapping.json` 기반 포즈 코드/범위(`080-129` 등)→배경 프리셋 자동 매핑 및 추천 | **S** — `test_pose_background_integration.py` 3건 + `test_common_background.py` 5건 통과, 120줄 경량 | 순수 Python (데이터 파일 `pose_background_mapping.json` 활용) | **Kiro 미보유**: Kiro `projects/`에 이미 `pose_background_mapping.json` 4개 존재하나 `generator/prompt.py:resolve_background()`가 이를 읽지 않고 단일 프리셋만 사용 | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/services/background_service.py` (`BackgroundService`) — `173L` / `c7c246014318` | 로스터별 `background.json` + 공용 배경 프리셋 조회 및 무배경(`none`) 판별 | **A** — `test_common_background.py` 5건 통과. 단, `presets.{key}.sdxl` 중첩 스키마 사용 | 데이터 스키마 변경 수반 | **Kiro에 부분 존재**: `generator/prompt.py:resolve_background()`는 플랫 `{"default": "..."}` 스키마 사용 (20개 로스터 호환 필수) | **보류·제외 (Tier 3)** |
| `data/themes/*.json` (8개 테마팩) + `PoseService.load_pose_db()` — `645L` / `7585806277e1` | `swimsuit`, `bunny`, `bdsm`, `wuxia_actions`, `spy_actions` 등 8개 공용 테마팩을 기본 포즈 DB와 동적 병합 | **A** — `test_pose_db_contracts.py` 통과, 단 영숫자 코드(`D01`, `S1`, `C1` 등) 사용 | 데이터 스키마 변경 수반 | **Kiro 미보유**: Kiro `pose_db.py:parse_pose_db()`는 정수 키(`int(key)`)만 허용해 영숫자 코드 파싱 불가 | **보류·제외 (Tier 3)** |
| `plepa_engine/services/generation_service.py` (`get_optimal_resolution_for_pose`) — `1,093L` / `88f6b94be847` | 포즈별 최적 해상도 반환 함수 (커밋 `c231242` 이후 전 포즈 `default_w, default_h` 단일 세로형 832x1216 패스스루로 단순화됨) | **C** — `test_dynamic_aspect_ratio.py` 3건 통과하나 실질 로직 없는 패스스루 | 순수 Python | **Kiro가 더 최신**: Kiro `scene_composer.py:273`에서 `entry.width`/`entry.height` 포즈별 개별 해상도 오버라이드를 이미 지원 | **보류·제외 (Tier 3)** |

### 영역 3. Auto-QC 검수 엔진 (6개 기능)
| 모듈 / 핵심 심볼 (줄 수 / SHA-256) | 기능 요약 | 완성도 등급 + 근거 | 백엔드 의존성 | Kiro 현황 대조 | 이식 판정 |
|---|---|---|---|---|---|
| `plepa_engine/qa_validator.py` (`_compute_color_burn_ratio`) — `402L` / `ed548bfc59aa` | 256×256 다운샘플링 기반 극단 네온 과포화(`S>0.94 & V>=0.35`) 및 RGB 채널 클리핑(Color Burn) 비율 측정 + 야경 예외(`0.35`) | **S** — `test_qa_validator.py` 10건 통과, 순수 NumPy/PIL(ML 모델 불필요), 초고속 | 순수 Python (엔진 독립) | **Kiro 미보유** | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/qa_validator.py` (`_check_closeup_aspect_drift`) — `402L` / `ed548bfc59aa` | 상반신/포트레이트/클로즈업 씬에서 얼굴 높이 비율(`< 8%`)로 전신 롱샷 이탈(화각 드리프트) 자동 감지 | **S** — `test_qa_validator.py` 통과, 기존 `detect_faces` 결과 재활용으로 추가 추론 비용 0 | 순수 Python (엔진 독립) | **Kiro 미보유** | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/qa_validator.py` (`validate_generated_image` Short-Circuit + 피사체 증발 + 오프스크린/밀착/faceless 분기) — `402L` / `ed548bfc59aa` | Person→Head→Face→Hand 순서 조기 종료(Short-Circuit), 피사체 증발(`persons==0` 또는 `heads==0 & faces==0`) 감지, `headless` 예외, 오프스크린/밀착/뒤통수 접촉/`faceless` 얼굴 상한(`<=1`) 정교화 | **S** — `test_qa_validator.py` 10건 통과, 오탐/미탐 실전 튜닝 완료. 단, 모듈 최상위 `imgutils` Eager Import는 Kiro 대비 열위 | 순수 Python (엔진 독립) | **Kiro에 부분 존재**: `kiro/generator/qa_validator.py`(`191L`, `a8285b150c7d`)는 **Lazy ML Load(`_ensure_qa_runtime`)가 더 우수**하나 Short-Circuit·오프스크린·밀착·피사체 증발·`faceless` 얼굴 상한 판별 부재 | **즉시 이식 추천 (Tier 1)** *(Kiro Lazy Load 유지 병합)* |
| `plepa_engine/qa_validator.py` (`check_blur` / `laplacian_score`, `check_aesthetic` / `anime_dbaesthetic`) — `402L` / `ed548bfc59aa` | 선택적 라플라시안 블러 점수 및 애니메이션 미학 점수(`imgutils.metrics`) 0단계 게이트 | **A** — 기본값 `False` 옵트인, 예외 안전 처리 완료 | 순수 Python (`imgutils.metrics` 선택 의존) | **Kiro 미보유** | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/services/generation_service.py` (`strict_censor_qc` 연동) — `1,093L` / `88f6b94be847` | 성인 노출 필수 씬에서 `detect_genitals()` 미탐지 시 구도 불량으로 판정해 자동 리롤 (`censor=False` 독립 지원 포함) | **A** — `test_censor_and_pipeline_fixes.py` 회귀 테스트 통과 | 순수 Python (엔진 독립) | **Kiro 미보유**: `kiro/generator/runner.py:_generate_and_validate_image()`는 Auto-QC만 수행하고 성기 미탐지 리롤 없음 | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/qa_validator.py` (`configure_qa_runtime`) — `402L` / `ed548bfc59aa` | CPU 스레드 제한 및 선택적 프로세스 우선순위 하향 지연 초기화 | **B** — 스레드 설정은 지연되었으나 `imgutils` import 자체는 최상위 Eager | 순수 Python | **Kiro가 더 최신**: `kiro/generator/qa_validator.py:_ensure_qa_runtime()`이 `imgutils` import까지 완전 Lazy Load 처리 | **보류·제외 (Tier 3)** |

### 영역 4. 자동 검열 엔진 (7개 기능)
| 모듈 / 핵심 심볼 (줄 수 / SHA-256) | 기능 요약 | 완성도 등급 + 근거 | 백엔드 의존성 | Kiro 현황 대조 | 이식 판정 |
|---|---|---|---|---|---|
| `plepa_engine/censor.py` (`_compute_scale_factor`, `_scale_int`, `_odd_kernel`, `apply_shadow_silhouette` 소프트 페더링, `apply_mosaic` ROI 국소화) — `3,787L` / `e52b81b0e8fb` | 832px 기준 해상도 비례 커널 스케일링(4K 대응), Shadow Box 소프트 타원 페더링, 모자이크 ROI 국소 리사이즈 최적화 | **S** — `test_smart_censor.py` 30건 포함 40건+ 통과, 순수 OpenCV/PIL | 순수 Python (엔진 독립) | **Kiro 미보유**: `kiro/generator/censor.py`(`832L`, `d09740561961`)는 고정 픽셀 커널(`16`, `14`), 직사각 Shadow paste, 전체 이미지 모자이크 리사이즈 사용 | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/censor.py` (`_SAM_MODEL_LOCK`, `unload_censor_models`, ROI Padded Crop SAM 추론) — `3,787L` / `e52b81b0e8fb` | 스레드 안전 MobileSAM 싱글톤 락, 배치 종료 후 VRAM 캐시 해제(`torch.cuda.empty_cache`), 4K 이미지 전체 대신 ROI 패딩 크롭만 SAM 추론 | **S** — 8GB VRAM 환경 OOM 방지 실증, 단위 테스트 통과 | 순수 Python (엔진 독립) | **Kiro 미보유**: Kiro `censor.py`는 락 없음, 전체 이미지 SAM 추론, VRAM 언로드 함수 없음 | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/censor.py` (`_detect_target_candidates`, `_get_roi_specs_for_pose`, 고신뢰 역광 Skin Density Gate 면제, `_filter_bottom_edge_false_positives`) — `3,787L` / `e52b81b0e8fb` | 체위별 맞춤형 1.6× Zoom-In ROI 다중 스케일 탐지, `score >= 0.50` 역광/야경 피부율 게이트 면제, IoU>0.45 병합(`penis` 우선), 하단 경계 오탐 필터링 | **S** — `test_smart_censor.py` & `test_censor_and_pipeline_fixes.py` 전수 통과, SPY 510장 실전 검증 | 순수 Python (엔진 독립, 포즈 카테고리 매핑만 어댑팅) | **Kiro에 부분 존재**: Kiro `censor.py`는 단일 전체 스캔 위주이며 역광 면제·하단 경계 오탐 필터·체위별 ROI 최적화 없음 | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/censor.py` (`apply_manga_bar`, `apply_manga_glow`, `_estimate_penis_axis_and_base`) — `3,787L` / `e52b81b0e8fb` | 주축·기저부 기하 추정 기반 상업 망가식 화이트 바(`manga_bar`) 및 글로우(`manga_glow`) 검열 스타일 | **A** — `test_smart_censor.py` 통과, 순수 OpenCV/NumPy | 순수 Python (엔진 독립) | **Kiro 미보유** | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/censor.py` (`verify_and_heal_censor`, `_render_censored_style`, `_atomic_replace_with_retry`) — `3,787L` / `e52b81b0e8fb` | 검열 후 잔여 노출 2차 재검증/치유 게이트, 공용 스타일 디스패처, Windows `os.replace` `PermissionError` 지수 백오프 재시도 | **S** — 단위 테스트 통과, Windows 파일락 크래시 방지 실증 | 순수 Python (엔진 독립) | **Kiro 미보유**: Kiro는 `verify_and_heal_censor` 및 `os.replace` 재시도 없음 (`runner.py:288`은 `unlink()+rename()` 비원자적 교체) | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/censor.py` (Phase P2.5 하이브리드 YOLO11s-seg + Semantic-Guided SAM 2.1 + 선화 장벽 스냅 + 손 가려짐 분리, ADR-95~99) — `3,787L` / `e52b81b0e8fb` | 커스텀 학습 `censor_seg` 모델 + SAM 2.1 상호배타 프롬프트 + 2D 선화 장벽 클램핑 + 전경 손 실루엣 보호 + Residual Span 2-Way 복원 | **S** — SPY 510장 정량 벤치마크 동결(ADR-99), `test_smart_censor.py` 30건 통과 | 커스텀 가중치(`models/censor_seg/`) 및 2,500줄+ 복잡도 수반 | **Kiro 미보유**: Kiro는 기본 MobileSAM + `detect_hands/faces/heads` 보호 마스크 사용 | **어댑팅 후 이식 (Tier 2)** *(모듈 분리 권장)* |
| `plepa_engine/censor.py` (`run_batch_censor`, `is_pose_censor_required`) — `3,787L` / `e52b81b0e8fb` | 폴더 일괄 검열 및 V3 대역 검열 대상 판정(`DAILY_EXPOSURE_CODES={"037"}`, `NON_EXPOSURE_H_POSES` 24종, `plepa_engine.services.pose_service` 의존) | **B** — `plepa`에서는 안정적이나 `_origin` 문자열 정확 일치만 체크(`aya_origin` 미필터) 및 V3 대역 하드코딩 | 데이터·폴더 스키마 변경 수반 | **Kiro가 더 최신**: Kiro Wave 3 `censor.py:run_batch_censor()`가 `backup_origin`, `restore_origin`, `char_names`, `_restore_from_origin_dirs()`, `_origin` 부분문자열 안전 필터 완비 | **보류·제외 (Tier 3)** |

### 영역 5. 서비스·계약·사전점검·감사 도구 (8개 기능)
| 모듈 / 핵심 심볼 (줄 수 / SHA-256) | 기능 요약 | 완성도 등급 + 근거 | 백엔드 의존성 | Kiro 현황 대조 | 이식 판정 |
|---|---|---|---|---|---|
| `plepa_engine/services/generation_service.py` (`GENERATION_OPTION_SPECS`, `compute_deterministic_pose_seed`) — `1,093L` / `88f6b94be847` | CLI·Engine·GUI 삼위일체 단일 진실 공급원(SSOT) 옵션 레지스트리 + CRC32 기반 프로세스 독립 결정론적 포즈 시드 산출 | **S** — `test_cli_gui_sync.py` 10건 + `test_audit_and_seed.py` 4건 전수 통과 | 순수 Python (엔진 독립) | **Kiro에 부분 존재**: `GenerationOptions` 데이터클래스는 있으나 CLI/GUI 옵션 메타 레지스트리(SSOT) 및 결정론적 시드 함수 없음 | **즉시 이식 추천 (Tier 1)** |
| `plepa_engine/precheck.py` (`run_pregeneration_check`, `check_pose_doc_sync`) — `384L` / `96117b45d371` | 6~7단계 사전 점검(포즈 규칙, 캐릭터 JSON, **전 포즈 조립 시뮬레이션 착의 고정/탈의 누수/테마 스왑 검증**, 배경 매핑 검증, 포즈 DB↔문서 동기화) | **A** — `campus`/`spy`/`oto`/`ykn` PASS, `test_pose_doc_sync.py` 5건 통과. 단, 일부 로스터별 `_SIGNATURE_OUTFIT_TOKENS` 하드코딩 및 `BREAK` 필수 규칙 존재 | 순수 Python (Kiro 스키마에 맞게 규칙 조정 필요) | **Kiro에 부분 존재**: `kiro/generator/precheck.py`(`184L`, `92fb509c8131`)는 정적 JSON 검사만 수행하고 **전 포즈 조립 시뮬레이션(착의 고정/알몸 의상 누수 검사)과 배경 매핑 검증 부재** | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/services/health_service.py` (`HealthService` 7단계 자가진단) — `712L` / `75cdb6e2be5e` | 포즈 DB→캐릭터→파이프라인→사전점검→워크플로우→검열→Auto-QC 7단계 통합 헬스 체크 및 테이블 리포터 | **A** — `test_cli_gui_sync.py:test_system_health_diagnostics` 통과 | 일부 ComfyUI/Plepa 서비스 결합 | **Kiro에 부분 존재**: `TestReport` 기반 `--test` 자가진단 존재 | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/services/asset_service.py` (`AssetService` 2-Track 탐색기, 휴지통 삭제/Undo, `_origin` 복원) — `438L` / `92965a0ad6f4` | 신규 2대 서브폴더(`01_normal`, `02_h_scenes`) + 구 6대 + 플랫 경로 3-Track 탐색, 번들 휴지통 이동(`delete_asset_bundle`) 및 복원(`restore_asset_bundle`) | **A** — `test_directory_structure.py` 4건 + `test_security_and_atomic_io.py` 7건 통과 | 데이터·폴더 스키마 일부 연동 | **Kiro 미보유**: Kiro는 플랫 `assets/{char}/` 구조이며 휴지통/Undo 서비스 없음 | **어댑팅 후 이식 (Tier 2)** |
| `plepa_engine/services/genit_exporter.py` (`GenitExporter`) — `203L` / `1b665ef73a17` | `genit_map.json` 동적 매핑 기반 Gen-IT 상용 규격(`{{url}}캐릭터코드/상황코드.webp`) 일괄 변환·패키징 | **S** — `test_genit_exporter.py` 3건 + `test_censor_and_pipeline_fixes.py` 동적 로스터 검증 통과, 203줄 경량 | 순수 Python (엔진 독립) | **Kiro에 부분 존재**: `gui/runner_bridge.py:build_char_zenit_block()`만 존재하며 파일 일괄 패키징/변환기 없음 | **즉시 이식 추천 (Tier 1)** |
| `scripts/audit_asset_alignment.py` — `506L` / `af472385108f` | 로스터 전체 캐릭터 에셋의 포즈 DB 대비 완비율, 라벨 불일치, 누락 코드 감사 및 안전 리네임 도구 | **A** — `test_asset_pose_alignment.py` 6건 통과 | 순수 Python (경로/파일명 규칙 어댑팅 필요) | **Kiro 미보유** | **어댑팅 후 이식 (Tier 2)** |
| `scripts/validate_genit_work.py` — `411L` / `0a04d80e10e6` | Gen-IT 5탭 완성본(글자 수, 설정집, 캐릭터, 6대 변수, 실제 에셋 404 검증) + Frontmatter `status` 기반 SHA-256 스마트 캐시 검증기 | **A** — 실전 운영 중(본 감사에서도 `103_입위약`/`104_입위강` 404 위험 정확 포착) | 순수 Python (`docs/genit/` 규약 의존) | **Kiro 미보유** | **어댑팅 후 이식 (Tier 2)** |
| `scripts/export_context.py` — `687L` / `3c77e71ca8d1` | AST/메타/해시/체크 기반 3-Tier 컨텍스트 스냅샷 및 델타 자동 추출기 (AI 협업 토큰 최적화) | **S** — `test_export_context.py` 6건 통과, 순수 표준 라이브러리 기반 | 순수 Python (경로 목록만 어댑팅) | **Kiro 미보유** | **즉시 이식 추천 (Tier 1)** |

### 영역 6. ComfyUI 워크플로우 & GUI (5개 기능)
| 모듈 / 핵심 심볼 (줄 수 / SHA-256) | 기능 요약 | 완성도 등급 + 근거 | 백엔드 의존성 | Kiro 현황 대조 | 이식 판정 |
|---|---|---|---|---|---|
| `plepa_engine/workflow_templates.py` (`build_sdxl_workflow`, `build_standalone_upscale_workflow`, `REQUIRED_CUSTOM_NODES`) + `comfy_client.py` (`verify_required_nodes`) — `296L` / `676e2fd746f2`, `462L` / `468312a277d2` | 2-Track 하이브리드 IP-Adapter(`full`/`face_only`), Face/Hand Detailer 체이닝, FreeU, 단독 4K 업스케일, 커스텀 노드 사전 감지(Pre-flight) | **S** — `test_preflight_nodes.py` 6건 + `test_upscale.py` 3건 + `test_cli_gui_sync.py` 통과 | **ComfyUI 전용** (Forge에서는 ADetailer/ControlNet/Extras API로 대체 구현 필요) | **Kiro에 부분 존재**: `generator/webui_client.py` + `reference.py`에 Forge용 ADetailer·ControlNet·FreeU·Extras 이미 구현됨 (단, `face_only` 2-Track 분기 컨셉은 참고 가치) | **보류·제외 (Tier 3)** *(컨셉만 참고)* |
| `plepa_engine/services/job_manager.py` (`GlobalJobManager`) — `360L` / `f7b5465866f0` | 비동기 FIFO 배치/리롤 작업 큐 직렬화, 진행률·이력·QC 경고 피드백·취소 관리 | **A** — `test_comfy_and_job_queue.py` 3건 통과 | 순수 Python (엔진 독립) | **Kiro에 부분 존재**: `gui/state.py:GuiRuntimeState`가 단일 작업 실행/취소만 지원하며 FIFO 대기열 큐 없음 | **어댑팅 후 이식 (Tier 2)** |
| `plepa_gui/pages/gallery.py` + `plepa_gui/pages/mobile_viewer.py` + `plepa_gui/api_routes.py` — `1,492L`/`0e6395447244`, `767L`/`67c65123192f`, `456L`/`dc3307b44352` | 캐릭터×포즈 매트릭스 비교 뷰, 라이트박스, `_origin` 스페이스바 토글·복원, 모바일 검수 갤러리, 즉시 재검열·리롤·삭제/Undo REST API + 토큰 인증 | **S** — `test_gui_all_features.py` 10건 + `test_mobile_inspection_api.py` 9건 통과, 실전 검수 핵심 | NiceGUI/FastAPI (Plepa 서비스 어댑팅 필요) | **Kiro 미보유**: `kiro/gui/` 6모듈은 생성 제어/모니터링 전용이며 **갤러리·라이트박스·매트릭스·모바일 뷰어·REST API 전혀 없음** | **어댑팅 후 이식 (Tier 2)** |
| `plepa_gui/components/retouch_editor.py` (`build_retouch_editor_script`) — `563L` / `27c82bde4f29` | PC 갤러리 & 모바일 뷰어 공용 인라인 터치/마우스 캔버스 덧칠(화이트/블랙 브러시, 지우개, Undo, 확대) 및 파일 교체 에디터 (ADR-86) | **A** — 최신 이식 완료, `test_mobile_inspection_api.py` API 연동 검증 | 프론트엔드 JS/HTML + 파일 교체 API | **Kiro 미보유** | **어댑팅 후 이식 (Tier 2)** |
| `plepa_gui/pages/generate.py` (동적 `GENERATION_OPTION_SPECS` 렌더링) — `544L` / `a55a0b36e5d4` | 옵션 스펙 레지스트리 기반 체크박스/셀렉트 자동 렌더링 + 설정 영속화 | **A** — `test_gui_all_features.py` 통과 | NiceGUI (`gui/components.py` 어댑팅) | **Kiro에 부분 존재**: `kiro/gui/components.py`(`479L`)에 수동 위젯 바인딩 존재 | **어댑팅 후 이식 (Tier 2)** |

### 영역 7. 포즈 DB & 에셋 체계 (3개 기능)
| 모듈 / 핵심 심볼 (줄 수 / SHA-256) | 기능 요약 | 완성도 등급 + 근거 | 백엔드 의존성 | Kiro 현황 대조 | 이식 판정 |
|---|---|---|---|---|---|
| `data/sdxl_pose_database.json` (V3 대역 `000~209`, 공통봉사 `064~079`, 3단계 시퀀스, `mob_tier`/`partner_pos` 메타) — `175종` | 4-Tier 모브 메타데이터 및 공통 봉사 대역이 반영된 최신 SDXL 포즈 DB | **A** — `test_pose_db_contracts.py`·`test_pose_doc_sync.py` 통과. 단, `_total_poses`(183) vs 실측(175) 미세 괴리 및 `events` 섹션 부재 | **데이터·폴더 스키마 변경 수반** | **Kiro와 구조 분기**: Kiro는 V2 159종(`events` 13종 유지) + 20개 로스터 기존 완성 에셋과 강결합 | **보류·제외 (Tier 3)** *(메타 필드·개선 프롬프트만 선별 병합)* |
| `data/pose_sets.json` + `PoseService.resolve_pose_codes()` — `21종` / `645L` / `7585806277e1` | `sample10`, `unified_100`, `h_scenes_52`, `otokonoko_52` 등 프리셋 포즈 세트 정의 및 범위/키워드 해석 | **S** — `test_cli_gui_sync.py` 통과, 1분 고속 검증(`sample10`)에 매우 유용 | 순수 Python + JSON (Kiro 코드 대역에 맞게 세트 조정) | **Kiro 미보유**: Kiro는 섹션명(`emotions,poses`) 또는 숫자 범위만 지원 | **즉시 이식 추천 (Tier 1)** |
| 2대 서브폴더(`01_normal`, `02_h_scenes`) + 3-Track 폴백 구조 (`asset_service.py`, `pose_service.py`) — `438L` / `92965a0ad6f4` | 에셋을 일반/성인 2개 폴더로 물리 분리하고 구 6대/플랫 폴더와 하위 호환 유지 | **A** — `test_directory_structure.py` 4건 + `test_v2_migration.py` 5건 통과 | **데이터·폴더 스키마 변경 수반** | **Kiro 미보유**: Kiro 20개 로스터가 플랫 `assets/{char}/` 구조로 안정 운영 중 | **보류·제외 (Tier 3)** *(기존 20개 로스터 무손실 원칙상 불필요)* |

---

## 3. 핵심 이식 후보 상세 딥다이브 (Tier 1 & Tier 2 중심)

### 3.1 프롬프트 품질·안정화 번들 (Tier 1 즉시 이식 — 체감 효과 최상)
- **대상 기능**: `harmonize_character_expression`, `remove_conflicting_tags_from_negative` + `_strip_tags_preserving_parens`, `CompositionAntiDriftMutator`, 가중치 상시 클램핑(`pos<=1.15`, `neg<=1.25`), `DEFAULT_THEME_OUTFITS` + 확장 `_OUTFIT_KEYWORDS`
- **구체적 코드 차이 (`plepa` vs `kiro`)**:
  - `kiro/generator/prompt.py:62`에는 `find_tag_conflicts(positive, negative)`가 있지만 **탐지만 하고 네거티브에서 제거하지 않음**. 반면 `plepa`의 `remove_conflicting_tags_from_negative()`는 중첩 괄호(`((smile:1.2, bad hands))`)를 깨뜨리지 않고 충돌 토큰만 외과적으로 제거함.
  - `kiro/generator/scene_composer.py:508`은 `enable_clamp_weights: bool = False`가 기본값이라 평소 가중치 클램핑이 작동하지 않고, 켜더라도 `full_prompt`만 클램핑하고 `actual_negative`(현재 `((...:1.55))`, `:1.8` 등 과도 가중치 다수 포함)는 클램핑하지 않아 Illustrious-XL 계열에서 색번짐/과포화 원인이 됨.
  - `kiro/generator/scene_composer.py`에는 캐릭터 고정 표정(`smile` 등)이 슬픈/분노/절정 포즈 표정과 충돌하는 문제를 푸는 `harmonize_character_expression()`과 샷 사이즈 반대 구도 이탈 방지(`CompositionAntiDriftMutator`)가 전무함.
- **Kiro 이식 시 주의·선행 조건**:
  - 모두 **순수 함수**이므로 `kiro/generator/prompt.py`와 `kiro/generator/scene_composer.py`에 직접 편입 가능하며 기존 20개 로스터 파일이나 Forge API에 어떤 파괴적 영향도 없음.
  - 단, `kiro/tests/test_wave2_core.py`에서 `scene_composer` 네거티브 가중치 문자열을 직접 단언하는 테스트가 있다면, 클램핑 기본값을 켜기 전에 테스트 기대치를 함께 확인해야 함.

### 3.2 Auto-QC 검수 엔진 고도화 (Tier 1 즉시 이식 — Lazy Load 보존 병합)
- **대상 기능**: `_compute_color_burn_ratio()`, `_check_closeup_aspect_drift()`, Short-Circuit(Person→Head→Face→Hand 조기 종료), 피사체 증발 감지 + `headless` 예외, 오프스크린/밀착/`faceless` 얼굴 상한(`<=1`), 선택적 `check_blur`/`check_aesthetic`
- **구체적 코드 차이 (`plepa` vs `kiro`)**:
  - `kiro/generator/qa_validator.py`는 **Wave 0의 `_ensure_qa_runtime()` Lazy ML Load**가 우수함(import 시점에 `imgutils`/`torch` 미로드). 반면 `plepa/plepa_engine/qa_validator.py:50~71`은 여전히 모듈 최상위에서 `imgutils`를 Eager Import함.
  - 판정 정밀도는 `plepa`가 압도적으로 앞섬: `kiro`는 `detect_person`→`detect_heads`→`detect_hands`→`detect_faces` 4개 ONNX 모델을 무조건 전부 실행(낭비)하며, Color Burn 감지, 화각 드리프트, 피사체 증발(`persons==0`), 오프스크린 파트너(`is_offscreen_partner`일 때 아예 검사를 건너뜀!), `faceless` 위반(`max_faces=1`)이 모두 빠져 있음.
- **Kiro 이식 시 주의·선행 조건**:
  - **절대 `plepa_engine/qa_validator.py`를 그대로 복사하지 말 것** (Kiro Lazy Load 파괴).
  - `kiro/generator/qa_validator.py`의 `_ensure_qa_runtime()` 뼈대는 100% 유지하면서, `plepa`의 순수 헬퍼(`_compute_color_burn_ratio`, `_check_closeup_aspect_drift`, `_is_headless_closeup_prompt`)와 `validate_generated_image()` 내부 Short-Circuit/분기 로직만 이식. `check_blur`/`check_aesthetic`용 `imgutils.metrics`도 `_ensure_qa_runtime()` 내부 Lazy Import로 편입.

### 3.3 `PoseBackgroundService` + `pose_sets.json` + `GenitExporter` + `export_context.py` (Tier 1 즉시 이식)
- **구체적 코드 차이 (`plepa` vs `kiro`)**:
  - Kiro `projects/`에는 이미 `pose_background_mapping.json`이 4개 로스터에 존재하지만, `kiro/generator/prompt.py:resolve_background()`가 이를 읽지 못해 모든 포즈에 단일 `default` 배경만 적용됨. `PoseBackgroundService`(120L)를 어댑팅하면 기존 플랫 `background.json` 스키마를 유지한 채 포즈 대역별 자동 배경 매핑이 즉시 활성화됨.
  - `GenitExporter`(203L)는 `genit_map.json`을 읽어 에셋을 상용 규격으로 패키징하는 순수 파일 변환기로, Kiro 20개 로스터의 플랫 `assets/{char}/` 경로만 지원하도록 경로 탐색부 5줄만 맞추면 즉시 동작.
  - `pose_sets.json`은 Kiro V2 대역(`000~199`, `events` 040~059)에 맞춰 코드 목록만 매핑하면 CLI/GUI 고속 샘플러(`sample10` 등)로 즉시 활용 가능.

### 3.4 검열 엔진 핵심 개선 이식 (Tier 1 안정화 + Tier 2 고급 기능)
- **구체적 코드 차이 (`plepa` vs `kiro`)**:
  - **Tier 1 (즉시 편입 가능)**: `_SAM_MODEL_LOCK`, `unload_censor_models()`, 동적 해상도 스케일 커널(`_compute_scale_factor`, `_odd_kernel`), ROI Padded Crop SAM 추론, `apply_shadow_silhouette` 소프트 타원 페더링, `apply_mosaic` ROI 국소 리사이즈, `verify_and_heal_censor`, `_atomic_replace_with_retry`.
  - **Tier 2 (어댑팅 필요)**: 다중 스케일 Zoom-In ROI + 고신뢰(`>=0.50`) 역광 Skin Density Gate 면제 + 하단 경계 오탐 필터 + `manga_bar`/`manga_glow` + Phase P2.5 하이브리드 YOLO11s-seg/선화 스냅/손 가려짐 분리.
- **Kiro 이식 시 주의·선행 조건**:
  - **Kiro Wave 3의 `run_batch_censor()`, `_restore_from_origin_dirs()`, `is_censor_target()`, `get_origin_backup_path()`는 Kiro가 더 깔끔하고 20개 로스터에 최적화되어 있으므로 반드시 보존**해야 함.
  - `kiro/generator/runner.py:288`의 비원자적 `save_path.unlink(); tmp_censored.rename(save_path)`를 `plepa`의 `_atomic_replace_with_retry()`로 교체하면 Windows 파일락 크래시와 중단 시 파일 유실 위험을 제거할 수 있음.
  - Phase P2.5(3,787줄) 전체를 한 파일에 넣기보다 `censor_styles.py` / `censor_seg.py` 등 서브모듈로 분리 이식하는 것을 권장.

### 3.5 4-Tier 모브 파이프라인(ADR-100/101/105) & GUI 갤러리/리터치 에디터 (Tier 2 어댑팅)
- **4-Tier 모브 파이프라인**:
  - `kiro/generator/scene_composer.py`는 현재 모든 2인 씬에 `faceless male`과 강한 네거티브(`:1.55`, `:1.8`)를 일괄 주입해 마네킹화/이염 위험이 있음.
  - Kiro `PoseEntry`에 선택 필드 `mob_tier: int | None = None`, `partner_pos: str | None = None`을 하위 호환 기본값(`None`)으로 추가하면, 기존 159종 V2 포즈 DB를 깨뜨리지 않고도 점진적으로 4-Tier 모브 규칙과 상안부 그림자 음영(`GEMINI.md` 9조 표준)을 적용할 수 있음.
- **GUI 갤러리·라이트박스·매트릭스·수동 리터치 에디터**:
  - Kiro `gui/`는 현재 NiceGUI 기반 **생성 제어/모니터링 전용(6모듈)**이며 생성된 이미지를 검수·비교·리롤·원본복원·터치 덧칠하는 갤러리가 전혀 없음.
  - Kiro도 동일하게 NiceGUI 기반이므로 `plepa_gui/pages/gallery.py` + `retouch_editor.py` + `GlobalJobManager`를 Kiro의 `gui/state.py` 및 `generator/runner.py` 훅에 연결하면 생산성이 대폭 향상됨 (단, 경로 탐색을 Kiro 플랫 `assets/{char}/` + `{char}_origin/` 구조에 맞게 어댑팅 필요).
- **`precheck.py` 전 포즈 조립 시뮬레이션 확장**:
  - Kiro `generator/precheck.py`에 `compose_scene_prompt()` 기반 착의 고정/탈의 의상 누수 시뮬레이션 단계를 추가하면, 20개 로스터 캐릭터 JSON 품질 회귀를 사전 차단 가능. 단, Plepa의 `BREAK` 필수 강제나 특정 로스터(`spy`/`campus`) 하드코딩 토큰은 제외하고 Kiro의 `char_prompt`/`nude_positive` 스키마에 맞춰 범용화해야 함.

---

## 4. `scripts/sync_to_kiro.py` 충돌 위험 진단

현재 `plepa/scripts/sync_to_kiro.py` (`324L`, `d8fe3b19be0c`)는 **Wave 0~4 리팩토링 이전의 구형 Kiro를 전제로 작성된 강제 덮어쓰기 스크립트**입니다. 최신 `kiro`(`a3bb763`)에 그대로 실행할 경우 아래 **5가지 파괴적 충돌**이 즉시 발생합니다.

| # | 대상 함수 / 라인 | 덮어쓰기 동작 | 최신 Kiro(Wave 0~4)에서의 파괴적 충돌 위험 | 심각도 |
|---|---|---|---|---|
| 1 | `sync_core_modules()` (L175~202) | `plepa_engine/censor.py` → `kiro/generator/censor.py` 통째 `shutil.copy2` | ① `from plepa_engine.config import ...`, `from plepa_engine.services.pose_service import ...`가 유입되어 **`ModuleNotFoundError: No module named 'plepa_engine'` 즉시 크래시**.<br>② Kiro Wave 3 통합 검열 코어의 핵심 심볼(`is_censor_target`, `extract_pose_code`, `get_origin_backup_path`, `_restore_from_origin_dirs`, `run_batch_censor(backup_origin, restore_origin, char_names)`)이 **전면 소멸**하여 `auto_censor.py`, `generator/runner.py`, `tests/test_wave3_gui_censor.py` 전부 파손. | **CRITICAL (치명적)** |
| 2 | `sync_core_modules()` (L175~202) | `plepa_engine/qa_validator.py` → `kiro/generator/qa_validator.py` 통째 `shutil.copy2` | ① Kiro Wave 0의 **Lazy ML Load(`_ensure_qa_runtime()`)가 소멸**하고 `imgutils` 최상위 Eager Import로 회귀.<br>② `tests/test_wave0_safety.py`의 import 무부작용/Lazy 로드 테스트 실패 및 GUI 기동 지연 유발. | **HIGH (높음)** |
| 3 | `sync_pose_database()` (L70~139) | `plepa/data/sdxl_pose_database.json` → `kiro/pose_database.json` 덮어쓰기 | ① `plepa` DB에는 `events` 섹션이 없어 `plepa_db.get("events", {})`가 빈 딕셔너리 `{}`로 기록됨 → **Kiro의 `events` 13종(040~059) 영구 증발**.<br>② `plepa`는 V3(`poses` 31종, `romance` 20종, `h_scenes` 47종, `special_otokonoko` 6종)인 반면 Kiro는 V2(`poses` 20종, `events` 13종, `romance` 4종, `h_scenes` 48종, `special_otokonoko` 3종) → Kiro 20개 로스터 기존 에셋 번호와 불일치 및 `tests/test_wave1_integrity.py` 파손. | **CRITICAL (치명적)** |
| 4 | `sync_project_configs()` (L142~172) | `plepa/projects/*/{background.json, pose_overrides.json, pose_background_mapping.json}` 덮어쓰기 | `plepa`의 `background.json`은 `{"presets": {"default": {"sdxl": "..."}}}` **중첩 스키마**이나, `kiro`의 `background.json`은 `{"default": "..."}` **플랫 문자열 스키마**(`generator/prompt.py:160`, `generator/precheck.py:172`). 덮어쓰기 시 Kiro 배경 로더가 문자열이 아닌 딕셔너리를 만나 **배경 전체 적용 실패 및 precheck 경고 폭발**. | **HIGH (높음)** |
| 5 | `rename_kiro_assets()` (L205~281) | `docs/POSE_MAPPING_V2.md` 매핑으로 `kiro/projects/*/assets/` 2-Pass 리네임 + `os.replace()` | 이미 V2 번호 체계로 전환 완료된 Kiro 20개 로스터 에셋에 재실행할 경우, 구번호→신번호 매핑에 걸리는 정상 신번호 파일들이 **재리네임되며 `os.replace()`로 기존 정상 파일을 덮어써 영구 유실**시킬 위험 (비멱등성). | **CRITICAL (치명적)** |

> **결론**: `scripts/sync_to_kiro.py`는 **절대 실행 금지(폐기 또는 전면 재설계 대상)**이며, Kiro 이식은 반드시 본 리포트의 Tier 1 → Tier 2 순서에 따라 **단위 기능별 어댑팅 + Kiro 테스트(`pytest` 34건 + 신규 회귀 테스트) 검증** 방식으로 진행해야 합니다.

---

## 5. 최신 컨텍스트 스냅샷 갱신 결과

- **실행 명령**: `.\.venv\Scripts\python.exe scripts/export_context.py`
- **갱신된 `snapshot_id`**: `20261120-0050-plepa@7f73b81+dirty-kiro@a3bb763`
- **생성 산출물** (`context_snapshot/`, `.gitignore` 대상 — 추적 파일 변경 없음):
  - `context_snapshot/00_README_FOR_AI.md` (2 KB)
  - `context_snapshot/10_TIER1_CONSTITUTION.md` (39 KB)
  - `context_snapshot/20_TIER2_CORE_LOGIC.md` (39 KB)
  - `context_snapshot/30_TIER3_RUNTIME.md` (18 KB)
  - 변경분: 9건
- **Git 추적 상태 확인**: `git status --short` 기준 기존 미커밋 16개 외 추가 추적 파일 변경 **0건** (신규 리포트 `plepa_feature_audit_for_kiro.md` 1건만 untracked).
