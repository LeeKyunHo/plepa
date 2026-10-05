# 플에파(PLEPA) 마스터 인계 및 AI 개발자 가이드 (Handover Guide)

> **문서 목적**: 다른 컴퓨터 환경에서 리포지토리를 클론하거나 새로운 Antigravity AI 에이전트 인스턴스가 투입되었을 때, 이전 프로젝트(키로)와의 관계, 하드웨어 최적화 배경, 주요 아키텍처 결정 사항(ADR), 프롬프트 불변식을 즉시 학습하고 일관성 있게 작업을 이어가기 위한 단일 진실 공급원(SSOT) 문서.  
> **최초 작성일**: 2026-09-30  
> **연계 문서**: 
> - ⚙️ 파이프라인 인터페이스 및 CLI 규격 → [`플에파_기능명세.md`](플에파_기능명세.md)  
> - 🎨 캐릭터 & 포즈 프롬프트 제작 규칙 → [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md)  
> - 📋 전체 80종 포즈 카탈로그 및 2~6글자 명칭 가이드 → [`POSE_CATALOG.md`](POSE_CATALOG.md)  
> - 🤖 에이전트 행동 지침 → [`GEMINI.md`](GEMINI.md)  
> - 🚀 빠른 시작 및 설치 가이드 → [`README.md`](README.md)  

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

4. **SDXL 메인 엔진 기본화, NTR MIX XIII 도입 및 Kiro 호환성 100% 보장 (ADR 2026-10-05)**
   - **배경 및 사용자 의사결정**:
     - FLUX(12B)는 인체 해부학적 정확도가 뛰어나나, 실사/3D 편향으로 인해 2D 서브컬처 미소녀 맑은 셀 채색에 한계(2.5D 잔여)가 있고 장당 80~120초가 소요됨.
     - 메이치(Meichi) 체크포인트는 여성 캐릭터에 특화되어 오토코노코 캐릭터(남성기 및 중성적 체형) 묘사 시 여성기 왜곡 및 과탈색 문제가 발생함.
     - 이에 사용자가 지정한 **NTR MIX XIII (`ntrMIXIllustriousXL_xiii.safetensors`, 6.46GB)**를 공식 기본 체크포인트로 도입함. 오토코노코 신체미, 다양한 H-씬 체위 및 결합 묘사력을 극대화.
     - 제작자 권장 최적 설정 탑재: `Step 28`, `CFG 5.0` (과포화 방지), `dpm++ 2m / karras`, 품질 태그 `amazing quality` 보강.
     - **Kiro 명령어 100% 호환성**: 키로에서 쓰던 문법(`--char`, `--codes`, `--all-chars`)을 플에파 파서에 완벽 연동하고, 키로와 동일한 포맷의 `사용법.txt` 치트시트를 루트에 구축하여 UX 혼선을 원천 차단.

5. **기본 빈칸 채우기(Smart Skip) 및 교체(`--overwrite` / `-f`) 정책**
   - Kiro 프로젝트의 사용자 경험과 일치하도록, CLI 옵션 미지정 시 이미 존재하는 파일은 건너뛰고 누락분만 채움.
   - 기존 에셋을 다시 뽑아 교체하고자 할 때만 `--overwrite` (또는 `-f`) 스위치를 명시.

6. **에셋 파일명 명명 규칙: 하이브리드 표준 (`prefix_000_라벨.webp`) 및 원본 보존 스마트 복제**
   - **배경 및 의사결정 (2026-10-05)**: 파일명만으로 포즈와 표정을 즉시 직관적으로 식별하면서도, 윈도우 파일 탐색기에서 `000`~`159` 카테고리 순서대로 완벽하게 정렬되도록 **`f"{prefix}_{code}_{label}.webp"` (예: `han_000_평상.webp`, `han_033_턱올리기.webp`, `ren_140_정상위.webp`)를 시스템 공식 표준(`--naming hybrid`)으로 채택**.
   - **3대 명명 모드 지원 (`--naming`)**:
     - `hybrid` (기본값): `prefix_000_라벨.webp` (순서 정렬 + 한글 직관성 동시 확보)
     - `code`: `prefix_000.webp` (기존 Kiro 호환 3자리 번호형)
     - `label`: `prefix_라벨.webp` (순수 한글형)
   - **원본 보존 스마트 복제 (Smart Fallback Copy)**: 기존의 `prefix_000.webp` 원본 파일은 손상 없이 100% 보존하며, 하이브리드 파일이 없는 경우 GPU 시간 소모 없이 즉시 하이브리드 사본으로 원자적 복제 동기화 수행.

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

