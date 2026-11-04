@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist "dist\KeyType\KeyType.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%CD%\dist\KeyType\KeyType.exe' -Verb RunAs"
    exit /b 0
)

echo 找不到 dist\KeyType\KeyType.exe，请先运行 build.cmd 打包。
pause
exit /b 1
