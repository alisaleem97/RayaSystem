@echo off
echo Preparing NexLab Environment...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ first.
    pause
    exit /b
)
if not exist "venv" (
    python -m venv venv
)
echo Installing dependencies...
"venv\Scripts\pip.exe" install -r requirements.txt
"venv\Scripts\python.exe" -m playwright install chromium
echo Setup Complete! Run 'start_nexlab.bat'
pause