9. **Face Detailer (Impact Pack) 및 4x Upscaler 연동 규격**
   - **YOLO 얼굴 감지 모델**: `ComfyUI/models/ultralytics/bbox/face_yolov8m.pt` (Bingsu/adetailer repo) 필수 배치.
   - **FaceDetailer 노드 입력 완결성**: 최신 Impact Pack 사양에 맞추어 `positive`, `negative`, `wildcard`, `sam_*` 9개 필수 인자를 FLUX/SDXL 템플릿에 각각 완벽 바인딩.
   - **원자적 WebP 저장 (Atomic Save & Retry)**: 업스케일된 고해상도(3328x4864) 이미지 저장 시 윈도우 파일 락(사진 뷰어/탐색기 썸네일러)에 의한 `OSError [Errno 22]`를 차단하기 위해 임시 파일 기록 후 안전 교체 및 재시도 로직 적용.

10. **Illustrious-XL / Meichi 공식 베스트 프랙티스 프롬프트 규격**
   - **네거티브 다이어트**: 2D 선화와 입체감을 억압하는 독소 태그(`flat color`, `thick lineart`, `paint`, `3d`, `cgi`, `photorealistic`)를 전면 배제하고, 결함 방어(`lowres, worst quality, bad quality, bad anatomy, bad hands, deformed, blurry`) 및 컷 분할 방어(`(comic:1.2), (multiple views:1.2), (panel layout:1.2)`)로 최적화.
   - **가중치 상한선(1.15)**: 민감도가 높은 Illustrious 텍스트 인코더에 맞춰 캐릭터 외형/의상 가중치를 1.15 이하로 정규화하고 다중 괄호 중첩을 단일화.
   - **표준 퀄리티 태그**: `masterpiece, best quality, very aesthetic, absurdres, newest` 통일.
   - **전체 로스터(don/man 13명) 규격화**: `sdxl_positive`, `sdxl_negative`, `ref_weight: 0.5` 일괄 통일.

11. **포즈 DB 2~6글자 직관적 명칭 표준화 및 `description` 필드 영구 탑재**
   - CLI 콘솔 로그와 매핑 가이드의 가독성을 위해 기존의 긴 명칭(`마주안아엉덩이주무름` 등)과 괄호 표기(`(선교/대면)`)를 직관적인 2~4글자(`밀착포옹`, `정면절정` 등)로 표준화함.
   - AI와 창작자가 프롬프트를 수정하거나 신규 제작할 때 시각적 기준점으로 삼을 수 있도록, 포즈 DB 80종 전체에 카메라 앵글, 손동작, 표정 의도를 서술한 `description` 필드를 공식 규격으로 도입함.
   - 전체 목록 열람: [`POSE_CATALOG.md`](POSE_CATALOG.md) 참조.

12. **000~019 감정 씬 타이트 바스트 샷(`bust shot, upper body portrait`) 전면 표준화**
   - 스탠딩 기본 감정 20종은 전신이 아닌 얼굴과 가슴 윗선의 볼륨감, 세부 표정이 시원하게 차오르는 타이트 바스트 샷으로 프롬프트 구도를 전면 통일함.

