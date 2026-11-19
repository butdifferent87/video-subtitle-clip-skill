#!/usr/bin/env bash
# video-subtitle-clip 스킬 맥 설치 스크립트
# 사용법: 이 폴더에서  bash install.sh
set -euo pipefail
cd "$(dirname "$0")"

command -v brew >/dev/null || { echo "Homebrew 가 필요하다: https://brew.sh" >&2; exit 1; }

echo "1/4  프로그램 설치 (ffmpeg@7, yt-dlp, whisper.cpp)..."
brew install ffmpeg ffmpeg@7 yt-dlp whisper-cpp

echo "2/4  파이썬 패키지 설치 (예비 받아쓰기·폰트 측정)..."
python3 -m pip install --user --upgrade faster-whisper pillow 2>/dev/null \
  || python3 -m pip install --user --break-system-packages --upgrade faster-whisper pillow

echo "3/4  받아쓰기 모델 (large-v3-turbo, 1.6GB)..."
M=~/.cache/whisper/models/ggml-large-v3-turbo.bin
if [[ -f "$M" ]]; then
  echo "  이미 있음: $M"
else
  mkdir -p "$(dirname "$M")"
  curl -L --fail -o "$M.part" \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
  mv "$M.part" "$M"
fi

echo "4/4  스킬을 Claude Code 폴더에 복사..."
DEST=~/.claude/skills/video-subtitle-clip
mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R video-subtitle-clip "$DEST"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +

echo
echo "완료! 받아쓰기 엔진:"
python3 "$DEST/scripts/fw_transcribe.py" --check
echo "  backend=cpp 면 맥 GPU 로 돈다."
