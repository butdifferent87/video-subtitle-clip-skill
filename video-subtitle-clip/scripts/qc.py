import json
#!/usr/bin/env python3
"""자막 품질 검사 — 층별로 나눠서 한 번에 돌린다.

각 층은 **서로 다른 실패 모드**를 잡는다. 아래 층이 통과했다고 위층이
보장되지 않는다. 실제로 싱크가 완벽한데 이중자막 짝이 단어 중간에서
잘려 있던 적이 있고, 번역이 완벽한데 폰트가 없어 두부가 뜬 적이 있다.

  L1 큐 구조   개수·타임코드 일치·겹침·빈 큐·중복
  L2 시각      전체 밀림(오프셋 스윕)·드리프트
  L5 짝 맞춤   각 줄이 그 자체로 읽히는가(단어 중간 절단·중복 어구)
  L6 렌더 전   폰트 글리프 커버리지·줄 폭 초과

usage:
  qc.py --kr ko.srt [--other ja.srt] [--words seg.json]
        [--font "Gmarket Sans Medium" --size 36]
        [--font2 "Hiragino Sans" --size2 18] [--width 1920]
"""
import argparse, glob, json, re, statistics, sys, unicodedata
from pathlib import Path

CUE = re.compile(
    r"(\d+)[^\S\n]*\n"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*-->[^\S\n]*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*\n"
    r"(.*?)(?=\n\s*\n|\Z)", re.S)

FAIL, WARN, OK = "FAIL", "warn", "ok"
results = []
def report(layer, name, status, detail=""):
    results.append((layer, name, status, detail))

def read(f):
    out = []
    for m in CUE.finditer(Path(f).read_text(encoding="utf-8-sig")):
        g = m.groups()
        a = int(g[1])*3600+int(g[2])*60+int(g[3])+int(g[4])/1000
        b = int(g[5])*3600+int(g[6])*60+int(g[7])+int(g[8])/1000
        out.append((a, b, g[9].strip()))
    return out

# ---------- L1 큐 구조 ----------
def layer1(kr, other):
    n = len(kr)
    report("L1", "큐 개수", OK, f"{n}개")
    bad = [i+1 for i,(a,b,_) in enumerate(kr) if b <= a]
    report("L1", "길이 0 이하", FAIL if bad else OK, f"{bad[:8]}" if bad else "")
    ov = [i+1 for i in range(n-1) if kr[i][1] > kr[i+1][0] + 1e-6]
    report("L1", "큐 겹침", FAIL if ov else OK, f"{len(ov)}개 {ov[:8]}" if ov else "")
    empty = [i+1 for i,(_,_,t) in enumerate(kr) if not t]
    report("L1", "빈 큐", WARN if empty else OK, f"{len(empty)}개 {empty[:8]}" if empty else "")
    dup = [i+2 for i in range(n-1) if kr[i][2] and kr[i][2] == kr[i+1][2]]
    report("L1", "연속 중복 텍스트", WARN if dup else OK, f"{len(dup)}개 {dup[:8]}" if dup else "")
    if other is not None:
        if len(other) != n:
            report("L1", "두 트랙 큐 수", FAIL, f"{n} vs {len(other)} — 이중자막 짝이 깨진다")
        else:
            diff = [i+1 for i in range(n) if abs(other[i][0]-kr[i][0])>0.001 or abs(other[i][1]-kr[i][1])>0.001]
            report("L1", "두 트랙 타임코드", FAIL if diff else OK,
                   f"{len(diff)}개 불일치 {diff[:8]}" if diff else "완전 동일")

