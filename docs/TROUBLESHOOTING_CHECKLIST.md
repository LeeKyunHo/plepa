# 🛠️ 플에파(PLEPA) 단계별 작동 체크리스트 및 장애 진단 가이드 (Troubleshooting Checklist)

> **문서 목적**: 시스템 이상이나 이미지 생성 실패, 구도/화질 결함이 발생했을 때, 어느 계층(인프라, 데이터, 프롬프트, 워크플로우, 후처리, GUI)에서 문제가 발생했는지 1분 안에 핀포인트로 파악하고 즉각 조치하기 위한 단일 기준 점검 매뉴얼(SOP)입니다.  
> **적용 대상**: 모든 사용자 및 투입된 Antigravity AI 에이전트.

---

## 🗺️ 1. 한눈에 보는 문제 진단 트리 (Diagnostic Flowchart)

```mermaid
flowchart TD
    Start["⚠️ 이미지 생성 또는 시스템 이상 발생"] --> Q1{"1. ComfyUI 통신 에러인가?<br>(Connection Refused / Port 8188)"}
    
    Q1 -->|"YES"| L1["[계층 1] 인프라 & ComfyUI 점검<br>• run_nvidia_gpu.bat 가동<br>• 8188 포트 점유 해제<br>• 모델 파일명 오타 확인"]
    Q1 -->|"NO"| Q2{"2. 캐릭터/포즈 로드 실패인가?<br>(JSON Decode / KeyError)"}
    
    Q2 -->|"YES"| L2["[계층 2] 데이터 & JSON 무결성 점검<br>• 캐릭터 JSON 필수 필드<br>• 포즈 번호(000~159) 존재 여부<br>• .plepa_backup 복구"]
    Q2 -->|"NO"| Q3{"3. 구도 파괴 / 의상 잔류 / 이염인가?<br>(남성 실종, H씬 옷 안 벗겨짐 등)"}
    
    Q3 -->|"YES"| L3["[계층 3] 프롬프트 조립기 점검<br>• --dry-run으로 프롬프트 출력 확인<br>• 탈의(nude) 의상 스트리핑<br>• 2인 상호작용 solo 태그 충돌 필터"]
    Q3 -->|"NO"| Q4{"4. 화질 저하 / 평면화 / 뭉개짐인가?<br>(Flat, Color Bleeding)"}
    
    Q4 -->|"YES"| L4["[계층 4] 워크플로우 & IP-Adapter 점검<br>• 레퍼런스(IP-Adapter) 꺼짐 확인 (--no_ref)<br>• 샘플러 설정 (Euler / DPM++ 2M Karras)<br>• VRAM 초과 여부"]
    Q4 -->|"NO"| Q5{"5. Face Detailer / 검열 실패인가?"}
    
    Q5 -->|"YES"| L5["[계층 5] 후처리 & 검열 점검<br>• face_yolov8m.pt 감지 여부<br>• dghs-imgutils 성기 검출 마진"]
    Q5 -->|"NO"| L6["[계층 6] 웹 GUI & 작업 관리자 점검<br>• 8080 포트 접속<br>• global_job_manager 작업 중복"]
```

---

## ⚡ 2. 10초 원클릭 긴급 진단 명령어

장애 발생 시 터미널에서 아래 명령어들을 순서대로 실행하여 문제 지점을 즉시 격리합니다:

| 점검 목적 | CLI 명령어 | 정상 기대 결과 |
| :--- | :--- | :--- |
| **전체 무결성 자체 진단** | `python flux_batch_generator.py --test` | `[PASS] 모든 진단 검사 항목을 통과했습니다.` |
| **ComfyUI 포트 연결 점검** | `Test-NetConnection -ComputerName 127.0.0.1 -Port 8188` | `TcpTestSucceeded : True` |
| **프롬프트 조립 점검 (GPU 미사용)** | `python flux_batch_generator.py -r spy -c kzk -p A00 --dry-run` | 조립된 프롬프트 콘솔 출력 |
| **파일 I/O 및 파이프라인 점검** | `python flux_batch_generator.py -r spy -c kzk -p A00 --mock` | 0.001초 만에 더미 WebP 생성 성공 |
| **단위 테스트 전수 검증** | `.\.venv\Scripts\python.exe -m pytest` | `43 passed` |

