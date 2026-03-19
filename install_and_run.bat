@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ================================
echo  YouTube Clip Downloader Setup
echo ================================
echo.

:: Get script directory
set "SCRIPT_DIR=%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [1/4] Python not found. Installing...
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo [ERROR] Python install failed.
        echo Download from https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo.
    echo Python installed. Please restart this file.
    pause
    exit /b 0
) else (
    echo [1/4] Python OK
)

:: Install dependencies
echo [2/4] Installing packages...
pip install PyQt6 yt-dlp --quiet

:: Check ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [3/4] Installing ffmpeg...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] ffmpeg auto-install failed.
        echo Download from https://www.gyan.dev/ffmpeg/builds/
    ) else (
        echo [3/4] ffmpeg OK
    )
) else (
    echo [3/4] ffmpeg OK
)

:: Run
echo [4/4] Starting...
echo.
cd /d "%SCRIPT_DIR%"
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] An error occurred.
    pause
)
