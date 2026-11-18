#!/usr/bin/env python3
"""자막을 다음 자막이 나올 때까지 붙잡아 둔다.

받아쓰기가 만든 자막은 말이 끝나는 순간 사라진다. 읽는 사람 입장에서는
문장을 다 읽기도 전에 글자가 없어지고, 자막이 깜빡이는 것처럼 보인다.
그렇다고 무조건 늘리면 아무도 말하지 않는 긴 구간에도 옛 자막이 남아
화면을 덮는다. 그래서 두 규칙을 쓴다.

- 다음 자막까지의 공백이 짧으면(기본 5초 이하) 다음 자막 직전까지 유지한다.
- 공백이 길면 말이 끝나고 잠깐만(기본 3초) 더 두고 사라진다.

원래 길이보다 짧아지는 일은 없다.

usage: hold_subs.py in.srt out.srt [--gap 5] [--tail 3] [--epsilon 0]
"""
import argparse
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--gap", type=float, default=5.0,
                    help="이 값 이하의 공백이면 다음 자막 직전까지 유지 (초)")
    ap.add_argument("--tail", type=float, default=3.0,
                    help="공백이 길 때 말이 끝나고 더 두는 시간 (초)")
    ap.add_argument("--epsilon", type=float, default=0.0,
                    help="다음 자막과의 간격 (초). 0이면 끊김 없이 이어진다. "
                         "0보다 크면 그 시간만큼 자막이 사라져 깜빡이는 것처럼 보인다")
    args = ap.parse_args()

    cues = []
    for m in CUE.finditer(Path(args.src).read_text(encoding="utf-8-sig")):
        g = m.groups()
        start = (int(g[1]) * 3600 + int(g[2]) * 60 + int(g[3])) + int(g[4]) / 1000
        end = (int(g[5]) * 3600 + int(g[6]) * 60 + int(g[7])) + int(g[8]) / 1000
        body = g[9].strip()
        if body:
            cues.append([start, end, body])

    if not cues:
        raise SystemExit(f"자막 큐를 못 찾음: {args.src}")

    held = 0
    for i, cue in enumerate(cues):
        if i + 1 < len(cues):
            gap = cues[i + 1][0] - cue[1]
            if gap <= args.gap:
                new_end = cues[i + 1][0] - args.epsilon
            else:
                new_end = cue[1] + args.tail
        else:
            new_end = cue[1] + args.tail
        if new_end > cue[1]:
            held += 1
            cue[1] = max(cue[1], new_end)

    with Path(args.dst).open("w", encoding="utf-8") as f:
        for n, (start, end, body) in enumerate(cues, 1):
            f.write(f"{n}\n{ts(start)} --> {ts(end)}\n{body}\n\n")

    total = sum(e - s for s, e, _ in cues)
    print(f"{len(cues)} cues, {held}개 연장 -> {args.dst}")
    print(f"  공백 {args.gap}초 이하 = 다음 자막까지 유지 / 초과 = +{args.tail}초 후 사라짐")
    print(f"  자막 총 노출 시간 {total:.1f}초")


if __name__ == "__main__":
    main()
