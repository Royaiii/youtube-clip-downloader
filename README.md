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
- 중복 파일 덮어쓰기 확인
- 저장 경로 자유 지정
- 다크 테마 UI

## 빠른 시작 (Windows)

1. [Python 3.10+](https://www.python.org/downloads/) 설치
2. 이 레포를 다운로드하거나 clone
3. `install_and_run.bat` 더블클릭

> 첫 실행 시 자동으로 필요한 패키지(PyQt6, yt-dlp, ffmpeg)를 설치합니다.

## 수동 설치

```bash
# 레포 클론
git clone https://github.com/Royaiii/youtube-clip-downloader.git
cd youtube-clip-downloader

# 패키지 설치
pip install -r requirements.txt

# ffmpeg 설치 (Windows)
winget install ffmpeg

# 실행
python main.py
```

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

## 의존성

| 패키지 | 용도 |
|--------|------|
| [PyQt6](https://pypi.org/project/PyQt6/) | GUI |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | YouTube 다운로드 엔진 |
| [ffmpeg](https://ffmpeg.org/) | 영상 구간 자르기 |

## 라이선스

MIT License — 자유롭게 사용, 수정, 배포할 수 있습니다.