---

## 📋 3. 계층별 세부 작동 체크리스트

### 🔌 [계층 1] 인프라 & ComfyUI 백엔드 통신 (Infrastructure Layer)
> **역할**: GPU 연산 엔진 및 체크포인트/UNet 로드, WebSocket 통신을 담당하는 최하단 기반 계층.

- [ ] **ComfyUI 가동 상태**: 브라우저에서 `http://127.0.0.1:8188`에 접속 시 정상 화면이 열리는가?
- [ ] **포트 충돌(8188)**: 백그라운드에 좀비 프로세스가 물려있지 않은가?
  - *조치*: `Get-NetTCPConnection -LocalPort 8188 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`
- [ ] **체크포인트 파일 실존**: `ComfyUI/models/checkpoints/` 폴더 내에 지정된 모델 파일(예: `loxsHEXMIX_hexmixV50.safetensors`, `waiIllustriousSDXL_v170.safetensors`, `unholyDesireMixSinister_v90.safetensors`)이 오타 없이 존재하는가?
- [ ] **VRAM 누수/초과**: RTX 4060 Ti(8GB)에서 CUDA Out of Memory 발생 시 모델 캐시 비우기 실행:
  - *조치*: `Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8188/free" -Body '{"unload_models": true, "free_memory": true}' -ContentType "application/json"`

---

### 💾 [계층 2] 데이터 & JSON 스키마 계층 (Data & Schema Layer)
> **역할**: 캐릭터 프로필, 포즈 DB(`data/`), 배경 프리셋의 데이터 무결성을 보장하는 계층.

- [ ] **캐릭터 JSON 구문 검증**: `projects/{roster}/characters/*.json` 파일에 JSON 문법 오류(쉼표 누락, 따옴표 누락)나 필수 필드(`prefix`, `appearance`, `gender`) 누락이 없는가?
- [ ] **포즈 DB 무결성**: `data/sdxl_pose_database.json`, `data/flux_pose_database.json` 및 `data/themes/*.json`에 대상 코드(`000`~`159`, `A00`~`G07`)와 `prompt`, `label`이 올바르게 존재하는가?
- [ ] **프로젝트 전용 배경(`background.json`) 존재 여부**: `projects/{roster}/background.json`이 정의되어 `A00~A32` 및 `000~019`의 `clean background`가 작품 세계관 배경으로 정상 치환되는가?
- [ ] **손상 시 안전 복구**: 파일 손상 발생 시 `.plepa_backup/` 폴더에서 직전 정상 버전 복원이 가능한가?

---

### 🧠 [계층 3] 프롬프트 조립 & 엔진 로직 계층 (Prompt Builder Layer)
> **역할**: 캐릭터 외형 + 포즈 DB + 배경 + 보정 태그를 결합하여 최종 긍정/부정 프롬프트를 만드는 계층.

- [ ] **착의 vs 탈의(H-씬) 스트리핑**:
  - 탈의(`required_outfit: "nude"`) 씬 생성 시 캐릭터 기본 의상 단어(`coat`, `dress`, `qipao`, `vest`, `holster`, `bolero`, `bunny`, `suspenders`, `tights` 등)가 완전히 제거되고 `sdxl_nude_positive`가 정상 채택되었는가?
- [ ] **2인 상호작용 충돌 필터링**:
  - 파트너가 존재하는 포즈에서 캐릭터 기본의 `solo` 태그가 자동으로 제거되었는가?
  - SDXL 네거티브에서 `1boy, male`이 자동 배제되어 남성 파트너가 정상 생성되는가?
