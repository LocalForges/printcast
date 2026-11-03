@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
title Printcast - WebView2
where python >nul 2>nul
if not errorlevel 1 (
    python src\desktop\desktop_launcher.py
    if errorlevel 1 pause
    exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 src\desktop\desktop_launcher.py
    if errorlevel 1 pause
    exit /b
)
echo Python 3 is required.
pause
