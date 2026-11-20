#!/usr/bin/env python3
"""받아쓰기 → openai-whisper 호환 JSON. 맥·윈도우 공용, 가장 빠른 엔진을 자동으로 고른다.

usage:
  fw_transcribe.py IN.wav OUT.json [MODEL] [LANG] ["도메인 용어 프롬프트"] [--backend=auto|cuda|cpp|cpu] [--vad]
  fw_transcribe.py --check        # 이 컴퓨터에서 어떤 엔진이 잡히는지만 본다

MODEL 기본 = turbo (large-v3-turbo). medium·large-v3 등도 된다.

엔진 선택 (auto):
  1. cuda — 엔비디아 GPU(윈도우 RTX 등). faster-whisper float16. 가장 빠르다.
  2. cpp  — 맥(애플 칩). whisper.cpp(`whisper-cli`)가 Metal GPU 로 돈다.
            실측 M3 Pro + large-v3-turbo: 5분 오디오 20초(약 15배).
  3. cpu  — 위 둘 다 없을 때. faster-whisper int8. 실측 1.5~2.8배(느림).

VAD(말소리 감지)는 기본으로 끈다. 켜면(--vad) 배경 음악 위의 말을 소음으로 보고 통째로 버린다
— 실측: 일본 마술 DVD 공연 구간(음악+관객 대화) 5권에서 648줄이 사라졌다(2026-11-20).
끄면 음악만 나오는 곳에 「ご視聴ありがとうございました」 같은 환각이 생기므로 HALLU 문구는 버린다.

출력 형식은 엔진과 무관하게 같다 → srt_from_whisper.py·check_sync.py·
align_second_lang.py·find_offset.py 를 그대로 쓴다.
"""
import glob
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

backend = "auto"
USE_VAD = "--vad" in sys.argv
# VAD 를 끄면 음악·무음 구간에 생기는 단골 환각 문구 — 세그먼트가 이것뿐이면 버린다 (fill_gaps.py 도 이 목록을 쓴다)
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
CHECK_ONLY = "--check" in sys.argv  # 어떤 엔진이 잡히는지만 출력하고 끝 (설치 확인용)
args = []
for a in sys.argv[1:]:
    if a.startswith("--") and a not in ("--check", "--vad") and not a.startswith("--backend"):
        sys.exit(f"알 수 없는 옵션: {a}\n" + __doc__)
    if a.startswith("--backend"):
        backend = a.split("=", 1)[1] if "=" in a else "auto"
    elif a not in ("--check", "--vad"):
        args.append(a)
if len(args) < 2 and not CHECK_ONLY:
    sys.exit(__doc__)
wav, out = (args + ["", ""])[:2]
model_name = args[2] if len(args) > 2 else "turbo"
lang = args[3] if len(args) > 3 else None
prompt = args[4] if len(args) > 4 else None

ALIASES = {"turbo": "large-v3-turbo"}


