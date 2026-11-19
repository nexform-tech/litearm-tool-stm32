"""故障原因在界面上的呈现 —— 断轴必须带"为什么"。"""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")

from litetool.gui.widgets import FAULT_SHORT          # noqa: E402


def _win():
    from PyQt5.QtWidgets import QApplication
    from litetool import settings as settings_mod
    from litetool.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    _ = app
    return MainWindow(settings_mod.Settings.load(None))


def test_short_names_cover_all_reasons():
    assert set(FAULT_SHORT) == set(range(1, 8))


def test_fault_summary_contains_axis_and_reason():
    w = _win()
    try:
        st = SimpleNamespace(fault_reasons=[(3, 1)], fault_axes=[3])
        text = w._fault_summary(st)
        assert "J4" in text
        assert "CAN" in text
    finally:
        w.close()


def test_fault_summary_old_firmware_is_empty():
    """旧固件 fault_reason 为空列表 -> 由调用方回退到 fault_detail。"""
    w = _win()
    try:
        st = SimpleNamespace(fault_reasons=[], fault_axes=[3])
        assert w._fault_summary(st) == ""
    finally:
        w.close()
