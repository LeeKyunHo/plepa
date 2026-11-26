# ⚡ 플에파 (PLEPA: Prompt-Light Engine for Portrait Assets)

ComfyUI 로컬 API(`127.0.0.1:8188`)를 기반으로 캐릭터 챗봇용 고화질 2D 애니메이션 스탠딩·일상·성인 에셋을 일관성 있게 대량 생산하는 **데이터 주도형 AI 에셋 파이프라인 & 웹 스튜디오**입니다.

---

## 🚀 1. 프로젝트 개요 및 기술 스택 (SDXL 단일 표준)

- **생성 엔진**: ComfyUI 로컬 API (`http://127.0.0.1:8188`) + SDXL Illustrious 단일 파이프라인
- **기본 체크포인트 & 사양**: `UnholyDesireMixSinisterAesthetic_V9_Illustrious.safetensors` (`CFG 4.0`, `Steps 28`, `dpmpp_2m / karras`, `CLIP Skip -2`, `FreeU` 활성)
- **하이브리드 최적 해상도**: `000~024` 세로형 (`832×1216`) / `025+` 가로형 (`1216×832`, `--width`/`--height` 지정 시 우선)
- **후처리·검열**: `FaceDetailer` (기본 활성) / `HandDetailer` (선택) / `4x-UltraSharp` 업스케일 / **Phase P2.5 하이브리드 검열** (`deepghs` + `censor_seg.pt` YOLO11s-seg + `sam2.1_s.pt`, 기본 `white_silhouette` 총 11종, `{char}_origin/` 100% 무손실 보존)
- **V3 포즈 데이터베이스 ([`data/sdxl_pose_database.json`](data/sdxl_pose_database.json))**:
  - 코어 DB `175`개 키(활성 `151`종 + 호환 보존 `24`종) · 포즈 단일 매핑 SSOT: **[`POSE_MAPPING.md`](POSE_MAPPING.md)**
  - `000~019` 감정(20) · `020~050` 일상(31) · `051~055` 로스터 이벤트(`events.json`) · `060~079` 로맨스/공통 봉사(20) · `080~127` 여성 성인(활성 35) · `130~132` 여성 특수(3) · `150~197` 오토코노코 성인(활성 39) · `133~135`/`200~202` 오토 특수
- **지원 로스터 (`12`개)**: `campus`, `spy`, `oto`, `ykn`, `sns`, `maid`, `murim`, `school`, `hey`, `man`, `don`, `default`

---

## ⚙️ 2. 빠른 실행 (CLI & NiceGUI 웹 스튜디오)

### A. 웹 스튜디오 (`:8080`) & 원격 모바일 접속
```powershell
# PC 로컬 스튜디오 기동 (http://localhost:8080)
.\.venv\Scripts\python.exe -m plepa_gui.app

# 원격 모바일 터널 & 토큰 보안 URL 자동 발급 (/mobile?token=...)
.\.venv\Scripts\python.exe scripts/start_remote.py
```

### B. CLI 배치 생성 & 사전 무결성 검증
```powershell
# 등록 캐릭터 목록 및 로스터 사전 점검 (착의·누드·테마·매핑·문서 7단계 검증)
.\.venv\Scripts\python.exe batch_generator.py -r campus -l
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r campus

# 10대 대표 골든 샘플 생성 / 특정 캐릭터 누락분 채우기 / 소급 재검열
.\.venv\Scripts\python.exe batch_generator.py -r campus -c aya -p sample10 --censor
.\.venv\Scripts\python.exe batch_generator.py -r campus --all-chars -p all --censor
.\.venv\Scripts\python.exe batch_generator.py -r oto --all-chars -p all --censor-only

# 전체 계약·단위 회귀 테스트 (240+종) & Gemini 노트북 스냅샷 갱신
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/export_context.py
```

---

## 🏗️ 3. 핵심 아키텍처 요약

