# 플에파(PLEPA) 마스터 인계 및 AI 개발자 가이드 (Handover Guide)

> **문서 목적**: 다른 컴퓨터 환경에서 리포지토리를 클론하거나 새로운 Antigravity AI 에이전트 인스턴스가 투입되었을 때, 이전 프로젝트(키로)와의 관계, 하드웨어 최적화 배경, 주요 아키텍처 결정 사항(ADR), 프롬프트 불변식을 즉시 학습하고 일관성 있게 작업을 이어가기 위한 단일 진실 공급원(SSOT) 문서.  
> **최초 작성일**: 2026-09-30  
> **연계 문서**: 
> - ⚙️ 파이프라인 인터페이스 및 CLI 규격 → [`플에파_기능명세.md`](플에파_기능명세.md)  
> - 🎨 캐릭터 & 포즈 프롬프트 제작 규칙 → [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md)  
> - 📋 전체 80종 포즈 카탈로그 및 2~6글자 명칭 가이드 → [`POSE_CATALOG.md`](POSE_CATALOG.md)  
> - 📚 문서 작성 요령 및 푸시 프로토콜 → [`DOCUMENTATION_GUIDE.md`](DOCUMENTATION_GUIDE.md)  
> - 📓 일자별 개발 로그 및 트러블슈팅 → [`개발일지.md`](개발일지.md)  
> - 🤖 에이전트 행동 지침 → [`GEMINI.md`](GEMINI.md)  
> - 🚀 빠른 시작 및 설치 가이드 → [`README.md`](README.md)  

> [!IMPORTANT]
> **🚨 AI 에이전트 불변 규칙: FLUX 완전 배제 및 토큰 최적화 (Token Optimization)**
> - 플에파는 현재 **SDXL(NTR MIX XIII 등) 단일 파이프라인**으로 영구 일원화되었습니다 (ADR-53).
> - FLUX 관련 파일은 `data/legacy/` 및 `plepa_engine/legacy/`로 완전히 격리·아카이브되었습니다.
> - **포즈 추가/수정, 기능 수정 시 FLUX 관련 파일(`data/legacy/flux_pose_database.json`, `flux_*.py` 등)을 일체 열람하거나 수정·동기화하지 마십시오.**
> - 모든 포즈의 단일 진실 공급원(SSOT)은 오직 **[`data/sdxl_pose_database.json`](../data/sdxl_pose_database.json)** 하나뿐입니다.

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

9. **체크포인트 프로필 자동 적용 시스템 (ADR 2026-10-06)**
   - **배경**: SDXL 체크포인트마다 최적 해상도/샘플러/CFG가 상이함 (예: WAI-Illustrious는 1024×1344 + Euler a, Unholy는 832×1216 + DPM++ 2M 권장).
   - **의사결정**:
     - 파라미터(해상도, 스텝, CFG, 샘플러, 스케줄러)는 **자동 적용**
     - 품질 태그(Positive/Negative)는 **문서 참고용으로만 제공** (프롬프트 자동 주입 안함)
   - **구현**: `checkpoint_profiles.json`에 5개 주요 체크포인트 프로필 등록 + 퍼지 매칭 로직
   - **우선순위**: 사용자 명시 인자 > 프로필 값 > Config 설정 > 하드코드 기본값
   - **참고 문서**: `docs/체크포인트프로필가이드.md`

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

18. **NiceGUI 기반 로컬 웹 스튜디오 구축 및 서비스 레이어 단일화 (ADR 2026-10-06)**
   - **배경**: CLI(`flux_batch_generator.py`)의 뛰어난 자동화 성능을 유지하면서, 캐릭터 외형 수정·복제, 80종 포즈 편집, 배경 프리셋 관리, 배치 생성 및 체형별 비교 갤러리를 화면에서 직관적으로 다룰 수 있는 GUI 환경 필요.
   - **아키텍처 원칙 (Single Source of Truth)**:
     - GUI가 독자적인 프롬프트 조립이나 파일 입출력을 수행하지 않고, CLI와 GUI가 완전히 동일한 `plepa_engine/services/`(`character_service`, `pose_service`, `background_service`, `asset_service`, `generation_service`)를 공유.
     - `flux_batch_generator.py`는 서비스 레이어를 호출하는 얇은 래퍼로 축소되어 기존 CLI 인수 및 기능 하위 호환성 100% 보장.
   - **안전한 데이터 보존 (Atomic Save & 회전 백업)**:
     - 모든 JSON 저장은 임시 파일 기록 후 `os.replace`로 교체하여 프로세스 강제 종료 시에도 0바이트 손상 원천 방지.
     - 저장 직전 `.plepa_backup/`에 타임스탬프 스냅샷 백업(최근 20개 자동 순환 보관).
     - 삭제는 영구 삭제 대신 `_trash/` 이동으로 안전성 확보.
   - **포즈 명시적 메타데이터 도입**:
     - 기존 키워드 추측 휴리스틱(057번 샤워벽치기에서 파트너 남성이 누락되던 버그의 근본 원인)을 종식하기 위해 `flags`(`nude`, `scene_type`, `wet`, `disabled`) 도입.
     - 라벨 변경 시 연관된 에셋 파일명 변경 계획(Dry-run) 및 동시 리네임 트랜잭션 제공.
   - **프롬프트 4,800개 회귀 방지 스냅샷 구축**:
     - 리팩터링 전후 전체 로스터 x 캐릭터 x 80개 포즈 x SDXL/FLUX 조합의 프롬프트 전수 일치를 검증하는 `tests/snapshot_prompts.py` 체계 상시 가동.
   - **실행 방법**:
     - 더블클릭: `run_gui.bat`
     - CLI 실행: `.\.venv\Scripts\python.exe plepa_gui/app.py` ➔ 브라우저에서 `http://127.0.0.1:8080` 접속.

---

19. **SDXL 기본 샘플러 DPM++ 2M Karras 영구 확정 및 SDE 망점 결함 규명 (ADR 2026-10-07)**
    - **배경 및 원인 규명**:
      - SDXL 생성물에서 발견되던 미세한 흰 반점, 망점, 자글거리는 도트 노이즈 결함의 원인을 규명하기 위해 SDE(`dpmpp_2m_sde`)와 2M(`dpmpp_2m`)을 동일 조건(유키노 동탄복 `ykn_don` 024~059 포즈 36장)으로 직접 A/B 비교 검증.
      - SDE는 매 스텝마다 브라운 운동 노이즈를 재주입하는 확률적(Stochastic) 특성으로 인해 2D 셀 채색 표면에 미세한 노이즈 잔상을 남기고 생성 속도도 장당 약 69.8초로 지연됨.
      - 반면 DPM++ 2M은 결정론적(Deterministic) 감쇄를 수행하여 잡티 없는 매끄러운 2D 셀 채색을 완벽히 구현하며, 장당 약 34.3초로 속도가 2배 이상 빠름.
      - 한편, 034번 머리통 분리 및 028/036번 시커먼 타버림 결함은 샘플러 문제가 아니라 포즈 DB의 프롬프트 중복(`holding head`) 및 `featureless silhouette` 태그 결함이었음을 확인하고 포즈 DB(`sdxl_pose_database.json`)를 교정하여 완전 해결함.
    - **최종 의사결정 및 불변식**:
      - **`DPM++ 2M Karras`**를 플에파 SDXL 파이프라인의 공식 기본 샘플러로 영구 확정.
      - 기본 파라미터 불변식: `DEFAULT_SDXL_SAMPLER = "dpmpp_2m"`, `DEFAULT_SDXL_SCHEDULER = "karras"`, `DEFAULT_SDXL_STEPS = 30`, `DEFAULT_SDXL_CFG = 5.0`.
      - 엔진 설정(`config.py`, `config_service.py`), 상태 파일(`.plepa_state/config.json`), GUI 설정 및 생성 화면 뱃지 전반에 기본값 동기화 완료.

20. **명문가 네쌍둥이 자매 4인 4색 캐릭터 규격 및 듀얼 루트 기획 확정 (ADR 2026-10-07)**
    - **배경**: 원작 '유키노시타 유키노'의 독보적인 황금 비율과 흑발, 맑은 눈매를 100% 동일하게 공유하면서도, 외모·체형·성격에서 즉시 식별 가능한 4인 4색 네쌍둥이 자매 연애 시뮬레이션 기획 확정.
    - **4인 4색 최종 스펙**:
      - **1녀 설유아 (`ykn_1st`)**: 실크 리본 사이드 테일 | 풍만한 가슴 볼륨 | 메가데레 (무한한 애정) | 크림 앙고라 가디건 & 핑크 리본 블라우스
      - **2녀 설세린 (`ykn_2nd`)**: 미디엄 레이어드 허쉬컷 (도회적 쇄골 단발) | 기본 가슴 & 매력적인 힙라인 (뒤태 특화) | 쿨뷰티 | 화이트 케이블 가디건 & 블루 리본 블라우스
      - **3녀 설시아 (`ykn_3rd`)**: 긴 생머리 양옆 붉은 리본 | 균형 잡힌 요염한 슬렌더 | 츤데레 (새빨개지는 자존심) | 베이지 트렌치 코트 & 체크 플리츠 스커트
      - **4녀 설하율 (`ykn_4th`)**: 어깨길이 세미롱 (귀 넘김) + 크리스탈 드롭 귀걸이 | 디폴트 가녀린 슬렌더 | 조용 과묵 쿠데레 & 뛰어난 테크닉 반전 | 딥 네이비 스퀘어넥 롱 드레스
    - **듀얼 루트 시나리오 체계**:
      - **루트 A [소꿉친구 순애]**: 오랜 세월 넷과 함께 자라온 주인공으로서, 닫힌 규수들의 마음을 차례로 열어가는 따뜻한 사랑 이야기.
      - **루트 B [전학생 라이벌 쟁탈전]**: 기존 소꿉친구 남성(가짜 주인공 NPC)과의 일상에 전학생인 플레이어가 개입하여, 네 자매의 마음을 하나씩 매료시키고 차지해 오는 스릴 넘치는 관계 전복 서사.

21. **쿠데레/무표정 캐릭터 표정 딜레마 해소 [눈매 앵커링 + 평문 기질 1.0] 및 의상 평문화 불변식 (ADR 2026-10-07)**
    - **문제점 규명**:
      - 캐릭터 JSON에 강한 무표정 태그(`:1.25`)를 상시 부여하면 포즈 DB의 감정 연출(미소, 활짝웃음, 키스, H씬 절정)과 충돌하여 표정이 로봇처럼 굳어버리거나 기괴한 표정이 발생함.
      - 반대로 무표정 태그를 완전히 제거하면 2D 애니 모델 특유의 기본 방긋 미소녀 편향으로 인해 과묵하고 서늘한 카리스마가 사라지는 양날의 검 발생.
    - **해결 공식 및 불변식**:
      - **눈매 앵커링(Eye Anchoring)**: 입과 볼을 얼리지 않고 눈매와 시선(`(sharp icy blue eyes:1.15), (half-closed eyes:1.05)`)으로 서늘한 눈빛을 앵커링.
      - **성격 기질 평문 1.0 주입**: 가중치 없는 순수 평문(`kuudere, quiet demeanor`, `megadere`, `cool beauty` 등)을 1.0으로 주입하여 기본 분위기만 형성하고 포즈 DB의 지시가 우선권을 가져가도록 보장.
      - **의상 본체 평문화 (1.0)**: 의상 본체에 부여되어 있던 가중치(`:1.15~1.2`)를 순수 1.0 평문으로 전환하여, 탈의(Nude)/H-씬에서 `strip_sdxl_outfit_tags()`가 의상을 100% 잔류 없이 제거하도록 보장.
    - **실측 검증**: 4자매 전원의 `000(평상)` 및 `001(미소)` 8장 배치 생성 결과, 평상시 고유 인상 유지 및 미소 표정의 자연스러운 개화(갭 모에)를 100% 확인.

