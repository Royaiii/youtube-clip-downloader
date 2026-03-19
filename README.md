# YouTube Clip Downloader

YouTube 영상에서 원하는 구간만 잘라서 다운로드하는 GUI 프로그램입니다.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## 기능

- YouTube URL 입력 → 영상 정보 자동 로드
- **드래그 슬라이더**로 시작/종료 구간 선택
- 실시간 다운로드 진행률 표시
- 소리 제거 옵션
- 정확한 자르기 옵션 (프레임 단위)
- 저장 경로 자유 지정
- 다크 테마 UI

## 스크린샷

> (추후 추가)

## 설치 및 실행

### 방법 1: Python으로 직접 실행 (권장)

```bash
# 필수 패키지 설치
pip install PyQt6 yt-dlp

# ffmpeg 설치 (Windows)
winget install ffmpeg

# 실행
python clip.py
```

### 방법 2: exe 직접 실행

[Releases](../../releases) 페이지에서 ZIP 다운로드 후:

1. ZIP 압축 해제
2. `YouTube클립다운로더.exe` 실행

> 같은 폴더에 `yt-dlp.exe`, `ffmpeg.exe`, `deno.exe`가 있어야 합니다.

## 사용법

1. YouTube URL 붙여넣기
2. **불러오기** 클릭 → 영상 제목과 길이 로드
3. 슬라이더 드래그 또는 시간 직접 입력으로 구간 선택
4. **다운로드** 클릭

### 옵션

| 옵션 | 설명 |
|------|------|
| 정확한 자르기 | 프레임 단위 정확하지만 느림 (재인코딩) |
| 소리 제거 | 오디오 트랙 제거 |

## 빌드 (exe 만들기)

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name "YouTube클립다운로더" clip.py
```

빌드 후 `dist/` 폴더에 아래 파일을 함께 넣어야 합니다:
- `yt-dlp.exe` — [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases)
- `ffmpeg.exe` — [ffmpeg builds](https://www.gyan.dev/ffmpeg/builds/)
- `deno.exe` — [deno releases](https://github.com/denoland/deno/releases)

## 의존성

| 패키지 | 용도 |
|--------|------|
| [PyQt6](https://pypi.org/project/PyQt6/) | GUI |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | YouTube 다운로드 |
| [ffmpeg](https://ffmpeg.org/) | 영상 구간 자르기 |
| [deno](https://deno.land/) | yt-dlp YouTube JS 해석 |

## 라이선스

MIT License
