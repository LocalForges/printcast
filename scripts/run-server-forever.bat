@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Printcast Server Guard
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
:loop
"%PY%" -m printcast --server-only --no-open-browser
echo Server exited, restart in 3s...
timeout /t 3 /nobreak >nul
goto loop
