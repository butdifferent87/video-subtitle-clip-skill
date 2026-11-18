#!/usr/bin/env python3
"""같은 타임코드의 두 SRT를 한 큐 두 줄(위 번역 / 아래 원어)로 합친다.

소프트섭으로 이중 자막을 내려면 트랙이 하나여야 한다. 두 트랙을 동시에
켜는 플레이어는 드물기 때문이다. 타임코드가 1:1이므로(align_second_lang.py
가 보장) 텍스트만 겹쳐 쓰면 된다.

usage: merge_dual_srt.py ko.srt en.srt dual.srt
"""
import re, sys
from pathlib import Path
P = re.compile(r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\s*\n|\Z)", re.S)
def rd(f): return [(m.group(2), m.group(3).strip()) for m in P.finditer(Path(f).read_text(encoding="utf-8"))]
a, b, dst = sys.argv[1], sys.argv[2], sys.argv[3]
x, y = rd(a), rd(b)
if len(x) != len(y):
    raise SystemExit(f"큐 수가 다르다 ({len(x)} vs {len(y)}). align_second_lang.py 로 맞춰라.")
bad = [i+1 for i, (p, q) in enumerate(zip(x, y)) if p[0] != q[0]]
if bad:
    raise SystemExit(f"타임코드가 어긋난 큐: {bad[:10]}")
Path(dst).write_text("\n".join(f"{i}\n{t}\n{k}\n{e}\n" for i, ((t, k), (_, e)) in enumerate(zip(x, y), 1)), encoding="utf-8")
print(f"{len(x)} cues -> {dst}")
