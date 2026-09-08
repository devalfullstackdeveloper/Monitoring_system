@echo off
REM Installs the local backend, dashboard, and tray agent at Windows logon.
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\OrgTrackerLocal.lnk"

if not exist "%STARTUP_DIR%" mkdir "%STARTUP_DIR%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = 'wscript.exe'; $sc.Arguments = '//nologo ' + [char]34 + '%~dp0start-all-background.vbs' + [char]34; $sc.WorkingDirectory = '%~dp0'; $sc.WindowStyle = 7; $sc.Save()"

echo Org Tracker will start automatically when this Windows user logs in.
echo To remove it, run uninstall-local-autostart.bat.