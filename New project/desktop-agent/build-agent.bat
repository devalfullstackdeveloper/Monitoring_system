@echo off
REM Builds a single OrgTrackerAgent.exe that employees can run without
REM installing Python. Run this once per release, on a Windows machine,
REM from inside an activated venv that already has requirements.txt AND
REM requirements-build.txt installed:
REM
REM   venv\Scripts\activate.bat
REM   pip install -r requirements.txt -r requirements-build.txt
REM   build-agent.bat
REM
REM Output: dist\OrgTrackerAgent.exe

cd /d "%~dp0"
pyinstaller --onefile --noconsole --name OrgTrackerAgent agent.py

echo.
echo Build complete: dist\OrgTrackerAgent.exe
echo Copy this .exe (and a .env file next to it, see .env.example) to each
echo employee machine, then run install-autostart.bat once on each machine.
