@echo off
chcp 65001 > nul
echo ============================================================
echo   플에파 실전 배치 생성 검증 테스트
echo ============================================================
echo.
echo [1단계] 샘플 캐릭터 - 감정 포즈 (000-019) 20종 테스트
echo         엔진: SDXL (Unholy Mix)
echo         체크포인트 프로필 자동 적용 확인
echo.
pause

python flux_batch_generator.py -c sample_character -p 000..019 --engine sdxl --ckpt "unholyDesireMixSinister_v90.safetensors"

echo.
echo ============================================================
echo   1단계 완료! 결과 확인 중...
echo ============================================================
echo.
pause

echo.
echo [2단계] 샘플 캐릭터 - 착의 씬 (020-039) 20종 테스트
echo.
pause

python flux_batch_generator.py -c sample_character -p 020..039 --engine sdxl --ckpt "unholyDesireMixSinister_v90.safetensors"

echo.
echo ============================================================
echo   2단계 완료! 계속 진행하시겠습니까?
echo ============================================================
echo.
pause

echo.
echo [3단계] 샘플 캐릭터 - H 씬 (040-059) 20종 테스트
echo         (자동 검열 테스트 포함)
echo.
pause

python flux_batch_generator.py -c sample_character -p 040..059 --engine sdxl --ckpt "unholyDesireMixSinister_v90.safetensors" --censor

echo.
echo ============================================================
echo   3단계 완료!
echo ============================================================
echo.
pause

echo.
echo [4단계] 샘플 캐릭터 - 오토코노코 씬 (140-159) 20종 테스트
echo.
pause

python flux_batch_generator.py -c sample_character -p 140..159 --engine sdxl --ckpt "unholyDesireMixSinister_v90.safetensors"

echo.
echo ============================================================
echo   전체 테스트 완료! (총 80종)
echo ============================================================
echo.
echo 결과 폴더: projects\default\assets\sample_character
echo.
pause
