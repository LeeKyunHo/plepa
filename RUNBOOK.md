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

### 2.6 2D 일러스트 자동 성기 검열 (`--censor`)
- 나체/성인 씬 생성 시 무검열 원본과 함께 상업 동인 표준 검열본(`*_censored.webp`)을 동시 보존합니다.
```powershell
# 1) 와이드 솔리드 바 (기본 권장값: 18% 적응형 캡슐 마진으로 100% 누수 차단 및 인체 곡선 보존)
python flux_batch_generator.py -r maid -c ren,han -p 144,052 --censor --censor-style bar

# 2) 그림자 실루엣 (형태 윤곽선 보존 및 내부 선화 디테일 흑회색 음영 덮개)
python flux_batch_generator.py -r maid -c ren,han -p 144,052 --censor --censor-style shadow

# 3) 격자 모자이크 (클래식 픽셀레이션)
python flux_batch_generator.py -r maid -c ren,han -p 144,052 --censor --censor-style mosaic

# 4) 검열 부위 지정 (--censor-targets {genital, penis, pussy, all})
python flux_batch_generator.py -r maid -c han -p 044,052 --censor --censor-targets genital
```

### 2.7 레퍼런스(IP-Adapter) 동작 제어 (`--no_ref` / `--use-ref`)
- **기본값**: **비활성화 (`no_ref=True`)**. ComfyUI IP-Adapter로 인한 형태 왜곡, 색상 번짐, 평면화(Flat)를 방지하고 순수 체크포인트 본연의 고화질 디테일을 보장합니다.
```powershell
# 1) 기본 생성 (IP-Adapter 없이 순수 고화질 프롬프트 생성 - 기본 동작)
python flux_batch_generator.py -r hey -c mal -p 034

# 2) 레퍼런스 강제 활성화가 필요할 때 (--use-ref)
python flux_batch_generator.py -r hey -c mal -p 000 --use-ref --ref_weight 0.4
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
