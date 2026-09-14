"""GUI 启动入口 —— `python3 -m litetool` / 安装后的 `litearm-tool` 命令共用。

配置查找顺序 (第一个存在者): `$LITEARM_TOOL_CONFIG` > 当前工作目录 `config.yaml`
> 包内基线 `config.yaml` (config.yaml 只在仓库根, 安装后缺失时用 dataclass 默认值)。
"""
from __future__ import annotations

import os
import sys


def config_path() -> str | None:
    env = os.environ.get("LITEARM_TOOL_CONFIG")
    if env:
        return env
    cwd_cfg = os.path.join(os.getcwd(), "config.yaml")
    if os.path.isfile(cwd_cfg):
        return cwd_cfg
    repo_cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config.yaml")
    return repo_cfg if os.path.isfile(repo_cfg) else None


def main(argv=None) -> int:
    from PyQt5.QtWidgets import QApplication

    from litetool.gui.main_window import MainWindow
    from litetool.settings import Settings

    settings = Settings.load(config_path())
    app = QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("LiteArm Tool STM32")
    win = MainWindow(settings)
    win.show()
    return app.exec_()
