# 플에파 (PLEPA: Flux Asset Pipeline)

> **플럭스(FLUX.1 [dev]) 기반 초고화질 캐릭터 챗봇 에셋 배치 생성 파이프라인**  
> ComfyUI 로컬 API와 연동하여 80종의 고품질 캐릭터 에셋을 자동 생성하고 얼굴 정밀 보정(Face Detailer) 및 업스케일, 젠잇(Gen-IT) 마크다운 자동 조립까지 한 번에 수행합니다.

---

## 🚀 빠른 시작 (Quick Start)

### 1. ComfyUI 환경 준비
본 파이프라인은 로컬에서 구동 중인 ComfyUI(`http://127.0.0.1:8188`)와 통신합니다.

1. **ComfyUI 포터블 다운로드**: [ComfyUI GitHub Releases](https://github.com/comfyanonymous/ComfyUI/releases)에서 `ComfyUI_windows_portable_nvidia.7z` 다운로드 후 압축 해제.
2. **필수 모델 다운로드 & 배치**:
   - **GGUF 모델**: [`flux1-dev-Q5_K_S.gguf`](https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-Q5_K_S.gguf) ➡️ `ComfyUI/models/unet/`
   - **T5 인코더**: [`t5xxl_fp8_e4m3fn.safetensors`](https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors) ➡️ `ComfyUI/models/clip/`
   - **CLIP-L 인코더**: [`clip_l.safetensors`](https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors) ➡️ `ComfyUI/models/clip/`
   - **VAE**: [`ae.safetensors`](https://huggingface.co/ffxvs/vae-flux/resolve/main/ae.safetensors) ➡️ `ComfyUI/models/vae/`
   - **업스케일러**: [`4x-UltraSharp.pth`](https://huggingface.co/lokCX/4x-Ultrasharp/resolve/main/4x-UltraSharp.pth) ➡️ `ComfyUI/models/upscale_models/`
3. **필수 확장 노드 (Custom Nodes)**:
   - `ComfyUI-Manager`
   - `ComfyUI-GGUF` (GGUF 모델 구동용)
   - `ComfyUI-Impact-Pack` (얼굴 자동 초정밀 보정 Face Detailer용)

### 2. ComfyUI 실행
`ComfyUI_windows_portable/run_nvidia_gpu.bat`를 실행하여 `127.0.0.1:8188` 포트를 대기 상태로 둡니다.

### 3. 파이프라인 실행
```bash
# 가상환경 활성화 (선택) 및 종속성 설치
pip install -r requirements.txt

# 기본 캐릭터 전체(80종) 생성
python flux_batch_generator.py -c sample_character -p all

# 특정 번호 대역만 생성 (예: 감정 씬 0~19번)
python flux_batch_generator.py -c sample_character -p emotions
```

---

## 📂 프로젝트 구조

```text
plepa/
├── flux_batch_generator.py      # 플에파 메인 실행 CLI
├── flux_pose_database.json      # 플럭스 전용 80종 영문 서술형 자연어 포즈 DB
├── plepa_engine/                # 플에파 전용 핵심 엔진
│   ├── config.py                # ComfyUI API 주소, 해상도, 스텝 설정
│   ├── comfy_client.py          # 비동기 ComfyUI 웹소켓/REST 클라이언트
│   ├── prompt_builder.py        # 서술형 영문 자연어 프롬프트 조합기
│   ├── workflow_templates.py    # GGUF + Face Detailer 워크플로우 템플릿
│   └── reporter.py              # Gen-IT 연동 마크다운 조립 및 결과 리포트
├── projects/                    # 로스터 및 캐릭터 저장소
│   └── default/
│       ├── characters/          # 캐릭터 정의 JSON
│       └── assets_flux/         # 생성된 WebP 이미지 결과물
├── GEMINI.md                    # 에이전트 지침
└── AI_HANDOVER_GUIDE.md         # 개발 히스토리 및 AI 인계서
```

---

## 🛠 권장 하드웨어 사양
- **GPU**: NVIDIA RTX 3060 이상 (VRAM 8GB 이상 권장)
- **RAM**: 32GB ~ 48GB 이상 (GGUF 모델 및 T5 텍스트 인코더 오프로딩 지원)
- **저장장치**: 고속 NVMe SSD (모델 빠른 로딩용)
