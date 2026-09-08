@echo off
REM Runs the agent from source, for local dev/testing only. Once you're
REM ready to roll this out to employee machines, build OrgTrackerAgent.exe
REM with build-agent.bat instead — employees should never need Python
REM installed or run this script.
cd /d "%~dp0"
call venv\Scripts\activate.bat
python agent.py
