"""固件升级页 / 控制器的离线测试 —— FakeEngine + 假 SDK，不碰 USB、不碰真板子。"""
from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtTest import QTest                         # noqa: E402
from PyQt5.QtWidgets import QApplication               # noqa: E402

import litearm as pa                                   # noqa: E402

from litetool import settings as settings_mod          # noqa: E402
from litetool.dfu.fake import FakeEngine               # noqa: E402
from litetool.gui.main_window import MainWindow        # noqa: E402
from litetool.gui.pages.firmware_page import FirmwarePage   # noqa: E402
from litetool.sdk_worker import TaskResult             # noqa: E402
from tests.fake_arm import FakeArm as WorkerFakeArm, make_state         # noqa: E402


# ------------------------------------------------------------------ 造镜像

def _rec(off: int, typ: int, data: bytes) -> str:
    body = bytes([len(data), (off >> 8) & 0xFF, off & 0xFF, typ]) + data
    return ":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper()


def make_hex(payload: bytes = b"Litearm1.9.0-7J\x00\x00\x00\x00") -> str:
    lines = [_rec(0, 0x04, bytes([0x08, 0x00]))]
    for off in range(0, len(payload), 16):
        lines.append(_rec(off & 0xFFFF, 0x00, payload[off:off + 16]))
    lines.append(":00000001FF")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ 假 SDK

class FakeArm:
    def __init__(self):
        self.enabled = False
        self.disarm_calls = 0
        self.enter_calls = 0
        self.enter_started = threading.Event()
        self.enter_gate: threading.Event | None = None

    def disable(self):
        self.disarm_calls += 1
        self.enabled = False

    def get_state(self, refresh: bool = False):
        return SimpleNamespace(value=SimpleNamespace(enabled=self.enabled))

    def enter_dfu(self):
        self.enter_calls += 1
        self.enter_started.set()
        if self.enter_gate is not None:
            self.enter_gate.wait(2.0)


class FakeSdk:
    """`SdkWorker` 的同形替身：submit 同步执行、close 只记一笔。"""

    def __init__(self, arm: FakeArm | None = None):
        self.arm = arm or FakeArm()
        self.online = True
        self.firmware = "Litearm1.8.0-7J"
        self.closed = 0

    def submit(self, name, fn, done):
        try:
            res = TaskResult(name, True, value=fn(self.arm))
        except BaseException as e:  # noqa: BLE001
            res = TaskResult(name, False, error=e)
        done(res)

    def close(self):
        self.closed += 1
        self.online = False


class NoEngine:
    def available(self):
        return False

    def backend_status(self):
        return "未安装 pyusb (pip install pyusb)"

    def find_device(self):
        return None

    def DfuDevice(self, dev=None, transfer_size=None):  # noqa: N802
        raise AssertionError("引擎不可用时不该被调用")


# ------------------------------------------------------------------ 组装

_APP = None


def _app():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def make_page(*, engine=None, sdk=None, online=True, logs=None,
              upgrading=None, reconnect=None) -> FirmwarePage:
    _app()
    page = FirmwarePage()
    page.set_engine(engine if engine is not None else FakeEngine(steps=2))
    page.set_worker(sdk if sdk is not None else FakeSdk())
    page.set_log(logs.append if logs is not None else (lambda _m: None))
    if upgrading is not None:
        page.set_upgrading_cb(upgrading)
    page.set_confirm(lambda _from_dfu: True)
    page.set_reconnect_override(
        reconnect or (lambda _hint: (True, "fake", "Litearm1.9.0-7J", "")))
    page.set_online(online)
    page._poll()
    return page


def load_valid(page: FirmwarePage) -> None:
    page.inspect_bytes("fw.hex", make_hex().encode())


