#!/usr/bin/env python3
"""SRT -> 스타일 적용된 ASS 자막 생성 (단일 / 이중).

ffmpeg 의 subtitles=...:force_style='...' 는 쉼표·따옴표 이스케이프가 까다롭고
필터 파서 버전마다 동작이 달라서 조용히 실패한다. ASS 파일을 직접 만들면
결과를 눈으로 확인하고 손으로 고칠 수 있다.

usage:
  # 단일
  make_ass.py --srt cut.srt --out cut.ass --width 640 --height 480

  # 이중 (원어 위 + 번역 아래)
  make_ass.py --srt src.srt --srt2 trans.srt --out cut.ass \
      --width 1920 --height 1080 --preset dual

이중 자막의 짝 맞추기: 두 SRT의 큐 개수가 같으면 순서대로 짝짓고,
다르면 시간 겹침이 가장 큰 큐끼리 짝짓는다. 번역은 원본 타임코드를
유지한 채 만드는 게 원칙이므로 보통은 전자가 된다.
"""
import argparse
import re
from pathlib import Path

CUE = re.compile(
    r"(\d+)[^\S\n]*\n"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*-->[^\S\n]*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})[^\S\n]*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.S,
)

PRESETS = {
    # (주 색, 부 색, 부 볼드)  — ASS 색은 &HBBGGRR 순서 (RGB 역순)
    "single": ("&H00FFFFFF", None, False),
    "dual": ("&H00FFFFFF", "&H00D0D0D0", False),
    "hikaro": ("&H00FFFFFF", "&H00A7E700", True),  # #00E7A7 emerald
}


