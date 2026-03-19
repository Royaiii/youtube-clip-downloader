@echo off
chcp 65001 >nul
echo ================================
echo  YouTube Clip Downloader Setup
echo ================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 설치하세요.
    pause
    exit /b 1
)

:: Install dependencies
echo [1/3] 패키지 설치 중...
pip install PyQt6 yt-dlp --quiet

:: Check ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [2/3] ffmpeg 설치 중...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] ffmpeg 자동 설치 실패. 수동 설치가 필요합니다.
        echo https://www.gyan.dev/ffmpeg/builds/
    )
) else (
    echo [2/3] ffmpeg OK
)

:: Run
echo [3/3] 실행 중...
echo.
python "%~dp0main.py"
