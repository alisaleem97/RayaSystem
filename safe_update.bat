@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ==========================================
echo    NexLab Safe System Update
echo ==========================================
echo.

set "VENV_PATH=venv"
set "PYTHON_EXE=%VENV_PATH%\Scripts\python.exe"
set "DB_FILE=lab_database.db"
set "UPDATE_FOLDER=NexLab_Update"

:: ──────────────────────────────────────────────
:: PRE-FLIGHT CHECKS
:: ──────────────────────────────────────────────

:: Check Python / venv exists
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment not found at '%VENV_PATH%'.
    echo         Please run 'install_requirements.bat' first.
    pause
    exit /b 1
)

:: Check database exists
if not exist "%DB_FILE%" (
    echo [ERROR] Database file '%DB_FILE%' not found.
    echo         This script must be run from inside the NexLab_Published folder.
    pause
    exit /b 1
)

:: Check update folder exists
if not exist "%UPDATE_FOLDER%" (
    echo [ERROR] Update folder '%UPDATE_FOLDER%' not found!
    echo.
    echo HOW TO USE THIS SCRIPT:
    echo   1. Stop the NexLab server ^(close the start_nexlab window^)
    echo   2. Copy the new NexLab_Published folder NEXT to this script
    echo      and rename it to '%UPDATE_FOLDER%'
    echo   3. Run this script again
    echo.
    pause
    exit /b 1
)

:: ──────────────────────────────────────────────
:: STEP 1: Confirm server is stopped
:: ──────────────────────────────────────────────
echo [IMPORTANT] Make sure the NexLab server is STOPPED before continuing.
echo             Close the 'start_nexlab.bat' window if it is open.
echo.
set /p confirm="Is the server stopped? (y/n): "
if /i "%confirm%" NEQ "y" (
    echo Update cancelled. Please stop the server and try again.
    pause
    exit /b 0
)
echo.

:: ──────────────────────────────────────────────
:: STEP 2: Checkpoint the database (flush WAL)
:: ──────────────────────────────────────────────
echo [Step 1/5] Flushing database writes (WAL checkpoint)...
"%PYTHON_EXE%" tools\checkpoint_db.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Database checkpoint failed. Update cancelled for safety.
    echo         Make sure the server is completely stopped and try again.
    pause
    exit /b 1
)
echo   Done.
echo.

:: ──────────────────────────────────────────────
:: STEP 3: Backup the database
:: ──────────────────────────────────────────────
echo [Step 2/5] Backing up database...
"%PYTHON_EXE%" tools\backup_db.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Database backup failed. Update cancelled for safety.
    pause
    exit /b 1
)
echo   Done.
echo.

:: ──────────────────────────────────────────────
:: STEP 4: Copy new code files (PROTECT data files)
:: ──────────────────────────────────────────────
echo [Step 3/5] Updating system files...
echo   Protected files (will NOT be overwritten):
echo     - lab_database.db (and WAL/SHM files)
echo     - .env (server configuration)
echo     - venv\ (Python environment)
echo     - backups\ (database backups)
echo     - uploads\ (patient attachments)
echo.

:: Use robocopy to merge new files into the current folder.
:: /E   = copy subdirectories including empty ones
:: /XF  = exclude specific files
:: /XD  = exclude specific directories
:: /NFL = no file listing (cleaner output)
:: /NDL = no directory listing
:: /NJH = no job header
:: /NJS = no job summary  
:: /IS  = include same files (overwrite even if identical)
:: /IT  = include tweaked files
robocopy "%UPDATE_FOLDER%" "." /E /IS /IT /XF "lab_database.db" "lab_database.db-wal" "lab_database.db-shm" ".env" /XD "venv" "backups" "uploads" "__pycache__" /NFL /NDL /NJH /NJS

:: Robocopy returns codes 0-7 for success, 8+ for errors
if %ERRORLEVEL% GEQ 8 (
    echo [ERROR] File copy failed with error code %ERRORLEVEL%.
    echo         Your database is safe. Check the update folder and try again.
    pause
    exit /b 1
)
echo   System files updated successfully.
echo.

:: ──────────────────────────────────────────────
:: STEP 5: Install any new dependencies
:: ──────────────────────────────────────────────
echo [Step 4/5] Checking for new dependencies...
"%VENV_PATH%\Scripts\pip.exe" install -r requirements.txt --quiet 2>nul
echo   Dependencies up to date.
echo.

:: ──────────────────────────────────────────────
:: STEP 6: Run database migrations
:: ──────────────────────────────────────────────
echo [Step 5/5] Running database migrations...
"%PYTHON_EXE%" migrations\run_all.py
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some migrations may have had issues. Check output above.
    echo           Your database backup is safe in the 'backups' folder.
)
echo.

:: ──────────────────────────────────────────────
:: DONE — Clean up update folder
:: ──────────────────────────────────────────────
echo ==========================================
echo   Update Complete!
echo ==========================================
echo.
echo   Your database and patient data are safe.
echo   A backup was created in the 'backups' folder.
echo.

:: Auto-cleanup the update folder
echo   Cleaning up update folder...
rmdir /S /Q "%UPDATE_FOLDER%" 2>nul
if not exist "%UPDATE_FOLDER%" (
    echo   '%UPDATE_FOLDER%' folder removed automatically.
) else (
    echo   Could not remove '%UPDATE_FOLDER%' folder. You can delete it manually.
)
echo.
echo   You can now run 'start_nexlab.bat' to start the system.
echo.
pause

