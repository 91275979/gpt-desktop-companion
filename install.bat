@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Install Python 3.11 or newer from https://www.python.org/downloads/windows/
    echo During installation, enable "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :failed
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Installation complete. Double-click start.vbs to launch GPT Companion.
pause
exit /b 0

:failed
echo.
echo [ERROR] Installation failed. Check the messages above and try again.
pause
exit /b 1
