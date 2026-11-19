#!/usr/bin/env python3
"""마술별 「연출」「해법」 타임 마커 -> 팟플레이어 책갈피(.pbf) + 목록(.txt) + ffmpeg 챕터(.ffmeta).

입력 markers.tsv (UTF-8, 한 줄에 마커 하나, # 로 시작하면 주석):
    시각<TAB>마술 이름<TAB>구분
    00:05:52	Ring off Rope	연출
    00:41:10	Ring off Rope	해법
  시각: hh:mm:ss / hh:mm:ss.mmm / mm:ss / 초(float)
  구분: 연출 | 해법 | 기타 (인트로·잡담·크레딧 등)

사용:
  python make_markers.py markers.tsv "OUT_DIR/영상이름"            # 영상이름.pbf, 영상이름_markers.txt, 영상이름.ffmeta
  python make_markers.py markers.tsv "OUT_DIR/영상이름" --offset -763 # 구간 클립: 원본 기준 시각을 클립 기준으로
  python make_markers.py markers.tsv "OUT_DIR/영상이름" --duration 129 # 챕터 끝 시각(마지막 챕터) 지정

- .pbf 는 영상과 **같은 폴더, 같은 이름**이어야 팟플레이어가 자동으로 읽는다.
- .ffmeta 는 자막을 구운 뒤 mp4 에 챕터로 심을 때 쓴다(재인코딩 없음, 수 초):
    ffmpeg -i IN.mp4 -i 영상이름.ffmeta -map 0 -map_chapters 1 -c copy OUT.mp4
"""
import argparse, os, sys

KINDS = {"연출", "해법", "기타"}


def parse_time(s):
    s = s.strip()
    if ":" not in s:
        return float(s)
    parts = [float(p) for p in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, sec = parts
    return h * 3600 + m * 60 + sec


def fmt(t):
    t = max(0, int(round(t)))
    return f"{t // 3600:d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("out_base", help="출력 경로 + 영상 이름(확장자 없이)")
    ap.add_argument("--offset", type=float, default=0.0, help="모든 시각에 더할 초 (클립이면 -구간시작)")
    ap.add_argument("--duration", type=float, default=None, help="영상 길이(초). 마지막 챕터의 끝")
    a = ap.parse_args()

    rows, bad, dropped = [], [], []
    for n, line in enumerate(open(a.tsv, encoding="utf-8-sig"), 1):
        line = line.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 3 or f[2].strip() not in KINDS:
            bad.append(f"{n}: {line}")
            continue
        t = parse_time(f[0]) + a.offset
        if t < 0 or (a.duration is not None and t > a.duration):
            dropped.append(f"{f[1].strip()} ({f[2].strip()})")
            continue  # 클립 범위 밖
        rows.append((t, f[1].strip(), f[2].strip()))
    if bad:
        sys.exit("형식 오류 (시각<TAB>이름<TAB>연출|해법|기타):\n" + "\n".join(bad))
    if not rows:
        sys.exit("마커가 없다")
    rows.sort()

    if dropped:
        print("  범위 밖이라 뺀 마커(짝이 잘렸으면 「해법 없음」은 오탐):", ", ".join(dropped), file=sys.stderr)

    def label(name, kind):
        s = name if kind == "기타" else f"{name} — {kind}"
        return s.replace("*", "＊")  # .pbf 는 * 를 구분자로 쓴다
    os.makedirs(os.path.dirname(os.path.abspath(a.out_base)), exist_ok=True)

    # 1) 팟플레이어 책갈피: UTF-16 LE(BOM), CRLF, "번호=밀리초*제목*"
    pbf = ["[Bookmark]"] + [f"{i}={int(round(t * 1000))}*{label(n, k)}*" for i, (t, n, k) in enumerate(rows)]
    pbf.append(f"{len(rows)}=")
    with open(a.out_base + ".pbf", "w", encoding="utf-16", newline="\r\n") as fh:
        fh.write("\n".join(pbf) + "\n")

    # 2) 사람이 읽는 목록
    txt = [f"{fmt(t)}  [{k}]  {n}" for t, n, k in rows]
    names = []
    for _, n, k in rows:
        if k != "기타" and n not in names:
            names.append(n)
    missing = [n for n in names if not any(r[1] == n and r[2] == "해법" for r in rows)]
    head = [f"# 마술 {len(names)}개, 마커 {len(rows)}개"]
    if missing:
        head.append("# 해법 마커 없음(시연만 있거나 해설이 다른 디스크): " + ", ".join(missing))
    open(a.out_base + "_markers.txt", "w", encoding="utf-8").write("\n".join(head + [""] + txt) + "\n")

    # 3) ffmpeg 챕터
    # 첫 챕터가 0초가 아니면 mp4 로 심을 때 ffmpeg 가 챕터 시각을 앞으로 당겨 버린다(실측) -> 0초에 「시작」 챕터를 깐다
    chap = rows if rows[0][0] < 0.5 else [(0.0, "시작", "기타")] + rows
    meta = [";FFMETADATA1"]
    for i, (t, n, k) in enumerate(chap):
        end = chap[i + 1][0] if i + 1 < len(chap) else (a.duration or t + 1)
        title = label(n, k).replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(t * 1000)}", f"END={int(end * 1000)}", f"title={title}"]
    open(a.out_base + ".ffmeta", "w", encoding="utf-8").write("\n".join(meta) + "\n")

    print(f"마커 {len(rows)}개 (마술 {len(names)}개) -> {a.out_base}.pbf / _markers.txt / .ffmeta")
    if missing:
        print("  해법 없음:", ", ".join(missing))


if __name__ == "__main__":
    main()
