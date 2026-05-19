@echo off
REM =============================================
REM  NexLab LIS — Start Server
REM  Secrets are loaded from .env file
REM =============================================

set "VENV_DIR=%~dp0venv"

REM Load environment variables from .env
if exist "%~dp0.env" (
    for /F "tokens=1,2 delims==" %%A in ('type "%~dp0.env"') do (
        REM Skip comments and empty lines
        echo %%A | findstr /r "^#" >nul 2>&1
        if errorlevel 1 (
            if not "%%A"=="" set "%%A=%%B"
        )
    )
)

if not exist "%VENV_DIR%" (
    echo [ERROR] Virtual environment not found. Please run install_requirements.bat or create a venv manually.
    pause
    exit /b
)

echo Starting NexLab LIS Server...
echo Access this system at: http://localhost:%PORT%
echo.

REM Start CBC Device Watcher in a separate window
echo Starting CBC Device Watcher...
start "NexLab CBC Device Watcher" "%VENV_DIR%\Scripts\python.exe" device_interfacing\device_watcher.py

"%VENV_DIR%\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port %PORT%
pause
