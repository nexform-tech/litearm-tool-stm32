"""夹爪 —— worker 线程、旁路停止、标定摘要与页面接线（全部离线）。"""
from __future__ import annotations

import os
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
        page.channel.setText("can1")
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
