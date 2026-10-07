@echo off
REM ============================================================
REM 플에파 베이스라인 테스트 배치 스크립트
REM 문제가 많이 발생하는 포즈 7종 테스트 (손/복잡한 포즈)
REM ============================================================

echo ============================================================
echo 플에파 베이스라인 품질 테스트 시작
echo 테스트 포즈: 31, 32, 36, 54, 56, 154, 156
echo ============================================================
echo.

REM 테스트할 캐릭터와 로스터 설정
set ROSTER=don
set CHARACTER=bjh

REM 현재 설정: Face Detailer + Upscale (현재 기본 설정)
echo [1/7] 포즈 031 (배후성추행) 생성 중...
python -u flux_batch_generator.py -r %ROSTER% -c %CHARACTER% -p 031 --engine sdxl --face-detailer --upscale
echo.

echo [2/7] 포즈 032 (벽치기) 생성 중...
python -u flux_batch_generator.py -r %ROSTER% -c %CHARACTER% -p 032 --engine sdxl --face-detailer --upscale
echo.

echo [3/7] 포즈 036 (공주님안기) 생성 중...
python -u flux_batch_generator.py -r %ROSTER% -c %CHARACTER% -p 036 --engine sdxl --face-detailer --upscale
echo.

echo [4/7] 포즈 054 (이라마치오) 생성 중...
python -u flux_batch_generator.py -r %ROSTER% -c %CHARACTER% -p 054 --engine sdxl --face-detailer --upscale
echo.

echo [5/7] 포즈 056 (입위벽밀착) 생성 중...
python -u flux_batch_generator.py -r %ROSTER% -c %CHARACTER% -p 056 --engine sdxl --face-detailer --upscale
echo.

echo [6/7] 포즈 154 (오토코노코 이라마치오) 생성 중...
python -u flux_batch_generator.py -r %ROSTER% -c %CHARACTER% -p 154 --engine sdxl --face-detailer --upscale
echo.

echo [7/7] 포즈 156 (오토코노코 입위벽밀착) 생성 중...
python -u flux_batch_generator.py -r %ROSTER% -c %CHARACTER% -p 156 --engine sdxl --face-detailer --upscale
echo.

echo ============================================================
echo 베이스라인 테스트 완료!
echo 생성된 파일 위치: projects\%ROSTER%\assets\%CHARACTER%\
echo.
echo 다음 단계:
echo 1. 생성된 7개 이미지의 품질을 확인하세요 (특히 손, 얼굴, 포즈)
echo 2. 문제점을 메모하세요 (손가락 변형, 얼굴 왜곡, 포즈 붕괴 등)
echo 3. 개선 기능을 하나씩 적용하며 비교 테스트를 진행합니다
echo ============================================================
pause
