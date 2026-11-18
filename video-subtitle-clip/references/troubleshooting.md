# 막혔을 때

실제로 부딪혀서 해결한 것들. 증상이 원인을 가리키지 않는 경우가 많아서, 증상별로 정리했다.

## 목차

증상 하나가 여러 도메인에 걸치는 일이 흔하다. 태그는 훑기 위한 것이지 경계가 아니다 —
"이음매가 튄다" 하나가 인터레이스·조각 추출·PTS·자막 보정 네 곳에 걸쳐 있던 적이 있다.

**🎬 영상** — 화면·컨테이너·소스 자체

- 🎬 [DVD VOB — 이음매가 튄다 / 화면이 멈춘다](#dvd-vob--이음매가-튄다--화면이-멈춘다)
- 🎬 [영상이 끊겨 보인다 — 인터레이스](#영상이-끊겨-보인다--인터레이스)
- 🎬 [확장자와 내용물이 다름](#확장자와-내용물이-다름)
- 🎬 [파일이 너무 큼](#파일이-너무-큼)

**🔊 소리**

- 🔊 [소리가 안 들린다 — 5.1 함정](#소리가-안-들린다--51-함정)

**💬 자막** — 렌더·타이밍·인코딩

- 💬 [ffmpeg 필터 오류](#ffmpeg-필터-오류)
- 💬 [자막이 안 보이거나 네모로 깨짐](#자막이-안-보이거나-네모로-깨짐)
- 💬 [자막 싱크가 통째로 밀림](#자막-싱크가-통째로-밀림)
- 💬 [한글 자막 인코딩](#한글-자막-인코딩)
- 💬 [이중 자막 큐가 안 맞음](#이중-자막-큐가-안-맞음)

**📥 소스 확보**

- 📥 [yt-dlp 실패](#yt-dlp-실패)
- 📥 [Whisper 결과가 이상함](#whisper-결과가-이상함)

---

## ffmpeg 필터 오류

```
[AVFilterGraph] Error parsing a filter description around:
[AVFilterGraph] Error parsing filterchain 'ass=cut.ass' around:
Error opening output file ...
```

**필터가 없는 것이지 문법이 틀린 게 아니다.** 메시지가 "parsing"이라 따옴표를 고치게 되는데 헛수고다. 확인:

```bash
ffmpeg -hide_banner -filters | grep -wE "ass|subtitles"
```

아무것도 안 나오면 그 빌드에 libass가 없다. Homebrew가 core `ffmpeg`를 슬림화하며 뺐다 (2026 기준 `brew deps ffmpeg` 에 libass가 없다).

```bash
brew install ffmpeg@7
/opt/homebrew/opt/ffmpeg@7/bin/ffmpeg ...
```

`ffmpeg@7`은 keg-only라 PATH의 `ffmpeg`를 대체하지 않는다. 기존 워크플로우가 안 깨지므로 이쪽이 안전하다. `ffmpeg@6`·`ffmpeg@5`도 libass가 있다.

`force_style` 쪽에서 나는 오류도 대개 같은 원인이다. 다만 libass가 있는데도 실패한다면, `force_style` 안의 쉼표가 필터 구분자로 먹히는 문제다 — 그래서 이 스킬은 ASS 파일을 따로 만든다.

## 자막이 안 보이거나 네모로 깨짐

인코딩은 성공했는데 화면에 자막이 없거나 `□□□`로 나온다. **폰트 문제는 로그에 안 남는다.** 반드시 프레임을 뽑아 눈으로 본다.

| 증상 | 원인 | 해결 |
|------|------|------|
| 자막 자체가 없음 | ASS의 Dialogue 시각이 영상 구간 밖 | `head` 로 ASS 시각 확인, `srtcut.py` 시프트 누락 여부 |
| 네모(두부) | 해당 글자를 가진 폰트 없음 | `--font` 로 명시 |
| 화면 밖으로 잘림 | PlayResX/Y 가 영상 해상도와 다름 | `--width`·`--height` 를 ffprobe 값과 맞춤 |
| 글자가 너무 크거나 작음 | 위와 동일 | 위와 동일 |

macOS 기본 폰트:

```bash
fc-list | grep -i "gothic\|hiragino\|apple sd"
```

- 한국어: `Apple SD Gothic Neo`
- 일본어: `Hiragino Sans` / `Hiragino Kaku Gothic ProN`
- 한+일 섞임: `Apple SD Gothic Neo` 로 두면 없는 글자는 fontconfig가 자동 폴백한다. 폴백이 마음에 안 들면 줄별로 `--font`·`--font2` 를 나눈다.

## 자막 싱크가 통째로 밀림

- **전체가 일정하게 밀림** → 구간 자르기 후 자막을 시프트 안 했다. `srtcut.py` 를 쓰거나, ASS의 모든 시각에 오프셋을 더한다.
- **뒤로 갈수록 벌어짐** → 프레임레이트 불일치. 옛날 자막에서 자주 나온다(23.976 ↔ 25). 비율로 스케일해야 한다:

```bash
python3 - <<'PY'
# 예: 25fps 기준 자막을 23.976fps 영상에 맞춤
ratio = 23.976 / 25.0
PY
```

- **영상 시작이 다름** → 방송 녹화본은 앞에 광고가 붙어 있는 경우가 있다. 자막 첫 대사가 나오는 시각을 영상에서 찾아 차이만큼 오프셋.

`-ss` 를 `-i` **뒤에** 두면 정확하지만 느리고, **앞에** 두면 빠르면서 프레임 정확하다(ffmpeg 2.1+). 앞에 두는 게 맞다.

## 확장자와 내용물이 다름

`.avi` 인데 실은 Matroska, `.mp4` 인데 실은 MPEG-TS 인 경우가 흔하다. 옛날 파일일수록 심하다.

```bash
ffprobe -v error -show_entries format=format_name -of default=noprint_wrappers=1 "INPUT"
```

이게 파이널컷이 파일을 못 읽는 진짜 원인인 경우가 많다. FCP는 AVFoundation만 쓰므로:

| FCP가 못 읽는 것 | 대응 |
|---|---|
| Matroska (mkv) 컨테이너 | MP4/MOV로 리먹스 또는 변환 |
| Vorbis / Opus 오디오 | AAC로 변환 |
| Xvid/DivX (mpeg4) 비디오 | H.264 또는 ProRes로 변환 |
| AVI 컨테이너 | 위와 동일 |

리먹스(재인코딩 없이 컨테이너만 교체)부터 시도하면 빠르고 화질 손실이 없다. 실패하면 재인코딩:

```bash
ffmpeg -i in.avi -c copy out.mov 2>&1 | tail -3     # 되면 끝
ffmpeg -i in.avi -c:v libx264 -crf 18 -c:a aac out.mp4
```

## 한글 자막 인코딩

국내 자막은 대부분 SMI이고 CP949(EUC-KR)다. UTF-8로 읽으면 깨진다. `smi2srt.py` 가 인코딩을 순서대로 시도하고 UTF-8로 내보낸다.

SRT인데 깨진다면:

```bash
file sub.srt                                  # charset 확인
iconv -f CP949 -t UTF-8 sub.srt > sub.utf8.srt
```

SMI의 `&nbsp;` 만 있는 `<SYNC>` 는 "여기서 자막 끝"을 뜻하는 마커지 자막이 아니다. 이걸 큐로 만들면 빈 자막이 깜빡인다 — `smi2srt.py` 는 걸러낸다.

## 이중 자막 큐가 안 맞음

번역 SRT는 **원본의 큐 번호와 개수를 그대로 유지**해야 한다. 번역하면서 두 큐를 한 문장으로 합치고 싶어지는데, 그러면 짝이 어긋난다.

`make_ass.py` 는 개수가 다르면 시간 겹침으로 짝을 찾지만, 어긋난 자막을 억지로 붙이는 것이라 결과가 이상해질 수 있다. 개수가 다르다는 경고가 뜨면 번역본을 고치는 쪽이 낫다.

문장이 큐를 넘나들면, 번역을 원본 큐 경계에 맞춰 나눠 담는다. 어색해도 싱크가 맞는 쪽이 낫다 — 화면과 자막이 어긋나면 읽는 사람이 바로 알아챈다.

## DVD VOB — 이음매가 튄다 / 화면이 멈춘다

두 VOB에 걸친 구간을 뽑았더니 이음매에서 소리가 튀고 화면이 잠깐 멈춘다. **원인은 조각내서 이어붙인 것 자체다.** 해결은 `SKILL.md` 1-b 절 — 바이트째 이어 붙여 하나의 스트림으로 읽는다. 아래는 그 길을 가지 않았을 때 만나는 것들이다.

### `-c copy` 로 떼어낸 조각은 끝이 썩어 있다

```bash
ffmpeg -ss 24:56 -i VTS_05_2.VOB -c copy -f mpegts a.ts   # ← 이렇게 하면
```

만들어진 조각의 **마지막 0.5~1초가 정지 프레임**이 된다. 마지막 GOP가 온전히 담기지 않아 디코더가 진짜 화면을 못 만들고 직전 프레임을 반복 출력한다. 재생하면 화면이 멈췄다가 툭 튄다.

확인 — 조각 끝부분의 프레임간 변화량을 재면 `0.00` 이 줄줄이 나온다:

```bash
# 끝 0.6초를 프레임 간격으로 뽑아 인접 프레임 차이를 본다. 0에 가까우면 정지.
```

같은 구간을 **원본에서 직접 디코딩**하면 멀쩡하다. 조각 파일을 중간에 만들지 않는 것이 답이다.

### VOB는 시각 탐색이 안 된다

`ffprobe` 가 길이를 26시간으로 읽거나 14초로 읽는다. PTS가 깨져 있어서다. 그래서:

- `-ss` 로 원하는 지점에 못 간다 (0.03초씩 바꿔도 같은 프레임이 나온다)
- `concat:` 프로토콜이나 `cat` 으로 이어붙인 파일은 더 심하다 — `-ss` 를 줘도 0.4초짜리 결과가 나온다

**해결**: 원본 단일 파일에서는 `-ss` 가 동작하므로 기준 프레임을 하나 뽑아두고, 이어붙인 스트림은 앞부분을 `fps` 필터로 훑어 상관계수로 위치를 찾는다. 찾은 값은 `-ss` 가 아니라 **`trim=start=N`** 으로 쓴다. `trim` 은 디코딩된 프레임 위에서 동작해 탐색이 필요 없다.

### `setpts`/`asetpts` 를 각각 리셋하면 A/V가 어긋난다

VOB는 비디오와 오디오의 첫 PTS가 다르다 (예: 비디오 1.9568초, 오디오 1.4000초 — 0.557초 차이). 이 차이가 곧 A/V 관계다.

```
[0:v]setpts=PTS-STARTPTS[v]    # 비디오를 자기 시작점 기준 0으로
[0:a]asetpts=PTS-STARTPTS[a]   # 오디오를 자기 시작점 기준 0으로  ← 관계가 지워진다
```

각자 0에 맞추면 그 0.557초가 사라져 소리가 그만큼 앞서거나 뒤처진다. 굳이 조각을 다뤄야 한다면 **두 스트림을 같은 기준값으로** 맞춰야 한다. 다만 필터에 들어오는 타임스탬프는 이미 0 기준으로 정규화돼 있으므로, `trim=start=1.9568` 처럼 **원본 PTS 절대값을 넣으면 영상 앞부분이 그만큼 잘려나간다.** 잘라낼 양은 절대값이 아니라 **두 스트림의 차이**다.

이 함정들이 겹치면 보정에 보정을 얹게 되고, 그 과정에서 이음매의 음성이 0.1초쯤 건너뛰어 단어가 잘린다. 애초에 조각내지 않는 것이 유일하게 확실한 해법이다.

### 이음매 검증법

고쳤다고 말하기 전에 수치로 확인한다.

```bash
# 1. 영상 — 이음매 전후 프레임간 변화량. 주변 중앙값의 2배를 넘으면 튄 것.
#    0.00 이 나오면 정지 프레임.
# 2. 오디오 — 경계에서 인접 샘플 점프. 주변 최대값보다 크면 클릭이 난다.
# 3. 말 — 이음매를 걸친 15초를 다시 받아쓰기해서 단어가 끊기거나 겹치지 않는지 본다.
```

세 가지가 모두 주변과 구별되지 않아야 끝난 것이다.

## 영상이 끊겨 보인다 — 인터레이스

**DVD로 볼 땐 멀쩡한데 내 결과물만 끊긴다면 거의 항상 이것이다.** 자세한 처리는 `SKILL.md` 1-c 절.

DVD·방송 녹화본은 인터레이스인 경우가 많다. 디인터레이스 없이 스케일하면 움직임마다 빗살이 생기고, 그게 끊김·떨림으로 보인다. 플레이어는 자동으로 풀어주므로 원본은 문제없어 보인다.

```bash
ffprobe -v error -select_streams v -show_entries stream=field_order -of default=noprint_wrappers=1 IN
ffmpeg -ss 60 -i IN -frames:v 300 -vf idet -f null - 2>&1 | grep "Multi frame"
```

`field_order=bb`/`tt` 이거나 `idet` 가 BFF/TFF 를 세면 인터레이스다. `bwdif=mode=1:parity=<0=TFF,1=BFF>` 를 **스케일 앞에** 건다.

고친 뒤 같은 `idet` 를 결과물에 돌려 `Progressive` 로 바뀌었는지 확인한다.

## 소리가 안 들린다 — 5.1 함정

완성본에서 **말소리가 안 들리거나 아주 작다**. `ffprobe` 로는 오디오 스트림이 멀쩡해 보여서 놓치기 쉽다. 채널 수를 봐야 한다.

```bash
ffprobe -v error -show_entries stream=codec_type,codec_name,channels -of default=noprint_wrappers=1 "FILE"
```

`channels=6` 이면 5.1 이다. 5.1 은 대사를 센터 채널에만 담기 때문에, 플레이어가 다운믹스를 제대로 못 하면 L/R 만 재생돼 **대사가 통째로 사라진다**. 스테레오 기기·브라우저·일부 편집 프로그램에서 흔하다.

유튜브에서 이게 생기는 이유는 `-f ba`(best audio)가 비트레이트만 보고 고르기 때문이다. EAC3 5.1(384k)이 스테레오 opus(114k)·m4a(130k)보다 숫자가 커서 5.1 이 선택된다.

**받을 때 막기:**

```bash
yt-dlp -f "bv*[height<=1080]+ba[audio_channels<=2]/b[height<=1080]" \
  --merge-output-format mp4 -o "out.%(ext)s" "URL"
```

**구울 때 막기** — 이미 5.1 을 받았어도 인코딩에서 되돌릴 수 있다. 다운믹스만으로는 여전히 작은 경우가 많아 음량 정규화를 같이 건다:

```bash
-af "loudnorm=I=-16:TP=-1.5:LRA=11" -ac 2 -ar 48000 -c:a aac -b:a 192k
```

`I=-16` 은 웹 영상의 통용 기준이다. 결과 확인:

```bash
ffmpeg -i out.mp4 -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
```

평균이 -20dB 안팎이면 정상, -30dB 아래면 아직 작다.

## yt-dlp 실패

| 증상 | 대응 |
|---|---|
| **`HTTP Error 403: Forbidden`** (자막은 되는데 영상만) | **`--cookies-from-browser chrome`** — 아래 참고 |
| `Sign in to confirm you're not a bot` | 위와 동일 |
| `The page needs to be reloaded.` | yt-dlp 가 낡았다. 아래 참고 |
| `Requested format is not available` | `-f "bv*+ba/b"` 로 완화, `-F` 로 목록 확인 |
| 자막이 안 받아짐 | `--list-subs` 로 실제 존재 여부부터 확인 |
| `--download-sections` 가 403 | 아래 참고 — 전체 받고 로컬에서 자른다 |

### 403 Forbidden — PO Token

유튜브가 PO Token(재생 출처 증명 토큰)을 요구하는데 yt-dlp 가 못 만들어서 나는 오류다. **자막은 받아지는데 영상 스트림만 403**이면 이것이다. 막히는 지점이 매번 같은 퍼센트(예: 10.7%)로 재현되는 것도 특징이다.

포맷 탐색은 시간 낭비다 — 1080p·720p·360p 를 다 시도해도 같은 곳에서 막힌다. **다만 progressive 포맷(18번, 360p 단일 파일)은 통과하는 경우가 있다.** 이건 "차단 자체는 진짜인데 저화질 대안은 열려 있다"는 신호이지 해결책은 아니다.

**1단계 — 쿠키.** 이것으로 풀리는 경우가 많다:

```bash
yt-dlp --cookies-from-browser chrome -f "bv*[height<=1080]+ba/b" --merge-output-format mp4 -o "out.%(ext)s" "URL"
```

브라우저 쿠키를 읽는 것은 사용자의 유튜브 계정을 다운로드에 연결하는 일이므로 **먼저 확인받는다**.

**2단계 — PO Token 플러그인.** 쿠키로 안 되는 영상이 실제로 있다. 최신 yt-dlp + 쿠키 + 클라이언트 4종(`web_safari`·`mweb`·`tv_embedded` 등)을 다 써도 같은 지점에서 막히는 사례를 만났다. 그때는 토큰을 **직접 만들어 주는** 플러그인을 깐다.

Node ≥ 18 이 필요하다(`node --version` 으로 확인). 두 부분으로 나뉜다 — yt-dlp 에 붙는 파이썬 플러그인과, 토큰을 생성하는 Node 스크립트.

```bash
# 1. 파이썬 플러그인 — yt-dlp 를 깐 것과 같은 파이썬에 설치해야 한다
/opt/homebrew/opt/python@3.14/bin/python3.14 -m pip install -U --break-system-packages bgutil-ytdlp-pot-provider

# 2. 토큰 생성기 — 위에서 깔린 플러그인과 같은 버전 태그로 받는다
git clone --depth 1 --branch 1.3.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git ~/bgutil-ytdlp-pot-provider
cd ~/bgutil-ytdlp-pot-provider/server && npm install --no-audit --no-fund && npx tsc
```

**버전을 맞추는 것이 중요하다.** pip 이 설치한 플러그인 버전(`pip show bgutil-ytdlp-pot-provider`)과 clone 하는 태그가 같아야 한다.

경로는 건드릴 필요가 없다. 플러그인이 `~/bgutil-ytdlp-pot-provider/server/build/generate_once.js` 를 기본값으로 찾는다. 확인:

```bash
yt-dlp --verbose --simulate "URL" 2>&1 | grep -i pot
```

`PO Token Providers: bgutil:http-... , bgutil:script-node-...` 가 뜨고 `unavailable` 이 아니면 준비된 것이다. 이후로는 **옵션을 따로 줄 필요 없이** 평소 명령이 그대로 동작한다. 상주 서버가 아니라 필요할 때만 스크립트가 호출되므로 평소엔 아무것도 돌지 않는다.

**순서를 지킨다** — 쿠키 → (실패 시) 플러그인. 플러그인 설치는 되돌리기 쉽지만 Node 의존성이 생기고 유튜브가 또 바꾸면 깨질 수 있으므로, 쿠키로 되는 영상에까지 미리 깔 이유는 없다.

### `--download-sections` 가 403

구간만 받는 이 옵션은 ffmpeg 이 스트림 URL에 직접 range 요청을 넣는 방식이라, 서명된 URL이 이를 거부하는 경우가 많다. 전체를 받고 로컬에서 자르는 편이 확실하다 — 짧은 영상은 용량 차이도 크지 않다.

### 버전이 낡았을 때

유튜브가 자주 바꿔서 yt-dlp 는 몇 달만 지나도 깨진다. **설치 경로부터 확인한다** — brew 판과 pip 판이 함께 깔려 있고 PATH 는 pip 판을 잡고 있는 경우가 흔해서, `brew upgrade yt-dlp` 를 해도 아무것도 안 바뀐다.

```bash
ls -l "$(which yt-dlp)"        # 181바이트 안팎 + python shebang = pip 설치본
head -1 "$(which yt-dlp)"      # 어느 파이썬인지
```

pip 설치본이면 그 파이썬으로 올린다:

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -m pip install -U --break-system-packages yt-dlp
```

## Whisper 결과가 이상함

- **엉뚱한 언어로 받아씀** → `--language` 미지정. 반드시 지정한다.
- **뒷부분이 통째로 반복** → 무음 구간에서 나는 환각. `--condition_on_previous_text False`
- **너무 느림** → 오디오만 추출해서 넣는다(`-vn -ac 1 -ar 16000`). 그래도 느리면 `--model small`.
- **고유명사가 다 틀림** → 정상이다. 태우기 전에 교정하는 것을 전제로 한다. `--initial_prompt` 에 고유명사를 넣어주면 나아진다.

## 파일이 너무 큼

`-crf` 를 올린다 (18 → 23 이면 절반 안팎). 화질을 유지하며 줄이려면 해상도를 낮춘다:

```bash
bash scripts/burn.sh IN.mp4 subs.ass OUT.mp4 --crf 23 --scale 1280:-2
```

`-2` 는 짝수로 맞춰 자동 계산하라는 뜻이다. H.264는 홀수 해상도를 싫어한다.

자막을 태우면 원본보다 커질 수 있다 — 자막 가장자리가 매 프레임 새로운 디테일이라 압축이 덜 된다. 정상이다.
