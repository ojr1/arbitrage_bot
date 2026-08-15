@echo off
REM ===========================================================
REM  run_2up.bat
REM  Location: project root (C:\projects\arbitrage_bot\)
REM
REM  Double-click this file to run the 2Up signal scan.
REM
REM  NOTE ON HOW THIS WORKS
REM  Version 1 called "venv\Scripts\activate.bat" first. That proved
REM  unreliable - activate.bat can hold the absolute path baked in when
REM  the venv was created, so if the project folder has ever been moved
REM  or renamed it quietly points nowhere and Windows falls back to the
REM  system Python, which has none of our libraries installed.
REM
REM  This version skips activation altogether and calls the venv's own
REM  python.exe directly. A venv python ALWAYS uses its own packages
REM  without needing to be "activated" - activation is only a convenience
REM  for typing "python" in a terminal.
REM ===========================================================

cd /d "%~dp0"

set "VENV_PY=%~dp0venv\Scripts\python.exe"
set "BOT=%~dp0scripts\2up_bot\run.py"

if not exist "%VENV_PY%" (
    echo.
    echo   ERROR: could not find the virtual environment's Python.
    echo   Expected at: %VENV_PY%
    echo.
    echo   Either this file is not in the project root, or the venv
    echo   needs rebuilding:
    echo       python -m venv venv
    echo       venv\Scripts\activate
    echo       pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "%BOT%" (
    echo.
    echo   ERROR: could not find the bot script.
    echo   Expected at: %BOT%
    echo.
    pause
    exit /b 1
)

REM Show which Python is actually running, so a fallback to the wrong
REM interpreter is obvious immediately rather than as a missing module.
echo   Using: %VENV_PY%
echo.

"%VENV_PY%" "%BOT%"

echo.
echo   ----------------------------------------------------------
echo   Finished. Spreadsheets are in the outputs folder.
echo   Press any key to close.
echo   ----------------------------------------------------------
pause >nul