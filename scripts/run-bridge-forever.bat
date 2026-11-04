@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Printcast Collector Guard
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
:loop
"%PY%" -c "from printcast.probe import bridge_status; import sys; sys.exit(0 if bridge_status()['ok'] else 1)"
if not errorlevel 1 (
    timeout /t 5 /nobreak >nul
    goto loop
)
node src\collector\live-collector.mjs
echo Collector exited, restart in 3s...
timeout /t 3 /nobreak >nul
goto loop
