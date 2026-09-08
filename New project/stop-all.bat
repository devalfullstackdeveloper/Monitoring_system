@echo off
REM Stops local tracker processes started from this project.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-local-tracker.ps1"
echo Org Tracker stopped.