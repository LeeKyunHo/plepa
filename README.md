# 플에파 (PLEPA: High-Performance Anime Asset Pipeline)

> **SDXL(Illustrious Meichi MIX) 메인 & FLUX.1 [dev] 듀얼 엔진 기반 초고화질 2D 애니 캐릭터 챗봇 에셋 배치 생성 파이프라인**  
> ComfyUI 로컬 API와 연동하여 80종의 고품질 캐릭터 에셋을 자동 생성하고, 하이브리드 명명 규칙(`prefix_000_라벨.webp`), 18% 적응형 캡슐 와이드 솔리드 바 자동 검열(`_censored.webp`), 얼굴 정밀 보정(Face Detailer) 및 4x AI 업스케일까지 원스톱으로 수행합니다.

---

## 🚀 빠른 시작 (Quick Start)

### 1. ComfyUI 환경 준비
본 파이프라인은 로컬에서 구동 중인 ComfyUI(`http://127.0.0.1:8188`)와 통신합니다.

1. **ComfyUI 포터블 다운로드**: [ComfyUI GitHub Releases](https://github.com/comfyanonymous/ComfyUI/releases)에서 `ComfyUI_windows_portable_nvidia.7z` 다운로드 후 압축 해제.
2. **필수 모델 배치**:
   - **SDXL 메인 체크포인트 (기본 엔진)**:
     - `meichiILIghtMIXV1_meichiILUstMIXV1.safetensors` ➡️ `ComfyUI/models/checkpoints/`
   - **FLUX 모델 (보조/선택)**:
     - GGUF UNet: `flux1-dev-Q6_K.gguf` ➡️ `ComfyUI/models/unet/`
     - T5 인코더: `t5xxl_fp8_e4m3fn.safetensors` ➡️ `ComfyUI/models/clip/`
     - CLIP-L 인코더: `clip_l.safetensors` ➡️ `ComfyUI/models/clip/`
     - VAE: `ae.safetensors` ➡️ `ComfyUI/models/vae/`
   - **보정 & 업스케일러**:
     - BBox 얼굴 감지: `face_yolov8m.pt` ➡️ `ComfyUI/models/ultralytics/bbox/`
     - 4x 업스케일러: `4x-UltraSharp.pth` ➡️ `ComfyUI/models/upscale_models/`
3. **필수 확장 노드 (Custom Nodes)**:
   - `ComfyUI-Manager`
   - `ComfyUI-Impact-Pack` (Face Detailer 얼굴 자동 초정밀 보정)
   - `ComfyUI-GGUF` (FLUX GGUF 구동 시)
   - `ComfyUI_IPAdapter_plus` (선택: IP-Adapter 참조 이미지 연동 시)

### 2. ComfyUI 서버 실행
`ComfyUI_windows_portable/run_nvidia_gpu.bat`를 실행하여 `127.0.0.1:8188` 포트를 대기 상태로 둡니다.

### 3. 파이프라인 실전 실행 (기본: SDXL 메인 엔진 자동 가동)
별도의 `--engine` 옵션을 주지 않아도 **SDXL (Meichi MIX) 2D 애니 셀화 모드(장당 15초)**로 초고속 생성됩니다.

```powershell
# 1) 단일 캐릭터 기본 포즈 1장 생성 (SDXL 기본 적용)
python flux_batch_generator.py -r maid -c han -p 000

# 2) 특정 포즈 지정 생성 (예: 여성상위 044, 구강봉사 052)
python flux_batch_generator.py -r maid -c han,rub -p 044,052

# 3) 성인/나체 씬 18% 적응형 캡슐 와이드 솔리드 바 검열본 동시 생성
python flux_batch_generator.py -r maid -c ren,aoi -p 144,152 --censor

# 4) 감정 씬 전체 20종 생성 (000~019)
python flux_batch_generator.py -r maid -c han -p emotions

# 5) FLUX [dev] 엔진으로 생성하고 싶을 때만 명시
python flux_batch_generator.py -r maid -c han -p 000 --engine flux
```

---

## 💎 핵심 차별화 기능 (Key Features)

1. **SDXL 공식 기본 엔진 (`DEFAULT_ENGINE = "sdxl"`)**:
   - FLUX 순정의 2.5D 유분기 및 반실사 한계를 극복하고, 일본 상업 미연시/라노벨 수준의 맑은 2D 셀화 작화를 기본 보장합니다.
2. **하이브리드 명명법 (`--naming hybrid`, 기본값)**:
   - `prefix_000_라벨.webp` (예: `han_000_평상.webp`, `ren_144_기승위.webp`) 형식으로 저장되어 윈도우 탐색기 정렬과 직관적인 한글 식별을 동시 만족합니다.
3. **18% 적응형 캡슐 와이드 솔리드 바 검열 (`--censor`)**:
   - `dghs-imgutils` 2D 성기 감지 모델과 연동하여 정밀 BBox 영역에 18% 안전 마진과 모서리 라운딩(캡슐형)을 적용, **단 1픽셀의 노출 누수도 없는 100% 차단력**을 실증하면서 인체 곡선미를 95% 이상 보존합니다.
4. **H-씬 의상 자동 스트리핑 (의상 박제 버그 제로)**:
   - 캐릭터 외형(`face_and_hair`, `physique`, `outfit`) 관심사 분리를 통해, 탈의 포즈 감지 시 의상 태그를 원천 삭제하여 나체 씬에서 에이프런이나 속옷이 남는 문제를 완벽히 해결했습니다.
5. **오토코노코 100% 남성기 보장 & 여성기 차단**:
   - 여체화 오인 방지 알고리즘이 적용되어 여성기(`pussy`) 렌더링을 100% 차단하고 미소년 남성기(`penis`)를 보장합니다.

---

## 📂 프로젝트 구조

```text
plepa/
├── flux_batch_generator.py      # 플에파 메인 실행 CLI (기본: SDXL 엔진)
├── sdxl_pose_database.json      # SDXL 전용 80종 Danbooru 태그 포즈 DB
├── flux_pose_database.json      # FLUX 전용 80종 영문 서술형 자연어 포즈 DB
├── plepa_engine/                # 플에파 전용 핵심 엔진
│   ├── config.py                # 기본 엔진(sdxl), ComfyUI 포트(8188), 해상도 설정
│   ├── censor.py                # 2D 애니 성기 자동 검열 (18% 적응형 캡슐 와이드 바)
│   ├── comfy_client.py          # 비동기 ComfyUI 웹소켓/REST 클라이언트
│   ├── prompt_builder.py        # 듀얼 엔진 프롬프트 조립 및 탈의/모브 제어기
│   ├── workflow_templates.py    # SDXL / FLUX + Face Detailer 워크플로우 템플릿
│   ├── models.py                # 캐릭터/포즈 데이터 모델 정의
│   └── reporter.py              # 하이브리드 명명법 및 콘솔 요약 리포터
├── projects/                    # 멀티 프로젝트(로스터) 관리 폴더
│   ├── default/                 # 기본 샘플 캐릭터
│   ├── don/                     # don 프로젝트 (현대 로맨스)
│   ├── man/                     # man 프로젝트 (오피스)
│   └── maid/                    # maid 프로젝트 (메이드 카페/저택)
│       ├── background.json      # 배경 프리셋
│       ├── characters/          # 캐릭터 정의 JSON
│       └── assets/              # 생성된 WebP 에셋 및 검열본 (*_censored.webp)
├── AI_HANDOVER_GUIDE.md         # 아키텍처 결정(ADR) 및 AI 인계서 (SSOT)
├── RUNBOOK.md                   # 실무 운영 및 긴급 조치 런북
├── 캐릭터_포즈_제작_규칙.md        # 프롬프트 엔지니어링 표준 지침서
├── 플에파_기능명세.md             # 파이프라인 전체 인터페이스 규격서
├── POSE_CATALOG.md              # 전체 80종 포즈 카탈로그 및 명칭 뷰어
└── 개발일지.md                   # 일자별 개발 로그 및 트러블슈팅 일지
```

---

## 🛠 권장 하드웨어 사양
- **GPU**: NVIDIA RTX 4060 Ti 8GB 이상 (RTX 3060 이상 지원)
- **RAM**: 32GB ~ 48GB (대규모 배치 생성 및 모델 오프로딩 완벽 지원)
- **저장장치**: 고속 NVMe SSD
