@echo off
REM Builds a portable Windows version of LeadScout AI into dist\LeadScout\
REM Run this on the developer PC, then copy dist\LeadScout to the client PC.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Creating virtual environment...
    python -m venv .venv || goto :error
)

echo Installing dependencies...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements-dev.txt || goto :error

echo Building...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --console ^
    --name LeadScout ^
    --collect-data playwright ^
    main.py || goto :error

mkdir dist\LeadScout\output 2>nul
copy /y README.md dist\LeadScout\ >nul
(
    echo @echo off
    echo "%%~dp0LeadScout.exe" --check
    echo pause
) > "dist\LeadScout\Check Setup.bat"

echo.
echo Build complete: dist\LeadScout\LeadScout.exe
echo Copy the whole dist\LeadScout folder to the client PC.
exit /b 0

:error
echo.
echo Build FAILED.
exit /b 1
