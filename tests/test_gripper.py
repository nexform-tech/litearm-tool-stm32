"""夹爪 —— worker 线程、旁路停止、标定摘要与页面接线（全部离线）。"""
from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from litetool.gripper import GripperTaskResult, GripperWorker
from tests.fake_arm import wait_for


class FakeGrip:
    def __init__(self, channel="can0", can_id=8, mst_id=None):
        self.channel = channel
        self.can_id = can_id
        self.mst_id = mst_id
        self.config = SimpleNamespace(calibrated=True, mount="normal",
                                      pos_closed_rad=1.14, pos_open_rad=0.0,
                                      rad_to_mm=73.0)
        self.info = SimpleNamespace(firmware="fake-1.0")
        self.connected = False
        self.enabled = False
        self.stopped = False
        self.keepalives = 0
        self.calls = []

    def connect(self):
        self.connected = True
        self.calls.append("connect")

    def disconnect(self):
        self.connected = False
        self.calls.append("disconnect")

    def load_calibration(self, path=None, template=None):
        self.calls.append(("load_calibration", path, template))
        return True

    def get_state(self, wait=True):
        return SimpleNamespace(position_mm=12.3, force_n=4.5, torque_nm=0.45,
                               temperature_mos=30, temperature_coil=31,
                               error_code=1 if self.enabled else 0,
                               fresh=True, data_age_s=0.01,
                               is_enabled=self.enabled)

    def enable(self):
        self.enabled = True
        self.calls.append("enable")

    def disable(self):
        self.enabled = False
        self.calls.append("disable")

    def open(self, speed=None, **kw):
        self.calls.append(("open", speed))

    def close(self, speed=None, **kw):
        self.calls.append(("close", speed))

    def grasp(self, force_n=None, hold_s=0.0, **kw):
        self.calls.append(("grasp", force_n, hold_s))
        return "grasped"

    def write_zero(self):
        self.calls.append("write_zero")

    def zero(self):
        self.calls.append("zero")

    def save_calibration(self, path=None):
        self.calls.append(("save_calibration", path))
        return path

    def refresh_status(self):
        self.calls.append("refresh_status")
        return True

    def send_mit_frame(self, q=0.0, kp=0.0, kd=0.0, dq=0.0, tau=0.0):
        self.calls.append(("send_mit_frame", q, kp, kd))
        self.keepalives += 1
        return self.enabled

    def stop(self):
        self.stopped = True
        self.calls.append("stop")


def _worker(grip=None, **kw):
    grip = grip or FakeGrip()
    w = GripperWorker(factory=lambda **kwargs: grip, poll_s=0.02, **kw)
    return w, grip


def test_worker_connects_polls_and_runs_actions():
    w, grip = _worker()
    try:
        w.open(channel="can0", can_id=8, mst_id=None)
        assert w.online
        assert wait_for(lambda: w.state is not None)
        assert w.state.position_mm == pytest.approx(12.3)

        got = []
        w.enable(cb=got.append)
        assert wait_for(lambda: got)
        assert got[0].ok and grip.enabled

        got2 = []
        w.grasp(20.0, 3.0, cb=got2.append)
        assert wait_for(lambda: got2)
        assert got2[0].ok and ("grasp", 20.0, 3.0) in grip.calls

        ok, why = w.stop_now()
        assert ok and grip.stopped
    finally:
        w.close()
    assert not w.online
    assert "disconnect" in grip.calls


class BlockingGraspGrip(FakeGrip):
    """保力循环直到失能才退出的假件 —— 用来验证"停止"真的能中止在途抓取。"""

    def __init__(self, channel="can0", can_id=8, mst_id=None):
        super().__init__(channel, can_id, mst_id)
        self.grasp_started = threading.Event()
        self.grasp_release = threading.Event()

    def grasp(self, force_n=None, hold_s=0.0, **kw):
        self.calls.append(("grasp", force_n, hold_s))
        self.grasp_started.set()
        self.grasp_release.wait(2.0)       # 只有 disable() 会放行
        return "grasped"

    def disable(self):
        self.enabled = False
        self.calls.append("disable")
        self.grasp_release.set()

    def stop(self):
        self.stopped = True
        self.calls.append("stop")


