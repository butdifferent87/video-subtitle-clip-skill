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

## 업데이트

맥에서 스킬을 고친 뒤 이 레포에 다시 올리면, 윈도우에서는 ZIP 을 다시 받아 `install.ps1` 을 다시 실행하면 된다.

## 구성

- `video-subtitle-clip/SKILL.md` — 스킬 본문 (작업 절차)
- `video-subtitle-clip/scripts/` — 자막 변환·싱크·검수·굽기 스크립트
- `video-subtitle-clip/references/troubleshooting.md` — 막혔을 때 해결법
- `install.ps1` — 윈도우 원클릭 설치
