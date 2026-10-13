"""
run_spy_batch.py
SPY 10인 순차 배치 생성 스크립트.
- 1차: 감정(A00~A23) + 첩보전용(S01~S10) (총 34종 x 10인)
- 2차: 일상행동(B01~B22) (총 22종 x 10인)
- 3차: 성인 씬(N01~N74)
- 4차: 테마 의상 팩(D, E, F)
"""

import sys
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PYTHON_EXE = str(Path(".venv/Scripts/python.exe").resolve())

PHASES = [
    ("1/4: 감정(A00~A23) 및 첩보전용(S01~S10)", "A00..A23,S01..S10"),
    ("2/4: 일상행동(B01~B22)", "B01..B22"),
    ("3/4: 성인 씬(N01~N74)", "N01..N74"),
    ("4/4: 테마 의상 팩(D, E, F)", "D01..D07,E01..E08,F01..F07"),
]

def main():
    print("=" * 64)
    print("  [플에파] SPY 10인 순차 배치 생성 시작 (SDXL / default 배경)")
    print("=" * 64)

    for idx, (title, pose_expr) in enumerate(PHASES, 1):
        print(f"\n▶ [{title}] 일괄 생성 시작 (포즈: {pose_expr})")
        cmd = [
            PYTHON_EXE,
            "flux_batch_generator.py",
            "-r", "spy",
            "-c", "all",
            "-p", pose_expr,
            "--engine", "sdxl",
            "--bg-preset", "default",
            "--overwrite",
        ]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"\n[오류] 단계 [{title}] 실행 중 에러 코드 {res.returncode} 반환")
            sys.exit(res.returncode)

    print("\n" + "=" * 64)
    print("  [완료] SPY 10인 전 포즈 생성이 성공적으로 완료되었습니다!")
    print("=" * 64)

if __name__ == "__main__":
    main()
