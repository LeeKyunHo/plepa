# 플에파 (PLEPA: High-Performance Anime Asset Pipeline)

> **SDXL (`unholyDesireMixSinister_v90.safetensors`) 단일 파이프라인 기반 초고화질 2D 애니 캐릭터 챗봇 에셋 배치 생성 엔진**  
> ComfyUI 로컬 API(`127.0.0.1:8188`)와 연동하여 V2 표준 포즈 에셋(여성 100종 / 캠퍼스 106종 / 오토코노코 `+70` 대칭 매핑)을 고속 생성하고, **AI 자동 품질 검수(Auto-QC)**, **정밀 외곽선 실루엣 검열(`white_silhouette`)**, **얼굴 정밀 보정(Face Detailer)** 및 **4x AI 업스케일**까지 원스톱으로 수행합니다.

---

## 🚀 빠른 시작 (Quick Start)

### 1. ComfyUI 환경 준비
본 파이프라인은 로컬에서 구동 중인 ComfyUI(`http://127.0.0.1:8188`)와 통신합니다.

1. **필수 모델 배치**:
   - **SDXL 메인 체크포인트**:
     - `unholyDesireMixSinister_v90.safetensors` ➡️ `ComfyUI/models/checkpoints/`
   - **보정 & 업스케일러**:
     - BBox 얼굴 감지: `face_yolov8m.pt` ➡️ `ComfyUI/models/ultralytics/bbox/`
     - 4x 업스케일러: `4x-UltraSharp.pth` ➡️ `ComfyUI/models/upscale_models/`
2. **필수 확장 노드 (Custom Nodes)**:
   - `ComfyUI-Manager`
   - `ComfyUI-Impact-Pack` (Face Detailer 얼굴 자동 정밀 보정)

### 2. 파이프라인 실전 실행 (`batch_generator.py`)
별도의 엔진 옵션을 주지 않아도 **SDXL 단일 파이프라인(CFG 5.0, 28 Steps, `dpmpp_2m` + `karras`, 장당 약 11.8초)**으로 생성됩니다.

```powershell
# 1) 캠퍼스 로스터 전체 캐릭터 V2 106종 배치 생성 + 자동 실루엣 검열
python batch_generator.py -r campus -c all -p all --censor

# 2) 특정 캐릭터의 특정 포즈만 재생성 (기존 에셋 덮어쓰기)
python batch_generator.py -r campus -c aya -p 051,060,061 --overwrite --censor

# 3) 이미 생성된 에셋 폴더에 대해 정밀 실루엣 검열만 단독 수행 (_origin 원본 자동 보존)
python batch_generator.py -r campus -c aya -p all --censor-only

# 4) 이미지 생성 전 5단계 무결성 사전 점검 (Precheck)
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r campus

# 5) 플에파 골든 스테이트를 형제 프로젝트(kiro)로 동기화 전파
python scripts/sync_to_kiro.py
```

---

## 💎 핵심 아키텍처 및 차별화 기능 (Key Features)

1. **SDXL 단일 파이프라인 & 6대 Mutator 체인 (`plepa_engine/prompt_pipeline.py`)**:
   - `PoseTagPreparation` ➔ `PositiveAssembly` ➔ `NegativeBase` ➔ `DefectDefense` ➔ `TwoPersonMob` ➔ `Sanitizer` 6단계 미들웨어 체인으로 프롬프트 조립, 태그 충돌 자동 정제(`remove_conflicting_tags_from_negative`), 가중치 안전 클램핑(`clamp_sdxl_weights`)을 수행합니다.
2. **V2 포즈 아키텍처 (`000~200`) 및 오토코노코 `+70` 대칭 법칙**:
   - 공용 감정(`000~019`), 일상 포즈(`020~039`), 이벤트(`040~052`), 로맨스(`060~063`)와 함께, 여성 성인 씬(`080~127`, `130`)에 정확히 `+70`을 더하면 오토코노코 성인 씬(`150~197`, `200`)과 1:1 대칭 매핑됩니다.
