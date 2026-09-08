@echo off
REM Local dev use only - for the real multi-machine rollout, the backend
REM runs once on a central server (see README: "Deploying across your
REM organization"), not launched per-employee like this.
cd /d "%~dp0"
call venv\Scripts\activate.bat

REM Read PORT from .env so this never drifts out of sync with what
REM desktop-agent\.env / frontend\.env expect - never hardcode a port here.
set "PORT=8000"
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%A in (".env") do (
        if /I "%%A"=="PORT" set "PORT=%%B"
    )
)

uvicorn app.main:app --reload --host 0.0.0.0 --port %PORT%
 