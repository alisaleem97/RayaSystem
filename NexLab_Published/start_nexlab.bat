@echo off
set "PORT=8000"
set "VENV_DIR=%~dp0venv"
if not exist "%VENV_DIR%" (
    echo [ERROR] Virtual environment not found. Please run 'install_requirements.bat' first.
    pause
    exit /b
)
echo Starting NexLab LIS Server...
echo Access this system at: http://localhost:%PORT%
"%VENV_DIR%\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port %PORT%
pause
