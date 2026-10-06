@echo off
chcp 65001 > nul
echo ======================================================
echo   [플에파 / PLEPA] 로컬 스튜디오 GUI 가동 중...
echo   접속 주소: http://127.0.0.1:8080
echo ======================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" plepa_gui\app.py
) else (
    python plepa_gui\app.py
)

pause
