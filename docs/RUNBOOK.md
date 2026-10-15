# 📘 [PLEPA Operations Runbook] 운영 및 긴급 조치 런북

> **문서 목적**: ComfyUI 로컬 서버 관리, 이미지 에셋 배치 생성 파이프라인 가동, VRAM 부족(OOM) 대응 등 **실무 운영 명령어와 긴급 트러블슈팅 매뉴얼**을 제공합니다.  
> **기반 사양**: Windows 11, Python 3.13, NVIDIA RTX 4060 Ti 8GB + 48GB System RAM, ComfyUI (포트 `8188`).

---

## 🚀 1. ComfyUI 서버 기동 및 상태 확인

### 1.1 서버 헬스체크 (PowerShell)
ComfyUI 서버가 정상 응답하는지 확인합니다:
```powershell
# 서버 상태 및 VRAM 정보 확인
Invoke-RestMethod -Uri "http://127.0.0.1:8188/system_stats" | ConvertTo-Json -Depth 3
```

### 1.2 서버 기동 (미실행 시)
ComfyUI 설치 폴더에서 실행:
```powershell
# 기본 실행 커맨드 (LowVRAM / MedVRAM 자동 최적화 모드)
python main.py --port 8188 --preview-method auto
```

---

## ⚡ 2. 에셋 생성 실전 명령어 (flux_batch_generator.py)

> 💡 **기본 엔진 안내 (Default: SDXL)**:  
> 2026-10-05 부로 **SDXL (`meichiILIghtMIXV1_meichiILUstMIXV1.safetensors`)**이 기본 엔진으로 자동 적용됩니다.  
> 별도의 `--engine` 옵션을 지정하지 않아도 장당 15초의 고속 2D 미소녀 애니 셀화 모드로 생성되며, FLUX 모드가 필요할 때만 `--engine flux`를 명시합니다.

### 2.1 단일 캐릭터 포즈 테스트 생성
신규 캐릭터의 얼굴과 의상 무결성을 단 1장으로 빠르게 검증할 때 사용합니다:
```powershell
# 1) man 로스터의 cyr 캐릭터 기본 포즈(000) 1장 생성
python flux_batch_generator.py -r man -c cyr -p 000

# 2) maid 로스터의 hana 캐릭터 단일 생성
python flux_batch_generator.py -r maid -c hana -p 000
```

### 2.2 특정 결함 포즈 강제 덮어쓰기 재생성 (`--overwrite`)
프롬프트를 수정한 후 기존 파일을 교체할 때 사용합니다:
```powershell
# 포즈 014(유혹) 및 019(키스)만 지정하여 강제 재생성
python flux_batch_generator.py -r man -c all -p 014,019 --overwrite
```

### 2.3 섹션별 배치 생성
```powershell
# 1) 감정/표정 에셋 20종만 순차 생성 (000~019)
python flux_batch_generator.py -r maid -c hana -p emotions

# 2) 일상 상호작용 포즈 20종 생성 (020~039)
python flux_batch_generator.py -r maid -c hana -p poses
```

### 2.4 파이프라인 무결성 사전 검증 (Dry-Run / Mock)
ComfyUI GPU를 쓰지 않고 프롬프트 조립 결과와 파일 I/O를 0.01초 만에 검증합니다:
```powershell
# 1) 프롬프트 조립 및 파일명 점검 (GPU 미사용)
python flux_batch_generator.py -r maid -c hana -p 000..005 --dry-run

# 2) 가상 더미 WebP 생성으로 전체 I/O 무결성 검증
python flux_batch_generator.py -r maid -c all -p 000 --mock
```

### 2.5 에셋 파일명 형식 선택 (`--naming`)
- 기본값: `hybrid` (`prefix_000_라벨.webp` 형식으로 생성하여 탐색기 정렬 및 한글 직관성 동시 확보)
```powershell
# 1) 하이브리드 표준형 (기본 권장값)
python flux_batch_generator.py -r maid -c han -p 000 --naming hybrid
# 결과: han_000_평상.webp

# 2) 순수 한글형 (간결성)
python flux_batch_generator.py -r maid -c han -p 000 --naming label
# 결과: han_평상.webp

# 3) 기존 번호형 (Kiro 3자리 번호 하위 호환)
python flux_batch_generator.py -r maid -c han -p 000 --naming code
# 결과: han_000.webp
```