def wait_result(page: FirmwarePage, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QTest.qWait(20)
        if page._result is not None and not page.is_running():
            return page._result
    raise AssertionError(f"升级没有结束: result={page._result} "
                         f"running={page.is_running()}")


# ------------------------------------------------------------------ 镜像/按钮
def test_valid_image_shows_summary_and_enables_start():
    page = make_page()
    load_valid(page)

    assert not page.summary_box.isHidden()
    assert page.ver_lbl.text() == "Litearm1.9.0-7J"
    assert page.size_lbl.text().endswith(" B")
    assert page.range_lbl.text().startswith("0x08000000..")
    assert len(page.sha_lbl.text()) == 64
    assert page.format_lbl.text() == "hex"

    assert not page.btn_start.isEnabled()          # 安全确认还没勾
    page.safety_cb.setChecked(True)
    assert page.btn_start.isEnabled()
    page.close()


def test_invalid_image_clears_summary_and_blocks_start():
    page = make_page()
    load_valid(page)
    page.safety_cb.setChecked(True)
    assert page.btn_start.isEnabled()

    page.inspect_bytes("bad.hex", b"this is not a firmware image")
    assert page._summary is None and page._blob is None
    assert page.summary_box.isHidden()
    assert not page.error_lbl.isHidden()
    assert not page.btn_start.isEnabled()
    page.close()


def test_offline_without_dfu_blocks_start():
    page = make_page(engine=FakeEngine(present=False), online=False)
    load_valid(page)
    page.safety_cb.setChecked(True)
    assert not page.btn_start.isEnabled()
    assert "未连接控制器" in page.status_lbl.text()
    page.close()


def test_engine_unavailable_is_named_before_any_hardware_action():
    page = make_page(engine=NoEngine())
    load_valid(page)
    page.safety_cb.setChecked(True)
    assert not page.btn_start.isEnabled()
    assert "不可用" in page.engine_lbl.text()

    # 即使绕过按钮直接点，控制器预检也会在碰硬件之前拒绝。
    # ⚠ 这个路径是同步的（`UpgradeController.start` 在预检失败时直接调
    # `on_result`，没有起线程），所以**不要**在这里跑 `QTest.qWait`：
    # CI 的 PyQt5-Qt5 5.15.19 + offscreen 下，处理结果后挂起的 `_poll`
    # 单次定时器会在事件循环里把进程打崩（SIGSEGV），而断言本来就不需要它。
    page._on_start()
    assert page._result is not None
    assert page._result.reason == "engine_unavailable"
    assert "引擎" in page.result_lbl.text()
    page.close()


# ------------------------------------------------------------------ 完整流程
def test_full_online_upgrade_walks_phases_and_comes_back():
    logs = []
    events: list[bool] = []
    phases: list[str] = []
    arm = FakeArm()
    sdk = FakeSdk(arm)
    engine = FakeEngine(steps=3)
    page = make_page(engine=engine, sdk=sdk, online=True, logs=logs,
                     upgrading=events.append)
    page.sig_progress.connect(lambda p: phases.append(p.phase))

    load_valid(page)
    assert page.summary_box.isHidden() is False
    page.safety_cb.setChecked(True)
    page._on_start()
    result = wait_result(page)

    assert result.ok is True, result
    assert result.version == "Litearm1.9.0-7J"
    assert arm.disarm_calls == 1 and arm.enter_calls == 1
    assert sdk.closed >= 1, "进 DFU 之后必须放开 CDC 端口"
    assert engine.last is not None and engine.last.written is not None
    assert engine.last.policy == "abort" and engine.last.left is True
    assert phases[0] == "validate" and "disarm" in phases and "enter_dfu" in phases
    assert phases[-1] == "done"
    assert "升级完成" in page.result_lbl.text()
    assert events and events[0] is True and events[-1] is False
    assert any("固件升级开始" in line for line in logs)
    page.close()


def test_flash_failure_is_reported_and_the_device_is_detached():
    engine = FakeEngine(steps=2, fail="flash")
    page = make_page(engine=engine)
    load_valid(page)
    page.safety_cb.setChecked(True)
    page._on_start()
    result = wait_result(page)

    assert result.ok is False and result.reason == "flash_failed"
    assert engine.last is not None and engine.last.left is True
    assert "烧录失败" in page.result_lbl.text()
    page.close()


def test_from_dfu_skips_disarm_and_enter():
    arm = FakeArm()
    sdk = FakeSdk(arm)
    engine = FakeEngine(steps=2)
    phases: list[str] = []
    page = make_page(engine=engine, sdk=sdk, online=False)
    page.sig_progress.connect(lambda p: phases.append(p.phase))

    assert "bootloader" in page.status_lbl.text()
    load_valid(page)
    page.safety_cb.setChecked(True)
    assert page.btn_start.isEnabled()
    page._on_start()
    result = wait_result(page)

    assert result.ok is True, result
    assert arm.disarm_calls == 0 and arm.enter_calls == 0
    assert "disarm" not in phases and "enter_dfu" not in phases
    assert phases[1] == "wait_dfu"
    assert engine.last is not None and engine.last.written is not None
    page.close()


def test_cancel_during_enter_dfu_stops_before_flash():
    arm = FakeArm()
    arm.enter_gate = threading.Event()
    sdk = FakeSdk(arm)
    engine = FakeEngine(steps=2)
    page = make_page(engine=engine, sdk=sdk)
    load_valid(page)
    page.safety_cb.setChecked(True)
    page._on_start()

    assert arm.enter_started.wait(2.0), "升级没有走到 enter_dfu"
    page._on_cancel()
    arm.enter_gate.set()
    result = wait_result(page)

    assert result.ok is False and result.reason == "cancelled"
    assert engine.last is None or engine.last.written is None
    page.close()


def test_reconnect_rpc_bridges_through_the_signal():
    """生产里这条 RPC 由主窗口在 GUI 线程回填；这里直接接一个回填槽。"""
    page = make_page(online=True)
    page.set_reconnect_override(None)
    page.reconnect_requested.connect(
        lambda hint: page.reconnect_finished(True, "COM9", "Litearm1.9.0-7J", ""))
    ok, port, firmware, error = page._reconnect_rpc("COM9")
    assert (ok, port, firmware, error) == (True, "COM9", "Litearm1.9.0-7J", "")
    page.close()


def test_reset_clears_the_selected_image():
    page = make_page()
    load_valid(page)
    page.safety_cb.setChecked(True)
    page._on_reset()
    assert page._summary is None and page._blob is None
    assert page.summary_box.isHidden()
    assert not page.btn_start.isEnabled()
    page.close()


def test_a_version_mismatch_is_a_visible_warning():
    """镜像 1.9.0、设备复位后报 1.8.0：烧录成功，但页面要把这条不一致摆出来。"""
    page = make_page(reconnect=lambda _hint: (True, "fake", "Litearm1.8.0-7J", ""))
    load_valid(page)
    page.safety_cb.setChecked(True)
    page._on_start()
    result = wait_result(page)

    assert result.ok is True
    assert result.warning and "1.9.0" in result.warning and "1.8.0" in result.warning
    assert not page.warning_lbl.isHidden()
    assert "1.8.0" in page.warning_lbl.text()
    page.close()


# ------------------------------------------------------------------ 真 worker 端到端

class DfuFakeArm(WorkerFakeArm):
    """`tests.fake_arm.FakeArm` + 失能态/授权记录/进 DFU —— 喂给真的 SdkWorker。"""

    def __init__(self):
        super().__init__(firmware="Litearm1.9.0-7J")
        self.entered = 0

    def get_state(self, refresh: bool = False, timeout: float = 0.5):
        st = make_state(self.n, 0, flags=0)          # flags=0 ⇒ enabled=False
        self._a.state = st
        self._a._on_status(b"")
        time.sleep(0.005)
        return pa.Msg(value=st, hz=0.0, timestamp=0.0)

    def license(self):
        return pa.LicenseInfo(state=0, ver=1, uid=bytes(range(0x10, 0x1C)),
                              cust_id=0, issued=0, flags=0)

    def enter_dfu(self):
        self.entered += 1
        self.close()


def test_full_upgrade_through_mainwindow_and_the_real_worker():
    """真 `SdkWorker`（SDK 所有者线程）+ 真主窗口 RPC：进 DFU、烧录、重连一条链路。"""
    _app()
    w = MainWindow(settings_mod.Settings.load(None))
    created: list[DfuFakeArm] = []

    def factory(_port):
        arm = DfuFakeArm()
        created.append(arm)
        return arm

    w.worker._factory = factory
    w._last_port = "fake"
    w.worker.open("fake")
    w._apply_online(True, "fake")
    fw = w.pages["firmware"]
    fw.set_engine(FakeEngine(steps=2))
    fw.set_confirm(lambda _from_dfu: True)
    fw.set_reconnect_override(None)          # 走真实的 MainWindow 重连 RPC
    fw.inspect_bytes("fw.hex", make_hex().encode())
    fw.safety_cb.setChecked(True)

    fw._on_start()
    result = wait_result(fw, timeout=15.0)

    assert result.ok is True, result
    assert len(created) >= 2, "升级后没有用新 Arm 重新建会话"
    assert created[0].entered == 1
    assert result.port == "fake"
    assert fw.state_lbl.text() == "已连接"
    assert w.worker.online is True
    w.worker.close()
    w.close()


def test_closing_during_an_upgrade_requires_confirmation(monkeypatch):
    """升级中的退出守卫必须真的挂在 closeEvent 上（曾经被同名方法覆盖成死代码）。"""
    from PyQt5.QtWidgets import QMessageBox

    _app()
    w = MainWindow(settings_mod.Settings.load(None))
    try:
        w.pages["firmware"].is_running = lambda: True
        monkeypatch.setattr(
            QMessageBox, "warning",
            staticmethod(lambda *a, **k: QMessageBox.No))

        class Event:
            def __init__(self):
                self.ignored = False

            def ignore(self):
                self.ignored = True

            def accept(self):
                self.ignored = False

        ev = Event()
        w.closeEvent(ev)
        assert ev.ignored, "升级中退出必须先确认，不能直接关窗"
    finally:
        w.pages["firmware"].is_running = lambda: False
        w.worker.close()
        w.close()
