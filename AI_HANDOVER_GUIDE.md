# 플에파(PLEPA) 마스터 인계 및 AI 개발자 가이드 (Handover Guide)

> **문서 목적**: 다른 컴퓨터 환경에서 리포지토리를 클론하거나 새로운 Antigravity AI 에이전트 인스턴스가 투입되었을 때, 이전 프로젝트(키로)와의 관계, 하드웨어 최적화 배경, 주요 아키텍처 결정 사항(ADR), 프롬프트 불변식을 즉시 학습하고 일관성 있게 작업을 이어가기 위한 단일 진실 공급원(SSOT) 문서.  
> **최초 작성일**: 2026-09-30  
> **프로젝트 공식 명칭**: 플럭스 에셋 파이프라인 (약칭: **플에파 / PLEPA**)  
> **연계 문서**: [`GEMINI.md`](GEMINI.md), [`README.md`](README.md), [`flux_pose_database.json`](flux_pose_database.json)

---

## 1. 프로젝트 탄생 배경 및 계보

- **기존 키로(Kiro) 프로젝트**: Stable Diffusion XL(Unholy Nova AI 체크포인트) 기반의 Danbooru 태그, BREAK 2청크 문법, ControlNet IP-Adapter를 사용하던 80종 캐릭터 챗봇 에셋 배치 생성기.
- **플에파(PLEPA)의 분리 신설**:
  - SD를 뛰어넘는 차세대 이미지 모델인 **FLUX.1 [dev]**의 압도적인 인체 묘사력, 사실적인 피부/조명 질감, 복합 상호작용 이해도를 활용하기 위해 신설.
  - 기존 키로 프로젝트의 코드베이스 무결성을 100% 보존하면서, 상위 레벨에서 완전히 독립된 GitHub 신규 리포지토리로 구축.
  - 키로의 핵심 자산인 **80종 에셋 체계(`000~019`, `020~039`, `040~059`, `140~159`, 3자리 제로패딩)**를 계승하여 파일명(`prefix_000.webp`)과 DB 키를 Kiro와 100% 동일하게 통일.
   - 불필요한 마크다운 가이드 파일(`*_genit_guide.md`)은 사용자의 요청에 따라 자동 생성을 영구 제거함.

---

## 2. 하드웨어 스펙 및 핵심 의사결정 기록 (ADR)

### 2.1 개발자(사용자) 하드웨어 환경
- **GPU**: NVIDIA GeForce RTX 4060 Ti **8GB VRAM**
- **RAM**: DDR4 **48GB (3200MHz, 4슬롯 풀뱅크)**
- **CPU**: Intel Core i5-13600KF (14코어 / 20스레드)
- **저장장치**: 고속 NVMe SSD

### 2.2 핵심 의사결정 사항 (Decisions & Rationale)
1. **런타임 백엔드: SD-WebUI-Forge 대신 ComfyUI 로컬 API 채택**
   - **이유**: 사용자가 "작업의 편리함보다 더 나은 최종 결과물(완성도)"을 강력히 희망함.
   - Forge는 단순 txt2img 생성에 그치지만, ComfyUI는 파이프라인 내부에 **자동 얼굴 정밀 보정(`Face Detailer`)**과 **AI 업스케일(`4x-UltraSharp`)**을 단일 비동기 워크플로우로 묶어 전신 샷에서도 압도적인 디테일을 보장할 수 있음.
   - 복잡한 노드 다이어그램은 Antigravity 에이전트가 코드로 자동화하므로 사용자는 CLI 명령어 한 줄(`python flux_batch_generator.py`)로 최상의 결과물을 얻음.

2. **모델 양자화 규격: GGUF Q6_K 포맷 채택**
   - **이유**: RTX 4060 Ti의 8GB VRAM 한계를 극복하면서도 순정 FP16 대비 화질 열화가 거의 없는 최상급 양자화 모델.
   - 사용자의 시스템 RAM이 **48GB**로 매우 방대하여 60장 연속 배치 생성 시에도 Q8_0 대비 생성 속도를 15~20% 단축(장당 약 79~88초)하면서도 뛰어난 인체 묘사력과 디테일을 보장.