### 2.6 2D 일러스트 자동 검열 (`--censor`)
- 나체/성인 씬 생성 시 무검열 원본(`assets/{prefix}/`)과 함께 대등한 위치의 독립 폴더(`censor_{prefix}/`)에 화이트 실루엣 검열본을 1:1 동일한 파일명으로 보존합니다.
- H-씬(오토코노코 포함)에만 자동 적용되며, 일반 착의 일상 씬은 자동 스킵됩니다.
```powershell
# 1) 화이트 실루엣 (기본 표준값: MobileSAM 기반 외곽선 곡률 100% 보존 및 순백색 #FFFFFF 채우기)
python batch_generator.py -c aya -p 055,065,068 --censor

# 2) 블랙 실루엣 (순수 검은색 #000000 외곽선 실루엣)
python batch_generator.py -c aya -p 065 --censor --censor-style silhouette

# 3) 와이드 솔리드 바 (18% 적응형 캡슐 마진)
python batch_generator.py -r maid -c ren,han -p 144,052 --censor --censor-style bar

# 4) 그림자 실루엣 (형태 윤곽선 보존 및 내부 선화 디테일 흑회색 음영 덮개)
python batch_generator.py -r maid -c ren,han -p 144,052 --censor --censor-style shadow
```

### 2.7 기존 생성 에셋 초고속 소급 검열 (`--censor-only`)
- ComfyUI GPU 호출 없이 이미 디스크에 생성된 이미지들을 0.2초 만에 스캔하여 `censor_{prefix}/` 폴더로 검열본만 일괄 생성합니다:
```powershell
# aya 캐릭터의 전체 에셋 중 H-씬만 선별하여 즉시 검열본 추출
python batch_generator.py -c aya -p all --censor-only
```

### 2.8 Auto-QC 결함 자동 감지 및 리롤 루프
- `imgutils.detect` 초고속 AI 감지기로 인원수 초과(1인 씬 2명 이상, 2인 씬 3명 이상), 손 증식(3개/5개 이상), 남성 얼굴 노출 등을 감지하여 자동으로 새 랜덤 시드로 재시도합니다 (기본 3회):
```powershell
# 1) 기본 생성 (Auto-QC 자동 가동, 최대 3회 재시도)
python batch_generator.py -c aya -p 034,055

# 2) 최대 재시도 횟수 상향
python batch_generator.py -c aya -p 034 --max-retries 5

# 3) Auto-QC 비활성화 (순수 1회 강제 생성)
python batch_generator.py -c aya -p 034 --no-qc
```

### 2.9 레퍼런스(IP-Adapter) 동작 제어 (`--no_ref` / `--use-ref`)
- **기본값**: **비활성화 (`no_ref=True`)**. ComfyUI IP-Adapter로 인한 형태 왜곡, 색상 번짐, 평면화(Flat)를 방지하고 순수 체크포인트 본연의 고화질 디테일을 보장합니다.
```powershell
# 1) 기본 생성 (IP-Adapter 없이 순수 고화질 프롬프트 생성 - 기본 동작)
python flux_batch_generator.py -r hey -c mal -p 034

# 2) 레퍼런스 강제 활성화가 필요할 때 (--use-ref)
python flux_batch_generator.py -r hey -c mal -p 000 --use-ref --ref_weight 0.4
```

### 2.10 Face Detailer 제어 (`--no-face-detailer`)
- **기본 동작**: 자동 활성화 (SEGS Ordered Filter 훅을 통해 화면 내 면적 1위 얼굴만 단독 필터링하여 여주인공만 고속 보정).
- 포즈 구도 테스트나 초고속 초안 생성(장당 10~11초)을 위해 Face Detailer를 끄고자 할 때 사용:
```powershell
python batch_generator.py -c aya -p 034 --no-face-detailer
```