- [ ] **헤어/의상 간 색상 이염(Color Bleeding) 및 역방향 보라빛 붕뜸(Reverse Color Cast) 방지**:
  - 남성 모브 태그 주입으로 인해 여주인공의 머리색이 검게 변하지 않도록 포지티브 컬러 앵커링이 작동하는가?
  - 반대로 **흰색/밝은 의상 캐릭터(`kzk` 등)에 유색 헤어 가중치(`lavender`, `purple` 등)를 중복 부여하여 피부와 흰 옷 전체가 보라빛으로 물들지 않았는가?** (단일 헤어 태그 `:1.1`~`:1.15`만 유지하고 `fair porcelain skin, crisp white ...`로 색감 분리)
  - **인접한 유색 조끼(`teal`)나 유색 헤어(`pink`)가 흰 블라우스(`cla`)나 흰 유니폼(`evl`)으로 번지지 않았는가?** (`(crisp pure snow-white ...:1.25)` 앵커링 및 네거티브에 `green shirt, teal shirt, greenish white` 또는 `pink clothes, pink dress` 차단 적용)
- [ ] **전신 구도(`full body, standing`) 배경 스케일 착시(거인화) 및 9등신 왜곡 방지 (`[패치 A-3]`)**:
  - 캐릭터 JSON에 과장된 다리 비율을 유발하는 `long slender limbs` 대신 `balanced body proportions`가 적용되었는가?
  - `background.json`에서 방 층고를 캐릭터 키로 압축시키는 `chandelier`, `ceiling`, `sofa`, `couch`가 제거되고 근접 벽면 + 아웃포커싱(`strong depth of field, heavily blurred background`)이 적용되었는가?
  - `prompt_builder.py`의 `[패치 A-3]`가 전신 스탠딩 포즈에 `(ceiling, chandelier, sofa, couch, armchair, door, doorframe, miniature room, giantess, from below, low angle, overly long legs, tiny head:1.3)` 네거티브를 자동 주입하는가?
- [ ] **캐릭터 이름/헤어 연상 임의 소품(이마 띠·손목 붕대 등) 생성 차단**:
  - `kzk` 등에서 프롬프트에 없는 이마 띠(`headband`)나 손목 붕대(`wrist bandages`)가 생성되지 않도록 포지티브에 `exposed clean forehead, bare wrists`, 네거티브에 `headband, sweatband, bandana, wrist bandages, arm wraps`가 적용되었는가?
- [ ] **무표정(쿠데레) 및 소심형(코베니형) 캐릭터 `A00` 표정 연동**:
  - 캐릭터 JSON에 입을 얼리는 강한 표정 태그 대신 눈매·눈썹 앵커링(`(half-closed eyes:1.1), (straight eyebrows:1.05)` 또는 `(tareme droopy eyes:1.1), (arched eyebrows:1.05)`)과 평문 기질(`kuudere, quiet demeanor` 또는 `shy nervous demeanor`)을 넣었는가?
  - `A00` 기본 스탠딩에서 `prompt_builder.py`가 해당 기질을 감지하여 `gentle smile`을 무표정/소심 표정으로 자동 치환했는가?
- [ ] **커튼 잡기 / 팔 벌리기 제스처 편향 방지**:
  - `background.json`에 `curtains`, `drapes` 등 손으로 잡기 쉬운 근경 사물이 들어있어 캐릭터가 양손으로 커튼을 움켜쥐지 않는가?
  - `A00` 포즈에 `introduction pose` 대신 `natural standing pose`가 적용되어 팔을 부자연스럽게 벌리지 않는가?

---

### ⚙️ [계층 4] 워크플로우 템플릿 & 이미지 생성 I/O 계층 (Workflow & Generation Layer)
> **역할**: 조립된 프롬프트와 파라미터를 ComfyUI 노드 그래프로 묶어 전송하고 WebP 파일로 저장하는 계층.

