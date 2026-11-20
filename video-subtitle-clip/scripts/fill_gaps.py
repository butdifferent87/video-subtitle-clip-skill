"""VAD 로 빠졌던 구간 채우기.

gap   : fill_gaps.py gap  OLD.srt NEW.srt OUT_gap.srt
        NEW(VAD 끔) 큐 중 OLD(기존 자막) 와 거의 안 겹치는 것만 뽑는다. 환각 문구는 버린다.
        겹치는 끝은 잘라서 기존 자막과 시간이 겹치지 않게 한다.
merge : fill_gaps.py merge OLD.srt ADD.srt OUT.srt
        두 srt 를 시각순으로 합치고 번호를 다시 매긴다.
"""
import re, sys

HALLU = ["ご視聴ありがとうございました", "ご視聴ありがとうございます", "チャンネル登録", "最後までご視聴",
         "Thank you for watching", "Thanks for watching", "Subtitles by", "Transcription by",
         "시청해 주셔서 감사합니다", "구독과 좋아요"]   # fw_transcribe.py 와 fill_gaps.py 에서 같게 유지


def is_hallu(text):
    """HALLU 문구와 구두점·공백을 지우고 남는 글자가 3자 이하면 환각으로 본다 (정상 대사는 남긴다)."""
    t = text.lower()
    if not any(h.lower() in t for h in HALLU):
        return False
    for h in HALLU:
        t = t.replace(h.lower(), "")
    return len(re.sub(r"[\W_]+", "", t)) <= 3


def ts(s):
    h, m, rest = s.split(":"); sec, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def fmt(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def read(p):
    out = []
    for blk in re.split(r"\n\s*\n", open(p, encoding="utf-8-sig").read().strip()):
        ln = blk.strip().splitlines()
        if len(ln) < 2 or "-->" not in ln[1]:
            continue
        a, b = [x.strip() for x in ln[1].split("-->")]
        out.append([ts(a), ts(b), "\n".join(ln[2:])])
    return out


def write(cues, p):
    with open(p, "w", encoding="utf-8") as f:
        for i, (a, b, t) in enumerate(cues, 1):
            f.write(f"{i}\n{fmt(a)} --> {fmt(b)}\n{t}\n\n")


def gap(old_p, new_p, out_p):
    old = sorted(read(old_p)); new = read(new_p); keep = []; drop_h = 0
    for a, b, t in new:
        if is_hallu(t):
            drop_h += 1; continue
        ov = sum(max(0, min(b, ob) - max(a, oa)) for oa, ob, _ in old if ob > a and oa < b)
        if ov > 0.3 * (b - a):
            continue
        # 기존 자막과 겹치는 끝을 잘라낸다
        for oa, ob, _ in old:
            if oa <= a < ob: a = ob
            if oa < b <= ob: b = oa
        # 기존 큐를 통째로 감싸는 경우 등, 잘라도 아직 겹치면 버린다
        if any(oa < b and ob > a for oa, ob, _ in old):
            continue
        if b - a >= 0.4:
            keep.append([a, b, t])
    write(keep, out_p)
    print(f"new {len(new)} -> gap {len(keep)} (환각 문구 {drop_h} 버림) -> {out_p}")


def merge(old_p, add_p, out_p):
    cues = sorted(read(old_p) + read(add_p))
    fixed = 0
    for x, y in zip(cues, cues[1:]):          # 겹치면 앞 큐를 뒤 큐 시작에서 끊는다
        if y[0] < x[1]:
            x[1] = y[0]; fixed += 1
    short = [c for c in cues if c[1] - c[0] < 0.3]
    cues = [c for c in cues if c[1] - c[0] >= 0.3]
    write(cues, out_p)
    print(f"{len(cues)} cues (겹침 {fixed}곳 끊음, 0.3초 미만 {len(short)}개 버림) -> {out_p}")


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] not in ("gap", "merge"):
        sys.exit(__doc__)
    {"gap": gap, "merge": merge}[sys.argv[1]](*sys.argv[2:5])
