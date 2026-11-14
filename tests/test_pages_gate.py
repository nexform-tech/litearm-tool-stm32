"""笛卡尔/整机页：输入可编辑，只有执行按钮受闸门。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")

from litetool import settings as settings_mod        # noqa: E402
from litetool.gui.pages.cart_page import CartPage    # noqa: E402
from litetool.gui.pages.machine_page import MachinePage  # noqa: E402

_APP = None


def _app():
    global _APP
    from PyQt5.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])


def _cart():
    _app()
    return CartPage(settings_mod.Settings.load(None))


def _machine():
    _app()
    return MachinePage()


def test_cart_speed_editable_but_move_gated():
    p = _cart()
    p.set_online(True)
    p.set_armed(False)
    p.set_busy(False)
    assert p.speed.isEnabled()          # 输入
    assert not p.btn_mp.isEnabled()     # 执行
    assert p.btn_tcp.isEnabled()        # 只读
    assert p.btn_ik.isEnabled()         # 纯计算


def test_cart_move_enabled_when_armed():
    p = _cart()
    p.set_online(True)
    p.set_armed(True)
    p.set_busy(False)
    assert p.btn_mp.isEnabled()


def test_machine_speed_editable_while_locked():
    p = _machine()
    p.set_online(True)
    p.set_armed(False)
    p.set_busy(False)
    assert p.speed.isEnabled()
    assert not p.btn_home.isEnabled()
