@echo off
cd /d "%~dp0"

REM Prefer the WorkBuddy-managed Python venv (has fastf1 pre-installed)
set "PY=C:\Users\20597\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

if exist "%PY%" (
    "%PY%" "%~dp0fetch_f1_data.py"
) else (
    python "%~dp0fetch_f1_data.py"
)

pause