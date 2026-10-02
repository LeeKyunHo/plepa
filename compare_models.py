"""
compare_models.py
3대 SDXL 모델(Unholy, HexMix, Meichi) 간 화풍 및 퀄리티 비교 벤치마크 생성기.
- 대상 포즈: 038, 039, 057, 059
- 포즈별 동일 시드 고정으로 완벽한 1:1 비교
- 결과 파일명: {model_prefix}_{pose_code}.webp (예: unh_038.webp, lox_038.webp, mei_038.webp)
- 저장 위치: projects/don/assets/model_comparison/
"""

import json
import sys
import time
from pathlib import Path

from plepa_engine.comfy_client import ComfyClient, ComfyClientError
from plepa_engine.config import (
    DEFAULT_REF_WEIGHT,
    DEFAULT_SDXL_CFG,
    DEFAULT_SDXL_HEIGHT,
    DEFAULT_SDXL_SAMPLER,
    DEFAULT_SDXL_SCHEDULER,
    DEFAULT_SDXL_STEPS,
    DEFAULT_SDXL_WIDTH,
    PROJECTS_DIR,
    configure_stdio,
)
from plepa_engine.models import CharacterConfig
from plepa_engine.prompt_builder import assemble_sdxl_prompt
from plepa_engine.reporter import open_in_explorer
from plepa_engine.workflow_templates import build_sdxl_workflow
from flux_batch_generator import find_reference_image, load_pose_db

configure_stdio()

MODELS = [
    {
        "prefix": "unh",
        "name": "Unholy 9.0",
        "ckpt": "unholyDesireMixSinister_v90.safetensors",
    },
    {
        "prefix": "lox",
        "name": "HexMix V5",
        "ckpt": "loxsHEXMIX_hexmixV50.safetensors",
    },
    {
        "prefix": "mei",
        "name": "Meichi IL-ust MIX V1",
        "ckpt": "meichiILIghtMIXV1_meichiILUstMIXV1.safetensors",
    },
]

TARGET_POSES = ["038", "039", "057", "059"]

# 포즈별 고정 시드 (동일 구도에서 모델별 화풍/광원/피부질감 1:1 비교용)
POSE_SEEDS = {
    "038": 2026038,
    "039": 2026039,
    "057": 2026057,
    "059": 2026059,
}


def main():
    roster = "don"
    char_prefix = "bjh"
    output_dir = PROJECTS_DIR / roster / "assets" / "model_comparison"
    output_dir.mkdir(parents=True, exist_ok=True)

    char_json_path = PROJECTS_DIR / roster / "characters" / f"{char_prefix}.json"
    if not char_json_path.exists():
        print(f"[오류] 캐릭터 파일을 찾을 수 없습니다: {char_json_path}")
        return 1

    with open(char_json_path, encoding="utf-8") as f:
        char_data = json.load(f)
    char = CharacterConfig.from_dict(char_data, file_path=char_json_path)

    pose_db = load_pose_db(engine="sdxl")
    client = ComfyClient()

    if not client.check_connection():
        print("[오류] ComfyUI 서버(127.0.0.1:8188)에 연결할 수 없습니다.")
        print("ComfyUI 폴더의 'run_nvidia_gpu.bat'를 먼저 실행해 주십시오.")
        return 1

    # 레퍼런스 이미지 업로드
    ref_file_name = None
    ref_weight = getattr(char, "ref_weight", DEFAULT_REF_WEIGHT)
    ref_path = find_reference_image(char.prefix, roster)
    if ref_path and ref_path.exists():
        try:
            ref_file_name = client.upload_image(ref_path)
            print(f"✔ IP-Adapter 레퍼런스 등록: {ref_path.name} (가중치: {ref_weight:.2f})")
        except Exception as e:
            print(f"[경고] 레퍼런스 업로드 실패: {e}")
            ref_file_name = None

    print("\n" + "=" * 68)
    print("  [플에파] 3대 SDXL 모델 비교 벤치마크 테스트 (Model Shootout)")
    print(f"  대상 캐릭터: {char.name} ({char.prefix})")
    print(f"  대상 모델: {', '.join(m['prefix'] + '(' + m['name'] + ')' for m in MODELS)}")
    print(f"  비교 포즈: {', '.join(TARGET_POSES)} (총 {len(MODELS) * len(TARGET_POSES)}개 에셋)")
    print("  옵션: Face Detailer=활성, 4x Upscale=활성, 포즈별 고정 시드 적용")
    print(f"  저장 폴더: {output_dir}")
    print("=" * 68 + "\n")

    total_start = time.time()
    total_count = len(MODELS) * len(TARGET_POSES)
    current_idx = 0

    for m_info in MODELS:
        m_prefix = m_info["prefix"]
        m_name = m_info["name"]
        m_ckpt = m_info["ckpt"]

        print(f"\n▶ [{m_name}] 모델 생성 시작 (체크포인트: {m_ckpt})")
        print("-" * 68)

        for p_code in TARGET_POSES:
            current_idx += 1
            pose = pose_db.get(p_code)
            if not pose:
                print(f"  [경고] 포즈 {p_code}를 DB에서 찾을 수 없습니다. 건너뜁니다.")
                continue

            out_filename = f"{m_prefix}_{p_code}.webp"
            out_path = output_dir / out_filename
            seed = POSE_SEEDS.get(p_code, 42)

            pos_prompt, neg_prompt, is_nude = assemble_sdxl_prompt(char=char, pose=pose)

            workflow = build_sdxl_workflow(
                ckpt_name=m_ckpt,
                positive_prompt=pos_prompt,
                negative_prompt=neg_prompt,
                output_prefix=f"compare_{m_prefix}_{p_code}",
                seed=seed,
                steps=DEFAULT_SDXL_STEPS,
                cfg=DEFAULT_SDXL_CFG,
                sampler=DEFAULT_SDXL_SAMPLER,
                scheduler=DEFAULT_SDXL_SCHEDULER,
                width=DEFAULT_SDXL_WIDTH,
                height=DEFAULT_SDXL_HEIGHT,
                use_face_detailer=True,
                use_upscale=True,
                ref_image_name=ref_file_name,
                ref_weight=ref_weight,
            )

            print(f"  [{current_idx:02d}/{total_count:02d}] {m_prefix}_{p_code} #{p_code} {pose.label:<12} (시드: {seed}) ➔ {out_filename}", end="", flush=True)

            t0 = time.time()
            try:
                client.generate_image(workflow=workflow, output_path=out_path)
                elapsed = time.time() - t0
                print(f" [완료: {elapsed:.1f}초]")
            except Exception as e:
                elapsed = time.time() - t0
                print(f" [실패: {e}]")

    total_elapsed = time.time() - total_start
    print("\n" + "=" * 68)
    print("  [완료] 3대 모델 비교 벤치마크 생성 완료!")
    print(f"  총 소요 시간: {total_elapsed / 60:.1f}분 (총 {total_count}장)")
    print(f"  저장 폴더: {output_dir}")
    print("=" * 68 + "\n")

    open_in_explorer(output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
