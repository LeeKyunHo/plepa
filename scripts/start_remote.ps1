# PLEPA 원격(외부망) 접속 런처
# NiceGUI 서버(8080) + Cloudflare Quick Tunnel을 함께 기동하고 공개 URL을 출력합니다.
# 사용법: 루트에서 `powershell -ExecutionPolicy Bypass -File scripts\start_remote.ps1`
# 주의: Quick Tunnel URL은 실행할 때마다 새로 발급됩니다.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Cf = Join-Path $Root "cloudflared.exe"

if (-not (Test-Path $Cf)) {
    Write-Host "[설치] cloudflared.exe 다운로드 중..."
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $Cf
}

# 1) GUI 서버 (이미 8080이 열려 있으면 재사용)
$listening = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Write-Host "[기동] NiceGUI 서버 (8080)"
    Start-Process -FilePath $Py -ArgumentList "plepa_gui/app.py --host 0.0.0.0 --port 8080" -WindowStyle Minimized
    Start-Sleep -Seconds 6
} else {
    Write-Host "[재사용] 8080 포트 서버가 이미 실행 중"
}

# 2) Cloudflare Tunnel
$Log = Join-Path $env:TEMP "plepa_tunnel.log"
if (Test-Path $Log) { Remove-Item $Log -Force }
Write-Host "[기동] Cloudflare Quick Tunnel"
Start-Process -FilePath $Cf -ArgumentList "tunnel --url http://127.0.0.1:8080" -RedirectStandardError $Log -WindowStyle Minimized

$url = $null
for ($i = 0; $i -lt 30 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $Log) {
        $m = Select-String -Path $Log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
}

if ($url) {
    Write-Host ""
    Write-Host "==============================================="
    Write-Host " PC 스튜디오 : $url"
    Write-Host " 모바일 뷰어 : $url/mobile"
    Write-Host "==============================================="
    Set-Clipboard -Value "$url/mobile"
    Write-Host "(모바일 뷰어 주소가 클립보드에 복사되었습니다)"
} else {
    Write-Host "[실패] 터널 URL을 찾지 못했습니다. 로그: $Log"
}
