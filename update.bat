@echo off
cd /d "%~dp0"

REM 优先使用 PATH 中的 python，找不到则回退到本机已知路径
set "PY=python"
where python >nul 2>nul || set "PY=C:\Users\20597\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

"%PY%" "%~dp0fetch_f1_data.py"
pause
