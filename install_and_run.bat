@echo off
chcp 65001 >nul
echo ================================
echo  YouTube Clip Downloader Setup
echo ================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [1/4] Python이 설치되어 있지 않습니다. 설치 중...
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo [ERROR] Python 자동 설치 실패.
        echo https://www.python.org/downloads/ 에서 직접 설치하세요.
        pause
        exit /b 1
    )
    echo.
    echo Python 설치 완료. 터미널을 다시 열고 이 파일을 다시 실행하세요.
    pause
    exit /b 0
) else (
    echo [1/4] Python OK
)

:: Install dependencies
echo [2/4] 패키지 설치 중...
pip install PyQt6 yt-dlp --quiet

:: Check ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [3/4] ffmpeg 설치 중...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] ffmpeg 자동 설치 실패. 수동 설치가 필요합니다.
        echo https://www.gyan.dev/ffmpeg/builds/
    ) else (
        echo [3/4] ffmpeg 설치 완료
    )
) else (
    echo [3/4] ffmpeg OK
)

:: Run
echo [4/4] 실행 중...
echo.
python "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo [ERROR] 실행 중 오류가 발생했습니다.
    pause
)