1. **7단계 프롬프트 Mutator 체인 ([`plepa_engine/pipeline/`](plepa_engine/pipeline/__init__.py) + [`prompt_pipeline.py`](plepa_engine/prompt_pipeline.py) 파사드)**:
   - `PoseTagPreparation` ➔ `PositiveAssembly` ➔ `NegativeBase` ➔ `DefectDefense` ➔ `TwoPersonMob` (`mob_tier 0~3` · `partner_pos` · 상안부 그림자 음영) ➔ `CompositionAntiDrift` ➔ `Sanitizer` (가중치 상한: 긍정 `1.15`, 부정 `1.25`).
2. **CLI · Engine · GUI 삼위일체 동기화 (`Trinity Sync`)**:
   - `GENERATION_OPTION_SPECS` ↔ `GenerationParams` ↔ `batch_generator.py` CLI ↔ `plepa_gui` Web UI 자동 렌더링 ↔ AST·파서 정밀 계약 테스트(`tests/test_cli_gui_sync.py`, `tests/test_contract_guards.py`).
3. **NiceGUI 8대 탭 + 수동 터치 덧칠 (`plepa_gui`)**:
   - `/characters` · `/poses` · `/backgrounds` · `/pose-sets` · `/generate` · `/gallery` · `/mobile` · `/settings` + 공용 캔버스 리터치(`retouch_editor.py`) + `GenitExporter` (`1024×1536` 일괄 패키징).
4. **Antigravity 에이전트 레일 (`.agents/`)**:
   - `PreToolUse` 물리 차단 Hook([`.agents/hooks.json`](.agents/hooks.json)) + 6종 전담 스킬([`.agents/skills/`](.agents/skills))로 에셋·레거시 보호 및 검증 게이트 자동 강제.

---

## 📁 4. 디렉토리 구조 (Active Layout)

```text
plepa/
├── GEMINI.md                     # 최상위 에이전트 행동 헌법 (규칙 1~11)
├── POSE_MAPPING.md               # ⭐ 전체 포즈·모브·배경·deprecated 단일 매핑 SSOT
├── batch_generator.py            # 통합 CLI 진입점 (삼위일체 동기화)
├── 사용법.txt                    # CLI 명령어 치트시트
├── data/
│   ├── sdxl_pose_database.json   # 코어 포즈 DB (175키, SSOT)
│   ├── pose_sets.json            # V3 프리셋 포즈 묶음 (sample10, campus_108 등)
│   ├── themes/                   # 공용 테마 의상 팩
│   └── legacy/                   # [격리] 구 FLUX DB (열람/수정 금지)
├── plepa_engine/                 # 엔진 전체 74모듈 <=350L / 전 함수 <=120L (Allowlist 0건)
│   ├── pipeline/                 # 7단계 Mutator 체인 서브패키지 (11모듈, <=285L)
│   ├── prompt_pipeline.py        # Mutator 체인 호환 파사드 (78L)
│   ├── workflow_templates.py     # SDXL 워크플로우 그래프 빌더 (workflow_nodes.py 분리)
│   ├── comfy_client.py           # ComfyUI REST/WS 클라이언트 (<=316L, comfy_transport.py 분리)
│   ├── censor/                   # Phase P2.5 하이브리드 검열 서브패키지 (19모듈, <=322L)
│   ├── qa_validator.py           # Auto-QC 품질/구도 자동 감지기 (qa_checks.py 규칙 분리)
│   ├── precheck.py               # 이미지 생산 전 7단계 무결성 검증 (precheck_rules.py 분리)
│   └── services/                 # CLI·GUI 공용 서비스 (generation/ 6모듈 · asset_helpers · pose_resolver/storage · health_checks_core/ops · GENERATION_OPTION_SPECS 29종)
├── plepa_gui/                    # NiceGUI 8대 탭 & REST API (/api/assets/*)
├── scripts/                      # context_exporter, start_remote, audit, validate_genit_work, novelchat_* 등
├── docs/                         # Active SSOT(젠잇·노벨챗 제작법, platforms/) & docs/archive/ (이력 보관소)
└── projects/{roster}/            # 12개 로스터별 캐릭터, 배경, events.json, 에셋(_origin 포함)
```