- [ ] **체크포인트 및 CFG 프로필 일치 여부 (색감 들뜸/네온 과포화 방지)**:
  - CLI/GUI 실행 시 프로젝트 표준 체크포인트(**`loxsHEXMIX_hexmixV50.safetensors`**, **CFG `4.5`**, `euler / normal`, `1024x1536`)가 적용되었는가?
  - *주의: `waiIllustriousSDXL_v170.safetensors`에 높은 CFG(`5.5` 이상)와 `art by raita` + 샹들리에 조명을 결합하면 전체 화면에 강한 보라색/노란색 네온 필터가 낀 것처럼 색감이 붕 뜨는 과포화가 발생함.*
- [ ] **IP-Adapter(레퍼런스) 완전 비활성화 여부**:
  - 기본 생성 시 레퍼런스 노드가 제외되었는가? (`no_ref=True`, `ref_weight=0.0`)
  - *주의: IP-Adapter가 켜져 있으면 2인 씬이나 특수 체위에서 심각한 인체 왜곡 및 텍스처 뭉개짐(Flat) 발생*
- [ ] **출력 디렉터리 권한 및 경로**:
  - `projects/{roster}/assets/{prefix}/` 폴더 생성 및 WebP 저장 권한에 이상이 없는가?
- [ ] **강제 덮어쓰기 플래그**:
  - 기존 파일 교체 시 `--overwrite` (또는 `-f`) 옵션이 부여되었는가?

---

### 🎨 [계층 5] 후처리 & 보정/검열 계층 (Post-Processing & Censor Layer)
> **역할**: Face Detailer 얼굴 보정, 4x 업스케일, 성기 자동 검열을 수행하는 계층.

- [ ] **Face Detailer 얼굴 인식**:
  - `ComfyUI/models/ultralytics/bbox/face_yolov8m.pt` 모델이 정상 로드되어 얼굴 검출 스킵 없이 보정되는가?
- [ ] **2D 성기 자동 검열 (`--censor`)**:
  - 나체/H씬에서 성기 인식 모델(`dghs-imgutils`)이 0.02초 내에 BBox를 잡고 `_censored.webp`를 정상 생성하는가?
  - 무검열 원본 파일이 훼손 없이 온전히 보존되는가?

---

### 🖥️ [계층 6] 웹 GUI & 백그라운드 작업 계층 (Web Studio & Job Layer)
> **역할**: NiceGUI 웹 화면 서빙 및 비동기 작업 스케줄링을 담당하는 최상단 사용자 인터페이스 계층.

- [ ] **웹 서버 가동 여부**: `http://127.0.0.1:8080`이 브라우저에서 정상 열리는가?
- [ ] **전역 작업 관리자 (`global_job_manager`)**:
  - 다른 작업이 이미 실행 중이어서 충돌하지 않는가?
  - 작업 취소 버튼이 정상 반응하여 배치를 안전하게 중단시키는가?
- [ ] **윈도우 탐색기 연동**: 라이트박스의 `PC 폴더 열기` 클릭 시 파일 탐색기 창이 정상 팝업되는가?
- [ ] **새 탭 고화질 뷰어 (`/view_image`)**: WebP 클릭 시 다운로드로 튕기지 않고 브라우저 탭 내에서 1:1 줌 인/아웃이 동작하는가?

---

## 🚨 4. 주요 증상별 원인 및 즉각 조치 빠른 표 (Quick Fix Reference)

