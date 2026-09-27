@echo off
setlocal
title LeadScout AI - Setup
cd /d "%~dp0"
echo ==========================================================
echo    LeadScout AI - one-time setup
echo ==========================================================
echo.
echo This installs everything LeadScout AI needs. It takes about
echo 5-10 minutes and needs an internet connection.
echo.

REM --- 1. Find Python 3.11 (or install it) ------------------------------
set "PY="
py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%ProgramFiles%\Python311\python.exe" set PY="%ProgramFiles%\Python311\python.exe"

if not defined PY (
    echo [1/4] Python 3.11 not found - installing it from Microsoft's app store service winget...
    where winget >nul 2>&1
    if errorlevel 1 goto :nopython
    winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY goto :nopython
echo [1/4] Python 3.11 found.

REM Windows limits file paths to 260 characters and some libraries install
REM deep folders, so the LeadScout AI folder itself must have a short path.
%PY% -c "import sys; sys.exit(len(sys.argv[1]) > 80)" "%~dp0"
if errorlevel 1 goto :longpath

REM --- 2. Private environment for LeadScout AI --------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Creating LeadScout AI's private Python environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo [2/4] Environment already exists.
)

REM --- 3. Libraries ------------------------------------------------------
echo [3/4] Installing libraries - this is the slow part, please wait...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check -q
if errorlevel 1 goto :fail

REM --- 4. Desktop shortcut with the LeadScout AI logo ---------------------
echo [4/4] Creating the "LeadScout AI" shortcut on your desktop...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\LeadScout AI.lnk'); $s.TargetPath='%~dp0Start LeadScout AI.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0assets\icon.ico'; $s.Description='LeadScout AI - Lead Generation Tool'; $s.Save()"

echo.
echo ==========================================================
echo    Checking this PC is ready...
echo ==========================================================
".venv\Scripts\python.exe" main.py --check
echo.
echo Setup complete! Start LeadScout AI any time with the
echo "LeadScout AI" icon on your desktop.
echo.
choice /C YN /M "Start LeadScout AI now"
if errorlevel 2 exit /b 0
start "" "%~dp0Start LeadScout AI.bat"
exit /b 0

:nopython
echo.
echo Python 3.11 could not be installed automatically.
echo Please install it manually:
echo   1. Open https://www.python.org/downloads/release/python-3119/
echo   2. Download "Windows installer (64-bit)" and run it.
echo   3. Tick "Add python.exe to PATH", click "Install Now".
echo   4. Run "Install LeadScout AI.bat" again.
echo.
pause
exit /b 1

:longpath
echo.
echo This folder's location is too long for Windows:
echo   %~dp0
echo Please move the whole "LeadScout AI" folder to  C:\LeadScout AI
echo and run "Install LeadScout AI.bat" again from there.
echo.
pause
exit /b 1

:fail
echo.
echo Setup did not finish. Check your internet connection and run
echo "Install LeadScout AI.bat" again. If it keeps failing, send a
echo screenshot of this window to your LeadScout AI provider.
echo.
pause
exit /b 1
