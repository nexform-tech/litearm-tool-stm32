"""故障详情按需查询的触发条件 —— 只在 joint_fault 变化时查一次。"""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")


def _win():
    from PyQt5.QtWidgets import QApplication
    from litetool import settings as settings_mod
    from litetool.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    _ = app
    return MainWindow(settings_mod.Settings.load(None))


def _st(jf=0x0008, available=True):
    return SimpleNamespace(joint_fault=jf, fault_detail_available=available,
                           fault_reasons=[], joints=[], n=7)


def test_query_triggered_once_per_fault_bitmap():
    w = _win()
    try:
        calls = []
        w._submit = lambda name, fn, cb=None: calls.append(name)
        st = _st()
        w._sync_fault_detail(st)
        w._sync_fault_detail(st)          # 位图相同 -> 不重复查
        assert calls == ["读故障详情"]
    finally:
        w.close()


def test_new_axis_triggers_new_query():
    w = _win()
    try:
        calls = []
        w._submit = lambda name, fn, cb=None: calls.append(name)
        w._sync_fault_detail(_st(0x0008))
        w._fault_query_inflight = False     # 模拟上一次查询完成
        w._sync_fault_detail(_st(0x000C))   # 新增一轴
        assert len(calls) == 2
    finally:
        w.close()


def test_old_firmware_never_queries():
    w = _win()
    try:
        calls = []
        w._submit = lambda name, fn, cb=None: calls.append(name)
        w._sync_fault_detail(_st(0x0008, available=False))
        assert calls == []
        assert w._fault_detail is None
    finally:
        w.close()


def test_clear_resets_detail():
    w = _win()
    try:
        w._submit = lambda name, fn, cb=None: None
        w._fault_detail = object()
        w._sync_fault_detail(_st(0x0000))
        assert w._fault_detail is None
    finally:
        w.close()
