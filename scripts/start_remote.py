"""
scripts/start_remote.py
NiceGUI 서버(8080)와 Cloudflare Quick Tunnel을 기동하고 모바일 접속 링크를 반환합니다.
"""

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
CF = ROOT / "cloudflared.exe"


def is_port_open(port: int = 8080) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    if not CF.is_file():
        print(f"[오류] cloudflared.exe를 찾을 수 없습니다: {CF}")
        sys.exit(1)

    # 1. 8080 서버 기동 확인
    if not is_port_open(8080):
        print("[기동] NiceGUI 웹 서버 (포트 8080)...")
        subprocess.Popen(
            [str(PY), "-m", "plepa_gui.app", "--host", "0.0.0.0", "--port", "8080"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        for _ in range(30):
            time.sleep(1)
            if is_port_open(8080):
                print("[성공] 8080 서버 기동 완료.")
                break
        else:
            print("[경고] 8080 포트 바인딩 지연 중 (계속 진행)...")
    else:
        print("[재사용] 8080 포트 서버가 이미 실행 중입니다.")

    # 2. Cloudflare Tunnel 기동
    print("[기동] Cloudflare Quick Tunnel 개설 중...")
    log_file = Path(os.environ.get("TEMP", ".")) / "plepa_tunnel.log"
    if log_file.exists():
        try:
            log_file.unlink()
        except Exception:
            pass

    log_fp = open(log_file, "w", encoding="utf-8")
    cf_proc = subprocess.Popen(
        [str(CF), "tunnel", "--url", "http://127.0.0.1:8080"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=log_fp,
        creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
    )

    tunnel_url = None
    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    for _ in range(35):
        time.sleep(1)
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    matches = pattern.findall(content)
                    if matches:
                        tunnel_url = matches[0]
                        break
            except Exception:
                pass

    if tunnel_url:
        mobile_url = f"{tunnel_url}/mobile"
        otoko_url = f"{tunnel_url}/otoko"
        print("\n" + "=" * 65)
        print(f"[Otoko 600 Viewer] {otoko_url}")
        print(f"[Mobile Link]      {mobile_url}")
        print(f"[PC Studio]        {tunnel_url}")
        print("=" * 65 + "\n")
    else:
        print("[실패] 터널 URL을 발급받지 못했습니다. 로그를 확인하세요:", log_file)


if __name__ == "__main__":
    main()
