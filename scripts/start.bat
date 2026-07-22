@echo off
REM ============================================================================
REM Confluence Trading Consultant - one-click app launcher.
REM Double-click to run.
REM ============================================================================
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0\.."

set "VENV=apps\api\venv"
set "PYEXE=%VENV%\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo First-time setup required.
    call "%~dp0\install.bat"
    exit /b %errorlevel%
)

if not exist "apps\web\node_modules" (
    echo First-time setup required.
    call "%~dp0\install.bat"
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo   Confluence Trading Consultant
echo.
echo   API: http://localhost:8000
echo   UI : http://localhost:3000  (opens automatically)
echo.
echo   Logs: %CD%\logs\api.log, %CD%\logs\web.log
echo   Stop: close this window or press Ctrl+C.
echo ============================================================
echo.

"%PYEXE%" "%CD%\apps\api\dev_server.py" %*
