"""故障页 —— 哪根轴、为什么、怎么办，一屏可见。"""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

from litetool.gui.pages.fault_page import FaultPage   # noqa: E402


_APP = None


def _page():
    global _APP
    from PyQt5.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])
    return FaultPage()


def _state(reasons, jf, mode="MOVE_J", enabled=True, drop=0):
    return SimpleNamespace(
        n=7, mode_name=mode, enabled=enabled, joint_fault=jf,
        fault_reason=reasons, drop_hold_reason=drop,
        joints=[SimpleNamespace(q=0.0, dq=0.0, tau=0.0,
                                t_mos=30.0, t_coil=30.0, err=1)
                for _ in range(7)],
    )


def test_no_fault_shows_green_summary():
    p = _page()
    p.update_from(_state([0] * 7, 0))
    assert p.head.text() == "无故障"
    assert "已使能" in p.detail.text()
    assert p.table.rowCount() == 7


def test_j4_can_loss_shows_axis_and_reason():
    p = _page()
    p.update_from(_state([0, 0, 0, 1, 0, 0, 0], 0x0008))
    assert "J4" in p.head.text()
    assert p.table.item(3, 1).text() == "断轴"
    reason = p.table.item(3, 2).text()
    assert "CAN" in reason
    assert p.table.item(3, 3).text()          # 处置非空
    assert p.table.item(0, 1).text() == "正常"


def test_old_firmware_without_reason_is_not_blank():
    p = _page()
    p.update_from(_state([], 0x0008))
    assert p.table.item(3, 1).text() == "断轴"
    assert "旧固件" in p.table.item(3, 2).text()


def test_event_history_appends():
    p = _page()
    p.add_event("J4 CAN 反馈丢失")
    assert "J4 CAN 反馈丢失" in p.hist.toPlainText()
