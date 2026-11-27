"""GUI 启动入口 —— `python3 -m litetool` / 安装后的 `litearm-tool` 命令共用。

配置查找顺序 (第一个存在者):
  `$LITEARM_TOOL_CONFIG` > 当前工作目录 `config.yaml`
  > [冻结包] 可执行文件同级 `config.yaml` > [冻结包] 随包基线 (`sys._MEIPASS`)
  > 源码树仓库根 `config.yaml`
最后一个都找不到时用 dataclass 默认值。
"""
from __future__ import annotations

import os
import sys


def _frozen_dirs() -> list:
    """[PyInstaller] 冻结后 `__file__` 指向 `_internal/`, 仓库根候选会失效 ——
    补上"可执行文件所在目录"(用户可见、可改的那份) 与 `sys._MEIPASS`(随包基线)。

    非冻结时返回空表, 老行为一字不变。
    """
    if not getattr(sys, "frozen", False):
        return []
    dirs = [os.path.dirname(os.path.abspath(sys.executable))]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
    return dirs


def config_path() -> str | None:
    env = os.environ.get("LITEARM_TOOL_CONFIG")
    if env:
        return env
    cwd_cfg = os.path.join(os.getcwd(), "config.yaml")
    if os.path.isfile(cwd_cfg):
        return cwd_cfg
    cands = _frozen_dirs() + [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    for d in cands:
        p = os.path.join(d, "config.yaml")
        if os.path.isfile(p):
            return p
    return None


def main(argv=None) -> int:
    from PyQt5.QtWidgets import QApplication, QMessageBox

    from litetool.gui.main_window import MainWindow
    from litetool.instance import InstanceGuard
    from litetool.settings import Settings

    raw = list(sys.argv if argv is None else argv)
    activation_url = _flag_value(raw, "--activation-url")
    if not activation_url and _has_option(raw, "--activation-url"):
        # 缺值不能悄悄回落到生产地址：使用者以为自己指到了 staging。
        print("[activation] --activation-url 缺少值；使用默认地址", file=sys.stderr)
    raw = _drop_option(raw, "--activation-url")
    if activation_url:
        # 授权页只读这个环境变量；与 `LITEARM_ACTIVATION_URL` 同一入口。
        os.environ["LITEARM_ACTIVATION_URL"] = activation_url
    # `--fake` 是 tool 自己的布尔开关，不是 Qt 参数；先摘掉再交给 QApplication。
    fake = "--fake" in raw
    if fake:
        raw = [arg for arg in raw if arg != "--fake"]
    settings = Settings.load(config_path())
    _prepare_gl(settings)
    app = QApplication(raw)
    app.setApplicationName("LiteArm Tool STM32")

    # 串口只能有一个所有者：第二个实例不打开串口，只把已有窗口提到前台。
    guard = InstanceGuard()
    if not guard.acquire():
        print("LiteArm Tool 已在运行，已切换到已有窗口。", file=sys.stderr)
        QMessageBox.information(
            None, "LiteArm Tool",
            "已有实例在运行，已为你切换到该窗口。\n"
            "同一时间只允许一个上位机占用串口。")
        return 0
    if guard.lock_error:
        # 建不出锁不阻止启动，但必须留痕：否则用户会以为"单实例保护生效了"。
        print(f"[WARN] 单实例锁不可用: {guard.lock_error}", file=sys.stderr)

    factory = None
    if fake:
        from litetool.fake import build_fake_arm_factory
        factory = build_fake_arm_factory()
    win = MainWindow(settings, arm_factory=factory, fake=fake)
    guard.activated.connect(win.activate)
    win.show()
    return app.exec_()


def _has_option(argv, name) -> bool:
    return any(arg == name or arg.startswith(name + "=") for arg in argv)


def _flag_value(argv, name):
    """`--name VALUE` / `--name=VALUE` → VALUE；没有返回 None。

    VALUE 以 `-` 开头时按"缺值"处理 —— 否则 `--activation-url -platform offscreen`
    会把 Qt 的 `-platform` 当成地址并把它从参数里删掉。
    """
    for i, arg in enumerate(argv):
        if arg == name:
            if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                return argv[i + 1]
            return None
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return None


def _drop_option(argv, name):
    """删掉 `--name` / `--name=VALUE`；只有确实带了值才连值一起删。"""
    out = []
    skip = False
    for i, arg in enumerate(argv):
        if skip:
            skip = False
            continue
        if arg == name:
            # 紧跟的 token 以 `-` 开头时它是另一个选项，不是本选项的值。
            skip = i + 1 < len(argv) and not argv[i + 1].startswith("-")
            continue
        if arg.startswith(name + "="):
            continue
        out.append(arg)
    return out


def _prepare_gl(settings) -> None:
    """Qt 之前设置 OpenGL 平台与 MSAA。

    ⚠ PyOpenGL 在 Linux 上默认可能选 EGL，而 Qt5/X11 的 context 是 GLX：
    实测报 `Attempt to retrieve context when no valid context`，3D 一项都画不出来。
    有 X11（含 XWayland）时强制 GLX；纯 Wayland 才交给 EGL。

    Windows 上若要求软件 GL（config `scene_software_gl` 或环境变量
    `LITEARM_TOOL_SOFTWARE_GL=1`），在 QApplication 之前让 Qt 选
    `opengl32sw.dll`；`litetool.scene.gl_backend` 会把 PyOpenGL 绑到同一个 DLL。
    """
    if sys.platform == "win32":
        from litetool.scene.gl_backend import software_gl_requested
        if getattr(settings, "scene_software_gl", False) or software_gl_requested():
            os.environ["LITEARM_TOOL_SOFTWARE_GL"] = "1"
            os.environ["QT_OPENGL"] = "software"
    if sys.platform.startswith("linux"):
        native_wayland = os.environ.get("QT_QPA_PLATFORM", "").startswith("wayland") or (
            os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"))
        os.environ.setdefault("PYOPENGL_PLATFORM", "egl" if native_wayland else "glx")
    samples = int(getattr(settings, "scene_msaa", 0) or 0)
    if samples > 0:
        from PyQt5.QtGui import QSurfaceFormat
        fmt = QSurfaceFormat.defaultFormat()
        fmt.setSamples(samples)
        QSurfaceFormat.setDefaultFormat(fmt)
