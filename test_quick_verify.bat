@echo off
chcp 65001 > nul
echo ============================================================
echo   플에파 빠른 검증 테스트 (대표 포즈만)
echo ============================================================
echo.
echo 테스트 포즈:
echo   000 (평상) - 감정
echo   001 (미소) - 감정  
echo   024 (뒤태) - 착의
echo   037 (딥키스) - 착의
echo   040 (정상위) - H씬
echo   054 (딥스로트) - H씬
echo.
echo 총 6개 포즈, 약 3-5분 소요 예상
echo.
pause

python flux_batch_generator.py -c sample_character -p 000,001,024,037,040,054 --engine sdxl --ckpt "unholyDesireMixSinister_v90.safetensors" --censor

echo.
echo ============================================================
echo   빠른 검증 완료!
echo ============================================================
echo.
echo 결과 확인:
explorer projects\default\assets\sample_character

pause
