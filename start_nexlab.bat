@echo off
set "PORT=8000"
set "NEXLAB_SECRET_KEY=4b43e2ea33359edea2eded998578fe8785eb26868802307904fdcf49de548f98"
set "GEMINI_API_KEY=AIzaSyAWeSEW-Z_sVZhFZmcpj1DmnLgRaTWatcU"
set "VENV_DIR=%~dp0venv"

if not exist "%VENV_DIR%" (
    echo [ERROR] Virtual environment not found. Please run install_requirements.bat or create a venv manually.
    pause
    exit /b
)

echo Starting NexLab LIS (Development)...
echo Access this system at: http://localhost:%PORT%
echo.
"%VENV_DIR%\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port %PORT% --reload
pause
