@echo off
REM Starts the LeadScout AI web app, reachable only from this computer.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo The virtual environment is missing. See "Getting Started" in README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address localhost
