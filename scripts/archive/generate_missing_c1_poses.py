# -*- coding: utf-8 -*-
"""
scripts/generate_missing_c1_poses.py
화풍 불일치(#076, #095, #106) 및 모브남 필로우토크(#115) 4종 포즈에 대해
설하율(hay) & 하루(har) 2인 C-1 화풍 정규 일괄 재생성 스크립트.
"""

import sys
import time
import shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plepa_engine.services.generation_service import GenerationParams, GenerationService
from plepa_engine.reporter import get_subfolder_for_code
from scripts.archive.run_full_inspection_batch import (
    C1_ARTIST_TAG,
    TARGET_CHARACTERS,
    get_contextual_quality_tag,
    generate_html_viewer,
    INSPECTION_DIR,
)

TARGET_CODES = ["076", "095", "106", "115"]

def generate_target_poses():
    service = GenerationService()
    print("=" * 70)
    print(" [C-1 화풍 정규 재생성: #076, #095, #106, #115]")
    print(f" C-1 화풍 태그: {C1_ARTIST_TAG}")
    print("=" * 70)

    for ch in TARGET_CHARACTERS:
        c_code = ch["code"]
        roster = ch["roster"]
        print(f"\n▶ 캐릭터: {ch['name']} ({c_code}, {roster})")

        for p_code in TARGET_CODES:
            quality_tag = get_contextual_quality_tag(p_code)
            combined_pos = f"{C1_ARTIST_TAG}, {quality_tag}"
            subfolder = get_subfolder_for_code(p_code)

            print(f"  ⚡ 생성 중... #{p_code} ({subfolder})")
            
            # 시드는 포즈별 다양성과 품질 수렴을 위해 고유 시드 부여
            pose_seed = 1001 + int(p_code)

            params = GenerationParams(
                character_expr=c_code,
                pose_expr=p_code,
                roster=roster,
                custom_pos=combined_pos,
                ckpt_tag=f"inspect_{c_code}_{p_code}",
                overwrite=True,
                engine="sdxl",
                censor=True,
                seed=pose_seed,
                no_ref=True,
            )

            t0 = time.time()
            res = service.run_batch(params, quiet=True)
            dur = time.time() - t0

            if res and res[0].success and res[0].image_path:
                gen_p = Path(res[0].image_path)
                if gen_p.exists():
                    # 1. inspection_batch 대상 폴더로 복사
                    dest_dir = INSPECTION_DIR / c_code / subfolder
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_dir / f"{c_code}_{p_code}_{gen_p.name.split('_', 2)[-1]}"
                    # 만약 이름 형식이 다르면
                    if not dest_file.name.endswith(".webp"):
                        dest_file = dest_dir / f"{c_code}_{p_code}.webp"
                    shutil.copy2(gen_p, dest_file)
                    print(f"     ✅ 성공 ({dur:.1f}초, {dest_file.stat().st_size//1024} KB) -> {dest_file.name}")
                else:
                    print(f"     ❌ 결과 파일 미발견: {gen_p}")
            else:
                err = res[0].error_message if res else "Unknown error"
                print(f"     ❌ 생성 실패: {err}")

    # HTML 갱신
    generate_html_viewer(INSPECTION_DIR)
    print("\n✅ 전체 대상 포즈 C-1 화풍 재생성 및 HTML 뷰어 갱신 완료!")

if __name__ == "__main__":
    generate_target_poses()