22. **모바일 클라우드 뷰어 마크다운 이미지 웹 표준 URL(`/C:/...`) 규격화 및 갤러리 퀵 프리셋 탑재 (ADR 2026-10-07)**
    - **문제점 규명**: 모바일 Antigravity 클라우드 웹 뷰어에서 윈도우 역슬래시(`\`) 및 선행 슬래시 누락 시 "Preview unavailable"이 발생하는 결함 확인.
    - **해결 조치**: 마크다운 아티팩트 내 이미지 경로를 웹 표준인 `/C:/Users/...` (선행 슬래시 + 포워드 슬래시)로 통일하고, `plepa_gui` 매트릭스 뷰에 `[🌸 네쌍둥이 4인 (000, 001)]` 원클릭 프리셋 버튼 신설.

23. **신규 독립 로스터 `projects/ykn/` 분리 및 캐릭터 접두사 한글명 매핑 (ADR 2026-10-07)**
    - **배경**: 기존 `don` 로스터에 혼재되어 있던 네쌍둥이 자매 캐릭터를 전용 프로젝트 폴더인 `projects/ykn/`으로 완전 분리 독립.
    - **캐릭터 ID 표준화**:
      - 1녀 설유아: `ykn_1st` ➔ **`yua`**
      - 2녀 설세린: `ykn_2nd` ➔ **`serin`**
      - 3녀 설시아: `ykn_3rd` ➔ **`sia`**
      - 4녀 설하율: `ykn_4th` ➔ **`hayul`**
    - **1번 미소 에셋 기반 레퍼런스 확립**: 4자매 전원의 #001 미소 에셋을 `references/{prefix}.webp`로 확정 배치하여 일관된 2D 애니 톤 및 의상 가이드라인 구축.

24. **SDXL Unholy 가중치 클램핑 안전선(긍정 1.15 / 부정 1.25) 및 다중 동의어 앵커링 기법 확립 (ADR 2026-10-07)**
    - **문제점 규명**:
      - SDXL Unholy Desire Mix v9.0 체크포인트는 가중치가 1.20을 초과하면 라텐트 클리핑으로 인해 피부가 황토색으로 타버리거나(overburn), 네온 컬러 왜곡이 발생함.
      - 반대로 가중치를 1.15로 일률 클램핑하면 원작 유키노의 압도적인 롱헤어 편향(99% 허리 기장)과 양쪽 리본 구조로 인해 사이드 테일이 양갈래로 변형되거나 단발/세미롱이 길어지는 현상 발생.
    - **해결 공식 및 불변식**:
      - **가중치 안전 클램핑선**: `clamp_sdxl_weights`에서 긍정 프롬프트는 과포화 방지를 위해 `max_weight=1.15`, 부정 프롬프트는 왜곡 없는 형태 억제를 위해 `max_weight=1.25`로 분리 제한.
      - **다중 동의어 앵커링 기법**: 높은 단일 가중치 대신 동의어와 형태 묘사를 4~5개 분할 나열하여 색상 왜곡 없이 100% 형태 고정:
        - 설유아 (단일 사이드 테일): `((side ponytail:1.15)), ((single ponytail:1.15)), ((hair tied on one side:1.15)), ((asymmetrical hairstyle:1.15)), ((hair draped over one shoulder:1.15)), single hair ribbon` (양갈래 유발 `sidelocks` 배제, 네거티브 `twintails, ribbons on both sides` 차단).
        - 설세린 (정통 히메컷 Hime Cut): `((hime cut:1.2)), ((blunt sidelocks:1.2)), ((jaw-length blunt sidelocks:1.15)), straight bangs` (네거티브 `((red ribbon:1.5)), ((hair ribbon:1.45)), ((ribbon:1.4))` 차단).
        - 설시아 (허리 긴 생머리): `((waist-length straight hair:1.15)), ((long straight hair:1.15)), ((small red hair ribbons on sides:1.15))` (네거티브 `short hair, bob cut, shoulder-length hair` 차단).
        - 설하율 (어깨 세미롱 & 언더붑 크롭티 & 청바지): `((shoulder-length hair:1.15)), ((medium hair:1.15)), ((hair ends at shoulders:1.15)), hair tucked behind ear` (네거티브 `long hair, hair past shoulders, (earrings:1.25), (dress:1.25)` 차단).

25. **웹 GUI 무결점 초기화(Zero-Selection) 원칙 및 매트릭스 뷰 엄격 로스터 격리 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**: 인터페이스 진입 시 기존/타 캐릭터가 임의로 선택되어 있거나 테이블에 타 로스터 캐릭터가 "미생성"으로 끼어드는 UX 혼선 원천 차단.
    - **해결 조치**:
      - **Zero-Selection 원칙**: 갤러리(`/gallery`) 및 배치 생성(`/generate`) 진입 시 및 로스터 전환 시, 캐릭터 선택 상태를 완전 빈 상태(`selected_chars = []`, `single_char = ""`)로 초기화. 사용자가 직접 원하는 대상을 능동적으로 선택하도록 보장.
      - **매트릭스 뷰 엄격 격리**: `prefixes = [p for p in state["selected_chars"] if p in char_counts]` 필터링을 통해 현재 로스터에 속하지 않는 캐릭터의 화면 출력을 원천 차단.
      - **라이트박스 풀사이즈 확대**: 모바일 및 PC 갤러리 팝업 다이얼로그를 화면 폭 92%, 높이 82vh의 쾌적한 풀사이즈로 확대.

26. **갤러리 전체 포즈 기본화, WebP 새 탭 다운로드 방지 뷰어 및 윈도우 탐색기 오픈 안정화 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**:
      1. 갤러리 진입 시 포즈 기본 범위가 36종/80종으로 제한되어 있어 전체 포즈(000~159)를 한눈에 볼 수 없었음.
      2. 라이트박스에서 "새 탭에서 원본 보기" 클릭 시 브라우저가 정적 WebP MIME 타입을 인식하지 못해 새 탭 화면 대신 파일 다운로드가 강제 실행됨.
      3. 상단 "에셋 폴더 열기" 및 라이트박스 "PC 폴더 열기" 클릭 시 파일 탐색기 창이 뜨지 않던 현상 발생.
      4. 퀵 버튼 클릭 시 제어 바를 재생성하면서 부모 슬롯이 삭제되어 `The parent element this slot belongs to has been deleted.` 런타임 에러로 이벤트가 중단되던 현상 발생.
    - **해결 조치**:
      - **전체 포즈 기본화**: `state["pose_set"] = "all"`, `state["selected_codes"] = sorted(all_poses.keys())` 및 포즈 범위 드롭다운 기본값 `"all": "전체 포즈 (160종)"` 설정. 퀵 버튼 라벨을 `[🌸 네쌍둥이 4인 (전체 포즈)]`로 동기화.
      - **새 탭 고화질 웹 뷰어 신설**: `mimetypes.add_type("image/webp", ".webp")` 등록 및 `@ui.page("/view_image")` 무손실 반응형 뷰어 라우트 구축. 라이트박스 버튼에 `href="/view_image?..." target="_blank"` 네이티브 링크를 부여하여 다운로드 튕김 0% 보장 및 원클릭 줌 인/아웃 토글 지원.
      - **탐색기 프로세스 호출 안정화**: `open_in_explorer`를 `subprocess.Popen(["explorer.exe", ...])` 리스트 인자 호출 방식으로 교체하여 cmd 파싱 오류 제거. 파일 대상일 경우 `explorer.exe /select,...`로 해당 이미지 자동 하이라이트.
      - **NiceGUI 슬롯 삭제 에러 방지**: `update_control_bars()` 호출 전에 `ui.notify`를 먼저 띄우고 `try...except` 보호를 적용하여 안전한 UI 라이프사이클 확립.

27. **설하율 의상 언더붑(Underboob) 크롭 흰티 리뉴얼 및 쨍함(과포화/네온) 색감 교정 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**:
      1. 귀걸이를 없애고, 크롭티셔츠를 더 짧게 만들어 언더붑(가슴 밑선 노출) 스타일로 변경 요청.
      2. 세린 등 다른 자매들과 비교했을 때 하율이만 지나치게 쨍하고 차가운 푸른빛/시안빛이 도는 톤 불균형 발생.
    - **원인 규명**:
      - 이전 레퍼런스(`references/hayul.webp`)가 푸른 도시 야경 조명 아래에서 생성되어 IP-Adapter가 시안빛 색조를 복제함.
      - `crystal drop earrings` 태그가 형광 청록 보석을 생성하며 주변으로 네온빛을 산란시킴.
      - 네거티브에 시안/네온/과포화 차단 태그 부재.
    - **해결 조치**:
      - `hayul.json`에서 귀걸이 완전 삭제 및 네거티브 `(earrings:1.25)` 차단.
      - 언더붑 크롭티 프롬프트 공식화: `(underboob:1.15), (exposed underboob:1.15), (plain white cropped t-shirt:1.15), short sleeves, underboob cut, exposed midriff, navel, blue denim jeans`.
      - 색감 안정화: 포지티브에 `soft natural lighting, warm indoor lighting`, 네거티브에 `(oversaturated:1.25), (neon:1.25), (blue tint:1.25), (cyan hair:1.2), (teal hair:1.2), (color burn:1.25)` 주입.
      - 세린이와 동일한 따뜻하고 부드러운 자연광 톤의 `#001 미소` 컷을 새 공식 레퍼런스로 확정 갱신.

28. **설세린 정통 히메컷(Hime Cut) 리뉴얼 및 붉은 리본 완전 박멸 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**:
      1. 머리 뒤쪽에서 원치 않는 붉은 리본 끈이 계속 튀어나오는 문제 발생.
      2. 슬릭컷 적용 시 원작 유키노의 기본 롱헤어와 유사해 보여 4자매 간 시각적 변별력이 약화됨.
    - **해결 조치**:
      - 원작 유키노 토큰의 고유 내장 리본을 차단하기 위해 네거티브에 `((red ribbon:1.5)), ((hair ribbon:1.45)), ((ribbon:1.4))` 초강력 주입 및 포지티브에 `(no ribbons:1.25), (no hair accessories:1.25), bare hair` 명시 선언으로 리본 0% 완전 박멸.
      - 일자 앞머리와 뺨/턱선에 칼단발 직각 단차를 주는 **정통 히메컷(`(hime cut:1.2), (blunt sidelocks:1.2), (jaw-length blunt sidelocks:1.15)`)**을 공식 도입하여 2녀 세린만의 독보적인 쿨뷰티 기품 확립.
      - 신규 히메컷 `#001 미소` 컷을 `projects/ykn/references/serin.webp` 공식 레퍼런스로 신설 저장 및 11종 전수 덮어쓰기 완료.

29. **설시아 정통 하이 포니테일(High Ponytail) 리뉴얼 및 대학교 사회봉사 동아리 [늘봄] 듀얼 시나리오 확립 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**:
      1. 설시아(3녀)의 헤어스타일을 포니테일로 변경 요청. (1녀 유아의 사이드 포니테일과 혼선 없도록 차별화 필요).
      2. 고교/학원물 배경에서 벗어나 **대학교 사회봉사 동아리** 무대로 세계관 전면 전환.
      3. 주인공 설정: 유치원부터 대학까지 함께 올라온 **동갑내기 소꿉친구 (순애 루트)** 및 이번 학기 새로 편입해 동아리에 들어온 **한 살 연상 편입생 선배 (NTL/쟁탈전 루트)** 듀얼 체계 구축.
    - **해결 조치**:
      - **하이 포니테일 공식화**: `sia.json`에 `(high ponytail:1.2)`, `(single high ponytail:1.15)`, `ponytail behind head` 명시 및 1녀 유아와의 혼동을 막기 위해 `(side ponytail:1.3)`, `(hair draped over shoulder:1.25)` 네거티브 철저 주입.
      - **에셋 전수 교체**: 하이 포니테일 `#001 미소` 컷을 `projects/ykn/references/sia.webp` 공식 레퍼런스로 교체하고 000~010 감정 에셋 11종 전수 덮어쓰기 생성 완료.
      - **세계관 설정집 문서화**: [`projects/ykn/01_대학교_사회봉사동아리_세계관_및_시나리오.md`](projects/ykn/01_대학교_사회봉사동아리_세계관_및_시나리오.md)를 독립 신설하여 동아리 [늘봄]의 4자매 학과/직책, 동방 밀실 및 엠티/봉사활동 스킨십 기믹, 소꿉친구 vs 편입생 선배 듀얼 시나리오 완비.

30. **설유아 핑크 틴트(Pink Cast) 왜곡 교정 및 크림 카디건/화이트 셔츠 리뉴얼 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**:
      1. 유아의 일러스트들이 전반적으로 과도하게 핑크빛으로 물들어 있는 원인 문의 및 레퍼런스 삭제 후 전면 재작업 요청.
    - **원인 규명**:
      - 기존 레퍼런스가 넓은 면적의 '올 핑크 케이블 니트'를 착용하여 광원 반사 및 컬러 블리딩(Color Bleeding) 현상 발생.
      - IP-Adapter 참조 가중치가 다른 자매들(`0.15`)보다 높은 `0.20`으로 설정되어 캔버스 전반에 핑크 색조를 강제 복제.
      - 프롬프트의 `pastel blouse` 단어가 핑크 편향을 가속화하고 네거티브 핑크 차단 장치 부재.
    - **해결 조치**:
      - 기존 핑크 레퍼런스 삭제 후, `yua.json`의 의상을 **`cream knit cardigan, crisp white blouse, collared shirt`**로 정돈.
      - IP-Adapter 가중치를 `0.20` ➔ `0.15`로 낮춰 다른 자매들과 일치.
      - 네거티브에 `(pink tint:1.25), (pink clothes:1.25), (pink sweater:1.25), (magenta cast:1.25), (oversaturated:1.2)` 주입.
      - 레퍼런스 없이 순수 프롬프트로 생성한 청순하고 따뜻한 `#001 미소` 컷을 새 공식 레퍼런스로 확정하고 000~010 감정 에셋 11종 전수 일괄 덮어쓰기 완료.

31. **설하율 왕가슴 & 조여진 블라우스 리뉴얼 및 4자매 영문 파일명(Prefix) 3글자 통일 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**:
      1. 파일명 및 시스템 식별자로 사용되는 영문 접두사(Prefix)를 전원 3글자로 통일 요청 (`serin` ➔ `ser`, `hayul` ➔ `hay`).
      2. 설하율(4녀)의 체형을 슬렌더에서 **풍만한 대흉(왕가슴)**으로 변경하고, 단추가 팽팽하게 당겨진 **타이트 조여진 화이트 블라우스** 느낌으로 연출 요청.
    - **해결 조치**:
      - **Prefix 3글자 일괄 규격화**:
        - 1녀: `yua` (3글자 유지)
        - 2녀: `serin` ➔ `ser` (`ser.json`, `ser.webp`, `assets/ser/ser_*.webp`)
        - 3녀: `sia` (3글자 유지)
        - 4녀: `hayul` ➔ `hay` (`hay.json`, `hay.webp`, `assets/hay/hay_*.webp`)
      - **하율 체형 및 의상 개편**:
        - `hay.json`에 `(voluptuous:1.2), (huge breasts:1.25), (massive bust:1.2)`, `(tight white collared blouse:1.2), (strained shirt:1.2), (buttons straining:1.2)` 주입.
        - 언더붑/크롭티/청바지/작은가슴 네거티브 차단.
        - 신규 레퍼런스 `hay.webp` 안착 및 000~010 감정 에셋 11종 전수 재생성 완료.

32. **80종 포즈 명칭(`label`) AI 대화 매칭 최적화 및 슬래시/공백 제거 단일 복합명사화 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**:
      1. AI 챗봇이 대화/지문 문맥에서 해당 포즈 이미지를 정확히 찾아 호출할 수 있도록, 지나치게 서술적이거나 긴 명칭을 13글자 이하로 최적화 요청.
      2. 슬래시(`/`) 기호나 띄어쓰기가 프롬프트/정규식에서 OR 조건으로 오인되거나 인식이 어긋나는 위험 방지 요구.
    - **해결 조치**:
      - 슬래시 및 불필요한 공백을 완전히 배제하고, 서브컬처/비주얼 노벨의 대표적 표준 키워드(`평상`, `수줍은홍조`, `토라짐`, `도도한팔짱`, `벽치기`, `공주님안기`, `딥키스`, `파이즈리`, `펠라치오`, `정상위` 등) **2~6글자 단일 복합명사**로 전수 확정.
      - `sdxl_pose_database.json`, `flux_pose_database.json` 80종 전수 라벨 일괄 갱신.
      - [`POSE_CATALOG.md`](POSE_CATALOG.md), [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md) 동기화 완료.

33. **캐릭터 스키마(`CharacterSchema`) `name` 필수 누락 Pydantic 유효성 에러 해결 및 자동 폴백 방어선 구축 (ADR 2026-10-07)**
    - **배경 및 원인 규명**:
      - `projects/man/characters/` 내 5명(`cyr`, `hsh`, `kma`, `sja`, `yca`)의 JSON 파일에 `name` 필드가 누락되어 있어, GUI 서버 및 백엔드 실행 시 Pydantic `Field required [type=missing, name]` 유효성 에러와 함께 캐릭터 로드 실패 경고 발생.
    - **해결 조치**:
      - `projects/man/characters/` 5개 파일에 정규 한국어/영문 이름(`채유림`, `한수현`, `강민아`, `서지안`, `윤채아`) 부여 및 동기화.
      - `plepa_engine/services/schemas.py`의 `CharacterSchema`에서 `name: str = Field(default="")` 및 `normalize_character_fields` 검증기에서 `name` 누락 시 `prefix`로 자동 폴백하는 2중 안전장치 추가. 향후 어떤 레거시/미완성 캐릭터 JSON이 유입되어도 서버 크래시 0% 보장.

35. **oes 기반 캐릭터 얼굴 통일 규격 및 ykn 프로젝트 캐릭터 전면 재구성 (ADR 2026-10-06)**
    - **배경 및 사용자 피드백**:
      1. xia 캐릭터의 얼굴이 과도하게 창백하게 렌더링되는 현상 발생.
      2. oes 캐릭터에서 헤어 상투가 두 개로 분리되거나 정수리로 올라가는 현상, 목 주위에 점이 여러 개 생기는 현상 발생.
      3. ykn 프로젝트 4명(yua, ser, sia, hay) 캐릭터를 oes 얼굴 기반으로 통일 재구성 요청. hay는 검정 블레이저 + 흰 셔츠 조임 연출.
    - **원인 규명**:
      - `clean pale skin` 태그: Illustrious 계열 모델에서 병적으로 창백한 피부로 오해석됨. `fair skin with healthy complexion`으로 교체.
      - `(beauty mark under left eye near cheek:1.2)`: `near cheek` 위치 지시어가 모호하여 목/턱 주위에 점이 분산 생성됨. `single beauty mark directly under left eye`로 명확화.
      - `((single hair bun...:1.3))`: 가중치 1.3이 부족하여 double bun으로 분리되거나 정수리로 이동. 1.45로 상향 및 네거티브에 `((hair bun on top of head:1.5))` 추가.
    - **oes/xia 수정 사항**:
      - 피부 표현: `clean pale skin` → `fair skin with healthy complexion` (양 캐릭터 공통)
      - 점 위치: `(beauty mark under left eye near cheek:1.2)` → `(single beauty mark directly under left eye:1.25)`
      - 머리 가중치: `:1.3` → `:1.45` (상투 이탈 방지)
      - 네거티브 추가: `((hair bun on top of head, high hair bun, bun on crown:1.5))`, `((multiple beauty marks, beauty marks on neck, beauty mark on chin, beauty mark on cheek:1.5))`
    - **ykn 프로젝트 캐릭터 재구성 (oes 얼굴 계승)**:
      - 공통 계승 요소: `(dark eyes:1.2)`, `(single beauty mark directly under left eye:1.25)`, `fair skin with healthy complexion`
      - 공통 네거티브: oes 동일한 3단계 방어선 (기형방지 + 성별배제 + 레이아웃배제 + 헤어색상 고정)
      - 개별 개성 유지:
        - **yua** (1녀): 사이드 포니테일 | 풍만한 볼륨 | 크림 니트 카디건 + 화이트 블라우스
        - **ser** (2녀): 히메컷 | 중간 가슴 + 넓은 힙 | 화이트 케이블 카디건
        - **sia** (3녀): 하이 포니테일 | 슬렌더 소가슴 | 베이지 트렌치 재킷
        - **hay** (4녀): 어깨선 세미롱 | 거대 가슴 | **검정 블레이저 조임 + 흰 셔츠**
    - **hay 의상 특이사항 — 블레이저 조임 연출 확립**:
      - `white collared shirt underneath` + `navy blue blazer worn over shirt` 레이어 구조 명시
      - `buttoned blazer straining over bust`, `blazer tightly covering breasts`, `buttons pulling taut`, `blazer stretched across chest`로 블레이저가 거대 가슴을 조이며 덮는 연출 구현
      - 의상 본체(`white collared shirt`, `navy blue blazer`, `dark pleated skirt`)는 가중치 1.0 평문 유지 (탈의씬 옷 잔류 방지 불변식 준수)
    - **IP-Adapter HEXMIX 비호환 결정**:
      - HEXMIX v5.0 체크포인트에서 IP-Adapter 활성화 시 품질 저하 현상 확인. 레퍼런스 해상도(700×1024 → 1024×1536) 일치 후 재시도에도 개선 없음.
      - 원인: Kiro(Forge ControlNet 자동 최적화) vs PLEPA(ComfyUI IPAdapterPlus 수동 설정) 방식 차이 및 IPAdapterPlus "PLUS (high strength)" 프리셋 과포화.
      - **결정**: HEXMIX 사용 시 `--no_ref` 옵션 기본 권장. 다른 체크포인트(Unholy, WAI)에서는 IP-Adapter 사용 가능.

34. **ComfyUI `object_info` 실시간 모델 자동 감지 및 체크포인트/UNet 동적 드롭다운 선택 구현 (ADR 2026-10-07)**
    - **배경 및 사용자 피드백**:
      1. ComfyUI `models/checkpoints/` 폴더 내에 위치한 모델 파일들을 GUI에서 일일이 타이핑하지 않고 드롭다운으로 편리하게 선택할 수 있도록 개선 요청.
      2. 체크포인트 변경 시 실제 생성 파이프라인 및 ComfyUI 워크플로우에 정상 적용되고 있는지 점검 및 무결성 보장 요청.
    - **해결 조치**:
      - **ComfyUI 실시간 모델 인트로스펙션 (`ComfyClient.get_available_models()`)**:
        - ComfyUI의 `/object_info/CheckpointLoaderSimple`, `/object_info/UnetLoaderGGUF`, `/object_info/UpscaleModelLoader`, `/object_info/VAELoader` 엔드포인트를 질의하여 설치된 모델 목록을 실시간 자동 파싱.
        - 서버 미가동 시에도 기본값으로 안전 폴백 처리되어 UI 크래시 0% 보장.
      - **GUI 설정 및 생성 페이지 동적 드롭다운 전면 연계**:
        - 환경 설정(`/settings`) 및 배치 생성(`/generate`) 페이지에 감지된 체크포인트/UNet/업스케일러 드롭다운 컴포넌트 탑재.
        - 드롭다운 선택뿐만 아니라 직접 파일명 입력도 지원하는 하이브리드 UI 모드(`use-input new-value-mode=add-unique`) 적용.
        - 배치 생성 페이지에서 엔진 전환(`sdxl` / `flux`) 시 대상 모델 선택기가 실시간 동적 전환되도록 구축.
      - **파이프라인 매핑 무결성 확립**:
        - `GenerationParams`의 `ckpt`, `unet` 기본값을 `None`으로 정비하여 `사용자 명시 선택값 ➔ 전역 설정값 ➔ 기본 상수` 순의 엄격한 우선순위 폴백 체계 확립.
36. **IP-Adapter(레퍼런스) 전역 기본 비활성화 및 2인 상호작용 포즈 충돌 필터 탑재 (ADR 2026-10-09)**
    - **배경 및 원인 규명**:
      1. 고정된 정면 스탠딩 레퍼런스 이미지를 ComfyUI IP-Adapter로 주입할 경우, 복잡한 체위나 2인 상호작용 포즈에서 인체 왜곡, 텍스처 뭉개짐(Color Bleeding), 디테일 상실 및 평면화(Flat)가 유발됨.
      2. 034번(`가슴파묻힘`) 등 파트너가 등장하는 2인 씬에서 캐릭터 기본 태그의 `solo` 및 네거티브의 `1boy, male, multiple characters`가 주입되어, 포즈 프롬프트의 남성 모브 지시와 정면 충돌하고 남성이 뒤에서 백허그하거나 괴기한 형태로 왜곡되는 구도 파괴 현상 발생.
    - **해결 조치**:
      - **IP-Adapter 전역 기본 비활성화**:
        - `config.py`의 `DEFAULT_REF_WEIGHT = 0.0` 설정.
        - `GenerationParams.no_ref = True` 기본값 확립 및 CLI 기본 동작을 비활성화로 설정 (`--use-ref` 플래그 명시 시에만 예외적 사용 허용).
        - 순수 프롬프트 + 체크포인트 + VAE + Face Detailer 조합으로 본연의 최고 선화 디테일 및 질감 100% 회복.
      - **2인 상호작용 프롬프트 충돌 필터 (`prompt_builder.py`)**:
        - 2인 포즈(`is_interactive` 감지 시) 캐릭터 프롬프트에서 `solo` 태그를 자동 스트리핑.
        - SDXL 네거티브에서 남성 차단 태그(`1boy`, `male`, `masculine`, `multiple characters` 등)를 자동 제거하여 파트너 모브 생성 정상화.
      - **034번 `가슴파묻힘` 포즈 구도 완전 개편 (`sdxl_pose_database.json`)**:
        - 남성이 앞에서 여자의 가슴골에 얼굴을 파묻고(`(man burying face between woman breasts:1.4)`, `(face buried in cleavage:1.35)`), 여성이 두 팔로 남성의 머리를 가슴으로 끌어안는 안도/포근 구도(`(woman hugging man head to her chest:1.4)`)로 수정하여 의도와 100% 일치하는 에셋 생성 확인.
37. **6대 기능 계층별 작동 체크리스트 및 장애 진단 체계 구축 (ADR 2026-10-10)**
    - **배경**:
      - 이미지 생성 실패, 구도 왜곡, 화질 저하, 프로세스 크래시 등 복합 장애 발생 시, 어느 계층(인프라, JSON 데이터, 프롬프트 조립, ComfyUI 워크플로우, 후처리/검열, 웹 GUI)에서 문제가 발생했는지 즉각 파악하기 위한 표준화된 진단 매뉴얼 필요.
    - **해결 조치**:
      - **[`TROUBLESHOOTING_CHECKLIST.md`](TROUBLESHOOTING_CHECKLIST.md) 공식 신설**:
        - **계층 1 (인프라 & ComfyUI)**: 8188 포트, VRAM 메모리 정리, 체크포인트 파일명 오타 검증.
        - **계층 2 (데이터 & JSON)**: 캐릭터 JSON 필수 필드, 포즈 DB 무결성, `.plepa_backup` 복구.
        - **계층 3 (프롬프트 조립기)**: `--dry-run` 무결성, 탈의(Nude) 스트리핑, 2인 씬 `solo` 및 남성 배제 충돌 필터.
        - **계층 4 (워크플로우 & I/O)**: IP-Adapter 비활성화(`no_ref=True`), `--mock` 초고속 I/O 검증, 저장 경로 권한.
        - **계층 5 (후처리 & 검열)**: Face Detailer 얼굴 인식, 성기 자동 검열(`--censor`) BBox 마진.
        - **계층 6 (웹 GUI & 작업 관리자)**: 8080 포트, `global_job_manager` 작업 중복 방지, 새 탭 뷰어.
      - **10초 원클릭 진단 명령어 규격화**:
        - 시스템 자체 진단(`--test`), 통신 점검(`Test-NetConnection`), GPU 미사용 출력 점검(`--dry-run`), 더미 파일 생성(`--mock`) 4단계 진단 프로토콜 확립.
38. **레거시 대용량 파일 정리 및 루트/문서 디렉토리 다이어트 (ADR 2026-10-10)**
    - **배경**:
      - 프로젝트 장기 진행에 따라 과거 키로(`.kiro/`) 시스템 클론(약 1.99GB), 인코딩 결함 중복 에셋 폴더, 1회성 마이그레이션 및 디버그 스크립트, 구버전 중복 문서(`docs/`) 등이 잔존하여 약 2.1GB의 디스크 낭비 및 문서 SSOT 혼선 유발.
    - **해결 조치**:
      - **대용량 잔재 삭제 (2.1GB 확보)**: 미참조 `.kiro/`(1.99GB) 및 `projects/hey/assets/ ` 깨진 중복 폴더(235장), `frameworks/` 삭제.
      - **일회성 스크립트 11종 완전 정리**: `migrate_pose_descriptions.py`, `update_assets_to_illustrious.py`, `compare_models.py`, `check_comfy_status.py`, `debug_*.py`, `test_*.bat` 삭제.
      - **단위 테스트 `tests/` 폴더 일원화**: 루트에 흩어져 있던 `test_checkpoint_cli.py`, `test_checkpoint_service.py`, `test_quality_tags.py`를 `tests/` 내부로 이동하여 pytest 단일 관리 체계 확립 (14개 테스트 전수 통과).
      - **문서 체계 단일화**: FLUX 초창기 구버전인 `docs/` 디렉토리를 정리하고 루트 마스터 문서(`플에파_기능명세.md`, `캐릭터_포즈_제작_규칙.md`, `POSE_CATALOG.md`, `RUNBOOK.md` 등)로 단일 기준(SSOT) 확립.
39. **사후 단독 4K AI 초해상화 파이프라인 및 GUI 라이트박스 원클릭 연동 (ADR 2026-10-11)**
    - **배경 및 사용자 요구사항**:
      - 디퓨전 전체 재생성(약 40~50초 소요, 구도 및 표정 변형 위험) 없이, 이미 생성 완료된 마음에 드는 WebP 에셋을 순수 AI 업스케일 모델(`4x-UltraSharp.pth`)만으로 4K(4096x6144) 초고화질로 선명하게 변환하는 독립 파이프라인 요청.
      - CLI 명령뿐만 아니라 웹 GUI 갤러리(`/gallery`) 라이트박스에서 원클릭으로 손쉽게 업스케일할 수 있는 기능 탑재 요청.
    - **해결 조치 및 기술 설계**:
      - **경량 단독 업스케일 워크플로우 (`build_standalone_upscale_workflow`)**:
        - KSampler, Denoise, VAEDecode 등 디퓨전 노드를 완전히 배제하고 `LoadImage` ➔ `UpscaleModelLoader`(`4x-UltraSharp.pth`) ➔ `ImageUpscaleWithModel` ➔ `SaveImage` 4개 노드만으로 구성.
        - 구도, 표정, 손가락 왜곡 0% 무손실 보존 및 RTX 4060 Ti 기준 2~4초(네트워크 전송 포함 15~18초) 초고속 처리.
      - **전담 서비스 레이어 (`UpscaleService`, `upscale_service.py`)**:
        - 이미지 해상도 분석(`get_image_dimensions`), 4K 판별(`is_already_4k`), 단일 파일 업스케일(`upscale_file`), 다중 배치 업스케일(`upscale_batch`) 모듈화.
      - **독립 CLI 스위트 (`plepa_upscaler.py`)**:
        - `-i <파일경로>` 단일 변환, `-r <로스터> -c <캐릭터> -p <포즈>` 에셋 타겟팅, `-f/--overwrite` 원본 덮어쓰기 지원.
      - **NiceGUI 갤러리 라이트박스 원클릭 연동 (`gallery.py`)**:
        - 이미지 라이트박스 상단에 현재 해상도(`1024x1536`), 4K UHD 뱃지 및 `[✨ 4K AI 업스케일]` 원클릭 버튼 배치.
        - 비동기 백그라운드 연산(`run.io_bound`) 및 완료 시 라이트박스 이미지/헤더 자동 갱신.
      - **단위 테스트 (`tests/test_upscale.py`)**:
        - 워크플로우 JSON 연결 무결성, 해상도 판별 및 Mock 연산 테스트 작성 (pytest 17개 전수 통과).
40. **캐릭터 의상 슬롯 모듈화 및 테마 팩 다이내믹 스왑 시스템 (ADR 2026-10-11)**
    - **배경 및 문제점**:
      - 기존 파이프라인에서는 캐릭터의 외모(얼굴, 헤어, 체형)와 기본 의상(교복, 사복)이 단일 프롬프트(`base_positive`)에 결합되어 있어, 수영복(D)이나 바니걸(F), 메이드복(G) 등 확장팩 의상을 적용할 때 기존 옷 파편(셔츠 카라, 벨트 등)이 섞여 나오는 **"의상 키메라/오염 현상"** 발생.
    - **해결 조치 및 기술 설계**:
      - **의상 슬롯(Costume Slot) 모듈화 (`models.py`)**:
        - `CharacterConfig`에 `outfits: Dict[str, str]` 딕셔너리 및 `get_outfit(slot)` 메서드 신설 (`default`, `nude`, `swimsuit`, `bunny`, `maid`, `combat` 등).
        - 캐릭터의 얼굴/헤어/체형(Identity)과 의상을 분리하고, 미지정 시 공용 기본 테마 의상(`DEFAULT_THEME_OUTFITS`)으로 안전 폴백.
      - **포즈별 다이내믹 의상 스왑 엔진 (`prompt_builder.py`)**:
        - 포즈의 `required_outfit` 또는 코드/섹션에 따라 의상 슬롯 자동 결정 (`resolve_pose_outfit_slot`).
        - 테마 포즈(예: `D01`) 요청 시 기존 캐릭터 프롬프트에서 기본 의상 태그를 `strip_sdxl_outfit_tags`로 완전 박멸한 후 테마 의상(비키니)을 결합하여 **의상 오염 0% 보장**.
      - **모듈형 테마 팩 아키텍처 및 접두사 코드 지원 (`pose_service.py`)**:
        - `themes/*.json` 또는 `projects/{roster}/themes/*.json` 자동 탐색 및 기본 포즈 DB 병합.
        - 영문 알파벳 접두사 코드(`D01~D07`, `A01~A32`, `B01~B24` 등) 정규화 및 CLI 표현식(`-p D`, `-p swimsuit`, `-p D01..D07`) 완벽 지원.
      - **실측 검증**:
        - `mal_D01_수영복전신.webp` 생성 성공 (기존 아카데미 교복 흔적 0%, 에메랄드 비키니 스왑 100% 무결성 확보).
        - 신규 단위 테스트 6종 (`tests/test_outfit_swap.py`) 추가, 전체 23개 pytest 100% PASS.
41. **복합 행위 동시 수행(`simultaneously`) 및 고난도 체위 3요소 앵커링 (ADR 2026-10-12)**
    - **배경 및 사용자 피드백**:
      - `N34(수유대딸)`에서 단순 포옹으로만 나오고 실질적 핸드잡이 누락되거나 구도가 어긋나는 현상 발생.
      - `N30(파일드라이버)` 등 역전 고난도 체위에서 상하체가 꼬이거나 단순 정상위로 왜곡되는 현상 발생.
    - **해결 조치**:
      - **복합 행위 동시 수행 (`simultaneously`)**: 상반신(가슴 밀착 및 시선)과 하반신(손으로 쥐는 손동작 및 파트너 위치)을 각각 1.30 이상의 가중치로 분리 구속하고 `((breastfeeding and handjob simultaneously:1.35))` 문법 확립.
      - **고난도 체위 3요소 앵커링**: 바닥 접촉면(`shoulders and upper back on bed`), 공중 척추 각도(`hips raised vertically in air, inverted position`), 무릎 접힘(`knees folded to sides of head`) 및 관찰 앵글(`from side view`) 3요소를 물리적으로 구속.
42. **모브 파트너 방향성 분기 및 테마 액션 결합 씬 상호작용 승격 (ADR 2026-10-12)**
    - **배경 및 원인 규명**:
      - `N02(정상위강)`에서 남성이 2명으로 렌더링되던 문제: `prompt_builder.py`의 모브 주입 로직에 `(from behind:1.1)`이 하드코딩되어 전면 체위와 정면 충돌함.
      - `S04(골목섹스)`에서 여성이 2명으로 복제(`2girls`)되던 문제: 테마 액션 섹션(`spy_actions`)이 1인칭 POV로 분류되어 네거티브에 남성 차단 태그(`1boy, male`)가 강제 주입됨.
    - **해결 조치**:
      - **모브 방향성 분기 (`is_rear_scene`)**: 후방 체위(`rear`, `behind`, `doggystyle`, `sumata`)에만 `(from behind:1.15)`를 주입하고, 전면 체위에서는 배제. 네거티브에 `(2boys:1.6), (multiple boys:1.6)` 추가.
      - **테마 결합 씬 승격**: 테마 액션 섹션이라도 성인 결합 키워드(`standing sex`, `penetration` 등)가 감지되면 2인 상호작용 씬으로 승격하여 모브 주입 및 여성 복제 원천 차단.
43. **레거시 H-씬(040~059, 140~159) 공식 은퇴 및 N 시리즈 단일화 (ADR 2026-10-12)**
    - **배경 및 사용자 의사결정**:
      - 구형 40종 포즈와 신규 N 시리즈(66종)가 완전 중복되어 캐릭터당 20장의 불필요한 GPU 시간(약 9분) 낭비 발생.
      - 구형 포즈에서 오랜 기간 축적된 우수한 세부 표현(시점, 표정, 떨림, 시트 묘사 등)을 계승할 필요성 확인.
    - **해결 조치**:
      - 구형 40종 내역을 [`docs/LEGACY_H_SCENES_ARCHIVE.md`](LEGACY_H_SCENES_ARCHIVE.md)에 보존.
      - 구형 포즈의 정교한 묘사를 `N01~N24` 프롬프트에 1:1 완벽 이식 및 고도화.
      - 기본 전체 생성(`all`) 시 레거시 섹션은 건너뛰고 N시리즈로 단일화.
44. **로스터별 스마트 테마팩 자동 연결 및 코스튬 기본 배제 정책 (ADR 2026-10-12)**
    - **배경 및 사용자 피드백**:
      - 스파이 로스터를 전체 생산할 때 무협 액션(C), 수영복(D), BDSM(E), 바니걸(F)이 무분별하게 혼입되어 194장으로 비대해지는 문제 해결 요청.
    - **해결 조치**:
      - **공통 코어 팩 (152종)**: 기본 표정(20) + 기본 포즈(20) + Genit 감정(24) + Genit 행동(22) + 통합 성인 N(66).
      - **로스터 전용 테마 자동 추가**: `spy` 로스터는 `spy_actions(10종)`만 연결되어 **총 162종** 생성. (`murim` 로스터는 `wuxia_actions(10종)`만 연결되어 총 162종).
45. **2인 밀착 씬(#034) 모브 블록 중복 제거, 표정 조화 파이프라인 및 SEGS Detailer Hook (ADR 2026-10-15)**
    - **배경 및 문제점**:
      1. `#034(가슴에얼굴묻기)` 등 2인 밀착 씬에서 Face Detailer가 파트너 남성의 가려진 옆얼굴/턱선까지 감지하여 2회 인페인팅을 실행, 생성 시간이 52초 이상으로 급증하고 남성 머리가 여주 머리색으로 오염되는 현상 발생.
      2. 아야메의 기본 정의 `cool calm expression`이 포즈의 `tender gentle smile`을 상쇄하여 여주인공이 미소 짓지 못하고 무표정화되는 현상 발생.
      3. 포즈 자체에 이미 남성의 위치와 뒤통수가 정의되어 있음에도, `TwoPersonMobMutator`가 독립 모브 블록(`solid black pants, muscular build`)을 추가 주입하여 모델이 "앞에 머리 묻는 남자 1명 + 뒤나 옆에 서 있는 큰 남자 1명"으로 남성을 2명씩 렌더링하는 분신 현상 발생.
      4. 파이프라인의 `\bmale\b` 정규식 삭제로 인해 `(male face visible)`이 `( face visible)`로 잘려 여주인공의 얼굴까지 네거티브에 걸리던 버그 확인.
    - **해결 조치**:
      1. **SEGS Ordered Filter Detailer Hook 연동 (`workflow_templates.py`)**: `SEGSOrderedFilterDetailerHookProvider`를 `FaceDetailer`의 `detailer_hook`으로 연결하여 면적 기준 최상위 1개 얼굴(`take_count: 1`)만 단독 필터링하도록 구성. `bbox_threshold`를 0.68로 상향하여 모브 얼굴 인페인팅 100% 스킵 및 생성 시간 24~36초대로 대폭 단축.
      2. **표정 지능형 조화 (`harmonize_character_expression`)**: 포즈에 미소/행복/홍조 등 능동 표정/감정 태그가 있을 때 캐릭터 기본 무표정을 자동 제거하여 여주인공의 다정한 미소 100% 반영.
      3. **밀착 씬 독립 모브 중복 방지 (`is_head_hug_scene`)**: 포즈 자체에 파트너 밀착이 이미 정의된 경우 추가 모브 BREAK 청크를 생략하고 네거티브에 `(2boys:1.8), (duplicate male:1.8), (standing male:1.5)`를 주입하여 100% 단일 1:1 관계 확립.
46. **Auto-QC 결함 자동 감지 및 리롤 루프, MobileSAM 화이트 실루엣 검열 및 독립 격리 저장 (ADR 2026-10-15)**
    - **배경 및 사용자 피드백**:
      1. 생성 후 인원 초과(1인 씬에 2명, 2인 씬에 3명 등), 손 증식(3개/5개 이상), 모브 남성 얼굴 노출 등 불량 이미지를 수작업으로 찾아 리롤하는 리소스 낭비 원천 차단 요구.
      2. 단순 사각 박스나 블러가 아닌, 실제 대상 부위의 외곽선(Contour) 곡률을 유지하는 유려한 실루엣 검열 요구 및 화이트 실루엣(#FFFFFF) 스타일 채택.
      3. 오랄/밀착 씬에서 여주인공 어깨/팔 피부 쪽으로 마스크가 번지던 결함 발견.
      4. 원본 에셋과 검열본이 한 폴더에 혼재되지 않고, 에셋 폴더와 대등한 위치의 독립 폴더(`censor_{prefix}/`)에 원본과 1:1 동일한 파일명으로 격리 저장되도록 요구.
    - **해결 조치**:
      - **초고속 Auto-QC 감지기 및 자동 재시도 루프 (`qa_validator.py`, `generation_service.py`)**:
        - `imgutils.detect` 기반 4대 감지기(`person`, `head`, `hand`, `face`)를 활용하여 장당 **0.05~0.08초** 만에 판정.
        - 불량 판정 시 노드 그래프의 KSampler/FaceDetailer 시드를 무작위 재생성하여 최대 `max_retries`(기본 3회)까지 자동 리롤.
      - **MobileSAM 기반 정밀 화이트 실루엣 (`censor.py`)**:
        - `mobile_sam.pt` 싱글톤 연동.
        - **피부 번짐 차단**: 밀착 씬 하단 확장 억제(4%), BBox 마스크 클램핑, 주 덩어리 대비 5% 미만/300px 미만 고립 노이즈 컨투어 100% 제거.
        - 타원 모폴로지 클로징 및 가우시안 안티앨리어싱을 거쳐 순수 화이트(#FFFFFF)로 메우는 `white_silhouette` 모드를 기본값으로 확정.
      - **H-씬 자동 분기 및 초고속 소급 검열 (`--censor-only`)**:
        - `PoseEntry.is_h_scene` 프로퍼티 신설로 착의 일상 포즈는 자동 스킵.
        - `--censor-only` 플래그로 ComfyUI 가동 없이 기존 에셋들을 장당 0.2초 만에 스캔하여 검열본 일괄 추출.
      - **독립 폴더 분리 저장 아키텍처**:
        - `projects/{roster}/censor_{char.prefix}/`에 원본 파일명 그대로 보존하여 게임 엔진/뷰어에서 폴더 경로 교체만으로 1:1 에셋 스왑 지원.

---

## 3. 플에파 시스템 아키텍처 및 불변식 (Invariants)

### 3.1 디렉토리 구조
```text
plepa/
├── .gitignore
├── GEMINI.md                    # 에이전트 행동 지침
├── AI_HANDOVER_GUIDE.md         # [본 문서] 시스템 아키텍처 및 의사결정 인계서 (SSOT)
├── THEME_PACK_GUIDE.md          # 전용 테마 팩 및 다이내믹 의상 스왑 포즈 제작 공식 지침서
├── 플에파_기능명세.md             # 파이프라인 인터페이스 및 CLI/ComfyUI 기술 규격서
├── 캐릭터_포즈_제작_규칙.md        # 캐릭터 JSON 및 80종 포즈 프롬프트 제작 완전 지침서
├── POSE_CATALOG.md              # 80종 포즈 카탈로그 및 2~4글자 명칭 뷰어
├── README.md                    # 설치 및 모델 가이드
├── flux_batch_generator.py      # 플에파 메인 실행 CLI
├── plepa_upscaler.py            # 사후 단독 4K AI 초해상화 CLI 도구
├── flux_pose_database.json      # 플럭스 전용 80종 영문 서술형 자연어 포즈 DB (3자리 000~159)
├── sdxl_pose_database.json      # SDXL 전용 80종 Danbooru 태그 포즈 DB (3자리 000~159)
├── themes/                      # 전역 공용 테마 팩 모듈 (swimsuit.json 등)
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

---

## 6. hey 프로젝트 — 해리포터 젠더벤드 캐릭터 규격 (ADR 2026-10-08)

### 6.1 프로젝트 개요
- **로스터 경로**: `projects/hey/characters/`
- **캐릭터**: `har` (해리), `her` (헤르미온느), `mal` (말포이) — 전원 젠더벤드
- **기본 엔진**: SDXL
- **체크포인트**: `flatbreadILV60.safetensors` (Flatbread - IL - v6.0, mommymia 제작, Illustrious 베이스)

### 6.2 캐릭터 규격 3인

| 항목 | har (해리) | her (헤르미온느) | mal (말포이) |
|------|-----------|----------------|------------|
| **Prefix** | `har` | `her` | `mal` |
| **체형** | `(large breasts:1.2)`, 볼륨 모래시계 | 슬렌더, medium breasts | voluptuous, very large breasts |
| **헤어** | 짧고 헝클어진 칠흑 단발 | 긴 웨이비 밤색 | 긴 직모 플래티넘 블론드 |
| **눈** | 밝은 청록/녹색 | 따뜻한 앰버 브라운 | 샤프한 회녹색, 쓰리메 |
| **특징** | 동그란 안경 | 주근깨, 소프트 뱅 | 하이라이트, 창백한 피부 |
| **착의 의상** | 흰 민소매 리브드 니트 + 딥 V넥 + 데님 쇼츠 + 버건디 가디건 | 버건디 크롭 니트 탑 + 화이트 미니 스커트 + 버건디 가디건 | 아이보리 크롭 카미솔 + 차콜 슬림 트라우저 + 에메랄드 가디건 |

### 6.3 듀얼 캐릭터 JSON 시스템 (핵심 아키텍처)

**원칙**: 포즈 번호에 따라 캐릭터가 자동으로 다른 프롬프트를 사용한다.

```
000~037번 (착의) → sdxl_positive     참조 (의상 태그 포함)
038~159번 (탈의) → sdxl_nude_positive 참조 (신체/얼굴 태그만, 의상 태그 0%)
```

**자동 분기 조건** (`plepa_engine/prompt_builder.py`의 `is_nude_pose()` 기준):
- `section == "shower"` (038~039) → nude
- `section == "h_scenes"` (040~059) → nude
- `section == "scenes_otokonoko"` (140~159) → nude
- 나머지 (000~037) → 착의

**엔진 처리 흐름**:
1. `is_nude_pose()` → nude 여부 판별
2. nude=True + `sdxl_nude_positive` 존재 → **`sdxl_nude_positive` 직접 사용** (의상 strip 불필요)
3. nude=True + `sdxl_nude_positive` 없음 → `sdxl_positive`에서 `strip_sdxl_outfit_tags()` 후 사용 (fallback)
4. `prompt_builder.py`가 자동으로 `, nude, completely nude` 추가

**`sdxl_nude_positive` 작성 규칙**:
- 의상 태그를 처음부터 포함하지 않을 것 (strip 로직 불필요)
- 체형 / 얼굴 / 헤어 / 눈 등 신체 외형 태그만 포함
- `nude, completely nude`는 엔진이 자동 추가하므로 직접 쓰지 않아도 됨

### 6.4 Flatbread IL v6.0 체크포인트 설정

| 항목 | 값 |
|------|-----|
| **파일명** | `flatbreadILV60.safetensors` |
| **제작자** | mommymia |
| **베이스** | Illustrious XL |
| **해상도** | 1024 × 1536 |
| **Sampler** | DPM++ 2M |
| **Scheduler** | Karras |
| **Steps** | 30 |
| **CFG** | 5.0 |
| **품질 태그(Positive)** | `masterpiece, newest, absurdres, incredibly absurdres, best quality, amazing quality, very aesthetic` |
| **품질 태그(Negative)** | `lowres, bad anatomy, worst quality, low quality, normal quality, bad hands, mutated, extra fingers, artifacts, disfigured` |
| **Face Detailer** | ✅ 권장 |
| **Upscale** | ✅ 권장 |

> `artist:hexmix:1.1` 태그 사용 금지 — Flatbread는 별도 아티스트 믹스 불필요

### 6.5 har (해리) 상세 규격

**착의 프롬프트 핵심 태그 (sdxl_positive)**:
- `((white sleeveless ribbed knit top:1.3))` — 민소매 흰 리브드 니트
- `((sleeveless:1.25)), ((bare shoulders:1.2))` — 민소매/어깨 노출
- `((deep v-neck:1.35)), ((plunging neckline:1.3))` — 깊은 V넥 가슴골 노출
- `((deep cleavage:1.35)), ((cleavage visible:1.25))` — 가슴골 강조
- `(blue denim shorts:1.15)` — 데님 쇼츠
- `(burgundy red open cardigan loosely draped:1.1)` — 버건디 오픈 가디건

**네거티브 핵심**:
- `long sleeves, turtleneck, high collar, covered shoulders, crew neck, round neck, closed neckline, covered chest`

### 6.6 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-10-08 | har 초기 생성. 터틀넥 스웨터 착의 컨셉. hexmix 체크포인트. |
| 2026-10-08 | `sdxl_nude_positive` 필드 신설. 038번~부터 탈의 씬 자동 적용. |
| 2026-10-08 | har 의상 변경: 터틀넥 → 민소매 흰 리브드 니트 + 딥 V넥. |
| 2026-10-08 | har 가슴 크기 조정: `gigantic/massive/huge` → `(large breasts:1.2)` 통일. |
| 2026-10-08 | `models.py` `sdxl_nude_positive` 필드 누락 버그 수정. `prompt_builder.py` 분기 로직 추가. 속옷 등장 문제 해결. |
| 2026-10-08 | 체크포인트 전환: hexmix → **Flatbread IL v6.0** (`flatbreadILV60.safetensors`). her/mal 포함 3캐릭터 전체 적용. |
| 2026-10-08 | her/mal `sdxl_nude_positive` 신규 추가. hey 프로젝트 전체 듀얼 JSON 시스템 완비. |

### 6.7 관련 파일 목록

| 파일 | 역할 |
|------|------|
| `projects/hey/characters/har.json` | 해리 캐릭터 정의 |
| `projects/hey/characters/her.json` | 헤르미온느 캐릭터 정의 |
| `projects/hey/characters/mal.json` | 말포이 캐릭터 정의 |
| `plepa_engine/models.py` | `CharacterConfig.sdxl_nude_positive` 필드 |
| `plepa_engine/services/schemas.py` | `CharacterSchema.sdxl_nude_positive` 스키마 |
| `plepa_engine/prompt_builder.py` | `is_nude_pose()` + `assemble_sdxl_prompt()` 분기 로직 |
| `plepa_engine/checkpoint_profiles.json` | Flatbread IL v6.0 프로필 등록 |

---

## 7. 아키텍처 결정 기록 (ADR)

### ADR-41: 1:1 포즈 코드 유지 기반 여성 vs 오토코노코 프롬프트 분기 시스템 (2026-10-11)
- **배경**: Genit 등 플랫폼 리소스 매핑 규격상 여성과 오토코노코 캐릭터가 동일한 상황 코드(`N01` 등)를 호출해야 함. 이전 방식(40번대 vs 140번대 물리적 코드 분리)은 확장 테마 팩과 단일 규격 매핑에 제약이 있었음.
- **결정 사항**:
  1. `PoseEntry` 모델에 `prompt_female` 및 `prompt_otokonoko` 필드와 `get_prompt(gender)` 메서드 도입.
  2. 공용 씬(A 감정, B 일상)은 기본 `prompt`로 공유하고, 체형/상호작용 분기가 필요한 특수 이벤트 씬은 동일 코드 내에서 내부 프롬프트를 성별에 따라 자동 분기.
  3. `prompt_builder.py`의 `assemble_flux_prompt` 및 `assemble_sdxl_prompt`에 성별 디스패치 연동.
- **결과**: URL/코드 체계의 100% 일관성을 유지하면서 두 성별 모두 자연스럽고 정교한 전용 씬 생성을 완벽 지원.

### ADR-42: Genit 상용 표준 세팅 규격화 및 GUI 원클릭 익스포터 구축 (2026-10-11)
- **배경**: 상용 인기 작가의 Genit 이미지 세팅(A 감정 24종, B 행동 22종, N 성인 46종, D/E/F 의상 22종) 규격을 플에파 시스템 표준으로 정착시키고, 웹 플랫폼 업로드용 포맷(`{{url}}캐릭터코드/상황코드.webp`, 예: `dist/genit/AA/A1.webp`)으로 간편하게 변환할 수 있는 기능 필요.
- **결정 사항**:
  1. `themes/` 내 공식 표준 테마 파일 완비 (`genit_emotions.json`, `genit_actions.json`, `adult.json`, `bdsm.json`, `bunny.json`).
  2. `pose_sets.json`에 Genit 팩 5종 및 풀패키지(114종) 공식 세트 등록.
  3. `GenitExporter` 서비스(`genit_exporter.py`) 신설: 내부 코드(A00, A01, N01 등) ➔ 플랫폼 코드(A0, A1, N1 등) 역정규화 및 8인 기본 캐릭터 매핑(한지아 AA, 서아윤 BB 등) 지원.
  4. NiceGUI 생성 페이지에 "Genit 상용 팩" 퀵 셀렉트 버튼 탑재, 갤러리 페이지에 "📦 Genit 내보내기" 원클릭 다이얼로그 탑재.
- **결과**: 상용 플랫폼 배포 준비 시간이 수작업 30분에서 원클릭 1초로 단축되고, 시스템 전반의 100% 상호 호환성 확보.

### ADR-43: 무협 아포칼립스 세계관 구축 및 유저 3대 시작 분기 시스템 확립 (2026-10-11)
- **배경**: 신규 프로젝트로 무협/무림소설 기반 캐릭터 챗봇을 기획함. 방대한 무협 문파 인물 수를 스토리적으로 압축하기 위해 마교의 중원 멸망 및 남만 야수궁 피난 설정을 채택함. 주인공의 위상이 일방적으로 높을 경우 긴장감이 저하되므로, 유저 취향에 맞춘 다중 시작 분기 및 스토리 위협을 형성할 적대 세력 구축이 요구됨.
- **결정 사항**:
  1. `projects/murim` 신규 프로젝트 생성 및 기획서(`01_무협_아포칼립스_기획_및_설정.md`) 작성.
  2. **유저 3대 시작 모드 확립**:
     - `[루트 1] 정파의 고수`: 명문정파 최후의 영웅/검선 (고결한 구원자, 사이다 전투, 헌신적 충성).
     - `[루트 2] 사파의 잡졸`: 밑바닥 패잔병/생존자 (지략과 기연으로 오만한 명문가를 굴복시키는 하극상 빌드업).
     - `[루트 3] 남만의 지배자`: 야수궁의 군주 (절대적 패도와 카리스마로 피난민들을 거느리고 통제/지배).
  3. **캐릭터 로스터 확장 (10인 네임드 + 2종 MOB)**:
     - Genit 표준 히로인 8인 (`AA` 백설아, `BB` 남궁채원, `CC` 소유화, `DD` 흑연화, `EE` 서예린, `FF` 진아영, `GG` 바라, `HH` 미아).
     - 마교 수뇌부 2인 (`II` 천마 천소희, `JJ` 우호법 야차 흑호련).
     - 세계관 씬 연출용 엑스트라 팩 2종 (`mob_nanman` 야수궁 전사단, `mob_cult` 마교 침공군).
  4. 무협 전용 배경 프롬프트 6종(`projects/murim/background.json`) 완비.
- **결과**: 고결한 영웅물, 밑바닥 역전극, 군주 패도물의 3대 플레이 경험을 단일 챗봇 세계관에서 자유롭게 즐길 수 있는 탄탄한 서사 및 비주얼 생성 인프라 완성.
### ADR-44: 무협 전용 정예 10종 팩(C1~C10) 구축 및 상황별 착의/탈의 불변식 확립 (2026-10-11)
- **배경**: 현대식 테마 팩(수영복, 바니걸 등)은 무협 세계관 몰입을 해치므로 제외하고, 선역부터 악당까지 보편적으로 사용할 수 있는 무협 전용 10종 팩(C1~C10)이 필요함. 또한 세계관 팩 적용 시 캐릭터 본래의 무협 복식(도복, 한푸, 아대 등)이 완벽히 보존되어야 하며, 반대로 호수목욕(C10), 온천(B16), H-씬(N1~N74) 등에서는 의상 파편 없이 실오라기 하나 없는 완전 탈의 상태가 보장되어야 함.
- **결정 사항**:
  1. 	hemes/wuxia_actions.json 신설 및 정예 10종(C01~C10: 운기수련, 전투대치, 초식공격, 내공주입, 주화입마, 무기손질, 달빛음주, 경공비행, 제압포로, 호수목욕) 구축.
  2. **의상 보존 vs 완전 탈의 불변식**:
     - **착의 씬 (A00~A23, B01~B10, C01~C09)**: default 슬롯으로 지정하여 캐릭터 JSON의 고유 복식(도복, 비단 예복, 아대, 비녀 등)을 100% 온전히 착용.
     - **완전 탈의 씬 (C10 호수목욕, B16 목욕, N01~N74 성인 씬)**: 
ude 슬롯으로 강제 지정하여 엔진의 strip_sdxl_outfit_tags 및 sdxl_nude_positive를 통해 모든 의상·악세서리 태그를 원천 박멸하고 완전 나체 렌더링.
  3. pose_sets.json 및 generate.py 퀵 버튼 바에 [⚔️ 무협 C](10종) 및 [🏮 무협풀팩(102)] 연동.
- **결과**: 현대식 테마의 이질감을 배제하고 무협 고유의 장르적 몰입도와 상황별 착의/탈의 정밀성을 100% 확보.

### ADR-45: 모브 파트너 무특징(Faceless/Obscured Face) 구도화 및 시각적 결함 9대 방어 체계 확립 (2026-10-11)
- **배경**:
  1. H-씬/스킨십 생성 시 남성 모브 파트너가 과도하게 미남이거나 디테일하게 묘사되어 히로인의 시각적 집중을 분산시킴.
  2. 이를 억제하기 위해 `blank face`, `featureless face` 태그를 도입했으나, 2D 애니 모델이 이를 물리적인 "흰 석고/노(Noh) 가면"으로 오인하여 모브는 물론 히로인의 얼굴에도 가면을 씌우거나 동공을 지워버리는 치명적 결함 발생.
  3. 또한 네거티브의 `colored skin`으로 인한 구릿빛 피부 탈색, 1:1 씬에서 2boys 소환, 무협 세계관에 어울리지 않는 현대식 가구(침대), 통신/촬영 기기, 최음 기구, 텍스트 말풍선 발생 등 복합 결함이 제기됨.
- **결정 사항**:
  1. **가면 유발 태그 영구 제명 및 순수 구도/음영 모브화**:
     - `blank face`, `featureless face` 전면 삭제.
     - 모브는 `(faceless male:1.15), (obscured male face:1.15), (male head out of frame:1.15), (shadow over male eyes:1.1), (from behind:1.1)` 순수 앵글과 음영으로만 무특징화.
     - 네거티브에 `mask, white mask, noh mask, blank face, pupil-less, empty eyes, white eyes:1.3` 상시 강제 주입.
  2. **구릿빛/태닝 피부 탈색 원천 차단**:
     - 네거티브에서 `colored skin` 완전 제거.
     - 구릿빛 캐릭터(`is_dark_skin`) 감지 시 네거티브에 `(pale skin:1.35), (white skin:1.35)` 주입, 포지티브에 `(radiant dark tan skin:1.2)` 고정.
  3. **지능형 다인(Gangbang) vs 1:1 분기**:
     - 갱뱅/3P/다인 씬: `2boys` 및 `group` 차단을 해제하고 `multiple faceless males` 주입.
     - 1:1 씬: `1boy` 정제 후 `(2boys:1.5), (multiple boys:1.5), (group:1.4)` 강력 차단.
  4. **무협 세계관 시대착오 요소 자동 정제**:
     - 포즈 태그의 `bed` ➔ 비단 침상, `camera POV` ➔ 은밀한 시점, `vibrator` ➔ 최음향/점혈, `stuck in wall` ➔ 동양풍 목조 격자벽 구도로 지능형 치환.
     - 네거티브에 `camera, phone, modern bed, vibrator, bra, panties:1.4` 추가.
- **결과**: 가면 및 동공 소실 0% 박멸, 남성 모브의 자연스러운 음영 처리, 구릿빛 피부의 완전한 보존 및 무협 고유 분위기 극대화 달성.

- **결과**: 갤러리 에셋 집계 100% 정상화(`aa`: 115장 등 즉시 노출) 및 회귀 버그 없는 안전한 배포 파이프라인 완성.

### ADR-47: 단일 진실 공급원(SSOT) 기반 메타데이터 주도형 동적 GUI 및 전수 계약 테스트 체계 확립 (2026-10-11)
- **배경**:
  1. 포즈/테마/로스터가 추가·수정될 때마다 관련 GUI 페이지(`poses.py`, `gallery.py`, `generate.py`)의 탭과 버튼을 일일이 수동 하드코딩해야 하여 누락 및 불일치 결함이 반복됨.
  2. 영숫자 포즈(`A00`, `C01` 등) 조회 시 `pose_service.py` 내부 레거시 `int(code)` 형변환으로 인해 화면 렌더링이 중단되던 취약점 발생.
- **결정 사항**:
  1. **메타데이터 레지스트리 단일 진실 공급원(SSOT) 구축 (`pose_service.py`)**:
     - `SECTION_METADATA` 단일 저장소를 신설하고, `get_active_sections()`를 통해 DB에 실제로 존재하는 섹션과 포즈 수량을 실시간 계산하여 반환.
  2. **GUI 포즈 페이지 100% 동적 루프화 (`poses.py`)**:
     - 하드코딩된 정적 탭(`tab_wuxia = ...`)을 완전 제거하고, `get_active_sections()` 기반 동적 루프로 UI를 자동 생성.
     - `SECTION_LABELS`를 `SECTION_METADATA`로부터 자동 파생하여 유지보수 포인트 단일화.
     - 영숫자 포즈 조회의 `int(code)`를 `normalize_code(code)`로 전면 교체하여 예외 차단.
  3. **전수 무결성 계약 테스트(Contract Test) 강화 (`tests/test_gui_all_features.py`)**:
     - `test_all_poses_details_rendering_safety`: DB 내 모든 영숫자 포즈의 상세 조회가 예외 없이 100% 성공하는지 자동 전수 스캔.
     - `test_active_sections_dynamic_metadata_contract`: 활성 섹션의 메타데이터 바인딩 및 정렬 순서 보장 검증.
     - `test_gui_poses_page_tabs_and_sections_sync`: 서비스 섹션과 GUI 레이블 간의 1:1 일치 보장.
- **결과**: 향후 어떤 포즈/테마가 추가되더라도 UI 코드를 단 한 줄도 손대지 않고 100% 자동 동기화되며, 계약 테스트로 사전 무결성을 완전 보장.


### ADR-48: 루트 디렉토리 베스트 프랙티스 리팩토링 및 포즈-배경 자동 매칭 시스템 구축 (2026-10-12)
- **배경**:
  1. 루트 디렉토리에 데이터 JSON(`flux_pose_database.json`, `sdxl_pose_database.json`, `pose_sets.json`), 문서(`*.md`), 일회성 스크립트(`*.py`), 로그 파일(`*.log`, `*.txt`)이 혼재되어 탐색성과 유지보수성이 저하됨.
  2. 로스터 및 포즈 세트(감정, 일상, 침실 성인 씬, 샤워/클리닉 씬)에 따라 적합한 배경 프리셋을 자동으로 매칭해 주는 서비스 계층이 필요함.
- **결정 사항**:
  1. **디렉토리 3계층 물리적 분리 (`data/`, `docs/`, `scripts/`)**:
     - 포즈 DB, 체크포인트 프로필, 테마 팩(`data/themes/`)은 `data/`로 이동.
     - 가이드·명세·개발일지 문서는 `docs/`로 이동 (루트에는 `README.md`, `GEMINI.md`, `사용법.txt` 유지).
     - 유틸리티/진단 스크립트는 `scripts/`로 이동하고 `plepa_engine/config.py`에 `DATA_DIR`, `DOCS_DIR`, `THEMES_DIR` 상수를 신설하여 전 모듈 참조 경로 단일화.
  2. **포즈-배경 자동 매칭 서비스 (`PoseBackgroundService`) 및 카테고리화된 포즈 세트 연동**:
     - `projects/{roster}/pose_background_mapping.json` 및 `plepa_engine/services/pose_background_service.py`를 통해 레거시 숫자 코드(`000-159`)와 Genit 영숫자 코드(`A00-A32`, `B01-B28`, `N01-N83`, `D/E/F`) 모두에 대해 최적의 배경 프리셋(`default`, `boudoir`, `office`, `clinic`)을 자동 추천.
     - `data/pose_sets.json`의 `_category` 구분선 객체를 `PoseService.load_pose_sets()`에서 안전하게 필터링하여 GUI 드롭다운 최상단에 Genit 표준 세트가 노출되도록 보장.
- **결과**: 클린 아키텍처 디렉토리 구조 확립 및 GUI 포즈 선택 시 배경 자동 전환 UX 완성.

### ADR-49: Project Spy 10인 전신 배경 스케일 착시(`[패치 A-3]`)·색상 이염·표정 제어 표준화 (2026-10-12)
- **배경**:
  1. `A00` 전신(`full body, standing`) 구도에서 배경에 `chandelier`, `ceiling`, `sofa`가 포함될 경우 모델이 방의 층고를 캐릭터의 키(`170cm`)로 압축 렌더링하여 캐릭터 머리가 천장에 닿는 거인화(Giantess) 착시 및 `long slender limbs` + `from below` 결합에 의한 9~10등신 다리 왜곡이 발생함.
  2. 유색 헤어(`kzk` 보라색, `evl` 핑크색)나 유색 조끼(`cla`의 `teal`)가 인접한 흰 의상(의사 가운, 간호사복, 흰 블라우스)으로 번지는 현상 및 캐릭터 이름(`kozuka`) 연상으로 인한 임의 소품(`headband`, `wrist bandages`) 생성 현상 발생.
  3. 무표정(`kzk`, `chl`, `scl`) 및 소심형(`rvn`) 캐릭터가 `A00`의 기본 `gentle smile` 때문에 고유 첫인상을 잃는 문제 발생.
- **결정 사항**:
  1. **전신 배경 스케일 착시 원천 차단 (`[패치 A-3]` & `background.json` 정제)**:
     - `projects/spy/background.json`에서 층고 기준물(`chandelier`, `sofa`, `curtains`)을 제거하고 근접 원목 벽면 + 강한 아웃포커싱(`close-up tall mahogany wood wall paneling, strong depth of field, heavily blurred background, soft bokeh`) 적용.
     - 10인 전원의 신체 비율 태그를 `balanced body proportions`로 통일하고, `prompt_builder.py` `[패치 A-3]`에서 전신 스탠딩 시 `(ceiling, chandelier, sofa, couch, armchair, door, doorframe, miniature room, giantess, from below, low angle, overly long legs, tiny head:1.3)` 네거티브를 자동 주입.
  2. **흰 의상 색상 이염 및 연상 소품 차단**:
     - 흰 블라우스(`cla`)와 흰 간호사복(`evl`)에 `(crisp pure snow-white ...:1.25)` 앵커링을 부여하고 네거티브에 `green shirt, teal shirt, greenish white` 및 `pink clothes, pink dress`를 배치하여 이염 0% 달성.
     - `kzk`에 `exposed clean forehead, bare wrists` 및 네거티브 `headband, wrist bandages` 차단을 적용.
  3. **캐릭터 리뉴얼 및 표정 자동 분기**:
     - `chl` (아사 콘셉트 + 하이슬릿 블랙 차이나 드레스), `rvn` (코베니 콘셉트 + 고노출 넥타이 오피스룩), `scl` (피오나 프로스트 콘셉트 + 은백발 비대칭 단발 + 가슴 버클 스트랩 & 크롭 가죽 재킷 스파이룩), `evl` (순백색 슬림핏 원피스형 간호사복) 리뉴얼 완료 및 `A00` 기질별 표정 자동 분기 확립.
- **결과**: Project Spy 10인 전원의 `A00` 프로필에서 등신대 스케일, 순백색 의상 색감 분리, 캐릭터별 고유 표정 및 콘셉트 무결성 100% 달성.

### ADR-51: 2인 씬 다수 남성(2boys/난교) 렌더링 결함 차단 및 단일 파트너 불변식 확립 (2026-10-14)
- **배경**:
  1. H-씬 중 후배위절정(059번) 등에서 남성 파트너가 2명 이상 생성되는(3P/다인 결합) 환각 결함이 발생.
  2. 원인 분석 결과, 파이프라인(`plepa_engine/prompt_builder.py`)에서 2인 씬 판정 시 `(solo:1.4)`를 네거티브에 주입하면서 동시에 `2boys`, `multiple boys` 차단 태그를 네거티브에서 제거해버리는 로직 버그가 있었음.
  3. 또한 포즈 DB의 프롬프트에 단일 파트너에 대한 명시가 누락되어 모델이 솔로는 피하되 남성을 2명 이상 생성하는 현상 유발.
- **결정 사항**:
  1. **네거티브 다수 남성 원천 차단 (`[패치 2BOYS]`)**:
     - `prompt_builder.py`의 2인 씬 분기에서 `1boy`, `male`, `masculine`만 제거하고, `((2boys, 3boys, multiple boys, multiple males, group sex, threesome, gangbang:1.35))`를 네거티브에 강제 주입하여 1:1 파트너십을 엄격히 고정.
  2. **포즈 프롬프트 단일 파트너 명시**:
     - `data/sdxl_pose_database.json` 및 `data/flux_pose_database.json`의 059번 포즈에 `((deep doggystyle climax with single male partner behind:1.3)), ((faceless male:1.2))`를 명시.
- **결과**: 2인 씬에서 남성 다수 출현 버그 원천 박멸 및 1:1 결합 씬 구도 안정화 달성.

### ADR-52: 시즈쿠(shz) 헤어 태그 단독 waves 바다/파도 연상 제거 및 네거티브 방어벽 구축 (2026-10-14)
- **배경**:
  - 캠퍼스 프로젝트의 시즈쿠(`shz`) 생성 시 실내 배경임에도 불구하고 뒷배경에 바다, 파도, 수면이 지속적으로 출현하는 배경 오염 결함 발생.
  - 원인 분석 결과, `shz.json`의 헤어스타일 프롬프트에 `(long wavy hair, voluminous messy waves:1.15)`가 포함되어 있었으며, Danbooru/SDXL 태그 체계에서 단독 `waves`는 헤어가 아닌 **바다 파도(ocean waves)** 태그로 인식됨.
- **결정 사항**:
  1. `projects/campus/characters/shz.json`의 헤어 태그를 `(voluminous messy wavy hair:1.15)`로 수정하여 머리카락으로 엄격히 한정.
  2. `sdxl_negative`에 `((ocean, sea, beach, water, waves, crashing waves, seashore, water surface:1.4))`를 추가하여 배경 수면 및 파도 연출 차단.
- **결과**: 실내 캠퍼스 및 자취방 배경에서 바다/파도 오염 0% 박멸.

### ADR-53: FLUX 파이프라인 레거시 패키지 격리 및 SDXL 중심 단일화 (2026-10-15)
- **배경**:
  - 플럭스(FLUX.1 [dev] GGUF)는 인체 묘사력은 우수하나 생성 속도가 장당 80~120초로 느리고 2.5D 실사 편향이 있어, 실질적인 메인 작업 흐름은 SDXL(NTR MIX XIII, 장당 34초, 2D 셀 채색 최적화)로 완전히 전환됨.
  - FLUX 관련 워크플로우 템플릿, 프롬프트 빌더, GUI 선택기, 기본 DB 경로 등이 코드베이스 전반에 분기로 산재하여 유지보수 복잡도를 유발하고 있었음.
  - 사용자의 의사결정("플럭스 모델은 근시일 안 쓸 것 같으니 분리해서 완전 레거시화")에 따라 FLUX 관련 코드를 전용 레거시 모듈로 완전히 분리 격리함.
- **결정 사항**:
  1. **레거시 패키지 신설 (`plepa_engine/legacy/`)**:
     - `flux_workflows.py`: `build_flux_workflow` 워크플로우 템플릿 분리 보존.
     - `flux_prompt_builder.py`: `assemble_flux_prompt` T5 자연어 빌더 분리 보존.
     - 메인 엔진 모듈(`workflow_templates.py`, `prompt_builder.py`)은 얇은 하위 호환 래퍼로 연결하여 기존 호출 코드의 무결성 유지.
  2. **설정 및 포즈 DB 기본값 SDXL 공식 일원화**:
     - `plepa_engine/config.py`: `POSE_DB_PATH = SDXL_POSE_DB_PATH`로 영구 확정. FLUX 상수는 레거시 섹션으로 주석 격리.
     - `data/legacy/flux_pose_database.json` 아카이브 보존.
     - `scripts/archive/add_gender_tags_flux.py` 이동.
  3. **GUI 및 CLI 정비**:
     - `plepa_gui/components/prompt_inspector.py`: `FLUX [레거시]` 탭으로 명시.
     - `plepa_gui/pages/generate.py`: `SDXL (표준)` 및 `FLUX [레거시]` 드롭다운 정리.
     - `batch_generator.py` 신설 및 `flux_batch_generator.py`를 하위 호환 래퍼로 전환.
- **결과**: SDXL 단일 중심 고속 파이프라인의 가독성과 응집도 극대화 달성, 필요 시 언제든 FLUX를 호출할 수 있는 완전한 안전 격리 완결.

### ADR-54: 에셋 파이프라인 확장 5대 코어 아키텍처 현대화 (2026-10-15)
- **배경**:
  - 도메인 규칙, 신규 로스터/세계관(무협, 판타지, 학원, 스파이 등), 특수 포즈 및 ComfyUI 노드 확장이 가속화됨에 따라 기존 모놀리식 절차적 코드의 5대 구조적 결합도(Coupling)와 유지보수 병목 해소가 요구됨:
    1. `prompt_builder.py`: 절차적 if-else 및 정규식 패치가 단일 함수에 수십 개 직렬 배치되어 세계관 확장 시 사이드 이펙트 위험 증가.
    2. `workflow_templates.py`: 노드 ID(`1`, `14`, `30`) 정적 하드코딩으로 다중 LoRA/ControlNet/Inpaint 동적 확장 한계.
    3. `comfy_client.py`: 이미지 1장 생성마다 반복되는 시스템 상태 폴링, 웹소켓 신규 연결 수립/종료 및 레퍼런스 이미지 무조건 재업로드 오버헤드.
    4. `generation_service.py`: 매직 넘버(48~99) 기반 필터링 및 대규모 배치 생성 시 복구/재시도를 위한 매니페스트 부재.
    5. `models.py`: `apply_profile()`의 인플레이스 객체 속성 덮어쓰기로 인한 장기 구동 GUI 서버 메모리 캐시 오염 리스크.
- **결정 사항**:
  1. **PromptContext & 6대 Mutator 파이프라인 체인 (`plepa_engine/prompt_pipeline.py`)**:
     - `PromptContext` 상태 객체를 6단계 미들웨어 체인(`PoseTagPreparationMutator` ➔ `PositiveAssemblyMutator` ➔ `NegativeBaseMutator` ➔ `DefectDefenseMutator` ➔ `TwoPersonMobMutator` ➔ `SanitizerMutator`)으로 순차 변환.
     - `prompt_builder.py`의 `assemble_sdxl_prompt`는 15줄의 얇은 위임 오케스트레이터로 경량화하여 하위 호환 100% 보장.
  2. **경량 그래프 빌더 도입 (`plepa_engine/graph_builder.py`)**:
     - `WorkflowGraph` 클래스를 신설하여 노드 추가 시 `add_node(class_type, **inputs)`로 동적 ID 발급 및 `graph.out(node_id, slot)` 출력 슬롯 레퍼런스 체이닝 지원.
     - `build_sdxl_workflow` 및 `build_standalone_upscale_workflow`의 노드 하드코딩을 동적 레고 블록 구조로 전면 교체.
  3. **웹소켓 세션 재사용 및 이미지 캐싱 (`plepa_engine/comfy_client.py`)**:
     - `with client.session():` 컨텍스트 매니저를 도입하여 배치 생성 루프 내에서 단일 WebSocket 연결을 유지·재사용.
     - `upload_image()`에 파일 수정 시각(`mtime`) 기반 인메모리 캐시를 적용하여 동일 레퍼런스 이미지의 불필요한 반복 네트워크 전송 0% 달성.
  4. **데이터 주도 필터링 및 원자적 저널링 (`plepa_engine/services/generation_service.py`)**:
     - 매직 넘버 대역(48~99) 판별 로직을 폐기하고 `PoseEntry`의 메타데이터(`section`, `target_gender`, `allowed_rosters`) 기반 데이터 주도형 필터링으로 전환.
     - 배치 생성 시 `projects/{roster}/assets/{prefix}/_batch_manifest.json`에 최종 프롬프트, 시드, 소요 시간, 성공 여부를 원자적 임시 파일 치환 방식으로 기록하여 사후 추적 및 부분 재시도(Retry) 기반 확립.
  5. **불변 팩토리 메서드 도입 (`plepa_engine/models.py`)**:
     - `CharacterConfig.with_profile(profile_name)`을 신설하여 `copy.deepcopy` 기반의 안전한 불변 복제본을 반환. 기존 `apply_profile()`도 내부적으로 원본을 건드리지 않고 필드를 안전 갱신하도록 정비.
- **결과**: Zero-Regression(기존 프롬프트 결과물 100% 일치)을 엄격히 검증 완료하였으며, 대규모 배치 생성 속도 향상, 노드/세계관 확장의 유연성 확보 및 메모리 안정성 극대화 달성.


