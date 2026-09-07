#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LiteArm STM32 上位机工具 —— PyQt5 GUI（USB CDC 直连固件）。

用法:
  pip install -r requirements.txt
  python3 main.py            # 启动 GUI（串口在 dialout 组则无需 root）
  python3 -m pytest          # 离线测试（协议/检查/客户端, 无需硬件）
"""
import os
import sys


def main() -> int:
    from PyQt5.QtWidgets import QApplication
    from litetool.gui.main_window import MainWindow
    from litetool.settings import Settings

    here = os.path.dirname(os.path.abspath(__file__))
    settings = Settings.load(os.path.join(here, "config.yaml"))

    app = QApplication(sys.argv)
    app.setApplicationName("LiteArm Tool STM32")
    win = MainWindow(settings)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
