#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LiteArm STM32 上位机工具 —— PyQt5 GUI（交互层经 litearm_core 直连固件）。

用法:
  pip install -e ../litearm-core && pip install -r requirements.txt
  python3 main.py            # 启动 GUI（串口在 dialout 组则无需 root）
  python3 -m litetool        # 同上（安装后是 litearm-tool 命令）
  python3 -m pytest          # 离线测试（无需硬件）
"""
import sys

from litetool.app import main

if __name__ == "__main__":
    sys.exit(main())
