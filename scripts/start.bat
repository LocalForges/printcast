@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
title Printcast - Desktop
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m printcast
if errorlevel 1 pause
exit /b
