#!/usr/bin/env python3
"""자막 전체가 일정하게 밀렸는지 찾아낸다 (오프셋 스윕).

**check_sync.py 로는 이걸 못 잡는다.** check_sync 는 자막마다 가장 가까운
단어를 찾아 오차를 재는데, 말이 촘촘한 소재는 어떤 오프셋에서도 0.5초 안에
단어가 하나쯤 있다. 실제로 0.53초 밀린 자막이 "중앙 오차 0.065초"로 통과했다.

그래서 기준을 바꾼다 — 단어가 아니라 **발화 시작점**(앞 단어와 gap 초 이상
떨어진 단어 = 새로 말을 시작하는 순간)에 맞춰보고, 오프셋을 훑어 일치 개수가
가장 많은 지점을 찾는다. 일치 개수는 오프셋에 따라 뚜렷한 봉우리를 그린다.

usage: find_offset.py subs.srt words.json [--range 3] [--gap 0.4] [--tol 0.3]
       find_offset.py subs.srt words.json --apply out.srt   (최적 오프셋 적용)
"""
import argparse, json, re, statistics
from pathlib import Path

CUE = re.compile(
    r"(\d+)[^\S\n]*\n"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*-->[^\S\n]*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*\n"
    r"(.*?)(?=\n\s*\n|\Z)", re.S)

def ts(v):
    v = max(0.0, v); h=int(v//3600); m=int(v%3600//60); s=int(v%60); ms=int(round((v-int(v))*1000))
    if ms == 1000: s, ms = s+1, 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srt"); ap.add_argument("words_json")
    ap.add_argument("--range", type=float, default=3.0, help="훑을 범위 ±초")
    ap.add_argument("--gap", type=float, default=0.4, help="이만큼 쉬면 새 발화의 시작으로 본다")
    ap.add_argument("--tol", type=float, default=0.3, help="일치로 칠 오차")
    ap.add_argument("--snap", type=float, default=0.35,
                    help="적용 시, 이 안에 발화 시작점이 있으면 거기에 딱 맞춘다")
    ap.add_argument("--apply", help="최적 오프셋(+스냅)을 적용해 저장할 파일")
    args = ap.parse_args()

    cues = []
    for m in CUE.finditer(Path(args.srt).read_text(encoding="utf-8-sig")):
        g = m.groups()
        a = int(g[1])*3600+int(g[2])*60+int(g[3])+int(g[4])/1000
        b = int(g[5])*3600+int(g[6])*60+int(g[7])+int(g[8])/1000
        cues.append([a, b, g[9].strip()])

    d = json.loads(Path(args.words_json).read_text(encoding="utf-8"))
    words = sorted(w["start"] for s in d.get("segments", []) for w in s.get("words", []))
    if not words:
        raise SystemExit("단어 시각이 없다. whisper 를 --word_timestamps True 로 돌린다.")
    onsets = [w for i, w in enumerate(words) if i == 0 or w - words[i-1] > args.gap]

    def hits(off):
        return sum(1 for a, _, _ in cues if min(abs(o-(a+off)) for o in onsets) < args.tol)

    steps = [k/100 for k in range(int(-args.range*100), int(args.range*100)+1, 5)]
    table = [(off, hits(off)) for off in steps]
    best_off, best_hit = max(table, key=lambda x: x[1])
    base_hit = hits(0.0)

    print(f"자막 {len(cues)}개 / 단어 {len(words)}개 / 발화 시작점 {len(onsets)}개")
    print(f"오프셋 0 일치 {base_hit}/{len(cues)}  →  최적 {best_off:+.2f}초 일치 {best_hit}/{len(cues)}")
    for off, h in table:
        if abs(off - best_off) <= 0.5 or h >= base_hit:
            bar = "#" * int(h * 40 / len(cues))
            print(f"  {off:+5.2f}  {h:3d}  {bar}" + ("  <-- 최적" if off == best_off else ""))

    if abs(best_off) < 0.1:
        print("\n밀림 없음.")
    else:
        print(f"\n🔴 자막이 {abs(best_off):.2f}초 {'늦다' if best_off < 0 else '이르다'}.")

    # 구간별로도 재서 드리프트(프레임레이트 불일치) 여부를 본다
    if cues:
        span = cues[-1][0]
        print("\n구간별 최적 오프셋 (값이 흐르면 프레임레이트 불일치 의심):")
        for i in range(4):
            lo, hi = span*i/4, span*(i+1)/4
            sub = [c for c in cues if lo <= c[0] < hi]
            if len(sub) < 5: continue
            def h2(off): return sum(1 for a,_,_ in sub if min(abs(o-(a+off)) for o in onsets) < args.tol)
            bo = max(steps, key=h2)
            print(f"  {lo/60:4.1f}~{hi/60:4.1f}분  {bo:+5.2f}초  ({len(sub)}개)")

    if args.apply:
        snapped = 0
        for c in cues:
            dur = c[1] - c[0]
            na = c[0] + best_off
            near = min(onsets, key=lambda o: abs(o-na))
            if abs(near-na) <= args.snap:
                na = near; snapped += 1
            c[0], c[1] = na, na + dur
        for i in range(len(cues)-1):
            if cues[i][1] > cues[i+1][0]: cues[i][1] = cues[i+1][0]
        Path(args.apply).write_text(
            "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i,(a,b,t) in enumerate(cues,1)), encoding="utf-8")
        errs = [min(abs(o-a) for o in onsets) for a,_,_ in cues]
        print(f"\n{best_off:+.2f}초 이동 + {snapped}개 스냅 -> {args.apply}")
        print(f"  중앙 오차 {statistics.median(errs):.3f}초")
        print("  ⚠️ 두 번째 언어 자막이 있으면 같은 보정을 똑같이 적용해야 짝이 유지된다.")

if __name__ == "__main__":
    main()
