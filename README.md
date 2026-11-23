# video-subtitle-clip (Claude Code 스킬)

영상에서 원하는 구간을 잘라 자막(원어+번역 이중 자막)을 입혀 MP4로 만드는 Claude Code 스킬.
유튜브 링크·로컬 파일(avi·mkv·mp4·mov) 모두 가능. 맥·윈도우 공용.

## 윈도우 PC에 설치하기

1. **Claude Code 설치** — 아직 없다면 먼저 설치하고 로그인.
2. **이 레포 받기** — 아래 둘 중 하나.
   - 브라우저로 이 레포 페이지 → 초록색 `Code` 버튼 → `Download ZIP` → 압축 풀기
   - 또는 Git 이 있다면: `git clone https://github.com/butdifferent87/video-subtitle-clip-skill.git`
3. **설치 스크립트 실행** — 압축 푼 폴더에서 주소창에 `powershell` 입력 후 엔터, 그리고:
   ```
   powershell -ExecutionPolicy Bypass -File .\install.ps1
   ```
   ffmpeg·yt-dlp·Python·Git 설치, 받아쓰기 패키지 설치, 스킬 복사까지 자동으로 한다.
4. **PowerShell·Claude Code 를 껐다 켜기** — 새 설정이 적용되도록.
5. Claude Code 에서 "이 유튜브 영상 3:20~5:10 잘라서 자막 붙여줘" 처럼 말하면 스킬이 동작한다.

엔비디아 그래픽카드(RTX 등)가 있으면 `install.ps1` 이 GPU 받아쓰기 부품(cuBLAS·cuDNN)까지 깔아서, 받아쓰기가 GPU 로 돈다. 설치 끝에 「GPU 받아쓰기 준비 끝」이 보이면 된다.

## 맥에 설치하기

이 폴더에서 `bash install.sh` — ffmpeg@7·yt-dlp·whisper.cpp 설치, 받아쓰기 모델(1.6GB) 다운로드, 스킬 복사까지 한다. 맥은 whisper.cpp 가 애플 칩 GPU 로 받아쓴다.

## 받아쓰기 엔진 (자동 선택)

`scripts/fw_transcribe.py` 가 컴퓨터에 맞는 가장 빠른 엔진을 고른다. 어느 게 잡혔는지는 `python3 scripts/fw_transcribe.py --check` 로 본다.

| 컴퓨터 | 엔진 | 속도 (영상 길이 대비) |
|--------|------|------|
| 윈도우 + 엔비디아 GPU | faster-whisper CUDA | 가장 빠름 |
| 맥 (애플 칩) | whisper.cpp Metal | 약 15배 (M3 Pro 실측, 정밀 시각 포함) |
| 그 외 | faster-whisper CPU | 1.5~3배 |

## 업데이트

이 레포가 원본이다. 고친 뒤 올리면, 맥은 `git pull && bash install.sh`, 윈도우는 `git pull`(또는 ZIP 다시 받기) 후 `install.ps1` 을 다시 실행한다.

## 구성

- `video-subtitle-clip/SKILL.md` — 스킬 본문 (작업 절차)
- `video-subtitle-clip/scripts/` — 자막 변환·싱크·검수·굽기 스크립트
- `video-subtitle-clip/references/troubleshooting.md` — 막혔을 때 해결법
- `install.ps1` — 윈도우 원클릭 설치
- `install.sh` — 맥 원클릭 설치
