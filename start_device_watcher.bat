@echo off
set "VENV_DIR=%~dp0venv"
if not exist "%VENV_DIR%" (
    echo [ERROR] Virtual environment not found. Please run 'install_requirements.bat' first.
    pause
    exit /b
)
echo =====================================================
echo    NexLab CBC Device Watcher
echo =====================================================
echo.
"%VENV_DIR%\Scripts\python.exe" device_interfacing\device_watcher.py
pause
