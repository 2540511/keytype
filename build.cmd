@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if errorlevel 1 (
    echo.
    echo 打包失败，请查看上面的日志。
    pause
    exit /b 1
)
echo.
pause
exit /b 0
