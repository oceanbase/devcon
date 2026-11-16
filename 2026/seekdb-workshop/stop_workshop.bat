@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
echo Stopping Workshop services and notebook kernels...
".venv\Scripts\python.exe" "scripts\stop_workshop.py"
set "WORKSHOP_STOP_STATUS=%errorlevel%"
goto done
:missing
echo Project Python was not found. Restore .venv before running this script.
set "WORKSHOP_STOP_STATUS=1"
:done
rem Release this window's working directory before the user deletes the course.
cd /d "%TEMP%"
echo.
echo If another PowerShell window is inside the course folder, run cd .. there.
echo Press any key to close this window.
pause >nul
exit /b %WORKSHOP_STOP_STATUS%
