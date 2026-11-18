# video-subtitle-clip 스킬 윈도우 설치 스크립트
# 사용법: PowerShell 에서 이 폴더로 이동 후
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"

Write-Host "1/4  프로그램 설치 (ffmpeg, yt-dlp, Python, Git)..." -ForegroundColor Cyan
winget install --id Gyan.FFmpeg      -e --accept-source-agreements --accept-package-agreements
winget install --id yt-dlp.yt-dlp    -e --accept-source-agreements --accept-package-agreements
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
winget install --id Git.Git          -e --accept-source-agreements --accept-package-agreements

# 방금 설치한 프로그램이 이 창에서도 보이게 PATH 새로고침
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

Write-Host "2/4  파이썬 패키지 설치 (받아쓰기·폰트 측정)..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install faster-whisper openai-whisper pillow

Write-Host "3/4  한글 깨짐 방지 (PYTHONUTF8=1)..." -ForegroundColor Cyan
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")

Write-Host "4/4  스킬을 Claude Code 폴더에 복사..." -ForegroundColor Cyan
$dest = Join-Path $env:USERPROFILE ".claude\skills\video-subtitle-clip"
New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse (Join-Path $PSScriptRoot "video-subtitle-clip") $dest

Write-Host ""
Write-Host "완료! 확인:" -ForegroundColor Green
ffmpeg -hide_banner -filters | Select-String -Pattern "\bass\b" | Select-Object -First 1
Write-Host "  위에 'ass' 줄이 보이면 자막 태우기 준비 끝."
Write-Host "  창을 닫고 새로 연 뒤 Claude Code 를 실행하세요."