3. **캐릭터 일관성(얼굴/외형) 전략**
   - 불필요한 LoRA 추가 학습을 강제하지 않고, 플럭스의 뛰어난 언어 이해도를 살려 **정밀한 영문 서술형 외형 묘사(Descriptive Appearance)**로 일관성을 확보.

4. **FLUX + SDXL (Unholy 9.0) 듀얼 엔진 전환 체계 구축**
   - **이유**: FLUX(12B)는 압도적 묘사력과 인체 해부학적 정확도를 제공하지만 8GB VRAM 환경에서 LoRA 적용 시 장당 약 199초가 소요됨.
   - 반면 SDXL 언홀리 9.0은 장당 **14초**의 경이로운 속도로 60장 배치를 14분 만에 끝내며 2D 애니 셀화 작화 재현력이 탁월함.
   - 따라서 CLI의 `--engine {flux, sdxl}` 매개변수 하나로 두 엔진을 자유롭게 스위칭할 수 있도록 듀얼 워크플로우 템플릿과 듀얼 포즈 DB(`flux_pose_database.json`, `sdxl_pose_database.json`)를 완벽히 격리·통합함.

5. **기본 빈칸 채우기(Smart Skip) 및 교체(`--overwrite` / `-f`) 정책**
   - Kiro 프로젝트의 사용자 경험과 일치하도록, CLI 옵션 미지정 시 이미 존재하는 파일은 건너뛰고 누락분만 채움.
   - 기존 에셋을 다시 뽑아 교체하고자 할 때만 `--overwrite` (또는 `-f`) 스위치를 명시.

6. **포즈 코드 및 파일명 3자리(`000`) 제로패딩 통일**
   - Kiro의 159번 오토코노코 씬까지 고려하여 모든 에셋 파일명을 `prefix_000.webp` 형식으로 규격화함.
   - CLI 입력(`-p 00,01`, `-p 0..5` 등)은 1~2자리 입력도 3자리(`000`, `001`)로 자동 매핑 지원.

7. **Kiro 핵심 기능 및 IP-Adapter 파이프라인 직결**
   - **IP-Adapter**: ComfyUI에 `ComfyUI_IPAdapter_plus` 노드 및 `CLIP-ViT-H-14` / `ip-adapter-plus_sdxl_vit-h` 모델을 배치하고 `IPAdapterUnifiedLoader` + `IPAdapterAdvanced` 노드를 연결.
   - CLI에서 `--ref_image`, `--ref_weight` (기본 0.50/JSON설정), `--no_ref` 지원 및 `references/{prefix}.webp` 자동 탐색 구현.
   - **편의 기능 5종 탑재**: `--list` (캐릭터 목록 표 출력), `--bg` (즉석 배경 문장 주입), `--custom_neg` (추가 네거티브 태그 결합), `--mock` (초고속 0.001초 가상 생성 시뮬레이션), `--profile` (다중 의상/헤어 스위칭).

8. **SDXL IP-Adapter 색상 과포화(Color Burn / Neon Tint) 방지 불변식**
   - **배경**: SDXL Plus 모델에서 기본값(V only, end_at 1.0, CFG 6.5, ref_weight 0.75+) 적용 시 청록색/녹색 채널 폭주 및 화이트 클리핑(38.5%)으로 선화와 피부톤이 타버리는 현상 발생.
   - **필수 최적화 파라미터**:
     - `embeds_scaling`: 반드시 **`'K+V'`** 적용 (절대 `'V only'` 사용 금지).
     - `end_at`: **`0.8`** (샘플링 후반 20%는 베이스 모델 디코더에 일임하여 선화와 하이라이트 보호).
     - `ref_weight`: **`0.50`** (캐릭터 기본값 및 CLI 기본값).
     - `DEFAULT_SDXL_CFG`: **`5.0`** (Unholy 9.0 체크포인트 최적 밸런스).
   - 적용 결과 화이트 클리핑이 38.5% → 12.2%로 정상화되고 피부톤이 자연스럽게 복원됨.

---

## 3. 플에파 시스템 아키텍처 및 불변식 (Invariants)

