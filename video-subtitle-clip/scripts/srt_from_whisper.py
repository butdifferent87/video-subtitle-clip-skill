#!/usr/bin/env python3
"""whisper json → 원어 SRT. 시각은 측정값 그대로, 사람은 글자만 건드린다.

**이 스크립트가 있는 이유**

받아쓰기 결과를 보면서 자막표를 손으로 타이핑하면 시각이 어긋난다. 옮겨
적다가 숫자가 틀리고, 긴 문장을 감으로 쪼개면서 경계가 밀린다. 실제로 그렇게
만든 자막에서 「감히」 한 줄이 5.4초 일찍 떴다 — 그 사이는 대사가 아니라
동물 반응 소리였다.

더 나쁜 건 그 오류가 검사를 통과한다는 점이다. `check_sync.py --fix` 는
가장 가까운 단어로 당기는데, 근처에 무관한 단어가 있으면 거기에 고정시키고
"오차 0" 이라고 보고한다. 도구는 어느 단어가 그 자막의 것인지 모른다.

그래서 순서를 뒤집는다. **시각을 먼저 확정하고, 번역은 그 위에 글자만 얹는다.**
이 스크립트가 시각이 박힌 껍데기를 만들면, 번역자는 각 큐의 텍스트만 바꾼다.
시각에는 손대지 않으므로 어긋날 여지가 없다.

usage:
  whisper OUT.wav --model medium --language en --output_format json \\
      --word_timestamps True --output_dir . --condition_on_previous_text False
  srt_from_whisper.py out.json base.srt [--max-dur 8] [--min-dur 0.4]

`--max-dur` 를 넘는 큐는 고르게 나눈다 — 목표 길이만큼 모으다가 경계 부근에서
가장 벌어진 곳(숨 쉬는 자리)을 찾아 끊는다. 받아쓰기가 여러 문장을 한 덩어리로
뭉쳐 놓는 일이 흔하고(41초짜리도 나온다), 그대로 두면 번역에서 문장이 통째로 빠진다.
"""
import argparse
import re
import json
from pathlib import Path


