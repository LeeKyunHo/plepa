# 🛠️ 플에파(PLEPA) 운영 및 트러블슈팅 런북 (RUNBOOK)

> **목적**: 개발자·에이전트·다중 PC 이식 환경에서 플에파를 에러 없이 즉시 가동, 검증, 배포하기 위한 **실전 운영 절차서 (How-To)**입니다.

---

## 1. 환경 구축 & 필수 모델 체크리스트 (Fresh Setup)

### 1.1 Python 가상환경 & 의존성 검증
```powershell
cd C:\Users\rbsgh\plepa
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe batch_generator.py --test
```

### 1.2 ComfyUI 필수 모델 & 확장팩 (`127.0.0.1:8188`)
* **체크포인트 (`ComfyUI/models/checkpoints/`)**:
  - 기본 SSOT: `UnholyDesireMixSinisterAesthetic_V9_Illustrious.safetensors` (`CFG 4.0`, `Steps 28`, `dpmpp_2m / karras`)
  - 선택 프리셋: `waiIllustriousSDXL_v170.safetensors`, `loxsHEXMIX_hexmixV50.safetensors`, `ponyDiffusionV6XL.safetensors`
* **FaceDetailer / HandDetailer (`ComfyUI/models/ultralytics/bbox/`)**:
  - `face_yolov8m.pt` (필수), `hand_yolov8s.pt` (`--hand-detailer` 시)
* **Upscaler (`ComfyUI/models/upscale_models/`)**: `4x-UltraSharp.pth`
* **IP-Adapter (`--use-ref` 시)**: `ip-adapter-plus_sdxl_vit-h.safetensors` + `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`
* **필수 커스텀 노드**: `ComfyUI-Impact-Pack`, `ComfyUI_IPAdapter_plus` (사전 점검: `--check-comfy`)
* **로컬 Phase P2.5 검열 모델 (`plepa/models/` & 루트)**:
  - `models/censor_seg.pt` (Hold-out 클린 학습 YOLO11s-seg) + `sam2.1_s.pt` (자동 다운로드/로드) + `deepghs/anime_censor_detection`

---

## 2. 표준 운영 파이프라인 (Day-to-Day Operation)

### 2.1 작업 전·후 무결성 Gate (오프라인 필수 검증)
```powershell
# 1. 전체 단위·계약 테스트 (로컬 에셋 무변경 세션 가드 + AST 래칫 포함)
.\.venv\Scripts\python.exe -m pytest -q

# 2. 주요 활성 로스터 7단계 사전 점검 (착의/누드/테마/배경/POSE_MAPPING.md 동기화)
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r campus
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r oto
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r spy

# 3. Gen-IT v2.2 완성본 무결성 검증
.\.venv\Scripts\python.exe scripts/validate_genit_work.py --force
```

### 2.2 배치 생성 · 검열 표준 실행
```powershell
# 드라이런으로 프롬프트 및 파일명 점검 (디스크/매니페스트 무접촉)
.\.venv\Scripts\python.exe batch_generator.py -r campus -c aya -p sample10 --dry-run

# 실서버 생성 (하이브리드 해상도: 000~024 832x1216, 025+ 1216x832 / white_silhouette 검열)
.\.venv\Scripts\python.exe batch_generator.py -r campus -c aya -p sample10 --censor --deterministic-pose-seed

# 기존 원본({_origin}) 유지한 채 검열 마스크만 0.2초 일괄 재적용
.\.venv\Scripts\python.exe batch_generator.py -r oto --all-chars -p all --censor-only

# 에셋 정합성·2섹터 구조 전수 감사
.\.venv\Scripts\python.exe scripts/audit_asset_alignment.py --roster campus
.\.venv\Scripts\python.exe scripts/audit_sector_assets.py --roster campus
```

