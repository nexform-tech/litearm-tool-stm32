"""GuiBridge —— 跨线程 Qt 信号桥。

读线程 / 命令工作线程 → emit → 主线程 slot（AutoConnection 自动转 QueuedConnection）。
"""
from PyQt5.QtCore import QObject, pyqtSignal


class GuiBridge(QObject):
    sig_log = pyqtSignal(str)             # 一行日志（主线程 append 到日志面板）
    sig_done = pyqtSignal(str, object)    # (命令名, 结果) —— 命令工作线程完成后触发
