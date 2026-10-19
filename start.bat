@echo off
if not exist "%~dp0start.vbs" (
    echo Missing start.vbs. Please restore the project launcher files.
    pause
    exit /b 1
)
start "" "%SystemRoot%\System32\wscript.exe" "%~dp0start.vbs"
exit /b 0
