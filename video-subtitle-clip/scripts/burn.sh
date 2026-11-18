#!/usr/bin/env bash
# 자막을 영상에 태워 MP4로 굽는다.
#
# usage: burn.sh INPUT SUBS.ass OUTPUT.mp4 [--ss 19:20] [--t 12:30] [--crf 18] [--scale 1280:-2]
#
# --ss/--t 를 주면 그 구간만 굽는다. 이때 자막은 이미 0초 기준으로
# 시프트돼 있어야 한다 (srtcut.py 가 하는 일). -ss 를 -i 앞에 두면
# 출력 타임스탬프가 0부터 시작하기 때문이다.
set -euo pipefail

# 맥: Homebrew ffmpeg@7 (libass 있음). 윈도우·기타: PATH 의 ffmpeg (winget Gyan.FFmpeg 은 libass 포함).
if [[ -z "${FFMPEG:-}" ]]; then
  if [[ -x /opt/homebrew/opt/ffmpeg@7/bin/ffmpeg ]]; then
    FFMPEG=/opt/homebrew/opt/ffmpeg@7/bin/ffmpeg
  else
    FFMPEG="$(command -v ffmpeg || true)"
  fi
fi

if [[ $# -lt 3 ]]; then
  sed -n '2,12p' "$0" | sed 's/^# \?//'
  exit 1
fi

INPUT="$1"; SUBS="$2"; OUTPUT="$3"; shift 3

SS=""; DUR=""; CRF=18; SCALE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ss)    SS="$2";    shift 2 ;;
    --t)     DUR="$2";   shift 2 ;;
    --crf)   CRF="$2";   shift 2 ;;
    --scale) SCALE="$2"; shift 2 ;;
    *) echo "모르는 옵션: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$FFMPEG" || ! -x "$FFMPEG" ]]; then
  echo "ffmpeg 이 없다: ${FFMPEG:-(PATH 에 없음)}" >&2
  echo "  맥: brew install ffmpeg@7 / 윈도우: winget install Gyan.FFmpeg" >&2
  exit 1
fi

# grep -q 는 첫 매치에서 바로 끝나 ffmpeg 에 SIGPIPE 를 보내고,
# pipefail 때문에 파이프라인 전체가 실패로 잡힌다. 출력을 먼저 받아둔다.
FILTERS="$("$FFMPEG" -hide_banner -filters 2>/dev/null || true)"
if ! grep -qw ass <<<"$FILTERS"; then
  echo "이 ffmpeg 엔 libass 가 없어서 자막을 태울 수 없다: $FFMPEG" >&2
  echo "  맥: brew install ffmpeg@7   # keg-only, 기존 ffmpeg 는 그대로" >&2
  echo "  윈도우: winget install Gyan.FFmpeg  (full 빌드, libass 포함)" >&2
  echo "  (기본 ffmpeg 는 Homebrew 가 슬림화하면서 libass 를 뺐다)" >&2
  exit 1
fi

[[ -f "$INPUT" ]] || { echo "입력 파일 없음: $INPUT" >&2; exit 1; }
[[ -f "$SUBS"  ]] || { echo "자막 파일 없음: $SUBS" >&2; exit 1; }

# 아래에서 임시 폴더로 cd 하므로 상대 경로는 전부 절대 경로로 바꿔둔다.
abspath() { local d f; d="$(cd "$(dirname "$1")" && pwd)"; f="$(basename "$1")"; echo "$d/$f"; }
INPUT="$(abspath "$INPUT")"
SUBS="$(abspath "$SUBS")"
mkdir -p "$(dirname "$OUTPUT")"
OUTPUT="$(abspath "$OUTPUT")"

# ass 필터는 파일명의 특수문자에 약하다. 심볼릭 링크로 안전한 이름을 만든다.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ln -s "$SUBS" "$WORK/subs.ass"

VF="ass=subs.ass"
[[ -n "$SCALE" ]] && VF="scale=${SCALE}:flags=lanczos,${VF}"

ARGS=(-hide_banner -loglevel warning -stats)
[[ -n "$SS" ]] && ARGS+=(-ss "$SS")
ARGS+=(-i "$INPUT")
[[ -n "$DUR" ]] && ARGS+=(-t "$DUR")
ARGS+=(
  -vf "$VF"
  -c:v libx264 -crf "$CRF" -preset medium -pix_fmt yuv420p
  -c:a aac -b:a 192k
  -movflags +faststart -y "$OUTPUT"
)

( cd "$WORK" && "$FFMPEG" "${ARGS[@]}" )

echo
echo "완성: $OUTPUT"
ls -lh "$OUTPUT" | awk '{print "  크기:", $5}'
echo "  → 자막이 실제로 있는 시각으로 프레임을 뽑아 눈으로 확인할 것:"
echo "     $FFMPEG -ss 95 -i \"$OUTPUT\" -frames:v 1 -y check.png"
