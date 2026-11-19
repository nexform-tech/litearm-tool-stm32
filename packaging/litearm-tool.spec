# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— litearm-tool-stm32 (onedir, 自包含)。

用法 (推荐走同目录 build.sh, 它会先备好干净 venv):
    pip install pyinstaller
    pyinstaller --clean --noconfirm packaging/litearm-tool.spec

## 关键决策与理由

**onedir 而非 onefile**: GUI 应用用 onefile 每次启动都要把 ~200MB 解压到 /tmp
(首启数秒), 且 `/tmp` 挂 `noexec` 的机器**直接跑不起来**。onedir 解包即用。

**必须用"非可编辑安装"的 litearm 来打**: 本仓的 SDK 依赖平时是
`pip install -e ../litearm-python`。editable 装法装的是一个 `__editable__*.pth` /
自定义 finder, **PyInstaller 的模块图常常跟不进去** —— 打出来的包会在运行期
`ModuleNotFoundError: litearm`。`build.sh` 用一个干净 venv 装非可编辑版,
从根上避开这件事 (顺带避开 conda 环境里那个会挡住 PyInstaller 的过时 `pathlib`)。

**排除 PyQt5 的用不到的模块**: `PyQt5-Qt5` 轮子里大头是 QtWebEngine 等,
本工具一行都没用。排除后体积能砍掉一大半。**刻意不排除** `QtSvg` / `QtPrintSupport`
/ `QtOpenGL` —— pyqtgraph 的导出与渲染路径会用到。

**`config.yaml` 进 `_internal/`** 作为随包基线; 可执行文件同级的那份由 `build.sh`
复制, 用户可直接改 —— `litetool/app.py::config_path()` 的冻结候选**优先取同级那份**。
"""
from pathlib import Path

ROOT = Path(SPECPATH).parent          # SPECPATH = <repo>/packaging

# ---- 排除: 本工具确定用不到的 (只列"确定没用"的, 宁可留大也不漏) ----
EXCLUDES = [
    # 与本项目无关的科学/工具栈
    "tkinter", "matplotlib", "scipy", "pandas", "PIL", "IPython", "jupyter",
    "pytest", "_pytest", "setuptools", "pip",
    # PyQt5 里本工具没用的模块 (QtWebEngine 是体积大头)
    "PyQt5.QtWebEngine", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebKit", "PyQt5.QtWebKitWidgets", "PyQt5.QtWebSockets", "PyQt5.QtWebChannel",
    "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtQuickWidgets", "PyQt5.QtQuick3D",
    "PyQt5.Qt3DCore", "PyQt5.Qt3DRender", "PyQt5.Qt3DInput", "PyQt5.Qt3DLogic",
    "PyQt5.Qt3DAnimation", "PyQt5.Qt3DExtras",
    "PyQt5.QtMultimedia", "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtPositioning", "PyQt5.QtLocation",
    "PyQt5.QtSensors", "PyQt5.QtSerialPort", "PyQt5.QtCharts",
    "PyQt5.QtDataVisualization", "PyQt5.QtNetworkAuth", "PyQt5.QtRemoteObjects",
    "PyQt5.QtScript", "PyQt5.QtScriptTools", "PyQt5.QtDesigner", "PyQt5.QtHelp",
    "PyQt5.QtUiTools", "PyQt5.QtSql", "PyQt5.QtTest", "PyQt5.QtXmlPatterns",
    "PyQt5.QtTextToSpeech", "PyQt5.QtXml", "PyQt5.QtOpenGL",
]

a = Analysis(
    [str(ROOT / "litetool" / "__main__.py")],   # `python3 -m litetool` 的入口
    pathex=[str(ROOT)],                          # 让 litetool 从**工作树**里取
    binaries=[],
    datas=[(str(ROOT / "config.yaml"), ".")],    # 随包基线 (找不到同级那份时兜底)
    hiddenimports=[
        # 串口枚举靠 pyserial 的运行时后端, 静态分析看不到
        "serial.tools.list_ports",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="litearm-tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX 对 Qt 库压缩后易出诡异问题, 且省不了多少
    console=False,             # GUI 应用; 从终端启动时 stdout/stderr 仍在终端可见
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="litearm-tool",
)
