"""连接假设备后的中英切换实测 —— 防止"静态英文、动态中文"回归。

离线单测里页面大多是空状态；真正连上设备后，状态条、采集/参数/固件摘要、
底部日志都会写入带数据的文案。这些文案在切语言时必须一起重写。本用例连接
`--fake` 的假 SDK，执行一组典型操作，再切英文逐页扫描。
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("litearm")
pytest.importorskip("pyqtgraph")

from litetool import i18n                                          # noqa: E402
from litetool import settings as settings_mod                      # noqa: E402
from litetool.fake import build_fake_arm_factory                   # noqa: E402
from litetool.gui.main_window import MainWindow                    # noqa: E402
from litetool.gui.prefs import UiPreferences                       # noqa: E402
from tests.test_i18n_ui import _chinese, _visible_strings          # noqa: E402

PAGES = ("overview", "scene", "capture", "log", "machine", "fault", "joint",
         "cart", "zerog", "gripper", "params", "guide", "diag", "install",
         "activation", "firmware", "settings")


def _pump(app, pred, timeout=6.0, what=""):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("timeout: " + what)


def test_connected_fake_session_switches_cleanly(tmp_path):
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    prefs = UiPreferences(path=str(tmp_path / "ui.ini"))
    prefs.set_language("zh")
    w = MainWindow(settings_mod.Settings.load(None),
                   arm_factory=build_fake_arm_factory(), fake=True, prefs=prefs)
    try:
        w.connect_fake()
        _pump(app, lambda: w.worker.online, what="worker online")
        _pump(app, lambda: w.worker.state is not None
              and w.worker.state.n == 7, what="7J state")
        w._tick()

        w._on_ctrl_cmd("enable")
        _pump(app, lambda: not w.worker.busy, what="enable")
        w._on_set_speed(50)
        _pump(app, lambda: not w.worker.busy, what="speed")
        w._on_movej([0.01] * 7, 0.10)
        _pump(app, lambda: not w.worker.busy, what="movej")
        w._on_get_tcp()
        _pump(app, lambda: w.pages["cart"]._tcp is not None, what="tcp")
        w.pages["params"]._on_refresh()
        _pump(app, lambda: w.pages["params"]._device_synced, what="params")
        w.pages["capture"]._on_start()
        _pump(app, lambda: not w.worker.busy, what="capture start")
        w.pages["capture"]._on_read()
        _pump(app, lambda: not w.worker.busy, what="capture read")

        # 切英文；设置页下拉是唯一入口，走它才能覆盖落盘/重译整条链路。
        page = w.pages["settings"]
        page.combo.setCurrentIndex(page.combo.findData("en"))
        _pump(app, lambda: i18n.language() == "en", what="language switch")

        for key in PAGES:
            w._on_nav(key)
            app.processEvents()
            w._tick()
            app.processEvents()
            leftover = _chinese(_visible_strings(w))
            assert leftover == [], f"{key} 切英文后仍有中文:\n" + "\n".join(leftover)
    finally:
        w.close()
        i18n.set_language("zh")