13. **실전 프롬프트 불변식과 지침서 격리 (Separation of Guidelines)**
   - 검증된 실전 프롬프트 공식(#019 뽀뽀 상체 숙임 공식, #014 유혹 의상보호 가슴 모으기 공식, #017 보호본능 겁먹음, #018 달콤한 집착, 모브 캐릭터 `BREAK` 격리 및 블랙 팬츠 고정 등)은 본 아키텍처 문서가 아닌 [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md)로 일원화 위임하여 문서 간 역할 중복을 방지함.

14. **032~036번 파트너 결합 제어 및 상체 포커스 개편 (ADR 2026-10-04)**
   - **`is_offscreen_partner` 도입**: 032(벽치기), 033(정면포옹), 035(침대덮침)처럼 화면 밖 파트너의 손/팔만 나와야 하는 POV 씬에서, `partner` 키워드로 인해 모브 남성의 전신과 블랙 팬츠(`solid black pants`)가 화면 모서리에 강제 침범하던 현상 해결. `prompt_builder.py`에서 `partner off-screen` 감지 시 모브 전신 주입을 배제하고 네거티브에 `((male body, male torso, male lower body, male legs, pants, trousers, black pants:1.5))`를 주입하여 손/팔 앵커링만 유지.
   - **034번 다중 머리 버그 원천 차단**: 전방 가슴 매몰(`face buried in breasts`)과 후방 구도(`partner from behind`)의 모순 태그를 해소하고 `single partner, 1boy`로 단일화, 네거티브에 `((extra head, two heads, 2boys:1.4))` 주입.
   - **035번 1인칭 상체 버스트 샷**: 와이드 샷으로 여캐 아래 남성 하반신이 깔리는 결함을 1인칭 타이트 상체 샷(`pov, from above, tight bust shot`)으로 전환하여 표정 연출에 집중.
   - **036번 부끄러운 눈감기 시선 안정화**: 모브 얼굴 응시로 인한 동공 왜곡을 방지하기 위해 부끄러움에 눈을 감고 고개를 살포시 숙이는(`closed eyes, head tilted down, bashful embarrassed expression`) 연출로 변경.

15. **2D 애니메이션 성기 자동 검열 규격 (ADR 2026-10-05: 슬림 블랙 바)**
   - **배경**: 젠잇(Genit) 등 공개 캐릭터 챗봇 플랫폼 등록 시의 심의 안전성과 성기 노출 규정 준수를 위해, 고화질 원본을 손상시키지 않고 배포용 검열본을 자동 생성하는 후처리 파이프라인 탑재.
   - **감지 엔진**: 2D 일러스트 특화 오픈소스 객체 감지 모델인 `deepghs/anime_censor_detection` (`dghs-imgutils`)을 적용하여 0.02초 만에 `penis`의 정확한 BBox 좌표 `(x1, y1, x2, y2)`를 추출.
   - **표준 시각 스타일: 슬림 블랙 바 (`bar`)**:
     - 2D 상업 동인지 및 미연시 업계의 공식 표준인 **25도 사선 슬림 블랙 바** (`plepa_engine/censor.py`)를 적용.
     - 남성기 중심을 관통하는 얇은 검은색 띠(두께 12~32px, 둥근 캡 처리)를 렌더링하여 성적 매력과 인체 라인은 최대한 살리면서 핵심 노출만 완벽히 차단.
     - 추가 스타일로 **그림자 실루엣 (`shadow`)** 및 **격자 모자이크 (`mosaic`)** 선택 지원.
   - **무검열 원본 보존 불변식**: 원본 에셋(`*_140_정상위.webp`)은 무검열 상태로 영구 보존하며, 검열본은 `*_censored.webp` 형태로 분리 생성하여 소장용과 배포용을 완벽 격리.

16. **046번 솔로 H씬 분기(`is_solo_scene`) 및 053번 결합키스 신설 (ADR 2026-10-04)**
   - **`is_solo_scene` 도입**: 파이프라인이 `h_scenes` 전체를 2인 결합으로 간주하여 침대에 홀로 누워 다리를 벌리고 유혹하는 046번 개각유혹에 모브를 강제 소환하고 `solo` 태그를 삭제하던 버그 해결. `solo` 감지 시 2인 모브 주입을 차단하고 `solo` 태그 보존 및 남성 억제 네거티브 가동. `trembling slightly` 제거 및 당당하고 매혹적인 유혹 시선으로 정제.
   - **053번/153번 결합키스 신설**: 52(구강봉사), 54(딥스로트), 55(구강사후)로 구강 관련 포즈가 3개나 중복되던 문제를 해소하고, 파트너와 완전히 밀착 결합한 상태에서 목덜미를 끌어안고 나누는 딥키스 체위(`deep passionate kiss while connected, missionary embrace, tongue entangled, arms around partner's neck`)로 전면 개편.

17. **의상 머메이드 왜곡 방지, 침대 와인잔 차단 및 헤어 이염 방지 공식 (ADR 2026-10-04)**
   - **머메이드 실루엣 왜곡 차단**: `mermaid silhouette dress`가 CLIP의 인어 토큰에 반응하여 하반신을 물고기 꼬리처럼 융합시키고 공주안기/착석 시 괴기스러운 꼬리 모양으로 늘어지는 결함 확인. `high side slit dress, elegant draped maxi dress`로 전면 교체하고 네거티브에 `((mermaid:1.4)), ((mermaid tail:1.4)), ((fishtail:1.4))` 필수 규격화.
   - **침대 및 H씬 와인잔 소품 전역 차단**: 침대 위에서 뜬금없이 생성되던 와인잔/술병을 막기 위해 네거티브에 `(wine, wine glass, champagne, glass, bottle, cup, drink, beverage:1.4)` 전역 주입.
   - **헤어 색상 이염 방지**: 유색 의상/눈동자 색소 누출로 인한 머리카락 변색 방지를 위해 포지티브 3중 컬러 앵커링 + 네거티브 오염 예상 색상 강력 차단 + `ref_weight: 0.50~0.55` 조절 3중 방어 메커니즘 정립.

---

## 3. 플에파 시스템 아키텍처 및 불변식 (Invariants)

### 3.1 디렉토리 구조
```text
plepa/
├── .gitignore
├── GEMINI.md                    # 에이전트 행동 지침
├── AI_HANDOVER_GUIDE.md         # [본 문서] 시스템 아키텍처 및 의사결정 인계서 (SSOT)
├── 플에파_기능명세.md             # 파이프라인 인터페이스 및 CLI/ComfyUI 기술 규격서
├── 캐릭터_포즈_제작_규칙.md        # 캐릭터 JSON 및 80종 포즈 프롬프트 제작 완전 지침서
├── POSE_CATALOG.md              # 80종 포즈 카탈로그 및 2~4글자 명칭 뷰어
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

- `000~019` (**`emotions`**): 1인 단독 샷, 다양한 표정 및 감정 묘사, 배경과 상호작용. 타이트 바스트 샷(`bust shot, upper body portrait`) 표준화.
- `020~039` (**`poses`**): 착의 일상 및 액션/스킨십 포즈 20종 (카우보이 샷).
- `040~059` (**`h_scenes`**): 2인 상호작용 결합 및 농밀 씬 20종 (자연어 상황 서술).
- `140~159` (**`scenes_otokonoko`**): 오토코노코 씬 20종 (040~059번과 1:1 대칭 매핑).
- **표준 라벨 및 카탈로그**: 모든 포즈는 2~6글자 명칭과 `description` 필드를 탑재하며, 전체 목록은 [`POSE_CATALOG.md`](POSE_CATALOG.md)에서 열람 가능. 상세 프롬프트 조립 규칙은 [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md)를 준수.

---

## 5. 투입된 에이전트 체크리스트
새로운 에이전트 인스턴스는 사용자의 요청을 처리할 때 다음 사항을 반드시 확인하십시오:
1. 사용자의 컴퓨터 스펙(RTX 4060 Ti 8GB + 48GB RAM)을 인지하고 무거운 FP16 모델을 강제하지 말 것.
2. 이미 합의된 ComfyUI 로컬 API 백엔드와 Face Detailer 통합 방향을 준수할 것.
3. 포즈 수정 및 캐릭터 제작 시 [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md)와 [`POSE_CATALOG.md`](POSE_CATALOG.md)를 최우선 참조할 것.
4. 포즈 DB의 모든 명칭은 2~6글자(`label`), 상세 연출 설명(`description`) 필드를 필수 유지할 것.
5. Git 커밋 메시지는 민감 표현을 완전히 배제하고 기술적·사무적 한국어로 작성할 것.
