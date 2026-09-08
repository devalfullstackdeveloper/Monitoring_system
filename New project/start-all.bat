@echo off
REM Launches backend, frontend, and desktop agent each in their own window,
REM for local dev/testing on one machine.
REM
REM One-time setup (venvs, npm install, .env files, create_admin.py) must
REM already be done in each folder before this will work — see README.md.
REM
REM This is NOT how you deploy to your organization — see README.md's
REM "Deploying across your organization" section for that.

start "Backend (FastAPI)"  cmd /k "%~dp0backend\start-backend.bat"
start "Frontend (React)"   cmd /k "%~dp0frontend\start-frontend.bat"
start "Desktop Agent"      cmd /k "%~dp0desktop-agent\start-agent.bat"
