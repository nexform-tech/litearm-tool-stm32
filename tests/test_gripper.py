"""夹爪 —— worker 线程、旁路停止、标定摘要与页面接线（全部离线）。"""
from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from litetool import i18n
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
        return SimpleNamespace(ok=True, state=self.get_state(), tries=1)

    def disable(self):
        self.enabled = False
        self.calls.append("disable")
        return True

    def open(self, speed=None, **kw):
        self.calls.append(("open", speed))
        return SimpleNamespace(ok=True)

    def close(self, speed=None, **kw):
        self.calls.append(("close", speed))
        return SimpleNamespace(ok=True)

    def grasp(self, force_n=None, hold_s=0.0, **kw):
        self.calls.append(("grasp", force_n, hold_s))
        return SimpleNamespace(ok=True)

    def write_zero(self):
        self.calls.append("write_zero")
        return SimpleNamespace(ok=True)

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


class FailedEnableGrip(FakeGrip):
    """使能失败但正常返回 —— LiteGrip 1.x 不为此抛异常。"""

    def enable(self):
        self.calls.append("enable")
        return SimpleNamespace(ok=False, state=self.get_state(), tries=3)


class FalseReturningGrip(FakeGrip):
    def disable(self):
        self.enabled = False
        self.calls.append("disable")
        return False


class PostTaskFaultGrip(FakeGrip):
    """动作自身返回成功，但收尾时状态帧报通信丢失（0x0D）。"""

    def __init__(self, channel="can0", can_id=8, mst_id=None):
        super().__init__(channel, can_id, mst_id)
        self.faulted = False

    def open(self, speed=None, **kw):
        self.calls.append(("open", speed))
        self.faulted = True
        return SimpleNamespace(ok=True)

    def get_state(self, wait=True):
        st = super().get_state(wait)
        if self.faulted:
            st.error_code = 13
            st.is_enabled = False
        return st


def test_a_result_with_ok_false_is_reported_as_a_failed_task():
    grip = FailedEnableGrip()
    w = GripperWorker(factory=lambda **kwargs: grip, poll_s=0.02)
    try:
        w.open()
        got = []
        w.enable(cb=got.append)
        assert wait_for(lambda: got)
        assert not got[0].ok
        assert "ok=False" in str(got[0].error)
    finally:
        w.close()


def test_a_bare_false_return_is_reported_as_a_failed_task():
    grip = FalseReturningGrip()
    w = GripperWorker(factory=lambda **kwargs: grip, poll_s=0.02)
    try:
        w.open()
        enabled = []
        w.enable(cb=enabled.append)
        assert wait_for(lambda: enabled and enabled[0].ok)
        got = []
        w.disable(cb=got.append)
        assert wait_for(lambda: got)
        assert not got[0].ok
        assert "False" in str(got[0].error)
    finally:
        w.close()


def test_a_fault_latched_after_the_task_is_reported_as_failed():
    grip = PostTaskFaultGrip()
    w = GripperWorker(factory=lambda **kwargs: grip, poll_s=0.02)
    try:
        w.open()
        got = []
        w.open_jaws(cb=got.append)
        assert wait_for(lambda: got)
        assert not got[0].ok
        assert "13" in str(got[0].error)
    finally:
        w.close()


class LegacyRefreshGrip(FakeGrip):
    """安装路径上命中了一份没有 ``refresh_status`` 的同名模块。"""

    refresh_status = None


class NoKeepaliveGrip(FakeGrip):
    """既没有 send_mit_frame 也没有 stop —— 使能后必锁 0x0D，页面必须拦住。"""

    send_mit_frame = None
    stop = None


def test_refresh_reports_the_missing_sdk_api_instead_of_raising():
    grip = LegacyRefreshGrip()
    w = GripperWorker(factory=lambda **kwargs: grip, poll_s=0.02)
    try:
        w.open()
        assert not w.supports("refresh_status")
        assert w.can_keep_alive()
        got = []
        w.refresh(cb=got.append)
        assert wait_for(lambda: got)
        assert not got[0].ok
        assert "refresh_status" in str(got[0].error)
    finally:
        w.close()


