@echo off
REM Removes the local tracker from this Windows user's Startup folder.
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\OrgTrackerLocal.lnk"
set "OLD_LAUNCHER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\OrgTrackerLocal.vbs"
if exist "%SHORTCUT%" del /Q "%SHORTCUT%"
if exist "%OLD_LAUNCHER%" del /Q "%OLD_LAUNCHER%"
echo Org Tracker automatic startup removed.