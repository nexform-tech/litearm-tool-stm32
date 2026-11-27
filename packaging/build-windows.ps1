# Windows 打包脚本 —— 与 build.sh 同一条流水线（干净 venv + 测试闸门 + PyInstaller onedir）。
#
# 用法（在仓库根目录）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build-windows.ps1
#   # 指定 SDK 源码 / 解释器 / 输出目录：
#   powershell -NoProfile -File packaging\build-windows.ps1 -SdkSrc C:\src\litearm-python
#
# 前置：Python 3.10+（`py -3.14` 可用）、能访问 GitHub/PyPI。目标机不需要 Python。
# 产物：packaging\out\litearm-tool-stm32-<版本>-windows-x86_64\ 与同名 .zip
#
# 与 build.sh 的差异：
#   * 不装 litegrip（仅 Linux / SocketCAN），所以 Windows 包没有夹爪页的可用连接；
#   * PyQt5 的 Windows wheel 自带 Qt 运行库，不需要系统 Qt；
#   * 本脚本只保证"启动并连上 CDC"，DFU（WinUSB）与 3D OpenGL 的 Windows
#     验收分别在 #19 / #17 的 PR 里，不以本包为据。
param(
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "-3.14",
    [string]$SdkSrc = "",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
if ($PSScriptRoot) {
    $Root = Split-Path -Parent $PSScriptRoot
} else {
    # `powershell -Command ". '...\build-windows.ps1'"` 这条通道下 $PSScriptRoot 可能为空；
    # 从仓库根运行时当前目录就是根。
    $Root = (Get-Location).Path
}
if (-not $OutDir) { $OutDir = Join-Path $Root "packaging\out" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Say($text) {
    Write-Host ""
    Write-Host "== $text ==" -ForegroundColor Cyan
}

Say "环境"
Write-Host "仓库      : $Root"
Write-Host "SDK 源码  : $SdkSrc"
Write-Host "输出目录  : $OutDir"

Say "1/6 备好干净 venv"
$Venv = Join-Path $OutDir "build-venv"
$Vpy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Vpy)) {
    & $PythonLauncher $PythonVersion -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "建 venv 失败（$PythonLauncher $PythonVersion）" }
}
& $Vpy -c "import sys; print('  Python', sys.version.split()[0], sys.executable)"

Say "2/6 装 SDK（非可编辑）+ 运行期依赖 + PyInstaller"
if (-not $SdkSrc) { $SdkSrc = Join-Path (Split-Path -Parent $Root) "litearm-python" }
if (-not (Test-Path (Join-Path $SdkSrc "pyproject.toml"))) {
    throw "找不到 SDK 源码: $SdkSrc（用 -SdkSrc 指定 litearm-python 目录）"
}
& $Vpy -m pip install -q --upgrade pip
& $Vpy -m pip install -q $SdkSrc
& $Vpy -m pip install -q -r (Join-Path $Root "requirements.txt") pyinstaller pytest
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }

Say "3/6 在构建环境里跑全量测试（离线）"
$oldQpa = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = "offscreen"
Push-Location $Root
try {
    & $Vpy -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "测试未过 —— 拒绝打包" }
} finally {
    Pop-Location
    if ($null -eq $oldQpa) { Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue }
    else { $env:QT_QPA_PLATFORM = $oldQpa }
}

Say "4/6 PyInstaller 构建（onedir）"
$Dist = Join-Path $OutDir "dist"
$Work = Join-Path $OutDir "build"
Remove-Item -Recurse -Force $Dist, $Work -ErrorAction SilentlyContinue
$Log = Join-Path $OutDir "pyinstaller-windows.log"
# PyInstaller 把 INFO 写到 stderr；PowerShell 会把它包成 NativeCommandError，
# 在 ErrorActionPreference=Stop 下直接中断。这里只看退出码。
$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Vpy -m PyInstaller --clean --noconfirm `
    --distpath $Dist --workpath $Work `
    (Join-Path $Root "packaging\litearm-tool.spec") *> $Log
$pyiCode = $LASTEXITCODE
$ErrorActionPreference = $oldEap
if ($pyiCode -ne 0) {
    Write-Host "构建失败，日志尾部：" -ForegroundColor Red
    Get-Content $Log -Tail 30
    throw "PyInstaller 失败"
}
Write-Host "  日志: $Log"

Say "5/6 组装交付目录"
$Version = (Select-String -Path (Join-Path $Root "pyproject.toml") `
    -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$Bundle = "litearm-tool-stm32-$Version-windows-x86_64"
$Stage = Join-Path $OutDir $Bundle
Remove-Item -Recurse -Force $Stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Stage | Out-Null
Copy-Item -Recurse -Force (Join-Path $Dist "litearm-tool\*") $Stage
Copy-Item (Join-Path $Root "config.yaml") $Stage
foreach ($d in @("presets", "templates", "docs")) {
    $src = Join-Path $Root $d
    if (Test-Path $src) { Copy-Item -Recurse -Force $src $Stage }
}
$runNotes = Join-Path $Root "packaging\README-运行说明.md"
if (Test-Path $runNotes) { Copy-Item $runNotes $Stage }

Say "6/6 压缩"
$Zip = "$Stage.zip"
Remove-Item -Force $Zip -ErrorAction SilentlyContinue
Compress-Archive -Path $Stage -DestinationPath $Zip -Force
$SizeMB = [math]::Round(((Get-ChildItem $Stage -Recurse | Measure-Object Length -Sum).Sum / 1MB), 1)
$ZipMB = [math]::Round(((Get-Item $Zip).Length / 1MB), 1)

Say "完成"
Write-Host "目录 : $Stage   ($SizeMB MB)"
Write-Host "压缩 : $Zip   ($ZipMB MB)"
Write-Host ""
Write-Host "现场用法: 解压后双击 litearm-tool.exe（或从终端启动看错误输出）"
Write-Host "串口驱动: Windows 10/11 自带 usbser.sys；若端口列表为空，装 STM32 VCP 驱动"