def test_can_keep_alive_requires_one_of_the_two_frame_senders():
    grip = NoKeepaliveGrip()
    w = GripperWorker(factory=lambda **kwargs: grip, poll_s=0.02)
    try:
        w.open()
        assert not w.can_keep_alive()
    finally:
        w.close()


def test_task_text_keeps_the_action_name():
    try:
        i18n.set_language("zh")
        assert GripperTaskResult("夹爪使能", True).text == "夹爪使能 完成"
        assert (GripperTaskResult("夹爪抓取 20.0N/3.0s", True).text
                == "夹爪抓取 20.0N/3.0s 完成")
        i18n.set_language("en")
        assert GripperTaskResult("夹爪使能", True).text == "Gripper enable complete"
        assert "gripper task" in GripperTaskResult(
            "夹爪抓取 20.0N/3.0s", True).text
    finally:
        i18n.set_language("zh")



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

    def supports(self, name):
        return True

    def can_keep_alive(self):
        return True

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
        # 原因必须顶在页头（issue #44）：小灰字在连接组底部，读起来像按钮坏了。
        assert not page.avail_banner.isHidden()
        assert "Linux" in page.avail_banner.text()
        # 用户最先点的是灰按钮本身，它自己的 tooltip 也要说明原因。
        assert "Linux" in page.btn_conn.toolTip()
    finally:
        page.shutdown()


class LegacyWorker(FakeWorker):
    """自报 2.2.0 的运行时装载：没有新鲜度字段，也没有 refresh_status。"""

    def __init__(self):
        super().__init__()
        self.state = SimpleNamespace(
            position_mm=12.3, force_n=4.5, torque_nm=0.45,
            temperature_mos=30, temperature_coil=31, error_code=1,
            is_enabled=True)

    def supports(self, name):
        return False

    def can_keep_alive(self):
        return False


def test_page_renders_an_old_snapshot_without_crashing_or_hiding_buttons(app):
    worker = LegacyWorker()
    worker.online = True
    page = _page(worker)
    try:
        page._tick()                     # 旧实现在这里 AttributeError: data_age_s
        assert page.pos_lbl.text() == "+12.30"
        assert "不支持" in page.fresh_lbl.text()
        assert not page.btn_refresh.isEnabled(), "缺少 refresh_status 时刷新不可用"
        assert not page.btn_enable.isEnabled(), "发不出保活帧时必须拦住使能"
        assert page.btn_stop.isEnabled(), "停止 / 释放永远可达"
        assert "不兼容" in page.log_view.toPlainText()
    finally:
        page.shutdown()


def test_page_hides_the_unavailable_banner_when_supported(app):
    page = _page(FakeWorker())
    try:
        assert page.available
        assert page.avail_banner.isHidden()
        assert page.btn_conn.toolTip() == ""
    finally:
        page.shutdown()


def test_page_retranslates_the_unavailable_banner(app):
    from litetool import i18n

    worker = FakeWorker(available=(False, "LiteGrip 仅支持 Linux（SocketCAN）"))
    page = _page(worker)
    try:
        try:
            i18n.set_language("en")
            page.retranslate()
            assert "unavailable" in page.avail_banner.text().lower()
            assert "Linux" in page.avail_banner.text()
            assert "Unavailable" in page.btn_conn.toolTip()
        finally:
            i18n.set_language("zh")
    finally:
        page.shutdown()


def test_nav_marks_the_gripper_page_linux_only_when_unavailable(monkeypatch, app):
    """Windows 包不含 litegrip：导航项就要写明限制，而不是等用户点进去猜。"""
    from litetool import settings
    from litetool.gui.main_window import MainWindow

    monkeypatch.setattr("litetool.gripper.availability",
                        lambda: (False, "LiteGrip 仅支持 Linux（SocketCAN）"))
    window = MainWindow(settings.Settings.load(None))
    try:
        item = window.nav._items["gripper"]
        assert "仅 Linux" in item.text(0), item.text(0)
    finally:
        window.close()


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
