@echo off
chcp 65001 > nul
echo [PLEPA] 포트 8080 방화벽 인바운드 규칙 등록 중... (관리자 권한 필요)
netsh advfirewall firewall add rule name="PLEPA Mobile Gallery 8080" dir=in action=allow protocol=TCP localport=8080
echo.
echo [완료] 방화벽 허용 완료! 아무 키나 누르면 창이 닫힙니다.
pause
