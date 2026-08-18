@echo off
REM ============================================================
REM run_freeze.bat
REM Sky Bet Acca Freeze screener.
REM
REM Costs 8 OddsPapi requests, plus up to 2 more only if the
REM team-name cache has gone stale (refreshes every 14 days).
REM
REM Calls venv\Scripts\python.exe directly rather than using
REM activate.bat, which still carries a stale path from the
REM project folder move.
REM ============================================================

REM Work from this file's own folder, so double-clicking works
REM regardless of where Explorer thinks it is.
cd /d "%~dp0"

echo.
echo ============================================================
echo  ACCA FREEZE SCREENER
echo ============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo ERROR: venv\Scripts\python.exe not found.
    echo        Expected it under %CD%
    echo.
    pause
    exit /b 1
)

venv\Scripts\python.exe scripts\freeze_bot\run_freeze.py %*

if errorlevel 1 (
    echo.
    echo ============================================================
    echo  RUN FAILED - see the error above.
    echo  The CSV may still have been written to output\
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done. Opening the output folder...
echo ============================================================
start "" "%CD%\output"

pause