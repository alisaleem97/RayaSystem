@echo off
echo ========================================
echo   Building NexPrint.exe
echo ========================================
echo.

REM Install dependencies
pip install pyinstaller pywin32

REM Build the executable
pyinstaller --onefile --windowed --name NexPrint --icon=icon.ico main.py

echo.
echo ========================================
echo   Build complete!
echo   Output: dist\NexPrint.exe
echo ========================================
echo.
echo IMPORTANT: Copy these files to the dist folder:
echo   - SumatraPDF.exe (download from sumatrapdfreader.org)
echo   - config.json
echo.
pause