### 3.1 디렉토리 구조
```text
plepa/
├── .gitignore
├── GEMINI.md                    # 에이전트 행동 지침
├── AI_HANDOVER_GUIDE.md         # [본 문서] 시스템 아키텍처 및 의사결정 인계서
├── README.md                    # 설치 및 모델 가이드
├── flux_batch_generator.py      # 플에파 메인 실행 CLI
├── flux_pose_database.json      # 플럭스 전용 80종 영문 서술형 자연어 포즈 DB (3자리 000~159)
├── sdxl_pose_database.json      # SDXL 전용 80종 Danbooru 태그 포즈 DB (3자리 000~159)
├── plepa_engine/                # 플에파 전용 핵심 엔진
│   ├── __init__.py
│   ├── config.py                # ComfyUI API 호스트(8188), 해상도, 스텝 등 기본 설정
│   ├── comfy_client.py          # ComfyUI WebSocket + REST API 비동기 클라이언트
│   ├── prompt_builder.py        # 서술형 자연어/태그 프롬프트 조합기
│   ├── workflow_templates.py    # GGUF / SDXL + Face Detailer + Upscale 통합 워크플로우 JSON 생성기
│   ├── models.py                # 캐릭터/포즈 데이터 모델 정의
│   └── reporter.py              # 콘솔 진행도 리포터
└── projects/
    └── {roster}/ (예: don, default)
        ├── background.json      # 프로젝트 전용 공통 배경 프리셋
        ├── characters/          # 캐릭터 정의 JSON (don, ksn, shn 등)
        ├── references/          # 캐릭터 레퍼런스 이미지 (.webp)
        └── assets/              # 생성된 80종 WebP 에셋 (prefix_000.webp ~)
            └── {prefix}/
```

### 3.2 4대 시스템 불변식
1. **Danbooru 쉼표 태그 및 `BREAK` 문법 철폐 (FLUX 모드 한정)**:
   - 플럭스는 T5-XXL 기반 언어 인코더를 사용하므로 `masterpiece, 1girl, solo` 같은 나열식 태그를 쓰지 않고, 자연스러운 영문 문장으로 프롬프트를 구성합니다.
2. **Negative 프롬프트 비의존 (FLUX 모드 한정)**:
   - 플럭스는 네거티브 프롬프트가 거의 작동하지 않거나 배제되어 있으므로, 원하지 않는 요소는 긍정 프롬프트의 상황 서술을 통해 구도상 자연스럽게 차단합니다.
3. **철저한 관심사 분리 (Separation of Concerns)**:
   - 프롬프트 데이터는 `flux_pose_database.json` 및 `sdxl_pose_database.json`에, 캐릭터 프로필은 `projects/{roster}/characters/`에, 파이프라인 실행 로직은 `plepa_engine/`에 격리합니다.
4. **다중 PC 이식성(Portability) 보장**:
   - 하드코딩된 로컬 절대 경로는 금지하며, 환경 변수(`COMFYUI_HOST`)나 설정 파일(`config.py`)을 통해 어떤 PC에서 클론하더라도 즉시 실행될 수 있도록 상대 경로를 유지합니다.

---

## 4. 80종 에셋 체계 계승 규격 (3자리 000~159)

- `000~019` (**`emotions`**): 1인 단독 샷, 다양한 표정 및 감정 묘사, 배경과 상호작용.
- `020~039` (**`poses`**): 착의 일상 및 액션/스킨십 포즈 20종.
- `040~059` (**`h_scenes`**): 2인 상호작용 결합 및 농밀 씬 20종 (자연어 상황 서술).
- `140~159` (**`scenes_otokonoko`**): 오토코노코 씬 20종 (040~059번과 1:1 대칭 매핑).

---

## 5. 투입된 에이전트 체크리스트
새로운 에이전트 인스턴스는 사용자의 요청을 처리할 때 다음 사항을 반드시 확인하십시오:
1. 사용자의 컴퓨터 스펙(RTX 4060 Ti 8GB + 48GB RAM)을 인지하고 무거운 FP16 모델을 강제하지 말 것.
2. 이미 합의된 ComfyUI 로컬 API 백엔드와 Face Detailer 통합 방향을 준수할 것.
3. Git 커밋 메시지는 민감 표현을 완전히 배제하고 기술적·사무적 한국어로 작성할 것.
