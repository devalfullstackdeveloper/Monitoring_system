@echo off
REM Run this ONCE on each employee's Windows machine, after copying
REM OrgTrackerAgent.exe (and its .env) into a permanent folder (e.g.
REM C:\Program Files\OrgTracker\ or anywhere that won't move/get deleted).
REM
REM It adds a tiny launcher to the current Windows user's Startup folder,
REM so the tracker starts automatically every time this user logs in —
REM no one has to remember to open it manually.

set "AGENT_DIR=%~dp0"
set "AGENT_EXE=%AGENT_DIR%OrgTrackerAgent.exe"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP_DIR%\OrgTrackerAgent.bat"

if not exist "%AGENT_EXE%" (
    echo ERROR: OrgTrackerAgent.exe not found next to this script.
    echo Build it first with build-agent.bat, or place this script next to the .exe.
    pause
    exit /b 1
)

> "%LAUNCHER%" echo @echo off
>> "%LAUNCHER%" echo start "" "%AGENT_EXE%"

echo Done. OrgTrackerAgent will now start automatically when this Windows
echo user logs in. To undo this, run uninstall-autostart.bat.
pause
