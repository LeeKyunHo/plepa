"""
scripts/run_wet_h_test.py
ADR-102 Wet-H Booster 대표 6컷(aya 060,080,086,088 + shz 086,092) 생성 및 갤러리 갱신.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
SEED = "20261116"
OUT_DIR = ROOT / "output" / "style_ab_test" / "mode_wet_h"

RUNS = [
    ("campus", "aya", "060,080,086,088"),
    ("campus", "shz", "086,092"),
]


def main() -> int:
    env = os.environ.copy()
    env["PLEPA_STYLE_MODE"] = "legacy"
    for roster, char, poses in RUNS:
        cmd = [
            PYTHON,
            "-u",
            str(ROOT / "batch_generator.py"),
            "-r", roster,
            "-c", char,
            "-p", poses,
            "--seed", SEED,
            "--censor",
            "--overwrite",
            "--out-dir", str(OUT_DIR),
        ]
        print(f"\n=== [Wet-H Booster] roster={roster} char={char} poses={poses} ===", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
        if proc.returncode != 0:
            print(f"[ERROR] Failed: char={char} exit={proc.returncode}", flush=True)
            return proc.returncode

    from scripts.benchmarks.build_style_ab_gallery import build_gallery
    gallery_path = build_gallery()
    print(f"\n=== [Wet-H Booster] Gallery updated: {gallery_path} ===", flush=True)
    return 0


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
