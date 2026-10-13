# run_pipeline.py
import os
import re
import subprocess
import sys
from pathlib import Path

def cleanup_old_labels():
    print("=== [1단계] 구 라벨 잔여 파일 정리 ===")
    assets_dir = Path("projects/campus/assets")
    if not assets_dir.exists():
        return
    pattern = re.compile(r"(033_.*턱들기|034_.*가슴파묻힘|037_.*딥키스|040_.*정상위|047_.*대면좌위|052_.*펠라치오|053_.*결합딥키스|056_.*서서벽밀착)")
    deleted_count = 0
    for p in assets_dir.rglob("*.png"):
        if pattern.search(p.name):
            try:
                p.unlink()
                print(f"삭제됨: {p.name}")
                deleted_count += 1
            except Exception as e:
                print(f"삭제 실패 ({p.name}): {e}")
    print(f"총 {deleted_count}개 구 라벨 파일 정리 완료.\n")

def run_command(cmd):
    print(f"실행 중: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"경고: 명령 실행 중 오류 코드 반환 ({result.returncode})")
    return result.returncode

def main():
    cleanup_old_labels()
    
    python_exe = sys.executable
    
    # 2단계: 16종 교체 재생성
    print("=== [2단계] 16종 포즈 Face Detailer 적용 덮어쓰기 생성 ===")
    cmd_phase1 = [
        python_exe, "flux_batch_generator.py",
        "-r", "campus",
        "-c", "all",
        "-p", "033,034,037,040,041,042,047,052,053,056,067,069,081,082,087,089",
        "--engine", "sdxl",
        "--overwrite",
        "--face-detailer"
    ]
    run_command(cmd_phase1)
    
    # 3단계: 전 캐릭터 빈칸 채우기
    print("\n=== [3단계] 전체 캐릭터 미생성 포즈 빈칸 채우기 연계 생성 ===")
    cmd_phase2 = [
        python_exe, "flux_batch_generator.py",
        "-r", "campus",
        "-c", "all",
        "-p", "all",
        "--engine", "sdxl",
        "--face-detailer"
    ]
    run_command(cmd_phase2)
    
    print("\n=== 모든 배치 작업 완료 ===")

if __name__ == "__main__":
    main()
