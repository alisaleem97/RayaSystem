@echo off
echo ========================================
echo   Building NexPrint.exe
echo ========================================
echo.

REM Clean previous build artifacts
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist NexPrint.spec del NexPrint.spec

REM Install dependencies
pip install pyinstaller pywin32

REM Build the executable (no icon since we don't have one)
pyinstaller --onefile --windowed --name NexPrint main.py

echo.

if exist dist\NexPrint.exe (
    echo ========================================
    echo   Build successful!
    echo ========================================
    echo.
    echo Copying required files to dist folder...
    if exist SumatraPDF.exe copy SumatraPDF.exe dist\
    copy config.json dist\
    echo.
    echo Output folder: dist\
    echo   - NexPrint.exe
    echo   - SumatraPDF.exe
    echo   - config.json
    echo.
    echo You can now copy the entire dist folder to client PCs.
) else (
    echo ========================================
    echo   Build FAILED! Check errors above.
    echo ========================================
)

echo.
pause
