"""GuiBridge —— 跨线程 Qt 信号桥。

SDK 所有者线程 / 后台任务 → emit → 主线程 slot（AutoConnection 自动转 QueuedConnection）。
`sig_task` 把回调一并携带过去，于是**任何**后台任务的结果都在 GUI 线程上被处理，
页面不必自己关心线程边界。
"""
from PyQt5.QtCore import QObject, pyqtSignal


class GuiBridge(QObject):
    sig_log = pyqtSignal(str)                 # 一行日志
    sig_log_record = pyqtSignal(object)       # 一条结构化日志记录（dict）
    sig_task = pyqtSignal(object, object)     # (TaskResult, 回调|None)
    sig_online = pyqtSignal(bool, str)        # (在线?, 说明)
    sig_reconnect = pyqtSignal(int, str)      # (第几次尝试, 说明)
