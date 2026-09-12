"""零重力拖动 (段②) 的 GUI 流测试 —— 保活心跳 / 状态回写 / 自动停止。

固件侧 CMD_ZERO_G 自带 watchdog_kick (0x20/0x21 都刻意不 kick), 所以上位机
必须周期重发, 否则 0.1s 后固件把模式掐回 fail-soft 持位。这里验证:
  - 未使能/故障锁存时拒绝进入
  - 进入后立刻发一帧 on=1, 且心跳定时器启动
  - 心跳每次重发 on=1
  - 固件自行退出 (mode != ZERO_G) 时自动停心跳并复位按钮
  - 串口异常 / 断开时自动停止
  - 显式退出发一帧 on=0 并停心跳
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from litetool import protocol as P  # noqa: E402
from litetool import settings as settings_mod  # noqa: E402
from litetool.gui.main_window import MainWindow  # noqa: E402

SOF = P.SOF


class _St:
    def __init__(self, mode=P.MODE_MOVE_J, enabled=True, has_fault=False):
        self.mode = mode
        self.mode_name = P.MODE_NAMES.get(mode, str(mode))
        self.enabled = enabled
        self.has_fault = has_fault


class _Link:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send_bytes(self, data: bytes):
        if self.fail:
            raise RuntimeError("port gone")
        self.sent.append(data)


class _Cli:
    def __init__(self, st):
        self.status = st


class _Sess:
    def __init__(self, st, link):
        self.status = st
        self.link = link
        self.client = _Cli(st)

    def close(self):
        self.link = None
        self.client = None


def _win(st=None, link=None):
    app = QApplication.instance() or QApplication([])
    w = MainWindow(settings_mod.Settings.load(None))
    link = link if link is not None else _Link()
    w.session = _Sess(st if st is not None else _St(), link)
    return app, w, link


def _zg_payloads(link):
    """从已发原始字节里解出 CMD_ZERO_G 的 payload (本仓 protocol 只有 pack)。"""
    out = []
    for d in link.sent:
        if len(d) >= 5 and d[0] == SOF and d[1] == P.CMD_ZERO_G:
            out.append(bytes(d[3:3 + d[2]]))
    return out


def test_zero_g_refused_when_not_enabled():
    _app, w, link = _win(_St(enabled=False))
    w._on_zero_g(True)
    assert _zg_payloads(link) == []              # 一帧都没发
    assert not w.control.btn_zg.isChecked()
    assert not w._zg_timer.isActive()
    w.close()


def test_zero_g_refused_when_fault_latched():
    _app, w, link = _win(_St(mode=6, has_fault=True))
    w._on_zero_g(True)
    assert _zg_payloads(link) == []
    assert not w._zg_timer.isActive()
    w.close()


def test_zero_g_enter_sends_on_and_starts_keepalive():
    _app, w, link = _win()
    w._on_zero_g(True)
    assert _zg_payloads(link) == [b"\x01"]
    assert w._zg_timer.isActive()
    assert w.control.btn_zg.isChecked()
    assert "保活" in w.control.zg_lbl.text()
    w.close()


def test_zero_g_keepalive_resends():
    _app, w, link = _win()
    w._on_zero_g(True)
    n0 = len(_zg_payloads(link))
    for _ in range(3):
        w._zg_keepalive()
    assert len(_zg_payloads(link)) == n0 + 3     # 每次心跳都重发一条
    assert all(p == b"\x01" for p in _zg_payloads(link))
    w.close()


def test_zero_g_autostops_when_firmware_leaves_mode():
    """固件因看门狗/急停/新命令退出零重力 -> 上位机必须停心跳并复位按钮。"""
    st = _St()
    _app, w, link = _win(st)
    w._on_zero_g(True)
    assert w._zg_timer.isActive()
    st.mode = P.MODE_MOVE_J                       # 固件自行退出
    w._zg_keepalive()
    assert not w._zg_timer.isActive()
    assert not w.control.btn_zg.isChecked()
    assert "已退出" in w.control.zg_lbl.text()
    w.close()


def test_zero_g_autostops_on_link_error():
    _app, w, link = _win()
    w._on_zero_g(True)
    link.fail = True
    w._zg_keepalive()
    assert not w._zg_timer.isActive()
    assert not w.control.btn_zg.isChecked()
    w.close()


def test_zero_g_exit_sends_off_and_stops():
    _app, w, link = _win()
    w._on_zero_g(True)
    w._on_zero_g(False)
    assert _zg_payloads(link) == [b"\x01", b"\x00"]
    assert not w._zg_timer.isActive()
    assert not w.control.btn_zg.isChecked()
    w.close()


def test_zero_g_disconnect_stops_keepalive():
    _app, w, _link = _win()
    w._on_zero_g(True)
    assert w._zg_timer.isActive()
    w._disconnect()
    assert not w._zg_timer.isActive()
    assert not w.control.btn_zg.isChecked()
    w.close()
