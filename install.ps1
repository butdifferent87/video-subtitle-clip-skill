# video-subtitle-clip 스킬 윈도우 설치 스크립트
# 사용법: PowerShell 에서 이 폴더로 이동 후
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"

Write-Host "1/5  프로그램 설치 (ffmpeg, yt-dlp, Python, Git)..." -ForegroundColor Cyan
winget install --id Gyan.FFmpeg      -e --accept-source-agreements --accept-package-agreements
winget install --id yt-dlp.yt-dlp    -e --accept-source-agreements --accept-package-agreements
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
winget install --id Git.Git          -e --accept-source-agreements --accept-package-agreements

# 방금 설치한 프로그램이 이 창에서도 보이게 PATH 새로고침
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

Write-Host "2/5  파이썬 패키지 설치 (받아쓰기·폰트 측정)..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install --upgrade faster-whisper openai-whisper pillow

Write-Host "3/5  엔비디아 GPU 확인..." -ForegroundColor Cyan
$hasNvidia = $null -ne (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
if ($hasNvidia) {
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
    # faster-whisper(ctranslate2)가 GPU 를 쓰려면 CUDA 12 용 cuBLAS + cuDNN 9 DLL 이 필요하다.
    # CUDA 툴킷을 통째로 깔 필요 없이 pip 패키지로 충분하다 (fw_transcribe.py 가 DLL 폴더를 찾아 등록한다).
    python -m pip install --upgrade nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
} else {
    Write-Host "  엔비디아 GPU 가 안 보임 -> CPU 로 받아쓰기 (느림)" -ForegroundColor Yellow
}

Write-Host "4/5  한글 깨짐 방지 (PYTHONUTF8=1)..." -ForegroundColor Cyan
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
$env:PYTHONUTF8 = "1"

Write-Host "5/5  스킬을 Claude Code 폴더에 복사..." -ForegroundColor Cyan
$dest = Join-Path $env:USERPROFILE ".claude\skills\video-subtitle-clip"
New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse (Join-Path $PSScriptRoot "video-subtitle-clip") $dest

Write-Host ""
Write-Host "완료! 확인:" -ForegroundColor Green
ffmpeg -hide_banner -filters | Select-String -Pattern "\bass\b" | Select-Object -First 1
Write-Host "  위에 'ass' 줄이 보이면 자막 태우기 준비 끝."
if ($hasNvidia) {
    $engine = python (Join-Path $dest "scripts\fw_transcribe.py") --check
    if ($engine -match "cuda") {
        Write-Host "  GPU 받아쓰기 준비 끝 (엔비디아 카드 인식됨)." -ForegroundColor Green
    } else {
        Write-Host "  ⚠ GPU 를 못 잡음 -> 그래픽 드라이버를 최신으로 올린 뒤 다시 실행." -ForegroundColor Yellow
    }
}
Write-Host "  창을 닫고 새로 연 뒤 Claude Code 를 실행하세요."
Write-Host "  (받아쓰기 모델 1.6GB 는 첫 실행 때 자동으로 받습니다.)"
