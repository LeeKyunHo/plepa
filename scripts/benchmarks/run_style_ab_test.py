"""
scripts/run_style_ab_test.py
Style A/B Test (Mode A legacy vs Mode B balanced) 배치 생성 및 4열 비교 갤러리 빌드 오케스트레이터.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
SEED = "20261116"

RUNS = [
    ("campus", "aya", "000,009,020,080,086,088"),
    ("oto", "kei", "000,009,020,150,156,158"),
]

MODES = [
    ("legacy", ROOT / "output" / "style_ab_test" / "mode_a_legacy"),
    ("balanced", ROOT / "output" / "style_ab_test" / "mode_b_balanced"),
]


def main() -> int:
    for mode_name, out_dir in MODES:
        env = os.environ.copy()
        env["PLEPA_STYLE_MODE"] = mode_name
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
                "--out-dir", str(out_dir),
            ]
            print(f"\n=== [Style A/B] mode={mode_name} roster={roster} char={char} poses={poses} ===", flush=True)
            proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
            if proc.returncode != 0:
                print(f"[ERROR] Failed: mode={mode_name} char={char} exit={proc.returncode}", flush=True)
                return proc.returncode

    from scripts.benchmarks.build_style_ab_gallery import build_gallery
    gallery_path = build_gallery()
    print(f"\n=== [Style A/B] Gallery built: {gallery_path} ===", flush=True)
    return 0


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
