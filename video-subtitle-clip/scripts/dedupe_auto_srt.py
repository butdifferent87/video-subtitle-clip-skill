#!/usr/bin/env python3
"""유튜브 자동생성 자막의 롤링 중복을 걷어낸다.

유튜브 자동자막은 화면에 두 줄을 굴리면서 보여주는 방식이라, SRT 로 뽑으면
- 같은 문장이 다음 큐에 또 나오고(윈도가 한 줄씩 밀림)
- 10ms 짜리 빈 큐가 사이사이 끼어 있다.

그대로 태우면 자막이 두 번씩 깜빡이고 읽을 수가 없다. 이 스크립트는
큐마다 "이전에 이미 나온 줄"을 제거해 새로 등장한 부분만 남기고,
빈 큐와 [Music] 류 잡음을 정리한 뒤 인접한 짧은 조각을 합친다.

usage: dedupe_auto_srt.py in.srt out.srt [--min-ms 700] [--keep-music]
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
NOISE = re.compile(r"\[(music|음악|applause|박수|laughter|웃음|拍手|音楽)\]", re.I)


def ms(h, m, s, milli):
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(milli)


def ts(v):
    v = max(0, v)
    h, v = divmod(v, 3600000)
    m, v = divmod(v, 60000)
    s, v = divmod(v, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{v:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--min-ms", type=int, default=700,
                    help="이보다 짧은 큐는 다음 큐에 합친다")
    ap.add_argument("--keep-music", action="store_true",
                    help="[Music] 같은 표시를 남긴다")
    args = ap.parse_args()

    raw = Path(args.src).read_text(encoding="utf-8-sig")

    # 1) 파싱하면서 각 큐를 줄 단위로 쪼갠다
    parsed = []
    for m in CUE.finditer(raw):
        g = m.groups()
        start, end = ms(*g[1:5]), ms(*g[5:9])
        lines = [ln.strip() for ln in g[9].split("\n") if ln.strip()]
        parsed.append((start, end, lines))

    # 2) 이미 나온 줄은 버리고 새 줄만 남긴다 (롤링 윈도 제거)
    seen = []
    fresh = []
    for start, end, lines in parsed:
        new = [ln for ln in lines if ln not in seen]
        seen.extend(new)
        if len(seen) > 40:
            seen = seen[-40:]
        if not args.keep_music:
            new = [NOISE.sub("", ln).strip() for ln in new]
        new = [ln for ln in new if ln]
        if new:
            fresh.append([start, end, " ".join(new)])

    # 3) 너무 짧은 큐는 다음 큐와 합친다 (10ms 잔해 흡수)
    merged = []
    for cue in fresh:
        if merged and (cue[0] - merged[-1][1]) < 120 and (merged[-1][1] - merged[-1][0]) < args.min_ms:
            merged[-1][1] = cue[1]
            merged[-1][2] = f"{merged[-1][2]} {cue[2]}".strip()
        else:
            merged.append(cue)

    # 4) 끝 시각이 다음 시작을 넘지 않게, 최소 노출 시간 확보
    for i, cue in enumerate(merged):
        nxt = merged[i + 1][0] if i + 1 < len(merged) else cue[1] + 2000
        cue[1] = min(max(cue[1], cue[0] + args.min_ms), nxt)

    with Path(args.dst).open("w", encoding="utf-8") as f:
        for n, (start, end, text) in enumerate(merged, 1):
            f.write(f"{n}\n{ts(start)} --> {ts(end)}\n{text}\n\n")

    print(f"{len(parsed)} raw cues -> {len(merged)} cues -> {args.dst}")


if __name__ == "__main__":
    main()
