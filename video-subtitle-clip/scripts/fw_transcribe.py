#!/usr/bin/env python3
"""faster-whisper 로 받아쓰기 → openai-whisper 호환 JSON.

긴 영상(1시간+)에서 기본 whisper 는 CPU 로 실시간의 1~3배가 걸린다.
faster-whisper(CTranslate2)는 같은 모델을 int8 로 돌려 4~8배 빠르다.
출력 형식을 openai-whisper 와 맞춰서 기존 스크립트(srt_from_whisper.py·
check_sync.py·align_second_lang.py)를 그대로 쓸 수 있게 한다.
"""
import json, sys, time
from faster_whisper import WhisperModel

wav, out, model_name = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "medium")
lang = sys.argv[4] if len(sys.argv) > 4 else None
prompt = sys.argv[5] if len(sys.argv) > 5 else None

m = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=10)
segs, info = m.transcribe(
    wav, language=lang, word_timestamps=True,
    condition_on_previous_text=False, initial_prompt=prompt,
    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
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

json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False)
n = sum(len(s["words"]) for s in data["segments"])
print(f"done: {len(data['segments'])} segments, {n} words -> {out}")
