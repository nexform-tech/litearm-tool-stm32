"""断线自愈 —— 判离线、按退避重拨、优先上次的口、丢弃旧命令、手动断开不重试。"""
from __future__ import annotations

import os
import time

import pytest

from litetool.sdk_worker import SdkWorker
from tests.fake_arm import FakeArm, wait_for, worker_arm_factory


def _worker(arms, **kw):
    logs, onlines, attempts, tasks = [], [], [], []
    w = SdkWorker(
        arm_factory=worker_arm_factory(arms),
        log=logs.append,
        on_online=lambda ok, why: onlines.append((ok, why)),
        on_task=tasks.append,
        on_reconnect=lambda n, why: attempts.append((n, why)),
        offline_timeout=0.05,
        idle_timeout=0.005,
        reconnect_initial_s=0.01,
        reconnect_max_s=0.02,
        **kw,
    )
    return w, logs, onlines, attempts, tasks


def test_link_loss_reconnects_and_reports_attempts():
    first = FakeArm()
    second = FakeArm(firmware="Litearm9.9-7J")
    w, logs, onlines, attempts, _ = _worker([first, second])
    try:
        w.open("p1")
        assert wait_for(lambda: w.state is not None)

        first.silent = True
        assert wait_for(lambda: any(ok is False for ok, _ in onlines)), "断线必须报离线"
        assert wait_for(lambda: w.online and w.arm is second), "必须重拨到下一条链路"
        assert w.firmware == "Litearm9.9-7J"
        assert attempts and attempts[0][0] == 1
        assert first.closed, "旧句柄必须关掉，不能留着占串口"
        assert any("重连" in m for m in logs)
    finally:
        w.close()


def test_manual_close_stops_retrying():
    first = FakeArm()
    calls = []

    def factory(port):
        calls.append(port)
        if len(calls) == 1:
            return first
        raise OSError("device gone")

    w = SdkWorker(arm_factory=factory, offline_timeout=0.05, idle_timeout=0.005,
                  reconnect_initial_s=0.02, reconnect_max_s=0.05)
    try:
        w.open("p1")
        first.silent = True
        assert wait_for(lambda: len(calls) >= 3), "失败后必须按退避继续尝试"
    finally:
        w.close()
    n = len(calls)
    time.sleep(0.2)
    assert len(calls) == n, "用户断开后不得再抢串口"


def test_initial_connect_failure_is_not_retried():
    calls = []

    def factory(port):
        calls.append(port)
        raise OSError("no device")

    w = SdkWorker(arm_factory=factory)
    with pytest.raises(OSError):
        w.open("p1")
    time.sleep(0.05)
    assert calls == ["p1"], "首次连接失败由用户决定，不自动重试"
    assert w._thread is None


def test_offline_drops_pending_tasks():
    """排队命令是在旧链路上受理的意图，重连后执行它等于让臂突然动一下。"""
    arm = FakeArm()
    w = SdkWorker(arm_factory=lambda port: arm)
    w._arm = arm
    ran, got = [], []
    w.submit("late", lambda a: ran.append(1), got.append)
    assert not got, "没有线程时任务只应排队"

    w._go_offline("拔线")
    assert ran == []
    assert got and not got[0].ok
    assert "断线" in str(got[0].error)


def test_reconnect_prefers_last_port_then_falls_back(monkeypatch):
    first = FakeArm()
    second = FakeArm(firmware="Litearm9.9-7J")
    calls = []

    def factory(port):
        calls.append(port)
        if port == "p1" and calls.count("p1") == 1:
            return first
        if port == "p2":
            return second
        raise OSError(f"{port} gone")

    monkeypatch.setattr("litetool.ports.find_ports",
                        lambda: [{"device": "p2"}, {"device": "p3"}])
    w = SdkWorker(arm_factory=factory, offline_timeout=0.05, idle_timeout=0.005,
                  reconnect_initial_s=0.01, reconnect_max_s=0.02)
    try:
        w.open("p1")
        assert wait_for(lambda: w.state is not None)
        first.silent = True
        assert wait_for(lambda: w.online and w.arm is second)
        assert calls[0] == "p1" and calls[1] == "p1", "重连先试上次成功的口"
        assert "p2" in calls, "上次的口不行时要重新枚举并试其它口"
        assert w._port == "p2"
    finally:
        w.close()


# ------------------------------------------------------------ GUI 接线
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")


@pytest.fixture(scope="module")
def app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _win():
    from litetool import settings
    from litetool.gui.main_window import MainWindow
    return MainWindow(settings.Settings.load(None))


def test_main_window_shows_reconnect_state(app):
    w = _win()
    try:
        w.worker._on_reconnect(2, "正在自动重连（第 2 次）…")
        assert "重连中(2)" in w.dot.text()
        assert "固件: —" == w.fw_lbl.text()
    finally:
        w.close()


def test_reconnect_does_not_restore_the_motion_unlock(app):
    w = _win()
    try:
        w._connected = True
        w.unlock_cb.setChecked(True)
        assert w._armed

        w._apply_online(False, "拔线")
        assert not w._armed, "断线必须收回解锁"

        w._apply_online(True, "已重连")
        assert not w._armed, "重连不得把旧解锁态带回来"
    finally:
        w.close()
