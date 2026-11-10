@echo off
setlocal
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0fenestra_z8_debug.pyw"
    exit /b 0
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0fenestra_z8_debug.pyw"
    exit /b 0
)
echo Python 3.11+ with Tk is required.
echo Install requirements-host.txt, then run fenestra_z8_debug.pyw.
pause
exit /b 1
