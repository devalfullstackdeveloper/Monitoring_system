@echo off
REM Removes the auto-start entry added by install-autostart.bat.
REM Does not stop an already-running agent — close it from the tray icon first.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP_DIR%\OrgTrackerAgent.bat"

if exist "%LAUNCHER%" (
    del "%LAUNCHER%"
    echo Removed auto-start entry.
) else (
    echo No auto-start entry found — nothing to do.
)
pause