def add_nvidia_dll_dirs():
    """윈도우: pip 로 깐 nvidia-cublas/cudnn 의 DLL 을 찾게 해준다.
    이게 없으면 GPU 가 있어도 `cublas64_12.dll is not found` 로 죽는다."""
    if os.name != "nt":
        return
    import site
    roots = site.getsitepackages() + [site.getusersitepackages()]
    for r in roots:
        for d in glob.glob(os.path.join(r, "nvidia", "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def has_cuda():
    try:
        add_nvidia_dll_dirs()
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def cpp_model_path(name):
    name = ALIASES.get(name, name)
    for d in [os.path.expanduser("~/.cache/whisper/models"),
              "/opt/homebrew/share/whisper-cpp/models",
              os.path.expanduser("~/whisper.cpp/models")]:
        p = os.path.join(d, f"ggml-{name}.bin")
        if os.path.exists(p):
            return p
    return None


def pick():
    if backend != "auto":
        return backend
    if has_cuda():
        return "cuda"
    if platform.system() == "Darwin" and shutil.which("whisper-cli") and cpp_model_path(model_name):
        return "cpp"
    return "cpu"


def run_faster_whisper(device):
    from faster_whisper import WhisperModel
    name = ALIASES.get(model_name, model_name)
    if device == "cuda":
        m = WhisperModel(name, device="cuda", compute_type="float16")
    else:
        m = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    segs, info = m.transcribe(
        wav, language=lang, word_timestamps=True,
        condition_on_previous_text=False, initial_prompt=prompt,
        vad_filter=USE_VAD, vad_parameters=dict(min_silence_duration_ms=500) if USE_VAD else None,
    )
    print(f"lang={info.language} dur={info.duration:.0f}s", flush=True)
    t0, data = time.time(), {"language": info.language, "segments": []}
    for i, s in enumerate(segs):
        data["segments"].append({
            "id": i, "start": s.start, "end": s.end, "text": s.text,
            "no_speech_prob": s.no_speech_prob, "avg_logprob": s.avg_logprob,
            "words": [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                      for w in (s.words or [])],
        })
        if i % 50 == 0:
            el = time.time() - t0
            print(f"  {s.end:7.1f}s / {info.duration:.0f}s  ({s.end/max(el,1):.1f}x)", flush=True)
    return data


def run_whisper_cpp():
    """whisper.cpp 는 토큰 단위 시각을 준다 → 공백으로 시작하는 토큰에서 새 단어를 연다.
    -mc 0 = 앞 문맥을 안 넘긴다(faster-whisper 의 condition_on_previous_text=False 와 같은 뜻).
    긴 영상에서 같은 문장이 끝없이 반복되는 환각을 줄인다."""
    model = cpp_model_path(model_name)
    tmp = tempfile.mkdtemp()
    base = os.path.join(tmp, "out")
    cmd = ["whisper-cli", "-m", model, "-f", wav, "-ojf", "-of", base, "-np",
           "-mc", "0", "-t", str(min(8, os.cpu_count() or 4))]
    if lang:
        cmd += ["-l", lang]
    if prompt:
        cmd += ["--prompt", prompt]
    print("whisper.cpp:", os.path.basename(model), flush=True)
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:  # 평소엔 Metal 초기화 로그가 수십 줄이라 숨기고, 실패할 때만 보여준다
        sys.exit(r.stderr[-3000:])
    raw = json.load(open(base + ".json", encoding="utf-8"))
    data = {"language": lang or raw.get("result", {}).get("language"), "segments": []}
    for i, seg in enumerate(raw["transcription"]):
        words = []
        for tok in seg.get("tokens", []):
            t = tok["text"]
            if t.startswith("[_") or t.startswith("<|"):
                continue
            st, en = tok["offsets"]["from"] / 1000, tok["offsets"]["to"] / 1000
            p = tok.get("p", 1.0)
            if words and not t.startswith(" "):
                w = words[-1]
                w["word"] += t
                w["end"] = en
                w["probability"] = min(w["probability"], p)
            elif t.strip():
                words.append({"word": t, "start": st, "end": en, "probability": p})
        ps = [w["probability"] for w in words] or [1.0]
        data["segments"].append({
            "id": i, "start": seg["offsets"]["from"] / 1000, "end": seg["offsets"]["to"] / 1000,
            "text": seg["text"],
            "no_speech_prob": None,  # whisper.cpp 는 안 준다 — 환각 판정은 qc.py --wav 가 따로 한다
            "avg_logprob": sum(math.log(max(p, 1e-6)) for p in ps) / len(ps),
            "words": words,
        })
    shutil.rmtree(tmp, ignore_errors=True)
    return data


eng = pick()
print(f"backend={eng}", flush=True)
if CHECK_ONLY:
    sys.exit(0)
t0 = time.time()
data = run_whisper_cpp() if eng == "cpp" else run_faster_whisper("cuda" if eng == "cuda" else "cpu")
before = len(data["segments"])
data["segments"] = [sg for sg in data["segments"] if not is_hallu(sg["text"])]
for i, sg in enumerate(data["segments"]):
    sg["id"] = i
if before - len(data["segments"]):
    print(f"환각 문구 세그먼트 {before - len(data['segments'])}개 버림 (HALLU)", flush=True)
json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False)
n = sum(len(s["words"]) for s in data["segments"])
dur = data["segments"][-1]["end"] if data["segments"] else 0
el = time.time() - t0
print(f"done [{eng}]: {len(data['segments'])} segments, {n} words, {el:.0f}s ({dur/max(el,1):.1f}x) -> {out}")
