@echo off
REM ============================================================================
REM Confluence Trading Consultant - one-click installer
REM Double-click to run. C:\python3.11+ and node are required.
REM ============================================================================
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0\.."

echo.
echo ============================================================
echo   Confluence Trading Consultant - First-time setup
echo ============================================================
echo.

REM ---- Locate Python ----
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not on PATH.
    echo Install Python 3.11+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ---- Locate Node ----
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not on PATH.
    echo Install Node 18+ from https://nodejs.org/
    pause
    exit /b 1
)

REM ---- Python venv ----
echo [1/4] Python venv ...
cd apps\api
if not exist "venv" (
    python -m venv venv
    if errorlevel 1 goto :err
)
call venv\Scripts\activate
python -m pip install --upgrade pip wheel setuptools >nul

REM ---- Backend deps ----
echo [2/4] Backend deps (this can take a few minutes) ...
pip install -r requirements.txt
if errorlevel 1 goto :err

REM ---- Frontend deps ----
echo [3/4] Frontend deps ...
cd ..\web
if not exist "node_modules" (
    call npm install
    if errorlevel 1 goto :err
)

REM ---- Build frontend ----
echo [4/4] Frontend production build ...
if not exist ".next" (
    call npm run build
    if errorlevel 1 goto :err
)

cd ..\..
echo.
echo ============================================================
echo   Setup complete!
echo.
echo   To start the app, double-click scripts\start.bat
echo ============================================================
echo.
pause
exit /b 0

:err
echo.
echo ERROR: Setup failed. See the messages above.
echo Reach out via https://commandcode.ai if the issue persists.
pause
exit /b 1
