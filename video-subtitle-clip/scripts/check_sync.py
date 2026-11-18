#!/usr/bin/env python3
"""자막 시각이 실제 발화와 맞는지 수치로 검사한다.

프레임 몇 장을 눈으로 보는 검수로는 타이밍을 못 잡는다. 87개 자막 중
서너 개만, 그것도 "떠 있다" 수준으로 보게 되기 때문이다. 실제로 프레임
검수를 통과한 결과물에서 14개가 어긋나 있던 적이 있다.

이 스크립트는 **결과물 오디오를 다시 받아쓰기한 결과**와 자막을 대조해
전 자막의 시각을 검사한다. 사람이 만든 자막이든 기계가 만든 자막이든,
"말이 시작되는 지점"에 자막이 붙어 있어야 한다는 기준은 같다.

usage:
  # 1) 결과물 오디오를 받아쓴다 (단어 단위 시각 필요)
  ffmpeg -i OUT.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le out.wav
  whisper out.wav --model medium --language en --output_format json \\
      --word_timestamps True --output_dir . --condition_on_previous_text False

  # 2) 대조
  check_sync.py cut.srt out.json [--tol 0.3] [--fix fixed.srt]

`--fix` 를 주면 어긋난 자막의 시작을 가장 가까운 단어 시각으로 당겨
새 SRT 를 쓴다. 끝 시각은 같은 양만큼 함께 옮겨 길이를 보존한다.

한계 — 받아쓰기가 놓친 말(웃음소리에 묻힌 대사 등)은 기준점이 없어
"어긋남"으로 잡힐 수 있다. 목록을 보고 판단한다. 자동 수정은 기준점이
tol 안에 있는 것만 건드리므로, 근처에 단어가 아예 없으면 그냥 둔다.
"""
import argparse
import json
import re
from pathlib import Path

CUE = re.compile(
    r"(\d+)[^\S\n]*\n"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*-->[^\S\n]*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.S,
)


def ts(v):
    v = max(0.0, v)
    h = int(v // 3600)
    m = int(v % 3600 // 60)
    s = int(v % 60)
    ms = int(round((v - int(v)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def load_cues(path):
    cues = []
    for m in CUE.finditer(Path(path).read_text(encoding="utf-8-sig")):
        g = m.groups()
        a = (int(g[1]) * 3600 + int(g[2]) * 60 + int(g[3])) + int(g[4]) / 1000
        b = (int(g[5]) * 3600 + int(g[6]) * 60 + int(g[7])) + int(g[8]) / 1000
        body = g[9].strip()
        if body:
            cues.append([a, b, body])
    return cues


def load_word_starts(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    starts = [w["start"] for s in d.get("segments", []) for w in s.get("words", [])]
    if not starts:
        raise SystemExit(
            f"{path} 에 단어 시각이 없다. whisper 를 --word_timestamps True 로 다시 돌린다."
        )
    return sorted(starts)


def nearest(sorted_vals, t):
    """t 에 가장 가까운 값과 그 차이(t - 값)를 돌려준다."""
    lo, hi = 0, len(sorted_vals) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_vals[mid] < t:
            lo = mid + 1
        else:
            hi = mid
    best = sorted_vals[lo]
    if lo > 0 and abs(sorted_vals[lo - 1] - t) < abs(best - t):
        best = sorted_vals[lo - 1]
    return best, t - best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srt")
    ap.add_argument("words_json", help="결과물 오디오를 받아쓴 whisper json")
    ap.add_argument("--tol", type=float, default=0.3, help="허용 오차 (초)")
    ap.add_argument("--fix", help="교정본을 쓸 경로")
    args = ap.parse_args()

    cues = load_cues(args.srt)
    starts = load_word_starts(args.words_json)

    rows = []
    for i, (a, b, text) in enumerate(cues, 1):
        _, delta = nearest(starts, a)
        rows.append((i, a, b, delta, text))

    off = [r for r in rows if abs(r[3]) > args.tol]
    deltas = sorted(abs(r[3]) for r in rows)
    med = deltas[len(deltas) // 2]

    print(f"자막 {len(cues)}개 / 기준 단어 {len(starts)}개 / 허용 {args.tol}초")
    print(f"  중앙 오차 {med:.3f}초 · 허용 초과 {len(off)}개")
    if off:
        print()
        for i, a, b, d, text in sorted(off, key=lambda r: -abs(r[3])):
            arrow = "늦음" if d > 0 else "이름"
            print(f"  #{i:>3} {a:7.2f}s  {d:+6.2f}초 {arrow}  「{text.replace(chr(10),' ')[:36]}」")

    if args.fix:
        fixed = 0
        for r in rows:
            i, a, b, d, text = r
            if abs(d) > args.tol:
                target, _ = nearest(starts, a)
                shift = target - a
                cues[i - 1][0] = a + shift
                cues[i - 1][1] = b + shift
                fixed += 1
        # 순서·겹침 정리
        cues.sort(key=lambda c: c[0])
        for i in range(len(cues) - 1):
            if cues[i][1] > cues[i + 1][0]:
                cues[i][1] = cues[i + 1][0]
        out = "\n".join(
            f"{n}\n{ts(a)} --> {ts(b)}\n{t}\n" for n, (a, b, t) in enumerate(cues, 1)
        )
        Path(args.fix).write_text(out, encoding="utf-8")
        print(f"\n{fixed}개 교정 -> {args.fix}")

    raise SystemExit(1 if off else 0)


if __name__ == "__main__":
    main()