def test_stop_during_a_grasp_disables_and_drops_queued_work():
    """一帧零力矩压不住保力循环：必须失能 + 丢弃排队任务，且如实报"已中止"。"""
    grip = BlockingGraspGrip()
    w = GripperWorker(factory=lambda **kwargs: grip, poll_s=0.02)
    try:
        w.open()
        running, queued = [], []
        w.grasp(20.0, 30.0, cb=running.append)
        assert grip.grasp_started.wait(1.0)

        w.open_jaws(cb=queued.append)       # 排在抓取后面
        ok, why = w.stop_now()
        assert ok and "失能" in why, why
        assert "disable" in grip.calls

        assert wait_for(lambda: running), "在途抓取没有结束"
        assert not running[0].ok and "中止" in str(running[0].error)
        assert queued and not queued[0].ok and "丢弃" in str(queued[0].error)
    finally:
        w.close()


def test_stop_when_idle_only_sends_zero_torque():
    """空闲时只发零力矩帧，不改变使能态。"""
    w, grip = _worker()
    try:
        w.open()
        ok, why = w.stop_now()
        assert ok and "失能" not in why
        assert "disable" not in grip.calls
    finally:
        w.close()


def test_idle_enabled_motor_gets_zero_torque_keepalive_frames():
    """DM4310 在最后一帧控制帧后 ~100 ms 自锁 0x0D；空闲必须持续发保活帧。"""
    w, grip = _worker()
    try:
        w.open()
        enabled = []
        w.enable(cb=enabled.append)
        assert wait_for(lambda: enabled and enabled[0].ok and grip.enabled)
        assert wait_for(lambda: grip.keepalives >= 3, timeout=1.0), \
            "使能后空闲没有保活帧"
        frames = [c for c in grip.calls if c[0] == "send_mit_frame"]
        assert frames and all(c[1:] == (0.0, 0.0, 0.0) for c in frames)

        disabled = []
        w.disable(cb=disabled.append)
        assert wait_for(lambda: disabled and disabled[0].ok and not grip.enabled)
        time.sleep(0.15)
        settled = grip.keepalives
        time.sleep(0.15)
        assert grip.keepalives == settled, "失能后仍在发保活帧"
    finally:
        w.close()


class StopOnlyGrip(FakeGrip):
    """没有 send_mit_frame 的旧接口：同样的一帧零力矩退回 stop()。"""

    send_mit_frame = None


def test_keepalive_falls_back_to_stop_on_an_older_sdk():
    grip = StopOnlyGrip()
    w = GripperWorker(factory=lambda **kwargs: grip, poll_s=0.02)
    try:
        w.open()
        enabled = []
        w.enable(cb=enabled.append)
        assert wait_for(lambda: enabled and enabled[0].ok and grip.enabled)
        assert wait_for(lambda: grip.calls.count("stop") >= 2, timeout=1.0)
    finally:
        w.close()



def test_calibration_summary_reports_travel_and_mount():
    w, _ = _worker()
    try:
        w.open()
        got = []
        w.calibration(cb=got.append)
        assert wait_for(lambda: got)
        summary = got[0].value
        assert summary["calibrated"] is True
        assert summary["mount"] == "normal"
        assert summary["travel_mm"] == pytest.approx(1.14 * 73.0)
    finally:
        w.close()


def test_submit_without_a_connection_is_rejected():
    w = GripperWorker()
    got = []
    w.enable(cb=got.append)
    assert got and not got[0].ok


def test_calibration_path_wins_over_mount():
    w, grip = _worker()
    try:
        w.open(mount="reverse", calibration_path="/tmp/cal.json")
        assert ("load_calibration", "/tmp/cal.json", None) in grip.calls
    finally:
        w.close()


# ------------------------------------------------------------ 页面
pytest.importorskip("PyQt5")


