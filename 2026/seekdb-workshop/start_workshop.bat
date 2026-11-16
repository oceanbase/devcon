@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto detect_python
if not exist ".venv\pyvenv.cfg" goto detect_python
".venv\Scripts\python.exe" scripts\setup_environment.py --check >nul 2>&1
if "%errorlevel%"=="0" goto launch
call :probe_python ".venv\Scripts\python.exe"
if not errorlevel 1 goto setup

:detect_python
set "WORKSHOP_BOOTSTRAP_PYTHON="
call :probe_python python
if not errorlevel 1 goto setup
call :probe_python python3
if not errorlevel 1 goto setup
call :probe_python py -3
if not errorlevel 1 goto setup
for %%V in (3.15 3.14 3.13 3.12 3.11) do (
  call :probe_python python%%V
  if not errorlevel 1 goto setup
)
for %%V in (315 314 313 312 311) do (
  if defined LOCALAPPDATA (
    call :probe_python "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    if not errorlevel 1 goto setup
  )
  if defined ProgramFiles (
    call :probe_python "%ProgramFiles%\Python%%V\python.exe"
    if not errorlevel 1 goto setup
  )
)

echo CPython 3.11 or newer was not found.
echo Install CPython 3.11 or newer ^(64-bit^) and enable "Add python.exe to PATH".
echo Then open a new terminal or double-click this file again.
goto failed

:setup
call %WORKSHOP_BOOTSTRAP_PYTHON% scripts\setup_environment.py
if not "%errorlevel%"=="0" goto failed

:launch
".venv\Scripts\python.exe" scripts\launch_notebook.py
if not "%errorlevel%"=="0" goto failed
echo.
echo Course is running. Copy the Notebook URL above if the browser did not open.
echo Press any key to close this window. The course will keep running.
pause >nul
exit /b 0

:probe_python
set "WORKSHOP_PROBE_FILE=%TEMP%\seekdb-python-probe-%RANDOM%-%RANDOM%.txt"
if exist "%WORKSHOP_PROBE_FILE%" del "%WORKSHOP_PROBE_FILE%" >nul 2>&1
call %* -c "import pathlib,sys; sys.exit(1) if sys.implementation.name != 'cpython' or sys.version_info[0] != 3 or sys.version_info[:2] < (3,11) else pathlib.Path(sys.argv[-1]).write_text('ok',encoding='utf-8')" "%WORKSHOP_PROBE_FILE%" >nul 2>&1
if not "%errorlevel%"=="0" goto probe_failed
if not exist "%WORKSHOP_PROBE_FILE%" goto probe_failed
del "%WORKSHOP_PROBE_FILE%" >nul 2>&1
set "WORKSHOP_BOOTSTRAP_PYTHON=%*"
exit /b 0

:probe_failed
if exist "%WORKSHOP_PROBE_FILE%" del "%WORKSHOP_PROBE_FILE%" >nul 2>&1
exit /b 1

:failed
echo.
echo Workshop startup failed. See the message above.
echo Startup logs: .runtime\launcher.log and .runtime\jupyter.log
pause
exit /b 1
