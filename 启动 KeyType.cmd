@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist "dist\KeyType\KeyType.exe" (
    start "" "dist\KeyType\KeyType.exe"
    exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo 没有找到 Python。可以直接运行 dist\KeyType\KeyType.exe，或先安装 Python 3.10+。
    echo.
    pause
    exit /b 1
)

where pythonw >nul 2>nul
if errorlevel 1 (
    start "" python "app.py"
) else (
    start "" pythonw "app.py"
)
exit /b 0
