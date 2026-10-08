"""
ComfyUI 서버 상태 및 준비 사항 체크
실제 생성 전에 필수 노드/모델이 준비되었는지 확인
"""

import sys
from plepa_engine.comfy_client import ComfyClient
from plepa_engine.config import COMFY_HOST

def check_comfy_status():
    """ComfyUI 연결 및 준비 상태 확인"""
    
    print("=" * 70)
    print("  ComfyUI 서버 상태 체크")
    print("=" * 70)
    
    client = ComfyClient(host=COMFY_HOST)
    
    # 1. 연결 체크
    print(f"\n[1] 서버 연결 확인: {COMFY_HOST}")
    if client.check_connection():
        print("  ✅ ComfyUI 서버 정상 작동 중")
    else:
        print("  ❌ ComfyUI 서버 연결 실패")
        print("\n해결 방법:")
        print("  1. ComfyUI 폴더에서 run_nvidia_gpu.bat 실행")
        print("  2. 브라우저에서 http://127.0.0.1:8188 접속 확인")
        print("  3. 방화벽 설정 확인")
        return 1
    
    # 2. 필수 체크포인트 확인
    print("\n[2] SDXL 체크포인트 확인")
    print("  📂 ComfyUI/models/checkpoints/ 폴더에 다음 파일 필요:")
    print("     - unholyDesireMixSinister_v90.safetensors (또는 다른 SDXL 체크포인트)")
    print("  ℹ️  자동 확인 불가 - 수동으로 확인해주세요")
    
    # 3. IP-Adapter 모델 확인
    print("\n[3] IP-Adapter 모델 확인")
    print("  📂 ComfyUI/models/ipadapter/ 폴더에 필요:")
    print("     - ip-adapter-plus_sdxl_vit-h.safetensors")
    print("  📂 ComfyUI/models/clip_vision/ 폴더에 필요:")
    print("     - CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")
    print("  ℹ️  자동 확인 불가 - 수동으로 확인해주세요")
    
    # 4. 필수 커스텀 노드 확인
    print("\n[4] 필수 커스텀 노드")
    print("  📂 ComfyUI/custom_nodes/ 폴더에 필요:")
    print("     - ComfyUI_IPAdapter_plus (IP-Adapter)")
    print("     - comfyui_controlnet_aux (ControlNet)")
    print("  ℹ️  자동 확인 불가 - 수동으로 확인해주세요")
    
    # 5. 업스케일러 (선택)
    print("\n[5] 업스케일 모델 (선택사항)")
    print("  📂 ComfyUI/models/upscale_models/ 폴더:")
    print("     - 4x-UltraSharp.pth (권장)")
    print("  ℹ️  --upscale 옵션 사용 시 필요")
    
    print("\n" + "=" * 70)
    print("  상태 체크 완료")
    print("=" * 70)
    print("\n준비가 완료되었으면 다음 명령으로 테스트를 시작하세요:")
    print("  python flux_batch_generator.py -c sample_character -p 000 --engine sdxl --dry-run")
    print("  (dry-run으로 프롬프트 확인 후 실제 생성)")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(check_comfy_status())
