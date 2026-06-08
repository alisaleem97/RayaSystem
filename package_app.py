import os
import shutil
import glob

def package():
    # --- CONFIGURATION ---
    PORT = 8000
    # ---------------------

    dist_dir = "NexLab_Published"
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir)

    # 1. Copy application directories
    include_dirs = ['app', 'routes', 'templates', 'static', 'uploads', 'tmp', 'device_interfacing', 'migrations', 'tools']
    # Removed lab_database.db from include_files to prevent overwriting production data
    # NOTE: .env is NOT included — server has its own config with different secrets
    include_files = [
        'main.py', 'models.py', 'database.py', 'requirements.txt',
        'update_system.bat', 'safe_update.bat', 'System_Update_Guide.md'
    ]

    for d in include_dirs:
        if os.path.exists(d):
            shutil.copytree(d, os.path.join(dist_dir, d), dirs_exist_ok=True,
                           ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
        else:
            os.makedirs(os.path.join(dist_dir, d), exist_ok=True)

    for f in include_files:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(dist_dir, f))

    # 2. Create Start Script
    start_bat_content = f"""@echo off
set "VENV_DIR=%~dp0venv"

REM Load environment variables from .env
if exist "%~dp0.env" (
    for /F "tokens=1,2 delims==" %%A in ('type "%~dp0.env"') do (
        echo %%A | findstr /r "^#" >nul 2>&1
        if errorlevel 1 (
            if not "%%A"=="" set "%%A=%%B"
        )
    )
)

if not exist "%VENV_DIR%" (
    echo [ERROR] Virtual environment not found. Please run 'install_requirements.bat' first.
    pause
    exit /b
)
echo Starting NexLab LIS Server...
echo Access this system at: http://localhost:%PORT%
echo.
REM Start CBC Device Watcher in a separate window
echo Starting CBC Device Watcher...
start "NexLab CBC Device Watcher" "%VENV_DIR%\\\\Scripts\\\\python.exe" device_interfacing\\\\device_watcher.py
"%VENV_DIR%\\\\Scripts\\\\python.exe" -m uvicorn main:app --host 0.0.0.0 --port %PORT%
pause
"""
    with open(os.path.join(dist_dir, "start_nexlab.bat"), "w") as f:
        f.write(start_bat_content)

    # 2b. Create standalone Device Watcher script
    watcher_bat_content = """@echo off
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
"%VENV_DIR%\\\\Scripts\\\\python.exe" device_interfacing\\\\device_watcher.py
pause
"""
    with open(os.path.join(dist_dir, "start_device_watcher.bat"), "w") as f:
        f.write(watcher_bat_content)

    # 3. Create Install Script
    install_bat_content = """@echo off
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
"venv\\\\Scripts\\\\pip.exe" install -r requirements.txt
"venv\\\\Scripts\\\\python.exe" -m playwright install chromium
echo Setup Complete! Run 'start_nexlab.bat'
pause
"""
    with open(os.path.join(dist_dir, "install_requirements.bat"), "w") as f:
        f.write(install_bat_content)

    # 4. Create Auto-Start Script
    autostart_bat_content = """@echo off
set "SCRIPT_PATH=%~dp0start_nexlab.bat"
set "SHORTCUT_PATH=%APPDATA%\\\\Microsoft\\\\Windows\\\\Start Menu\\\\Programs\\\\Startup\\\\NexLab_LIS.lnk"
powershell "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%');$s.TargetPath='%SCRIPT_PATH%';$s.WorkingDirectory='%~dp0';$s.WindowStyle=7;$s.Save()"
echo Added to Startup!
pause
"""
    with open(os.path.join(dist_dir, "add_to_startup.bat"), "w") as f:
        f.write(autostart_bat_content)

if __name__ == "__main__":
    package()
    print("Packaging finished successfully.")
