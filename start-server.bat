@echo off
cd /d "%~dp0"
echo ========================================
echo   F1 Dashboard 启动中...
echo ========================================
echo.
echo  服务器: http://127.0.0.1:5500
echo  页面:   http://127.0.0.1:5500/f1-dashboard.html
echo.
echo  浏览器将在 1 秒后自动打开。
echo  关闭此窗口将停止服务器。
echo  ----------------------------------------
echo.

REM 延迟 1 秒后自动打开浏览器（后台执行，不阻塞服务器）
start "" cmd /c "timeout /t 1 /nobreak >nul & start http://127.0.0.1:5500/f1-dashboard.html"

REM 优先使用 PATH 中的 python，找不到则回退到本机已知路径
set "PY=python"
where python >nul 2>nul || set "PY=C:\Users\20597\.workbuddy\binaries\python\versions\3.13.12\python.exe"

REM 启动 HTTP 服务器（前台运行，Ctrl+C 或关闭窗口即停止）
"%PY%" -u f1-server.py
