#!/usr/bin/env python3
"""ko.srt 의 특정 큐 텍스트만 교체한다. 시각은 절대 건드리지 않는다.
usage: patch_srt.py <start_index> [srt파일] <<'EOF'   (한 줄에 한 큐)
"""
import re, sys
from pathlib import Path
P = re.compile(r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\s*\n|\Z)", re.S)
p = Path(sys.argv[2] if len(sys.argv) > 2 else "ko.srt")
cues = [[m.group(2), m.group(3).strip()] for m in P.finditer(p.read_text(encoding="utf-8"))]
start = int(sys.argv[1])
lines = [l.rstrip("\n") for l in sys.stdin if l.strip()]
for i, t in enumerate(lines):
    cues[start - 1 + i][1] = t
p.write_text("\n".join(f"{i}\n{a}\n{t}\n" for i, (a, t) in enumerate(cues, 1)), encoding="utf-8")
print(f"{start}~{start+len(lines)-1} 반영 ({len(lines)}큐) / 전체 {len(cues)}")