| 현상 / 증상 | 근본 원인 | 즉각 조치법 |
| :--- | :--- | :--- |
| **전체적으로 보라빛/노란빛 색감이 강하게 붕 뜸** | 1) `waiIllustriousSDXL` + 높은 CFG(5.5) 과포화<br>2) 흰 옷 캐릭터에 유색 헤어 가중치 중복 부여 | 1) 기본 프로필(`loxsHEXMIX_hexmixV50.safetensors`, CFG `4.5`, `euler/normal`) 사용<br>2) 유색 헤어 태그를 1개로 줄이고 `fair porcelain skin, crisp white ...` 추가 |
| **흰 셔츠/유니폼에 조끼나 머리카락 색(초록빛/핑크빛)이 번짐** | 인접한 `teal` 조끼(`cla`) 또는 `pink` 헤어(`evl`) 토큰이 흰색 의상으로 이염됨 | 흰 의상을 `(crisp pure snow-white ...:1.25)`로 강조하고 `teal` 대신 `slate-navy` 사용 + 네거티브에 `green shirt, greenish white, pink clothes, pink dress` 추가 |
| **전신(`A00`)에서 캐릭터 키가 거인처럼 커 보이고 구도가 이상함** | 배경의 천장(`chandelier`, `ceiling`)·낮은 가구(`sofa`)가 층고를 캐릭터 키로 압축하고 `long slender limbs` + `from below`가 결합됨 | `background.json`에서 `chandelier, sofa` 제거 후 근접 벽면 + 아웃포커싱 사용, 캐릭터에 `balanced body proportions` 적용, `[패치 A-3]` 자동 방어선 확인 |
| **프롬프트에 없는 이마 띠(`headband`)나 손목 붕대(`bandages`)가 생김** | 캐릭터 이름(`kozuka` 등)이나 단발 태그에서 모델이 격투가 소품을 연상함 | 포지티브에 `exposed clean forehead, bare wrists`, 네거티브에 `headband, sweatband, bandana, wrist bandages, arm wraps` 추가 |
| **`A00`에서 캐릭터가 자꾸 양손으로 커튼을 잡음** | 배경의 `curtains` 태그와 `introduction pose`의 결합 편향 | `background.json`에서 `curtains` 제거 및 `A00`을 `natural standing pose`로 유지 |
| **무표정/소심 캐릭터가 0번(`A00`)에서 활짝 웃음** | `A00` 포즈의 기본 `gentle smile` 태그 강제 적용 | 캐릭터 JSON에 눈매·눈썹 고정 + `kuudere, quiet demeanor` 또는 `shy nervous demeanor` 명시 |
| **`art by raita` 적용 시 이마에 열쇠구멍/보석 생성** | 작가 화풍 학습 데이터의 이마 장식 편향 | `BREAK` 앞단에 `clean smooth forehead, neat hairline`, 네거티브에 `forehead mark, keyhole` 추가 |
| **흰 셔츠/블라우스 위로 브라 컵이 하얗게 비침** | `white blouse` 또는 `sheer` 태그의 속옷 투과 현상 | `unbuttoned white blouse, deep cleavage`로 바꾸고 네거티브에 `exposed bra, exposed bra cup, see-through` 추가 |
| **화질이 뭉개지고 평면화(Flat)됨** | IP-Adapter(레퍼런스) 과포화 간섭 | `--no_ref` 기본값 확인 |
| **남성 파트너가 생성되지 않거나 기괴함** | 캐릭터 태그의 `solo` 및 네거티브 `1boy` 충돌 | `prompt_builder.py`의 2인 감지 자동 필터 가동 확인 |
| **남성이 2명 이상 생성됨 (2boys 결함)** | 포즈 프롬프트와 모브 프롬프트의 중복 `1boy` 주입 | 포즈 태그에 `1boy` 포함 시 `mob_positive` 주입 차단 로직 확인 |
| **H씬에서 옷이나 소품이 벗겨지지 않음** | 의상 가중치 초과(`:1.15`) 또는 손 소품 고정 | 의상 본체를 가중치 `1.0` 평문으로 낮추고 손 소품(`syringe`, `holder` 등) 제거 |
| **여캐 머리색이 검게 오염됨 (Color Bleeding)** | 남성 모브의 `short black hair` 태그 누출 | 여캐 포지티브에 헤어 컬러 앵커링 주입 |
| **ComfyUI 작업 큐 전송 시 HTTP 400 에러** | 체크포인트 파일명 오타 (언더스코어 누락 등) | `checkpoint` 이름을 ComfyUI 실제 파일명과 일치시킴 |
| **GUI에서 "이미 실행 중" 알림 발생** | 이전 백그라운드 배치가 아직 미종료 상태 | `작업 취소` 버튼 클릭 또는 잠시 대기 후 재시도 |
