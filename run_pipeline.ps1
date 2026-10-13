# run_pipeline.ps1
$ErrorActionPreference = "Continue"

Write-Host "=== [1단계] 구 라벨 잔여 파일 정리 ==="
Get-ChildItem -Path "projects/campus/assets" -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '033_.*턱들기|034_.*가슴파묻힘|037_.*딥키스|040_.*정상위|047_.*대면좌위|052_.*펠라치오|053_.*결합딥키스|056_.*서서벽밀착'
} | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Host "삭제됨: $($_.Name)"
}

Write-Host "=== [2단계] 16종 포즈 Face Detailer 적용 덮어쓰기 생성 ==="
& .\.venv\Scripts\python.exe flux_batch_generator.py -r campus -c all -p "033,034,037,040,041,042,047,052,053,056,067,069,081,082,087,089" --engine sdxl --overwrite --face-detailer

Write-Host "=== [3단계] 전체 캐릭터 미생성 포즈 빈칸 채우기 연계 생성 ==="
& .\.venv\Scripts\python.exe flux_batch_generator.py -r campus -c all -p all --engine sdxl --face-detailer

Write-Host "=== 모든 배치 작업 완료 ==="
