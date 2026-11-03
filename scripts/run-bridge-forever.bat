@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Collector Guard
set "PYTHONPATH=%CD%\src\desktop;%PYTHONPATH%"
:loop
python -c "from desktop_launcher import bridge_status; import sys; sys.exit(0 if bridge_status()['ok'] else 1)"
if not errorlevel 1 (
    timeout /t 5 /nobreak >nul
    goto loop
)
node src\collector\live-collector.mjs
echo Collector exited, restart in 3s...
timeout /t 3 /nobreak >nul
goto loop
