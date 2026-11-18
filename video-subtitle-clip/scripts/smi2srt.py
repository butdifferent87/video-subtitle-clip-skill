#!/usr/bin/env python3
"""SAMI(.smi) -> SubRip(.srt) 변환.

- CP949/EUC-KR 자동 감지 후 UTF-8 출력
- <SYNC Start=ms> 단위로 큐 추출, 다음 SYNC 를 종료 시각으로 사용
- &nbsp; 만 있는 큐는 '자막 없음' 구간이므로 버림
- <br> 은 줄바꿈, 나머지 태그는 제거
"""
import html
import re
import sys
from pathlib import Path


def decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp949", "euc-kr", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def clean(chunk: str) -> str:
    chunk = re.sub(r"(?i)<br\s*/?>", "\n", chunk)
    chunk = re.sub(r"<[^>]+>", "", chunk)
    chunk = html.unescape(chunk)
    chunk = chunk.replace("\xa0", " ")
    lines = [ln.strip() for ln in chunk.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def ts(ms: int) -> str:
    ms = max(0, ms)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse(text: str):
    marks = list(re.finditer(r"(?i)<sync\s+start\s*=\s*[\"']?(-?\d+)[\"']?[^>]*>", text))
    cues = []
    for i, m in enumerate(marks):
        start = int(m.group(1))
        end_pos = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = clean(text[m.end():end_pos])
        cues.append((start, body))

    out = []
    for i, (start, body) in enumerate(cues):
        if not body:
            continue
        end = cues[i + 1][0] if i + 1 < len(cues) else start + 3000
        if end <= start:
            end = start + 1000
        out.append((start, end, body))
    return out


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".srt")
    cues = parse(decode(src.read_bytes()))
    with dst.open("w", encoding="utf-8") as f:
        for n, (start, end, body) in enumerate(cues, 1):
            f.write(f"{n}\n{ts(start)} --> {ts(end)}\n{body}\n\n")
    print(f"{len(cues)} cues -> {dst}")


if __name__ == "__main__":
    main()
