#!/usr/bin/env python3
"""잘게 잘린 원어 큐를 「문장 단위」 큐로 다시 묶는다. 번역은 이 결과 위에 얹는다.

**이 스크립트가 있는 이유**

srt_from_whisper.py --max-dur 4 는 말을 시간으로 자른다. 문장을 길게 잇는
화자(실측: Woody Aragon DVD 2.5시간, 2,783큐)는 거의 모든 문장이 중간에서
잘리고, 번역을 그 조각에 1:1로 맞추면 한국어가 「…쇼거든요. 쇼를 보고」처럼
다음 문장 머리를 매단 채 끝난다. qc.py 가 「한국어 문장 절단 484곳」으로
경고했는데도 그대로 넘겼다가 오너가 화면을 보고 지적했다(2026-11-20).

**규칙**
- 원어 큐를 이어 붙이다가 문장이 끝나면(. ? !) 끊는다.
- 문장이 너무 길면(--max-dur 초 또는 --max-chars 글자) 쉼표 뒤 → 큰 쉼(0.3초+)
  순으로 자리를 찾아 끊는다. 그래도 없으면 한도에서 끊는다.
- 말 사이 공백이 --gap 초보다 크면 문장이 안 끝났어도 끊는다(장면 전환).
- 시각은 측정값만 쓴다: 묶음의 시작 = 첫 큐 시작, 끝 = 마지막 큐 끝. 새 경계를 손으로
  찍지 않으므로 싱크가 깨지지 않는다(SKILL 2-c 「병합은 허용」).

usage: regroup_sentences.py base.srt sent.srt [--max-dur 7] [--max-chars 90] [--gap 1.2]
"""
import argparse
import re
from pathlib import Path

P = re.compile(r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\s*\n|\Z)", re.S)
END = re.compile(r"[.?!…][\"')\]]*$")
SOFT = re.compile(r"[,;:][\"')\]]*$")


def sec(t):
    h, m, s = t.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def ts(v):
    ms = int(round(max(0.0, v) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--max-dur", type=float, default=7.0)
    ap.add_argument("--max-chars", type=int, default=90)
    ap.add_argument("--gap", type=float, default=1.2)
    a = ap.parse_args()

    cues = [(sec(m.group(2)), sec(m.group(3)), " ".join(m.group(4).split()))
            for m in P.finditer(Path(a.src).read_text(encoding="utf-8"))]
    groups, cur = [], []

    def flush(part):
        if part:
            groups.append((part[0][0], part[-1][1], " ".join(c[2] for c in part)))

    for c in cues:
        if cur:
            gap = c[0] - cur[-1][1]
            dur = c[1] - cur[0][0]
            chars = sum(len(x[2]) + 1 for x in cur) + len(c[2])
            if gap > a.gap:
                flush(cur)
                cur = []
            elif dur > a.max_dur or chars > a.max_chars:
                # 넘친다 → 지금 묶음 안에서 가장 좋은 끊을 자리: 쉼표 뒤 > 큰 쉼 > 바로 여기
                best = next((j for j in range(len(cur) - 1, 0, -1) if SOFT.search(cur[j - 1][2])), None)
                if best is None and len(cur) > 1:
                    g, j = max((cur[j][0] - cur[j - 1][1], j) for j in range(1, len(cur)))
                    best = j if g >= 0.3 else None
                if best:
                    flush(cur[:best])
                    cur = cur[best:]
                else:
                    flush(cur)
                    cur = []
        cur.append(c)
        if END.search(c[2]):
            flush(cur)
            cur = []
    flush(cur)

    Path(a.dst).write_text(
        "\n".join(f"{i}\n{ts(s)} --> {ts(e)}\n{t}\n" for i, (s, e, t) in enumerate(groups, 1)),
        encoding="utf-8")
    durs = [e - s for s, e, _ in groups]
    ends = sum(1 for *_, t in groups if END.search(t))
    print(f"{len(cues)} -> {len(groups)} cues · 문장 끝으로 끝나는 큐 {ends}/{len(groups)} "
          f"({ends * 100 // max(len(groups), 1)}%) · 최장 {max(durs):.1f}초 · 평균 {sum(durs) / len(durs):.1f}초")


if __name__ == "__main__":
    main()
