@echo off
REM Developer shortcut: start the LeadScout AI web app (this computer only).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo The virtual environment is missing. See "Getting Started" in README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" launch.py
if errorlevel 1 pause
