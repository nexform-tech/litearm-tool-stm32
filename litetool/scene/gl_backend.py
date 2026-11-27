"""Windows 软件 OpenGL 后备 —— 让 PyOpenGL 与 Qt 用同一个 Mesa DLL。

Windows 上 Qt 可能静默回落到自带的 Mesa（`opengl32sw.dll`）：没有可用桌面
OpenGL 的机器、远程桌面/虚拟显示器都可能这样。此时 PyOpenGL 仍去加载系统
`opengl32.dll`，两边拿到的是**不同驱动**的 context，绘制全部报
`Attempt to retrieve context when no valid context`，3D 视口保持黑色。

本模块把 PyOpenGL 的 Win32 平台绑定到 Qt 正在使用的同一个 `opengl32sw.dll`。
必须在 `pyqtgraph.opengl` / `OpenGL.GL` 首次 import **之前**调用。

开关：`LITEARM_TOOL_SOFTWARE_GL=1`，或 `config.yaml` 的
`scene_software_gl: true`（由 `app._prepare_gl` 转成前一个环境变量）。
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

ENV_FLAG = "LITEARM_TOOL_SOFTWARE_GL"


def software_gl_requested() -> bool:
    """环境变量是否要求 Windows 软件 GL；其它平台恒为 False。"""
    if sys.platform != "win32":
        return False
    return os.environ.get(ENV_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def _mesa_path() -> Path | None:
    candidates = []
    try:
        import PyQt5
        candidates.append(Path(PyQt5.__file__).resolve().parent
                          / "Qt5" / "bin" / "opengl32sw.dll")
    except Exception:  # noqa: BLE001 - 找不到 PyQt5 时下面还有 _MEIPASS 候选
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "PyQt5" / "Qt5" / "bin"
                          / "opengl32sw.dll")
    for path in candidates:
        if path.is_file():
            return path
    return None


def prepare_software_gl() -> bool:
    """把 PyOpenGL 的 Win32 平台切换到 Qt 的 Mesa。返回是否打了补丁。"""
    if not software_gl_requested():
        return False
    path = _mesa_path()
    if path is None:
        print("[3D] 要求软件 OpenGL，但找不到 opengl32sw.dll", file=sys.stderr)
        return False
    try:
        mesa = ctypes.WinDLL(str(path), mode=ctypes.RTLD_GLOBAL)
        import OpenGL.platform as platform

        plat = platform.PLATFORM
        plat.GL = mesa
        # `lazy_property` 已经缓存过的旧系统 GL 函数必须清掉；`WGL` 也是从
        # `self.OpenGL` 派生的，一并清。
        for attr in ("OpenGL", "WGL", "GetCurrentContext",
                     "CurrentContextIsValid", "getExtensionProcedure"):
            plat.__dict__.pop(attr, None)
        # `OpenGL.contextdata.getContext()` 走的是**模块级**
        # `platform.GetCurrentContext`，只改 PLATFORM 实例不够 —— 那样它仍用
        # 系统 opengl32 查当前 context，拿到 NULL 后拒绝所有绘制。
        wgl_get_context = mesa.wglGetCurrentContext
        wgl_get_context.restype = ctypes.c_void_p
        platform.GetCurrentContext = wgl_get_context
        platform.OpenGL = mesa
        platform.GL = mesa
    except Exception as e:  # noqa: BLE001 - 软件 GL 失败不能让 3D 页崩掉
        print(f"[3D] 软件 OpenGL 初始化失败: {e}", file=sys.stderr)
        return False
    print(f"[3D] 使用 Qt 自带的软件 OpenGL: {path}", file=sys.stderr)
    return True
