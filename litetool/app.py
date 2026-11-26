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
    from PyQt5.QtWidgets import QApplication

    from litetool.gui.main_window import MainWindow
    from litetool.settings import Settings

    raw = list(sys.argv if argv is None else argv)
    activation_url = _flag_value(raw, "--activation-url")
    if activation_url:
        # 授权页只读这个环境变量；与 `LITEARM_ACTIVATION_URL` 同一入口。
        os.environ["LITEARM_ACTIVATION_URL"] = activation_url
        raw = _drop_option(raw, "--activation-url")
    settings = Settings.load(config_path())
    app = QApplication(raw)
    app.setApplicationName("LiteArm Tool STM32")
    win = MainWindow(settings)
    win.show()
    return app.exec_()


def _flag_value(argv, name):
    """`--name VALUE` / `--name=VALUE` → VALUE；没有返回 None。"""
    for i, arg in enumerate(argv):
        if arg == name and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return None


def _drop_option(argv, name):
    out = []
    skip = False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg == name:
            skip = True
            continue
        if arg.startswith(name + "="):
            continue
        out.append(arg)
    return out
