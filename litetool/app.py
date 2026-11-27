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

    settings = Settings.load(config_path())
    app = QApplication(list(sys.argv if argv is None else argv))
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

    win = MainWindow(settings)
    guard.activated.connect(win.activate)
    win.show()
    return app.exec_()
