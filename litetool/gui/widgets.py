"""小部件 —— 暗色控制台风格日志面板。"""
import time

from PyQt5.QtGui import QColor, QFont, QTextCursor
from PyQt5.QtWidgets import QPlainTextEdit


class LogPanel(QPlainTextEdit):
    """带时间戳的日志面板；append_line 在 GUI 主线程调用（经信号桥转达）。"""

    _STYLE = (
        "QPlainTextEdit { background:#1e1e1e; color:#c8c8c8;"
        " font-family:'DejaVu Sans Mono','Courier New',monospace; font-size:12px; }"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self.setStyleSheet(self._STYLE)
        self._level_color = {
            "[OK]": "#6fdd8b",
            "[ERR]": "#ff6b6b",
            "[WARN]": "#ffd166",
            "[INFO]": "#c8c8c8",
        }

    def append_line(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        color = "#c8c8c8"
        for key, c in self._level_color.items():
            if msg.startswith(key):
                color = c
                break
        self.appendHtml(f'<span style="color:#808080">[{ts}]</span> '
                        f'<span style="color:{color}">{msg}</span>')

    def clear_log(self):
        self.clear()

    # 便于从任意线程调用：经信号桥后到达主线程，无需锁。