### 2.9 사후 단독 4K AI 초해상화 (`plepa_upscaler.py`)
- 이미 생성이 완료된 기존 WebP 이미지를 디퓨전 재연산 없이 순수 AI 초해상화 모델(`4x-UltraSharp.pth`)로 2~4초 만에 `4096x6144` 초고화질로 단독 업스케일합니다.
- 구도, 표정, 손가락 왜곡 0% 무손실 보존.
```powershell
# 1) 특정 이미지 파일 단독 4K 업스케일 (기본: _4k.webp 접미사로 별도 생성)
python plepa_upscaler.py -i "projects/hey/assets/mal/mal_034_가슴파묻힘.webp"

# 2) 특정 캐릭터의 특정 포즈 에셋 업스케일
python plepa_upscaler.py -r hey -c mal -p 034

# 3) 기존 원본 파일을 4K 화질로 직접 덮어쓰기 교체 (-f / --overwrite)
python plepa_upscaler.py -r hey -c mal -p 034 --overwrite

# 4) 웹 GUI 라이트박스에서 원클릭 업스케일:
#    http://localhost:8080/gallery ➔ 이미지 클릭 ➔ 상단 [✨ 4K AI 업스케일] 버튼 클릭
```

### 2.9 다이내믹 의상 스왑 및 확장 테마 팩 생성 (`-p D`, `-p swimsuit`)
- 캐릭터의 외모(얼굴/헤어/체형)는 온전히 보존한 채, 기존 교복을 완전 박멸하고 수영복/바니걸 등 테마 의상으로 자동 갈아입혀 생성합니다.
- `themes/` 또는 `projects/{roster}/themes/`의 JSON 테마 팩을 자동 로드합니다.
```powershell
# 1) 특정 캐릭터의 수영복 테마(D01~D07) 7종 일괄 생성
python flux_batch_generator.py -r hey -c mal -p D

# 2) 수영복 특정 포즈 단일 생성 (D01 수영복전신)
python flux_batch_generator.py -r hey -c mal -p D01

# 3) 사전 점검 (GPU 미사용 프롬프트 및 의상 스왑 확인)
python flux_batch_generator.py -r hey -c mal -p D --dry-run
```

---

## 🚨 3. 긴급 장애 조치 매뉴얼 (Emergency Troubleshooting)

> 💡 **심층 계층별 진단 가이드**: 시스템 전체 6대 기능 계층별 세부 진단 트리 및 체크리스트는 **[`TROUBLESHOOTING_CHECKLIST.md`](TROUBLESHOOTING_CHECKLIST.md)**를 참조하십시오.

### 3.0 원클릭 10초 긴급 무결성 점검
```powershell
# 1) 전체 시스템 무결성 자체 진단 (FLUX/SDXL 포즈 DB, 프롬프트 조립, 워크플로우 전수 검사)
python flux_batch_generator.py --test

# 2) ComfyUI 통신 포트 상태 점검
Test-NetConnection -ComputerName 127.0.0.1 -Port 8188

# 3) GPU 미사용 프롬프트 출력 점검
python flux_batch_generator.py -r hey -c mal -p 034 --dry-run
```

### 3.1 VRAM 부족 에러 (CUDA Out of Memory) 발생 시
RTX 4060 Ti 8GB 환경에서 고해상도 생성 중 VRAM이 부족할 때 조치법:
1. **해상도 강제 조정**: 기본 `896x1152`를 `--width 768 --height 1024`로 낮춰 실행.
2. **LoRA 또는 업스케일러 일시 비활성화**:
   ```powershell
   python flux_batch_generator.py -r maid -c hana -p 000 --no_ref
   ```
3. **ComfyUI 모델 캐시 비우기 (메모리 해제)**:
   ```powershell
   Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8188/free" -Body '{"unload_models": true, "free_memory": true}' -ContentType "application/json"
   ```

### 3.2 포트 충돌 또는 프로세스 먹통 시
8188 포트가 좀비 프로세스에 물려 있을 때 강제 종료:
```powershell
# 8188 포트를 점유 중인 프로세스 PID 확인 및 강제 종료
Get-NetTCPConnection -LocalPort 8188 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### 3.3 Face Detailer 얼굴 미검출 시
`face_yolov8n.pt`가 인식을 못 하고 스킵될 때:
- `projects/{roster}/characters/{prefix}.json`의 얼굴 묘사 태그가 너무 어둡거나 가려졌는지 확인.
- `--face-detailer` 옵션 플래그가 켜져 있는지 확인.
