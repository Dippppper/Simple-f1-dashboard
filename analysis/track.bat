@echo off
set "PY=python"
where python >nul 2>nul || set "PY=C:\Users\20597\.workbuddy\binaries\python\versions\3.13.12\python.exe"
"%PY%" "%~dp0track_speed_map.py" %*