def parse_srt(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    cues = []
    for m in CUE.finditer(text):
        g = m.groups()
        start = (int(g[1]) * 3600 + int(g[2]) * 60 + int(g[3])) * 1000 + int(g[4])
        end = (int(g[5]) * 3600 + int(g[6]) * 60 + int(g[7])) * 1000 + int(g[8])
        body = " ".join(ln.strip() for ln in g[9].strip().split("\n") if ln.strip())
        if body:
            cues.append((start, end, body))
    return cues


def ass_time(ms):
    ms = max(0, ms)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:d}:{m:02d}:{s:02d}.{ms // 10:02d}"


def pair(primary, second):
    """원어 큐마다 대응하는 번역 큐를 찾는다."""
    if len(primary) == len(second):
        return [(p, s[2]) for p, s in zip(primary, second)]

    paired = []
    for cue in primary:
        best, best_overlap = None, 0
        for s in second:
            overlap = min(cue[1], s[1]) - max(cue[0], s[0])
            if overlap > best_overlap:
                best, best_overlap = s[2], overlap
        paired.append((cue, best))
    return paired


def escape(text):
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


# --- 자막바를 직접 그리는 모드 -------------------------------------------------
#
# libass 의 BorderStyle=3 은 글자 뒤에 상자를 깔아주지만, 상자 높이가 폰트의
# ascent+descent 로 정해진다. 한글은 디센더를 쓰지 않으므로 아래쪽에 빈 공간이
# 남아 글자가 위로 뜬 것처럼 보인다. 그래서 상자를 \p 드로잉으로 직접 그리고,
# 글자는 실제 잉크(글자가 칠해지는 영역)의 중심이 상자 중심에 오도록 옮긴다.
#
# 상자 높이를 큐마다 실제 잉크로 재면 "자." 와 "이제 고전..." 의 바 높이가
# 달라져 깜빡인다. 그래서 높이는 파일 전체 자막의 잉크 범위로 한 번만 재고,
# 폭만 큐마다 잰다. 고정 기준 문자열을 쓰지 않는 이유는, 'g' 같은 디센더를
# 넣어두면 한글만 있는 자막에서 상자가 아래로 늘어나 글자가 위로 뜨고,
# 빼두면 영어가 섞였을 때 디센더가 상자 밖으로 나가기 때문이다.


def load_font(family, size):
    """fontconfig 로 실제 폰트 파일을 찾아 PIL 로 연다. 실패하면 None."""
    import subprocess

    try:
        from PIL import ImageFont
    except ImportError:
        return None
    try:
        path = subprocess.run(
            ["fc-match", "-f", "%{file}", family],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if path:
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    # fc-match 없음(윈도우 기본) → 폰트 폴더에서 이름으로 찾는다
    try:
        from qc import findfont
        path = findfont(family)
        return ImageFont.truetype(path, size) if path else None
    except Exception:
        return None


def ink_range(font, all_lines):
    """파일 전체 자막이 실제로 칠하는 세로 범위 (한 줄 기준)."""
    tops, bots = [], []
    for ln in all_lines:
        b = font.getbbox(ln)              # (x0, y0, x1, y1), 원점은 ascent 상단
        if b[3] > b[1]:                   # 공백만 있는 줄은 건너뛴다
            tops.append(b[1])
            bots.append(b[3])
    if not tops:
        ascent, descent = font.getmetrics()
        return 0, ascent

    # 최소/최대가 아니라 중앙값을 쓴다. 쉼표 하나가 베이스라인 아래로 삐져나가면
    # 최대값 기준 상자는 그만큼 아래로 늘어나고, 쉼표 없는 대부분의 자막은
    # 그 안에서 위로 뜬 것처럼 보인다. 중앙값은 "보통 줄"의 위치를 잡아주고
    # 예외적인 글자는 안쪽 여백이 흡수한다.
    from statistics import median
    return round(median(tops)), round(median(bots))


def box_geometry(fonts, lines, inks):
    """상자 크기와 글자 보정량을 픽셀로 계산한다.

    줄마다 폰트와 크기가 다를 수 있다(이중 자막은 아래 줄이 더 작다).
    각 줄을 **자기 폰트로** 재지 않으면 상자가 실제보다 넓거나 높아진다.
    """
    heights = [sum(f.getmetrics()) for f in fonts]
    text_w = max(f.getlength(ln) for f, ln in zip(fonts, lines))

    tops, bots, off = [], [], 0
    for i in range(len(fonts)):
        tops.append(off + inks[i][0])
        bots.append(off + inks[i][1])
        off += heights[i]
    ink_top, ink_bot = min(tops), max(bots)

    # \an5 는 글자의 메트릭 박스 중심을 \pos 에 맞춘다. 잉크 중심은 그와
    # 어긋나 있으므로(한글은 디센더를 안 써서 위로 치우친다) 그 차이만큼
    # 글자를 반대로 옮겨야 잉크가 상자 한가운데 온다.
    return text_w, ink_bot - ink_top, (ink_top + ink_bot) / 2 - sum(heights) / 2


def build_boxed(args, rows, color1):
    """상자 + 글자를 각각의 이벤트로 내보낸다."""
    font = load_font(args.font, args.size)
    if font is None:
        return None

    pad_x = args.box_pad_x or round(args.size * 0.45)
    pad_y = args.box_pad_y or round(args.size * 0.30)
    alpha = f"&H{args.box_alpha:02X}&"
    cx = args.width / 2

    font2 = load_font(args.font2, args.size2) or font
    ink1 = ink_range(font, [text for (_, _, text), _ in rows])
    ink2 = ink_range(font2, [tr for _, tr in rows if tr]) if args.srt2 else ink1

    events = []
    for (start, end, text), trans in rows:
        lines = [escape(text)]
        fonts, inks = [font], [ink1]
        if trans:
            lines.append(escape(trans))
            fonts.append(font2)
            inks.append(ink2)

        text_w, text_h, shift = box_geometry(fonts, lines, inks)
        box_w = round(text_w + pad_x * 2)
        box_h = round(text_h + pad_y * 2)

        cy = args.height - args.margin - box_h / 2      # 상자 중심 y
        x0 = round(cx - box_w / 2)
        y0 = round(cy - box_h / 2)

        t0, t1 = ass_time(start), ass_time(end)
        events.append(
            f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,"
            f"{{\\an7\\pos({x0},{y0})\\bord0\\shad0\\1c&H000000&\\1a{alpha}\\p1}}"
            f"m 0 0 l {box_w} 0 {box_w} {box_h} 0 {box_h}{{\\p0}}"
        )

        body = lines[0]
        if trans:
            override = (f"\\fn{args.font2}\\fs{args.size2}"
                        f"\\c{args.color2_resolved}\\b{1 if args.bold2 else 0}")
            body = f"{body}\\N{{{override}}}{lines[1]}"

        events.append(
            f"Dialogue: 1,{t0},{t1},Default,,0,0,0,,"
            f"{{\\an5\\pos({round(cx)},{round(cy - shift + args.box_nudge_y)})"
            f"\\bord0\\shad0}}{body}"
        )

    return events


def build(args):
    primary = parse_srt(args.srt)
    if not primary:
        raise SystemExit(f"자막 큐를 못 찾음: {args.srt}")

    color1, color2, bold2 = PRESETS[args.preset]
    if args.color2:
        color2 = args.color2
    args.color2_resolved, args.bold2 = color2, bold2

    rows = pair(primary, parse_srt(args.srt2)) if args.srt2 else [(c, None) for c in primary]

    boxed = build_boxed(args, rows, color1) if args.box else None

    # 직접 그리기가 안 되면(PIL 없음·폰트 못 찾음) libass 의 BorderStyle=3 으로 물러선다.
    # 반응형 바는 나오지만 글자가 세로 가운데에서 살짝 위로 뜬다.
    if args.box and boxed is None:
        print("경고: PIL 또는 폰트 파일을 못 찾아 BorderStyle=3 으로 대체한다 "
              "(글자가 바 안에서 살짝 위로 뜬다)")

    if args.box and boxed is None:
        border_style, border_size, shadow = 3, round(args.size * 0.12, 1), 0
        back = "&H00000000"
        outline_col = f"&H{args.box_alpha:02X}000000"
    elif args.box:
        border_style, border_size, shadow = 1, 0, 0
        back = outline_col = "&H00000000"
    else:
        border_style, border_size, shadow = 1, args.outline, 1
        back, outline_col = "&H80000000", "&H00000000"

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {args.width}
PlayResY: {args.height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{args.font},{args.size},{color1},{color1},{outline_col},{back},{-1 if args.bold else 0},0,0,0,100,100,0,0,{border_style},{border_size},{shadow},2,{args.margin_h},{args.margin_h},{args.margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    if boxed is not None:
        lines = boxed
    else:
        lines = []
        for (start, end, text), trans in rows:
            body = escape(text)
            if trans:
                override = f"\\fn{args.font2}\\fs{args.size2}\\c{color2}\\b{1 if bold2 else 0}"
                body = f"{body}\\N{{{override}}}{escape(trans)}"
            lines.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{body}"
            )

    Path(args.out).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    kind = "이중" if args.srt2 else "단일"
    style = "자막바 직접 그림" if boxed is not None else ("자막바(libass)" if args.box else "테두리")
    print(f"{len(rows)} cues ({kind}, {style}) -> {args.out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--srt", required=True, help="주 자막 (이중일 땐 원어)")
    p.add_argument("--srt2", help="보조 자막 (이중일 땐 번역)")
    p.add_argument("--out", required=True)
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--preset", choices=list(PRESETS), default="single")
    import os
    default_font = "Malgun Gothic" if os.name == "nt" else "Apple SD Gothic Neo"
    p.add_argument("--font", default=default_font)
    p.add_argument("--font2", default=default_font)
    p.add_argument("--size", type=int, default=0, help="0이면 화면 높이의 6%%")
    p.add_argument("--size2", type=int, default=0, help="0이면 주 자막의 80%%")
    p.add_argument("--color2", help="번역 색 (&HBBGGRR)")
    p.add_argument("--outline", type=float, default=2.5, help="테두리 두께 (--box 아닐 때)")
    p.add_argument("--bold", type=int, default=1, choices=[0, 1],
                   help="폰트 이름에 Bold/Medium 이 들어가면 0 (이중 볼드 방지)")
    p.add_argument("--box", action="store_true",
                   help="테두리 대신 글자 뒤에 어두운 자막바를 깐다")
    p.add_argument("--box-alpha", type=lambda v: int(v, 0), default=0x66,
                   help="자막바 투명도. 00=불투명, FF=완전투명 (기본 0x66)")
    p.add_argument("--box-pad-x", type=float, default=0,
                   help="자막바 좌우 여백. 0이면 글자 크기의 45%%")
    p.add_argument("--box-pad-y", type=float, default=0,
                   help="자막바 상하 여백. 0이면 글자 크기의 30%%")
    p.add_argument("--box-nudge-y", type=float, default=0,
                   help="글자를 바 안에서 아래(+)/위(-)로 미세 이동. "
                        "libass 의 세로 중심 기준이 폰트 메트릭과 조금 달라 "
                        "폰트에 따라 몇 px 남을 수 있다. 렌더해서 재고 채운다")
    p.add_argument("--margin", type=int, default=0, help="하단 여백, 0이면 높이의 4%%")
    p.add_argument("--margin-h", type=int, default=0, help="좌우 여백, 0이면 너비의 4%%")
    args = p.parse_args()

    # 해상도에 비례해 기본값을 잡는다. 640x480 에서 30, 1080p 에서 64 정도.
    args.size = args.size or max(16, round(args.height * 0.06))
    args.size2 = args.size2 or max(14, round(args.size * 0.8))
    args.margin = args.margin or max(10, round(args.height * 0.04))
    args.margin_h = args.margin_h or max(10, round(args.width * 0.04))

    if args.srt2 and args.preset == "single":
        args.preset = "dual"

    build(args)


if __name__ == "__main__":
    main()
