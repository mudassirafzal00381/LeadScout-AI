@echo off
title LeadScout AI
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo LeadScout AI is not installed yet.
    echo Please double-click "Install LeadScout AI.bat" first.
    echo.
    pause
    exit /b 1
)
echo Starting LeadScout AI... your browser will open in a moment.
".venv\Scripts\python.exe" launch.py
if errorlevel 1 pause
