@echo off
chcp 65001 > nul
cd /d "%~dp0"
title [PLEPA] SPY 10인 배치 생성기

echo ============================================================
echo   [플에파] SPY 10인 순차 배치 생성 시작
echo   - 1차: 감정(A00~A23) + 첩보전용(S01~S10) (총 34종 x 10인)
echo   - 2차: 일상행동(B01~B22) (총 22종 x 10인)
echo   - 3차: 성인 씬(N01~N74)
echo   - 4차: 테마 의상 팩(D, E, F)
echo ============================================================
echo.

echo ▶ [1/4] 감정(A00~A23) 및 첩보 전용 10종(S01~S10) 일괄 생성...
.\.venv\Scripts\python.exe flux_batch_generator.py -r spy -c all -p "A00..A23,S01..S10" --engine sdxl --bg-preset default
if errorlevel 1 goto error

echo.
echo ▶ [2/4] 일상행동(B01~B22) 22종 일괄 생성...
.\.venv\Scripts\python.exe flux_batch_generator.py -r spy -c all -p "B01..B22" --engine sdxl --bg-preset default
if errorlevel 1 goto error

echo.
echo ▶ [3/4] 성인 씬(N01~N74) 일괄 생성...
.\.venv\Scripts\python.exe flux_batch_generator.py -r spy -c all -p "N01..N74" --engine sdxl --bg-preset default
if errorlevel 1 goto error

echo.
echo ▶ [4/4] 테마 의상 팩(D, E, F) 일괄 생성...
.\.venv\Scripts\python.exe flux_batch_generator.py -r spy -c all -p "D01..D07,E01..E08,F01..F07" --engine sdxl --bg-preset default
if errorlevel 1 goto error

echo.
echo ============================================================
echo   [완료] SPY 10인 전 포즈 생성이 성공적으로 완료되었습니다!
echo ============================================================
if "%~1"=="--no-pause" exit /b 0
pause
exit /b 0

:error
echo.
echo [오류 발생] 배치 생성 도중 문제가 발생했습니다. 창을 닫기 전 로그를 확인해 주세요.
if "%~1"=="--no-pause" exit /b 1
pause
exit /b 1
