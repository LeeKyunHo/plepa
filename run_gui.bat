@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ======================================================
echo   [PLEPA] Asset Studio GUI
echo   URL: http://127.0.0.1:8080
echo ======================================================

netstat -ano | findstr "127.0.0.1:8080" | findstr "LISTENING" > nul
if %errorlevel%==0 (
    echo [INFO] Port 8080 is already in use - GUI server is already running.
    echo [INFO] Opening browser only.
    start "" http://127.0.0.1:8080
    pause
    exit /b 0
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" plepa_gui\app.py
) else (
    python plepa_gui\app.py
)

pause