# ---------- L2 시각 ----------
def layer2(kr, words_json, gap=0.4, tol=0.3, rng=3.0):
    if not words_json:
        report("L2", "시각 검사", WARN, "words.json 없음 — 건너뜀")
        return
    d = json.loads(Path(words_json).read_text(encoding="utf-8"))
    words = sorted(w["start"] for s in d.get("segments", []) for w in s.get("words", []))
    if not words:
        report("L2", "시각 검사", WARN, "단어 시각 없음"); return
    onsets = [w for i,w in enumerate(words) if i==0 or w-words[i-1] > gap]
    starts = [a for a,_,t in kr if t]
    def hits(off): return sum(1 for a in starts if min(abs(o-(a+off)) for o in onsets) < tol)
    steps = [k/100 for k in range(int(-rng*100), int(rng*100)+1, 5)]
    best = max(steps, key=hits)
    h0, hb = hits(0.0), hits(best)
    # 절대 증가분이 아니라 '봉우리가 얼마나 뾰족한가'로 본다.
    # 실측: 진짜 0.53초 밀림 = 50→98 (1.96배). 보정 후 잔여 = 99→108 (1.09배, 잡음).
    ratio = hb / max(h0, 1)
    st = FAIL if (abs(best) >= 0.15 and ratio >= 1.30) else (
         WARN if (abs(best) >= 0.15 and ratio >= 1.12) else OK)
    tail = {FAIL: "  ← 이만큼 이동해야 한다", WARN: "  애매 — 앵커 대사로 눈 확인",
            OK: "  봉우리 평평 = 정상"}[st]
    report("L2", "전체 밀림", st,
           f"최적 {best:+.2f}초 · 일치 {h0}→{hb}/{len(starts)} ({ratio:.2f}배){tail}")
    span = starts[-1] if starts else 0
    offs = []
    for i in range(4):
        lo, hi = span*i/4, span*(i+1)/4
        sub = [a for a in starts if lo <= a < hi]
        if len(sub) < 5: continue
        offs.append(max(steps, key=lambda o: sum(1 for a in sub if min(abs(x-(a+o)) for x in onsets) < tol)))
    if len(offs) >= 3:
        drift = max(offs) - min(offs)
        mono = all(offs[i] <= offs[i+1] for i in range(len(offs)-1)) or \
               all(offs[i] >= offs[i+1] for i in range(len(offs)-1))
        st = FAIL if (drift > 0.6 and mono) else (WARN if drift > 0.6 else OK)
        report("L2", "드리프트", st,
               f"구간별 {[f'{o:+.2f}' for o in offs]} (폭 {drift:.2f}초)" +
               ("  ← 한 방향으로 흐른다. 프레임레이트 불일치 의심" if st == FAIL else ""))

# ---------- L5 짝 맞춤 ----------
JP_CONT = "ぁ-んゝゞー"          # 이 글자로 시작하면 앞 큐의 꼬리일 가능성
SENT_END = "。？！」』~〜.?!"      # 「…」「、」는 빼둔다 — 이어짐 표시지 끝이 아니다
# 큐가 이걸로 끝나면 뒤로 이어진다. 일본어에서 가장 확실한 절단 신호다.
# 실측: 「日本の…」/「じゃなく、」 는 말줄임표 때문에 부호 규칙을 빠져나갔지만
# 조사 규칙에는 걸린다.
DANGLING = ("の","が","は","を","に","で","と","へ","や","も","から","まで",
            "って","という","ような","ので","のに","けど","けれど","し","ば")
