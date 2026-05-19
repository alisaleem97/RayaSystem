@echo off
setlocal
set "VENV_PATH=venv"
set "PYTHON_EXE=%VENV_PATH%\Scripts\python.exe"

echo ==========================================
echo       NexLab System Update Tool
echo ==========================================
echo.

:: Step 1: Backup Database
echo [Step 1/3] Backing up database...
"%PYTHON_EXE%" tools\backup_db.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Database backup failed. Update cancelled for safety.
    pause
    exit /b %ERRORLEVEL%
)
echo.

:: Step 2: Inform User about Code Updates
echo [Step 2/3] Code Updates
echo Please ensure you have copied the new system files into this folder.
echo (If you are using Git, you would 'git pull' now.)
echo.
set /p confirm="Have you updated the system files? (y/n): "
if /i "%confirm%" NEQ "y" (
    echo Update paused. Please copy the new files and run this script again.
    pause
    exit /b 0
)
echo.

:: Step 3: Run Migrations
echo [Step 3/3] Running database migrations...
"%PYTHON_EXE%" migrations\run_all.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Migrations failed. Please check the logs.
    pause
    exit /b %ERRORLEVEL%
)
echo.

echo ==========================================
echo System Update Completed Successfully!
echo ==========================================
echo.
echo You can now restart the system using 'start_nexlab.bat'.
echo.
pause
