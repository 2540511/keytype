# KeyType build script
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== KeyType build ==" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "没有找到 python，请先安装 Python 3.10+。"
}

python -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "当前 Python 缺少 tkinter，请安装带 Tcl/Tk 的 Python。"
}

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "安装 PyInstaller..." -ForegroundColor Yellow
    python -m pip install --disable-pip-version-check -r requirements-dev.txt
}

if (-not (Test-Path "assets\keytype.ico")) {
    Write-Host "生成图标..." -ForegroundColor Yellow
    python tools\make_icon.py
}

Write-Host "打包中（onedir，无控制台）..." -ForegroundColor Yellow
$icon = Join-Path $PSScriptRoot "assets\keytype.ico"
$versionFile = Join-Path $PSScriptRoot "version_info.txt"
$appFile = Join-Path $PSScriptRoot "app.py"
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name KeyType `
    --icon $icon `
    --add-data "$icon;assets" `
    --version-file $versionFile `
    --distpath "dist" `
    --workpath "build" `
    --specpath "build" `
    $appFile

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 打包失败。"
}

# 清掉旧版本可能留下的 onefile 文件，避免误点。
$oldOnefile = Join-Path $PSScriptRoot "dist\KeyType.exe"
if (Test-Path $oldOnefile) {
    Remove-Item $oldOnefile -Force
}

$exe = Join-Path $PSScriptRoot "dist\KeyType\KeyType.exe"

# 浏览器/编辑器以管理员权限运行时，需要显式以管理员启动。
$adminLauncher = Join-Path $PSScriptRoot "dist\KeyType\以管理员身份启动.cmd"
$launcherText = @(
    '@echo off',
    'cd /d "%~dp0"',
    'powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath ''%~dp0KeyType.exe'' -Verb RunAs"'
) -join "`r`n"
[System.IO.File]::WriteAllText(
    $adminLauncher,
    $launcherText,
    (New-Object System.Text.UTF8Encoding($false))
)

$usage = Join-Path $PSScriptRoot "dist\KeyType\使用说明.txt"
$usageText = @(
    'KeyType 1.0.0',
    '',
    '普通启动：双击 KeyType.exe',
    '管理员启动：双击 以管理员身份启动.cmd（目标浏览器/编辑器以管理员运行时必须用这个）',
    '',
    '使用：',
    '1. 把文字放进 KeyType 文本框',
    '2. 先用鼠标点进目标输入框',
    '3. 按 Ctrl+Alt+K，或点“开始键入”后在倒计时内切换到目标窗口',
    '4. 按 Esc 可随时中止',
    '',
    '完整说明见仓库 README.md。'
) -join "`r`n"
[System.IO.File]::WriteAllText(
    $usage,
    $usageText,
    (New-Object System.Text.UTF8Encoding($false))
)

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
$folderSize = [math]::Round(((Get-ChildItem (Split-Path $exe) -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB, 1)
$zip = Join-Path $PSScriptRoot "dist\KeyType-1.0.0-win64.zip"
if (Test-Path $zip) {
    Remove-Item $zip -Force
}
Compress-Archive -Path (Join-Path $PSScriptRoot "dist\KeyType\*") -DestinationPath $zip -CompressionLevel Optimal

Write-Host ""
Write-Host "完成：$exe" -ForegroundColor Green
Write-Host "目录大小：$folderSize MB，主程序：$size MB" -ForegroundColor Green
Write-Host "分发包：$zip" -ForegroundColor Green