def layer3(kr, words_json, wav=None):
    """받아쓰기 환각 의심 — 박수·음악 위에 지어낸 말.

    실측(Slydini #6 「number three, number four, number five」): 박수 3초를
    앞 문장의 세기 패턴에 이어 받아썼다. 흔적이 단어 시각에 남는다.
      · 길이 0인 단어 (number 20.30~20.30)
      · 비정상적으로 늘어진 단어 (four 1.28초)
      · 단어 확신도 낮음 (fw_transcribe 가 저장한 경우)
    의심 큐는 --wav 가 있으면 그 구간만 VAD 켜고 단독 재받아쓰기해서
    말소리가 없으면 FAIL. 없으면 warn.
    """
    if not words_json or not Path(words_json).exists():
        report("L3", "환각 의심", WARN, "words.json 없음 — 건너뜀"); return
    d = json.loads(Path(words_json).read_text(encoding="utf-8"))
    ws = [w for seg in d.get("segments", []) for w in seg.get("words", [])]
    sus = []
    for i, (a, b, t) in enumerate(kr):
        inw = [w for w in ws if a - 0.2 <= (w["start"]+w["end"])/2 < b + 0.2]
        if len(inw) < 2: continue
        zero = sum(1 for w in inw if w["end"] - w["start"] < 0.02)
        longw = sum(1 for w in inw if w["end"] - w["start"] > 1.0 and len(w["word"].strip()) <= 6)
        lowp = sum(1 for w in inw if w.get("probability", 1) < 0.35)
        score = zero + longw + (1 if lowp >= max(2, len(inw)//2) else 0)
        if score >= 2 or (zero and longw):
            sus.append((i+1, a, b, zero, longw, lowp))
    if not sus:
        report("L3", "환각 의심", OK); return
    fails, warns = [], []
    if wav and Path(wav).exists():
        import subprocess, tempfile
        from faster_whisper import WhisperModel
        m = WhisperModel("small", device="cpu", compute_type="int8")
        lang = d.get("language")
        for n, a, b, *_ in sus:
            tmp = tempfile.mktemp(suffix=".wav")
            subprocess.run([_ffmpeg(),"-y","-v","error","-ss",str(max(0,a-0.3)),
                            "-i",wav,"-t",str(b-a+0.6),tmp], check=True)
            segs, _ = m.transcribe(tmp, language=lang, vad_filter=True, condition_on_previous_text=False)
            segs = list(segs)
            # 「뭔가 받아써지면 진짜 말」은 틀린 기준이다 — VAD 가 박수를 통과시키고
            # 모델이 다른 환각(「You can't do that.」×2)을 만든다. 실측 구분선:
            #   환각  무음확률 0.43 · 확신도 -1.01 · 같은 문장 반복
            #   진짜  무음확률 0.12~0.32 · 확신도 -0.53 (억양 심한 #8 도 -0.94/0.12 로 통과)
            # Whisper 가 무음 구간을 버리는 기준(no_speech 높음 AND logprob 낮음)과 같은 모양.
            texts = [x.text.strip() for x in segs]
            hallu = (not segs
                     or all(x.no_speech_prob >= 0.4 and x.avg_logprob <= -0.9 for x in segs)
                     or (len(texts) >= 2 and len(set(texts)) == 1 and min(x.avg_logprob for x in segs) <= -0.8))
            (fails if hallu else warns).append(n)
    else:
        warns = [n for n, *_ in sus]
    if fails:
        report("L3", "환각 (말소리 없음)", FAIL,
               f"{fails} — 단독 재받아쓰기에서 말소리 0. 박수·음악 위에 지어낸 대사다. 큐를 지운다")
    if warns:
        detail = ", ".join(f"#{n}(0초단어{z}·늘어짐{l})" for n,_,_,z,l,_ in sus if n in warns)
        report("L3", "환각 의심", WARN, f"{detail} — 원문을 귀로 확인")

def layer3x(other, ref_srt):
    """두 번째 받아쓰기와 단어 단위 대조 — 한 단어만 틀린 오류를 잡는다.

    실측(Slydini): 「no skews」「brilliant is not so good」「I came over here」.
    문장 전체 유사도는 높아서(>60%) 어떤 검사에도 안 걸렸다. 유튜브 자동자막
    (en-orig, 구글 ASR)은 「no excuse」「believe me」「I can put here」로 들었고
    Whisper large-v3 도 1번은 「no excuse」였다. 사용자가 1번을 먼저 의심했다.
    구글도 틀린다(「robber bent」「Le to give」) — 그래서 warn 이고, 사람이 고른다.
    """
    if not ref_srt or not Path(ref_srt).exists() or not other:
        return
    t = Path(ref_srt).read_text(encoding="utf-8")
    ref = []
    for m in re.finditer(r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})\n(.*?)(?=\n\s*\n|\Z)", t, re.S):
        g = m.groups()
        a = int(g[0])*3600+int(g[1])*60+int(g[2])+int(g[3])/1000
        b = int(g[4])*3600+int(g[5])*60+int(g[6])+int(g[7])/1000
        line = g[8].strip().split("\n")[-1].strip()      # 유튜브 롤링 자막: 마지막 줄만 새 말
        if not ref or ref[-1][2] != line: ref.append((a, b, line))
    STOP = set("a an the i you it is it's to of and in on this that so me my he him his be do "
               "see look watch here there what one".split())
    norm = lambda x: re.sub(r"[^a-z' ]", " ", x.lower()).split()
    odd = []
    for i, (a, b, txt) in enumerate(other, 1):
        near = set(norm(" ".join(x[2] for x in ref if x[0] < b+1.0 and x[1] > a-1.0)))
        miss = [w for w in norm(txt) if w not in STOP and len(w) > 2 and w not in near]
        if miss: odd.append(f"#{i}{miss}")
    report("L3", "두 번째 받아쓰기와 불일치", WARN if odd else OK,
           f"{len(odd)}곳 {' '.join(odd[:8])} — 한쪽만 들은 단어. 귀로 듣고 고른다" if odd else "")

def layer5(kr, other):
    if other is None:
        report("L5", "짝 맞춤", WARN, "두 번째 트랙 없음 — 건너뜀"); return
    mid, dang = [], []
    for i in range(len(other)-1):
        cur, nxt = other[i][2], other[i+1][2]
        if not cur or not nxt: continue
        bare = cur.rstrip("…、,・ ")           # 이어짐 표시를 벗겨내고 본다
        if not bare: continue
        if bare[-1] not in SENT_END and re.match(f"^[{JP_CONT}]", nxt):
            mid.append(i+1)
        if any(bare.endswith(d) for d in DANGLING):
            dang.append(i+1)
    report("L5", "어절 중간 절단", WARN if mid else OK,
           f"{len(mid)}곳 {mid[:10]} — 다음 큐가 히라가나로 시작. 단어가 쪼개졌는지 눈으로 확인" if mid else "")
    # 조사로 끝나는 것 자체는 정상일 수 있다 — 한국어도 같은 자리에서 끊기면 짝이 맞는다.
    # 진짜 문제는 **한국어는 문장을 끝냈는데 일본어만 매달려 있는** 자리다.
    KR_END = ("다.","요.","까?","죠.","다!","요!","네.","까.",".","?","!")
    mismatch = [i for i in dang
                if i-1 < len(kr) and kr[i-1][2].rstrip("」』\"' ").endswith(KR_END)]
    parallel = [i for i in dang if i not in mismatch]
    report("L5", "조사 매달림(짝 어긋남)", WARN if mismatch else OK,
           f"{len(mismatch)}곳 {mismatch[:10]} — 한국어는 문장을 끝냈는데 일본어만 이어진다. 합쳐야 한다" if mismatch else "")
    if parallel:
        report("L5", "조사 매달림(짝 맞음)", OK, f"{len(parallel)}곳 {parallel[:10]} — 한국어도 같이 끊긴다. 정상")
    rep = []
    for i in range(len(other)-1):
        a, b = other[i][2], other[i+1][2]
        if len(a) >= 3 and len(b) >= 3 and (a[:4] == b[:4]):
            rep.append(i+2)
    # 한국어 쪽 절단 — 부호 없이 연결어미로 끝나면 문장이 다음 큐로 넘어간 것이다.
    # 실측(Slydini #2): 「이걸 못 잡아내면」/「곤란하죠.」 — 한 큐 한 문장 위반.
    # 번역자가 원어 경계를 따라 일부러 쪼갠 자리(「등을 돌린 사이에」)도 걸리므로 warn.
    KR_CONNECT = ("면","고","는데","은데","ㄴ데","서","지만","니까","으니","라","게","도록",
                  "려고","면서","다가","자","며","데","고서","거나","든지","사이에","동안")
    krcut = []
    for i, (_, _, t) in enumerate(kr[:-1]):
        line = t.replace("\n", " ").strip()
        if not line or line[-1] in ".?!。？！」』…~〜":
            continue
        bare = line.rstrip(", ")
        if any(bare.endswith(e) for e in KR_CONNECT):
            krcut.append(i+1)
    report("L5", "한국어 문장 절단", WARN if krcut else OK,
           f"{len(krcut)}곳 {krcut[:12]} — 연결어미로 끝나 다음 큐로 넘어간다. 한 큐 한 문장으로 다시 쓰거나 병합" if krcut else "")
    report("L5", "인접 큐 어구 중복", WARN if rep else OK, f"{rep[:10]}" if rep else "")
    lone = [i+1 for i,(_,_,t) in enumerate(other) if t and len(t) <= 2 and t[-1] not in SENT_END]
    report("L5", "조각만 남은 큐", WARN if lone else OK, f"{len(lone)}개 {lone[:10]}" if lone else "")

def _ffmpeg():
    import os, shutil
    if os.environ.get("FFMPEG"): return os.environ["FFMPEG"]
    mac = "/opt/homebrew/opt/ffmpeg@7/bin/ffmpeg"
    return mac if os.path.exists(mac) else (shutil.which("ffmpeg") or "ffmpeg")

# 윈도우 폰트는 파일명이 패밀리명과 다르다 (Malgun Gothic → malgun.ttf).
_WIN_FONT_ALIAS = {"malgungothic": "malgun", "yugothic": "yugoth", "yugothicui": "yugoth",
                   "msgothic": "msgothic", "meiryo": "meiryo", "meiryoui": "meiryo"}

# ---------- L6 렌더 전 ----------
def findfont(name):
    if not name: return None
    key = name.lower().replace(" ", "").replace("_", "")
    pats = ["/Users/*/Library/Fonts/*", "/Library/Fonts/*", "/System/Library/Fonts/*",
            "/System/Library/Fonts/Supplemental/*"]
    import os
    if os.name == "nt":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        pats = [os.path.join(windir, "Fonts", "*"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts", "*")]
        key = _WIN_FONT_ALIAS.get(key, key)
    for pat in pats:
        for p in glob.glob(pat):
            if key in Path(p).stem.lower().replace(" ", "").replace("_", ""):
                return p
    return None

def layer6(kr, other, args):
    try:
        from PIL import ImageFont
    except ImportError:
        report("L6", "렌더 전 검사", WARN, "PIL 없음 — 건너뜀"); return
    def check(track, fname, size, label):
        if track is None or not fname: return
        fp = findfont(fname)
        if not fp:
            report("L6", f"{label} 폰트", FAIL, f"'{fname}' 못 찾음"); return
        # 글리프 커버리지 — 없는 글자는 .notdef(두부)로 그려진다.
        # 사설영역 문자를 그려 '두부 비트맵'을 얻고, 같은 모양이면 없는 글자로 본다.
        fchk = ImageFont.truetype(fp, 48)
        def bitmap(ch):
            try: return bytes(fchk.getmask(ch))
            except Exception: return None
        tofu = bitmap("\ue05f")
        miss = {}
        for i,(_,_,t) in enumerate(track):
            for ch in t:
                if ch in "\n " or unicodedata.category(ch).startswith("Z"): continue
                if ch in miss: continue
                bm = bitmap(ch)
                if bm is not None and tofu is not None and bm == tofu:
                    miss.setdefault(ch, i+1)
        if miss:
            sample = "".join(list(miss)[:12])
            report("L6", f"{label} 글리프", FAIL,
                   f"'{Path(fp).name}' 에 없는 글자 {len(miss)}종: {sample} (첫 등장 #{list(miss.values())[0]}) — 두부(□) 발생")
        else:
            report("L6", f"{label} 글리프", OK, Path(fp).name)
        # 폭
        f = ImageFont.truetype(fp, size)
        limit = args.width * 0.96
        wide = []
        for i,(_,_,t) in enumerate(track):
            line = " ".join(x.strip() for x in t.split("\n") if x.strip())
            w = f.getlength(line)
            if w > limit: wide.append((i+1, int(w)))
        report("L6", f"{label} 줄 폭", FAIL if wide else OK,
               f"{len(wide)}개 초과 (한계 {int(limit)}px) {wide[:5]}" if wide
               else f"최대 {int(max((f.getlength(' '.join(x.strip() for x in t.split(chr(10)) if x.strip())) for _,_,t in track), default=0))}px / 한계 {int(limit)}px")
    check(kr, args.font, args.size, "1행")
    check(other, args.font2, args.size2, "2행")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kr", required=True)
    ap.add_argument("--other")
    ap.add_argument("--words")
    ap.add_argument("--wav", help="환각 의심 구간 재받아쓰기용 16kHz wav")
    ap.add_argument("--ref", help="독립된 두 번째 받아쓰기 SRT (유튜브 en-orig 등)")
    ap.add_argument("--font"); ap.add_argument("--size", type=int, default=36)
    ap.add_argument("--font2"); ap.add_argument("--size2", type=int, default=18)
    ap.add_argument("--width", type=int, default=1920)
    args = ap.parse_args()

    kr = read(args.kr)
    other = read(args.other) if args.other else None
    layer1(kr, other); layer2(kr, args.words); layer3(kr, args.words, args.wav); layer3x(other, args.ref); layer5(kr, other); layer6(kr, other, args)

    w = max(len(n) for _,n,_,_ in results)
    cur = None
    for layer, name, st, detail in results:
        if layer != cur: print(); cur = layer
        mark = {OK:"  ok  ", WARN:" warn ", FAIL:" FAIL "}[st]
        print(f"{layer} [{mark}] {name.ljust(w)}  {detail}")
    nf = sum(1 for *_, st, _ in ((r[0],r[1],r[2],r[3]) for r in results) if st == FAIL)
    nw = sum(1 for r in results if r[2] == WARN)
    print(f"\n{'='*60}\nFAIL {nf}건 · warn {nw}건")
    sys.exit(1 if nf else 0)

if __name__ == "__main__":
    main()
