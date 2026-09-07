"""GUI 冒烟 —— offscreen 构造主窗口并跑几轮空转，防 import/布局回归。

需要 PyQt5/pyqtgraph；无显示环境时用 offscreen 平台插件。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")


def test_mainwindow_constructs_and_ticks_offscreen():
    from PyQt5.QtWidgets import QApplication
    from litetool import settings as settings_mod
    from litetool.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    st = settings_mod.Settings.load(None)
    w = MainWindow(st)
    w._tick()            # session=None 分支
    w._tick_plot()
    w._lock_motion("test")
    w.close()
    assert w.session is None
