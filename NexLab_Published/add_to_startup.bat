@echo off
set "SCRIPT_PATH=%~dp0start_nexlab.bat"
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\NexLab_LIS.lnk"
powershell "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%');$s.TargetPath='%SCRIPT_PATH%';$s.WorkingDirectory='%~dp0';$s.WindowStyle=7;$s.Save()"
echo Added to Startup!
pause