### 2.3 웹 스튜디오 & 원격 모바일 검수 서버 운용
```powershell
# A. PC 로컬 NiceGUI 스튜디오 (8대 탭 + 수동 터치 덧칠 + Genit 1024x1536 일괄 내보내기)
.\.venv\Scripts\python.exe -m plepa_gui.app

# B. 원격 스마트폰 접속 (8080 기동 + PLEPA_MOBILE_TOKEN 발급 + Cloudflare Tunnel URL 출력)
.\.venv\Scripts\python.exe scripts/start_remote.py

# C. (은퇴 · 아카이브) 구형 `:8085` 뷰어 — 정식 대체 경로는 위 B(`start_remote.py` + `/mobile`)를 사용하세요.
.\.venv\Scripts\python.exe scripts/archive/generate_inspection_viewer.py
.\.venv\Scripts\python.exe scripts/archive/serve_benchmark_mobile.py
```

### 2.4 Gemini 노트북 상시 싱크 (`scripts/export_context.py`)
```powershell
# context_snapshot/ 내 고정 5개 파일 (00~30 + 50_REFACTORING_PLAN.md) 자동 덮어쓰기 & 구파일 정리
.\.venv\Scripts\python.exe scripts/export_context.py
```
- **노트북 워크플로우**: `context_snapshot/` 5개 고정 파일을 NotebookLM/Gemini 소스로 유지하면, 덮어쓰기 후 소스 새로고침만으로 전체 코드맵·헌법·Wave 리팩토링 현황이 즉시 동기화됩니다.
- **형제 레포(`kiro`) 안내**: [`scripts/sync_to_kiro.py`](../scripts/sync_to_kiro.py)는 최신 Kiro(Wave 0~4 / P1~P4) 덮어쓰기 파손을 막기 위해 기본 실행이 차단(`exit 2`, `--force-unsafe` 전용)되어 있습니다. 필요한 기능은 수동 어댑팅으로 이식합니다.

---

## 3. 자주 발생하는 장애 대응 (Troubleshooting)

| 증상 | 근본 원인 | 즉시 조치 명령어 / 해법 |
| :--- | :--- | :--- |
| **`WinError 32` / 탐색기 파일 잠금** | Windows COM Surrogate(`dllhost.exe`)의 WebP 썸네일 점유 | `taskkill /f /im dllhost.exe` |
| **포트 `8080` 또는 `8085` 충돌** | 백그라운드 웹 서버/터널 프로세스 잔존 | `Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue \| ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }` |
| **원격 `/mobile` 401/403 오류** | `PLEPA_MOBILE_TOKEN` 누락 또는 잘못된 Referer/Origin | `scripts/start_remote.py` 콘솔에 출력된 `?token=...` 전체 하이퍼링크로 재접속 |
| **검열 과다/누락 (P2.5 동결 이후)** | `ADR-99` 기준 임계치 동결 정책(예외 케이스) | 웹 `/gallery`·`/mobile`의 **`✏️ 터치 덧칠`**(0.5초 마스킹/지우개) 또는 **`🔄 원본`** 복원 사용 (임계치 임의 튜닝 금지) |
| **모브 남캐 눈/얼굴 노출 또는 헤어 이염** | `mob_tier 1/3` 또는 `events.json` 포즈 자체 음영/차단 누락 | [`캐릭터_포즈_제작_규칙.md`](캐릭터_포즈_제작_규칙.md)의 뒤통수·상안부 그림자 음영 3종 세트 직접 명기 (`bald`/`faceless`/앞머리 가림 금지) |
| **계약 테스트(`test_contract_guards.py`) 실패** | 모듈 `>350줄` / 함수 `>120줄` 초과 또는 레이어/CLI-GUI 불일치 | 함수 분리로 제한 준수 + `GENERATION_OPTION_SPECS`/`batch_generator.py` 4곳 삼위일체 동기화 |
| **`scripts/export_context.py` 후 `docs/AI_HANDOVER_GUIDE.md` 반영 누락** | 구 `context_snapshot/` 잔여 파일 존재 | Wave 2 이후 자동 정리됨 (`00_README_FOR_AI`, `10_TIER1`, `20_TIER2`, `30_TIER3`, `50_REFACTORING_PLAN`) |