def ts(v):
    v = max(0.0, v)
    h = int(v // 3600)
    m = int(v % 3600 // 60)
    s = int(v % 60)
    ms = int(round((v - int(v)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def sentences(words):
    """구두점 기준으로 문장을 끊는다."""
    out, buf, start = [], [], None
    for w in words:
        if start is None:
            start = w["start"]
        buf.append(w)
        if w["word"].strip()[-1:] in ".?!。？！":
            out.append((start, w["end"], buf))
            buf, start = [], None
    if buf:
        out.append((start, buf[-1]["end"], buf))
    return out


def join_cjk(ws):
    """일본어 whisper 는 단어를 글자 단위로 낸다 — 공백 없이 붙인다.
    라틴 문자·숫자끼리만 공백을 남긴다 (COP23 같은 표기 대비)."""
    out = ""
    for w in ws:
        t = w["word"].strip()
        if out and re.match(r"[A-Za-z0-9]", t) and re.search(r"[A-Za-z0-9]$", out):
            out += " "
        out += t
    return out.strip()


def split_long_cjk(start, end, ws, max_dur, min_chars=6):
    """일본어·중국어는 띄어쓰기가 없다 — 글자 수로 끊으면 단어가 쪼개진다.

    실측(악센트 강의): 「大きく分/ける」「ド/レミ」「高いか低い/か」.
    그래서 **구두점(、。？！)에서만** 끊고, 구두점이 없으면 가장 크게 쉬는
    자리에서 끊는다. 목표 길이를 조금 넘기더라도 말 덩어리를 지키는 쪽이 낫다.
    """
    if end - start <= max_dur or len(ws) < min_chars * 2:
        return [(start, end, ws)]
    # 구두점이 아예 없는 세그먼트가 흔하다(실측 14초 한 덩어리). 그래서 구두점만
    # 보지 않고, 「문장이 끝나는 꼴」과 조사에 점수를 줘서 문절 경계를 찾는다.
    text_at = lambda k: "".join(w["word"].strip() for w in ws[:k])
    TAIL2 = ("です","ます","した","ない","ある","いる","ので","から","けど","こと","もの","とか","ですね","ますね")
    PARTICLE = "はがをにでともねよかやのへ"
    NG_NEXT = "ゃゅょっーんアィゥェォ"      # 이 글자로 시작하면 단어 중간이다
    def score(k):
        before = text_at(k)
        if not before: return -9
        nxt = ws[k]["word"].strip()[:1]
        sc = 0
        if before[-1] in "、。？！，.": sc += 5
        elif any(before.endswith(t) for t in TAIL2): sc += 3
        elif before[-1] in PARTICLE: sc += 2
        if nxt and nxt in NG_NEXT: sc -= 4
        if before[-1] in "ゃゅょっー": sc -= 4
        return sc
    puncts = [k for k in range(1, len(ws)) if score(k) >= 2]
    out, i = [], 0
    while i < len(ws):
        j = i + min_chars
        while j < len(ws) and ws[j]["end"] - ws[i]["start"] < max_dur:
            j += 1
        if len(ws) - j < min_chars:
            j = len(ws)
        if j < len(ws):
            # 목표 지점 근처(최대 1.6배 길이까지)의 구두점을 최우선으로 고른다
            cap = ws[i]["start"] + max_dur * 1.6
            cand = [k for k in puncts if i + min_chars <= k <= len(ws) - min_chars and ws[k-1]["end"] <= cap]
            if cand:
                # 점수 높은 자리 우선, 같으면 목표 지점에 가까운 쪽
                j = max(cand, key=lambda k: (score(k), -abs(k - j)))
            else:
                lo = max(i + min_chars, j - max(2, (j - i) // 3))
                hi = min(len(ws) - min_chars, j + 3)
                if lo < hi:
                    j = max(range(lo, hi), key=lambda k: ws[k]["start"] - ws[k-1]["end"])
        chunk = ws[i:j]
        out.append((chunk[0]["start"], chunk[-1]["end"], chunk))
        i = j
    return out


def split_long(start, end, ws, max_dur, min_words=3):
    """긴 큐를 고르게 나눈다.

    가장 벌어진 곳에서 재귀적으로 자르면 안 된다. 말이 촘촘한 구간은 간격이
    다 비슷해서 아무 데나 잘리고, 그 결과 두 단어짜리 조각이 우수수 생긴다.
    대신 앞에서부터 목표 길이만큼 모으다가, **경계 부근에서 가장 벌어진 곳**을
    찾아 그곳에서 끊는다. 길이가 고르면서 숨 쉬는 자리를 살릴 수 있다.
    """
    if end - start <= max_dur or len(ws) < min_words * 2:
        return [(start, end, ws)]

    out = []
    i = 0
    while i < len(ws):
        j = i + min_words
        while j < len(ws) and ws[j]["end"] - ws[i]["start"] < max_dur:
            j += 1
        if len(ws) - j < min_words:      # 남은 꼬리가 너무 짧으면 합친다
            j = len(ws)
        if j < len(ws):
            # 경계 앞뒤 창에서 끊을 자리를 고른다. 쉼표·마침표 뒤가 최우선이고,
            # 없으면 가장 벌어진 곳으로 간다. 구절 한가운데서 자르면
            # ("While his back was turned, this" / "kid did what...") 읽기 나쁘다.
            lo = max(i + min_words, j - max(2, (j - i) // 3))
            hi = min(len(ws) - min_words, j + 2)
            if lo < hi:
                def score(k):
                    prev = ws[k - 1]["word"].strip()
                    at_punct = prev[-1:] in ",.?!;:、。？！"
                    return (at_punct, ws[k]["start"] - ws[k - 1]["end"])
                j = max(range(lo, hi), key=score)
        chunk = ws[i:j]
        out.append((chunk[0]["start"], chunk[-1]["end"], chunk))
        i = j
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words_json")
    ap.add_argument("dst")
    ap.add_argument("--max-dur", type=float, default=8.0,
                    help="이보다 긴 큐는 쪼갠다 (초)")
    ap.add_argument("--min-dur", type=float, default=0.4,
                    help="이보다 짧은 큐는 최소 이 길이로 늘린다 (초)")
    ap.add_argument("--cjk", action="store_true",
                    help="일본어·중국어: 단어를 공백 없이 붙이고 、。？！ 에서 끊는다")
    args = ap.parse_args()

    d = json.loads(Path(args.words_json).read_text(encoding="utf-8"))
    words = [w for s in d.get("segments", []) for w in s.get("words", [])]
    if not words:
        raise SystemExit(
            f"{args.words_json} 에 단어 시각이 없다. "
            "whisper 를 --word_timestamps True 로 다시 돌린다."
        )

    cues = []
    if args.cjk:
        # 🔴 일본어는 whisper 의 **세그먼트를 그대로 쓴다.**
        # 세그먼트는 이미 문장 단위로 끊겨 있는데(실측 257개 / 21분), 글자 수로
        # 다시 쪼개면 「大きく分/ける」「ド/レミ」처럼 단어가 갈린다. 띄어쓰기가
        # 없어서 경계를 알 수 없기 때문이다. 긴 것만 、。 에서 나눈다.
        for seg in d.get("segments", []):
            sw = seg.get("words") or []
            txt = join_cjk(sw) if sw else seg.get("text", "").strip()
            a, b = seg["start"], seg["end"]
            if not txt: continue
            if b - a <= args.max_dur * 2 or not sw:
                cues.append([a, max(b, a + args.min_dur), txt]); continue
            # 너무 길면 구두점에서 나눈다 (없으면 그대로 둔다 — 쪼개느니 긴 게 낫다)
            cut = [k for k in range(1, len(sw)) if sw[k-1]["word"].strip()[-1:] in "、。？！"]
            if not cut:
                cues.append([a, max(b, a + args.min_dur), txt]); continue
            prev = 0
            for k in list(cut) + [len(sw)]:
                if k - prev < 2: continue
                part = sw[prev:k]
                if part[-1]["end"] - part[0]["start"] < 1.0 and k != len(sw): continue
                cues.append([part[0]["start"], part[-1]["end"], join_cjk(part)])
                prev = k
            if prev < len(sw):
                part = sw[prev:]
                cues[-1][1] = part[-1]["end"]
                cues[-1][2] += join_cjk(part)
        cues = [c for c in cues if c[2]]
    else:
     for start, end, ws in sentences(words):
        for a, b, chunk in split_long(start, end, ws, args.max_dur):
            if args.cjk:
                # 일본어 whisper 는 단어를 글자 단위로 낸다 — 공백 없이 붙인다.
                # 라틴 문자끼리만 공백을 남긴다 (COP23, ドイツ 같은 혼용 대비).
                text = ""
                for w in chunk:
                    t = w["word"].strip()
                    if text and re.match(r"[A-Za-z0-9]", t) and re.search(r"[A-Za-z0-9]$", text):
                        text += " "
                    text += t
                text = text.strip()
            else:
                text = " ".join(w["word"].strip() for w in chunk).strip()
            if text:
                cues.append([a, max(b, a + args.min_dur), text])

    # 겹침 정리 — 뒤 큐가 앞 큐보다 먼저 시작하면 앞을 잘라 맞춘다
    cues.sort(key=lambda c: c[0])
    for i in range(len(cues) - 1):
        if cues[i][1] > cues[i + 1][0]:
            cues[i][1] = cues[i + 1][0]

    Path(args.dst).write_text(
        "\n".join(f"{n}\n{ts(a)} --> {ts(b)}\n{t}\n" for n, (a, b, t) in enumerate(cues, 1)),
        encoding="utf-8",
    )
    longest = max(b - a for a, b, _ in cues)
    print(f"{len(cues)} cues -> {args.dst}")
    print(f"  가장 긴 큐 {longest:.1f}초 · 총 {cues[-1][1]:.1f}초")
    print("  이제 각 큐의 **글자만** 번역으로 바꾼다. 시각은 건드리지 않는다.")


if __name__ == "__main__":
    main()
