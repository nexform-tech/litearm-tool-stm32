"""关节页闸门：按钮要拦，输入框不该拦。

背景：原实现对所有控件统一 `setEnabled(can)`，未解锁时连关节数字都输不进去，
现场表现为"这个页面坏了"。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")

from litetool.gui.pages.joint_page import JointPage   # noqa: E402

_APP = None


def _page():
    global _APP
    from PyQt5.QtWidgets import QApplication
    from litetool import settings as settings_mod
    _APP = QApplication.instance() or QApplication([])
    p = JointPage(settings_mod.Settings.load(None))
    p.set_joints(7)
    return p


def test_inputs_editable_while_locked():
    p = _page()
    p.set_online(True)
    p.set_armed(False)
    p.set_busy(False)
    # 按钮受闸门
    assert not p.btn_mj.isEnabled()
    assert not p.btn_js.isEnabled()
    # 输入控件仍可编辑
    assert p.mj_row.isEnabled()
    assert p.js_q.isEnabled()
    assert p.ma_q.isEnabled()
    assert p.mj_speed.isEnabled()


def test_buttons_enabled_when_armed():
    p = _page()
    p.set_online(True)
    p.set_armed(True)
    p.set_busy(False)
    assert p.btn_mj.isEnabled()
    assert p.btn_js.isEnabled()


def test_buttons_disabled_when_offline():
    p = _page()
    p.set_online(False)
    p.set_armed(True)
    assert not p.btn_mj.isEnabled()
    # 离线也不影响填写
    assert p.mj_row.isEnabled()
