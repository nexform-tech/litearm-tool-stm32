"""`--fake` 演示模式 —— 假设备连接、状态流、主窗口自动接入。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("litearm")

from litetool.fake import build_fake_arm_factory


def test_fake_arm_connects_and_streams_state():
    arm = build_fake_arm_factory()("fake")
    try:
        assert arm.n == 7
        assert str(arm.firmware).startswith("Litearm")
        st = arm.get_state(refresh=True, timeout=1.0).value
        assert st is not None
        assert len(st.q) == 7
        arm.enable()
        arm.disable()
    finally:
        arm.close()


def test_mainwindow_fake_mode_auto_connects():
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    from litetool import settings
    from litetool.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(settings.Settings.load(None),
                   arm_factory=build_fake_arm_factory(), fake=True)
    try:
        assert w.combo.currentData() == "fake"
        QTest.qWait(300)
        assert w.worker.online, "fake 模式应自动接上假设备"
        assert w.worker.state is not None
        assert "FAKE" in w.windowTitle()
    finally:
        w.close()
