#!/usr/bin/env python3
"""기준 SRT와 **똑같은 큐 경계**로 두 번째 언어 SRT를 만든다.

이중 자막은 두 SRT의 큐 개수와 시각이 1:1로 맞아야 한다. 원어 자막과 번역
자막을 따로 만들면 개수가 어긋나고, 그러면 `make_ass.py` 가 시간 겹침으로
억지로 짝을 지어 엉뚱한 줄끼리 붙는다.

그래서 이미 시각이 확정된 SRT(보통 번역본)를 기준으로 잡고, 받아쓰기의 단어를
각 큐의 시간 창에 나눠 담아 두 번째 언어 SRT를 만든다. 시각은 기준 SRT에서
그대로 복사하므로 어긋날 수가 없다.

usage: align_second_lang.py base.srt words.json out.srt

주의 — 기준 SRT 는 `hold_subs.py` **적용 전** 것을 쓴다. 유지 시간을 늘린
뒤의 창은 침묵 구간까지 덮고 있어서, 그 창으로 단어를 담으면 다음 발화가
앞 큐로 딸려 들어온다.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_srt", help="시각의 기준이 되는 SRT (hold 적용 전)")
    ap.add_argument("words_json", help="whisper json (--word_timestamps True)")
    ap.add_argument("dst")
    ap.add_argument("--pad", type=float, default=0.15,
                    help="큐 경계 바깥에서도 이만큼은 걸치면 담는다 (초)")
    args = ap.parse_args()

    cues = []
    for m in CUE.finditer(Path(args.base_srt).read_text(encoding="utf-8-sig")):
        g = m.groups()
        a = (int(g[1]) * 3600 + int(g[2]) * 60 + int(g[3])) + int(g[4]) / 1000
        b = (int(g[5]) * 3600 + int(g[6]) * 60 + int(g[7])) + int(g[8]) / 1000
        cues.append([a, b, ""])

    d = json.loads(Path(args.words_json).read_text(encoding="utf-8"))
    words = [w for s in d.get("segments", []) for w in s.get("words", [])]
    if not words:
        raise SystemExit("단어 시각이 없다. whisper 를 --word_timestamps True 로 돌린다.")

    # 단어의 중심이 어느 창에 들어가는지로 배분한다. 어느 창에도 안 들어가면
    # (침묵 구간에 걸친 말) 가장 가까운 창에 넣되 pad 안쪽일 때만.
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        placed = False
        for c in cues:
            if c[0] <= mid < c[1]:
                c[2] = (c[2] + " " + w["word"].strip()).strip()
                placed = True
                break
        if not placed:
            near = min(cues, key=lambda c: min(abs(c[0] - mid), abs(c[1] - mid)))
            if min(abs(near[0] - mid), abs(near[1] - mid)) <= args.pad:
                near[2] = (near[2] + " " + w["word"].strip()).strip()

    Path(args.dst).write_text(
        "\n".join(f"{n}\n{ts(a)} --> {ts(b)}\n{t}\n" for n, (a, b, t) in enumerate(cues, 1)),
        encoding="utf-8",
    )
    empty = sum(1 for _, _, t in cues if not t)
    print(f"{len(cues)} cues -> {args.dst}  (빈 큐 {empty}개)")
    if empty:
        print("  빈 큐 = 그 시간대에 받아쓴 말이 없다는 뜻. 번역 자막만 뜬다.")


if __name__ == "__main__":
    main()
