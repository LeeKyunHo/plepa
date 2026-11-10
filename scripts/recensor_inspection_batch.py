# -*- coding: utf-8 -*-
"""
scripts/recensor_inspection_batch.py
신규 정밀 검열(귀두 노출 방지 + 여성 부위 배제 + 비노출 100% 원본 보존)을
기존 무검열 원본(_origin)에서 읽어와 output/inspection_batch에 즉시 일괄 재적용하는 스크립트.
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image
from plepa_engine.censor import censor_image
from scripts.run_full_inspection_batch import generate_html_viewer
INSPECT_DIR = ROOT / "output" / "inspection_batch"

TARGETS = [
    {"code": "har", "roster": "campus"},
    {"code": "hay", "roster": "ykn"},
]

def recensor_all():
    updated = 0
    skipped = 0

    for item in TARGETS:
        c_code = item["code"]
        roster = item["roster"]
        origin_root = ROOT / "projects" / roster / "assets" / f"{c_code}_origin"

        if not origin_root.exists():
            continue

        # 원본 이미지들 수집:
        # 과거 벤치마크 실험 폴더(ckpt_mix_*, ckpt_ctuning_*, ckpt_hybrid_*)는 철저히 배제!
        # 오직 정규 01_normal, 02_h_scenes 또는 최신 ckpt_inspect_ 만 허용
        origin_files = {}
        for f in origin_root.rglob("*.webp"):
            s = str(f).replace("\\", "/")
            if any(legacy in s for legacy in ("ckpt_mix_", "ckpt_ctuning_", "ckpt_hybrid_")):
                continue
            parts = f.stem.split("_")
            if len(parts) >= 2:
                p_code = parts[1]
                # ckpt_inspect_ 우선 (최신 생성본)
                if p_code not in origin_files or "ckpt_inspect_" in s:
                    origin_files[p_code] = f

        # 대상 디렉토리 갱신
        char_inspect_dir = INSPECT_DIR / c_code
        if not char_inspect_dir.exists():
            continue

        for target_p in char_inspect_dir.rglob("*.webp"):
            parts = target_p.stem.split("_")
            if len(parts) < 2:
                continue
            p_code = parts[1]

            if p_code in origin_files:
                orig_file = origin_files[p_code]
                img = Image.open(orig_file).convert("RGB")
                censored, count = censor_image(
                    img,
                    style="white_silhouette",
                    pose_code=p_code,
                    enable_anchor_fallback=False,  # 미탐지 시 억지 앵커 박스 투척 절대 금지
                )
                censored.save(target_p, "WEBP", quality=95)
                updated += 1
            else:
                skipped += 1

    print(f"Recensor complete: updated={updated}, skipped={skipped}")
    
    # 모바일 뷰어 HTML 갱신
    generate_html_viewer(INSPECT_DIR)
    print("HTML viewer regenerated successfully with cache-busting timestamps.")

if __name__ == "__main__":
    recensor_all()
