#!/usr/bin/env python3
"""번역자가 「뜻 단위」로 묶은 큐 범위로 이중 자막을 만든다. 시각은 원래 큐의 측정값만 쓴다.

**왜 이 단계가 있나**

받아쓰기는 말을 시간(--max-dur 4)으로 자르고, 쉼 없이 말하는 화자는 마침표도
거의 안 찍힌다(실측 Woody DVD: 문장 끝 부호로 끝나는 큐 43%). 그래서 기계가
문장 경계를 못 찾는다 → regroup_sentences.py 만으로는 부족하다.
번역자(사람이든 모델이든)는 뜻을 아니까, **연속된 원어 큐를 한 문장 단위로 묶고**
그 묶음마다 원어 교정본 + 번역을 낸다. 이 스크립트는 그 묶음을 검사하고 SRT 로 만든다.

입력 groups.tsv — 한 줄에 한 묶음, 탭 구분:
  시작큐<TAB>끝큐<TAB>교정한 원어<TAB>번역
  예) 3	5	In this DVD I will share a special show I built for you.	이번 DVD에서는 여러분을 위해 만든 특별한 쇼를 보여드릴게요.

검사(하나라도 걸리면 멈춘다):
  - 범위가 1부터 끝 큐까지 빈틈·겹침 없이 이어지는가
  - 묶음 길이가 --max-dur 초를 넘지 않는가 (넘으면 목록만 경고)
  - 빈 원어·번역이 없는가

usage: build_from_groups.py base.srt groups.tsv dual.srt [--max-dur 10] [--ko ko.srt] [--en en.srt]
       (dual.srt = 위 번역 / 아래 원어 한 큐 두 줄)
"""
import argparse
import re
import sys
from pathlib import Path

P = re.compile(r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\s*\n|\Z)", re.S)


def sec(t):
    h, m, s = t.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


ap = argparse.ArgumentParser()
ap.add_argument("base")
ap.add_argument("groups")
ap.add_argument("dst")
ap.add_argument("--max-dur", type=float, default=10.0)
ap.add_argument("--ko")
ap.add_argument("--en")
a = ap.parse_args()

base = [(m.group(2), m.group(3)) for m in P.finditer(Path(a.base).read_text(encoding="utf-8"))]
rows = []
for ln, line in enumerate(Path(a.groups).read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
        continue
    parts = line.split("\t")
    if len(parts) != 4:
        sys.exit(f"{a.groups}:{ln} 칸이 4개가 아니다: {line[:80]}")
    s, e, en, ko = int(parts[0]), int(parts[1]), parts[2].strip(), parts[3].strip()
    if not en or not ko:
        sys.exit(f"{a.groups}:{ln} 빈 원어/번역")
    rows.append((s, e, en, ko))

expect = 1
for s, e, *_ in rows:
    if s != expect or e < s:
        sys.exit(f"범위가 어긋났다: {expect}번부터 와야 하는데 {s}-{e}. 빈틈·겹침을 고쳐라.")
    expect = e + 1
if expect - 1 != len(base):
    sys.exit(f"끝 큐가 {expect - 1} — 원본은 {len(base)}개. 뒤쪽이 빠졌다.")

long = [(s, e, round(sec(base[e - 1][1]) - sec(base[s - 1][0]), 1)) for s, e, *_ in rows
        if sec(base[e - 1][1]) - sec(base[s - 1][0]) > a.max_dur]

out, ko_out, en_out = [], [], []
for i, (s, e, en, ko) in enumerate(rows, 1):
    t = f"{base[s - 1][0]} --> {base[e - 1][1]}"
    out.append(f"{i}\n{t}\n{ko}\n{en}\n")
    ko_out.append(f"{i}\n{t}\n{ko}\n")
    en_out.append(f"{i}\n{t}\n{en}\n")
Path(a.dst).write_text("\n".join(out), encoding="utf-8")
if a.ko:
    Path(a.ko).write_text("\n".join(ko_out), encoding="utf-8")
if a.en:
    Path(a.en).write_text("\n".join(en_out), encoding="utf-8")
print(f"{len(base)} 큐 -> {len(rows)} 묶음 -> {a.dst}")
if long:
    print(f"⚠ {a.max_dur:.0f}초 넘는 묶음 {len(long)}개: {long[:15]}")