@pytest.fixture(scope="module")
def app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class FakeWorker:
    def __init__(self, available=(True, "")):
        self._available = available
        self.online = False
        self.state = SimpleNamespace(
            position_mm=12.3, force_n=4.5, torque_nm=0.45,
            temperature_mos=30, temperature_coil=31, error_code=1,
            fresh=True, data_age_s=0.01, is_enabled=True)
        self.calls = []

    def available(self):
        return self._available

    def open(self, **kw):
        self.calls.append(("open", kw))
        self.online = True

    def close(self):
        self.calls.append("close")
        self.online = False

    def enable(self, cb=None):
        self.calls.append("enable")

    def disable(self, cb=None):
        self.calls.append("disable")

    def open_jaws(self, speed=None, cb=None):
        self.calls.append("open")

    def close_jaws(self, speed=None, cb=None):
        self.calls.append("close_jaws")

    def grasp(self, force, hold, cb=None):
        self.calls.append(("grasp", force, hold))

    def refresh(self, cb=None):
        self.calls.append("refresh")

    def calibration(self, cb=None):
        self.calls.append("calibration")

    def load_calibration(self, path=None, mount=None, cb=None):
        self.calls.append(("load_calibration", path, mount))

    def save_calibration(self, path=None, cb=None):
        self.calls.append(("save_calibration", path))

    def write_zero(self, cb=None):
        self.calls.append("write_zero")

    def stop_now(self):
        self.calls.append("stop")
        return True, "sent"


def _page(worker):
    from litetool import settings
    from litetool.gui.pages.gripper_page import GripperPage
    return GripperPage(settings.Settings.load(None), worker=worker)


def test_page_connects_with_the_configured_identity(app):
    worker = FakeWorker()
    page = _page(worker)
    try:
        page.channel.setCurrentText("can1")
        page.can_id.setValue(9)
        page.mst_id.setValue(24)
        page._toggle_connect()
        assert worker.calls and worker.calls[0][0] == "open"
        kw = worker.calls[0][1]
        assert kw == {"channel": "can1", "can_id": 9, "mst_id": 24,
                      "mount": None, "calibration_path": None}
        page._tick()
        assert page.pos_lbl.text() == "+12.30"
        assert page.force_lbl.text() == "+4.50"
        assert page.temp_lbl.text() == "30/31"
    finally:
        page.shutdown()


def test_page_disables_motion_until_busy_clears(app):
    worker = FakeWorker()
    page = _page(worker)
    try:
        worker.online = True
        page._tick()
        assert page.btn_open.isEnabled()
        page._busy = True
        page._refresh()
        assert not page.btn_open.isEnabled()
        assert page.btn_stop.isEnabled(), "停止永远可达"
        page._on_task(GripperTaskResult("x", True))
        assert page.btn_open.isEnabled()
    finally:
        page.shutdown()


def test_page_reports_unavailable_platform(app):
    worker = FakeWorker(available=(False, "LiteGrip 仅支持 Linux（SocketCAN）"))
    page = _page(worker)
    try:
        assert not page.btn_conn.isEnabled()
        assert "不可用" in page.conn_lbl.text()
    finally:
        page.shutdown()


def test_page_populates_the_channel_dropdown(monkeypatch, app):
    monkeypatch.setattr("litetool.gui.pages.gripper_page.list_channels",
                        lambda: ["can1", "vcan0"])
    worker = FakeWorker()
    page = _page(worker)
    try:
        items = [page.channel.itemText(i) for i in range(page.channel.count())]
        assert items == ["can1", "vcan0"]
        assert page.channel.currentText() == "can1"
        page.channel.setCurrentText("vcan0")
        page._toggle_connect()
        assert worker.calls[0][1]["channel"] == "vcan0"
    finally:
        page.shutdown()


def test_page_channel_falls_back_to_can0(monkeypatch, app):
    monkeypatch.setattr("litetool.gui.pages.gripper_page.list_channels",
                        lambda: [])
    page = _page(FakeWorker())
    try:
        assert page.channel.currentText() == "can0"
    finally:
        page.shutdown()


def test_refreshing_channels_keeps_a_typed_name(monkeypatch, app):
    found = ["can0"]
    monkeypatch.setattr("litetool.gui.pages.gripper_page.list_channels",
                        lambda: list(found))
    page = _page(FakeWorker())
    try:
        page.channel.setCurrentText("vcan0")
        found[:] = ["can0", "can1"]
        page._refresh_channels()
        assert page.channel.currentText() == "vcan0"
        items = [page.channel.itemText(i) for i in range(page.channel.count())]
        assert items == ["can0", "can1", "vcan0"]
    finally:
        page.shutdown()
