@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
title Printcast Live Collector
where node >nul 2>nul
if errorlevel 1 (
    echo Node.js is required.
    pause
    exit /b 1
)
if not "%~1"=="" (
    node src\collector\live-collector.mjs %~1
) else (
    node src\collector\live-collector.mjs
)
pause
