#!/usr/bin/env python3
"""SRT 구간 추출 + 0초 기준 시프트.

usage: srtcut.py in.srt out.srt START END   (START/END 는 초 또는 MM:SS / HH:MM:SS)
구간에 걸치는 큐는 경계에서 잘라 살린다.
"""
import re
import sys
from pathlib import Path

PAT = re.compile(
    r"(\d+)[^\S\n]*\n"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*-->[^\S\n]*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.S,
)


def to_ms(v: str) -> int:
    if ":" not in v:
        return int(float(v) * 1000)
    parts = [float(p) for p in v.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts
    return int((h * 3600 + m * 60 + s) * 1000)


def ts(ms: int) -> str:
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    src, dst, start_arg, end_arg = sys.argv[1:5]
    start, end = to_ms(start_arg), to_ms(end_arg)

    out = []
    for m in PAT.finditer(Path(src).read_text(encoding="utf-8")):
        g = m.groups()
        cue_start = (int(g[1]) * 3600 + int(g[2]) * 60 + int(g[3])) * 1000 + int(g[4])
        cue_end = (int(g[5]) * 3600 + int(g[6]) * 60 + int(g[7])) * 1000 + int(g[8])
        if cue_end <= start or cue_start >= end:
            continue
        body = g[9].strip()
        if not body:
            continue
        out.append((max(cue_start, start) - start, min(cue_end, end) - start, body))

    with Path(dst).open("w", encoding="utf-8") as f:
        for n, (a, b, body) in enumerate(out, 1):
            f.write(f"{n}\n{ts(a)} --> {ts(b)}\n{body}\n\n")
    print(f"{len(out)} cues -> {dst}")


if __name__ == "__main__":
    main()