3. **정밀 외곽선 실루엣 검열 (`white_silhouette` & `_origin` 원본 보존)**:
   - `dghs-imgutils` 성기 감지(`penis` + `pussy`) + 고환 하단 35% 확장 + MobileSAM 외곽선 추출 + 멀티스케일 2x 타일 스캔 + `POSE_SAFE_ANCHORS` 안전 앵커 폴백을 결합하여, 입술/혀 침범 없이 노출 부위만 정밀 백색 실루엣 처리하고 원본은 `{char}_origin/`에 무손실 보존합니다.
4. **AI 자동 품질 검수 (Auto-QC 4대 감지기, `plepa_engine/qa_validator.py`)**:
   - 생성 직후 ① 색감 과포화(Color Burn), ② 남성 모브 분신(Multi-Male Clone), ③ 여운/단독 씬 남성 난입(Solo Intrusion), ④ 기형적 장신(9~10등신)을 자동 판별하여 불량 시 시드를 바꿔 즉시 재생성합니다.

---

## 📂 프로젝트 디렉토리 구조

```text
plepa/
├── batch_generator.py           # 플에파 메인 실행 CLI (생성, Auto-QC, 검열 통합)
├── flux_batch_generator.py      # 하위 호환용 경량 CLI 래퍼 (batch_generator 위임)
├── run_gui.bat                  # NiceGUI 기반 웹 대시보드 실행기
├── GEMINI.md                    # 에이전트 최상위 프로젝트 헌법 및 규칙
├── data/                        # 프롬프트 데이터베이스 (SSOT)
│   ├── sdxl_pose_database.json  # SDXL V2 마스터 포즈 DB (000~200 + 레거시 호환)
│   ├── pose_sets.json           # V2 표준 포즈 세트 정의 (unified_100, campus_106 등)
│   ├── themes/                  # 의상/장르 테마 팩 JSON
│   └── legacy/                  # 아카이브된 구버전 데이터
├── plepa_engine/                # 플에파 핵심 백엔드 엔진
│   ├── config.py                # 전역 상수, 해상도(832x1216), 샘플러 설정
│   ├── prompt_pipeline.py       # SDXL 6대 Mutator 체인 및 태그 충돌 정제기
│   ├── prompt_builder.py        # 프롬프트 조립 퍼사드 및 가중치 클램핑
│   ├── censor.py                # 정밀 외곽선 실루엣 검열기 (MobileSAM + 멀티스케일 + 안전 앵커)
│   ├── qa_validator.py          # Auto-QC 4대 불량 감지기
│   ├── precheck.py              # 배치 생산 전 5단계 무결성 사전 점검기
│   ├── comfy_client.py          # 비동기 ComfyUI 웹소켓/REST 클라이언트
│   ├── workflow_templates.py    # SDXL 단일 CLIPTextEncode + Face Detailer 워크플로우
│   └── services/                # 캐릭터, 포즈, 배경, 생성 서비스 레이어
├── plepa_gui/                   # NiceGUI 기반 웹 프론트엔드
├── projects/                    # 로스터별 캐릭터 JSON, 오버라이드, 에셋 폴더
│   ├── campus/                  # 캠퍼스 로스터 (6명 x 106종 완비)
│   ├── spy/                     # 1960s 첩보 살롱 로스터 (10명)
│   └── ...                      # maid, school, cafe, bani, dark_generals 등
├── scripts/                     # 유틸리티 스크립트
│   ├── sync_to_kiro.py          # plepa ➔ kiro 골든 스테이트 자동 전파 브릿지
│   ├── plepa_upscaler.py        # 독립 실행형 4x AI 업스케일러
│   └── archive/                 # 구버전 일회성 마이그레이션 스크립트 보관소
├── docs/                        # 핵심 아키텍처 및 운영 문서
│   ├── AI_HANDOVER_GUIDE.md     # 아키텍처 결정 기록(ADR 1~48) 및 마스터 인계서
│   ├── DOCUMENTATION_GUIDE.md   # 문서 동기화 및 푸시 5단계 표준 프로토콜
│   ├── POSE_CATALOG.md          # V2 포즈 카탈로그 (000~200)
│   ├── POSE_MAPPING_V2.md       # V1 ↔ V2 포즈 번호 1:1 매핑 사전
│   ├── KIRO_SYNC_REPORT.md      # plepa ↔ kiro 양방향 시너지 전파 리포트
│   └── archive/                 # 구버전 완료 문서 보관소
└── tests/                       # pytest 자동화 테스트 스위트 (57종)
```
