"""升级控制器（`litetool/dfu/controller.py`）的离线测试。

只测 tool 侧适配的判据：失能/进 DFU 的失败怎么映射、进 DFU 后何时放掉串口、
"存在≠可用"的权限重试、以及两个开跑前的闸。烧录时序本身由 `test_dfu_engine.py`
与 `test_dfu_image.py` 的流水线用例覆盖。
"""
from __future__ import annotations

import threading
from types import SimpleNamespace


import litearm as pa

from litetool.dfu import controller, fake
from litetool.sdk_worker import TaskResult


class Arm:
    def __init__(self):
        self.enabled = False
        self.disabled = 0
        self.entered = 0
        self.disable_error: BaseException | None = None
        self.enter_error: BaseException | None = None

    def disable(self):
        self.disabled += 1
        if self.disable_error is not None:
            raise self.disable_error
        self.enabled = False

    def get_state(self, refresh: bool = False):
        return SimpleNamespace(value=SimpleNamespace(enabled=self.enabled))

    def enter_dfu(self):
        self.entered += 1
        if self.enter_error is not None:
            raise self.enter_error


class Sdk:
    def __init__(self, arm: Arm | None = None):
        self.arm = arm or Arm()
        self.online = True
        self.firmware = "Litearm1.9.0-7J"
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


SUMMARY = SimpleNamespace(name="fw.hex", size=32, sha256="ab" * 32, version=None)


def run(*, sdk=None, engine=None, from_dfu=False, blob=b"\x00" * 32,
        reconnect=None) -> tuple:
    sdk = sdk or Sdk()
    engine = engine or fake.FakeEngine(steps=1)
    results: list = []
    done = threading.Event()

    def on_result(result):
        results.append(result)
        done.set()

    ctl = controller.UpgradeController(
        sdk=sdk, engine_module=engine,
        reconnect=reconnect or (lambda _hint: (True, "fake", "Litearm1.9.0-7J", "")),
        on_progress=lambda _p: None, on_result=on_result,
        on_log=lambda _m: None, on_upgrading=lambda _b: None)
    started = ctl.start(blob, 0x08000000, SUMMARY, from_dfu=from_dfu)
    assert done.wait(5.0), "升级没有返回结果"
    return started, results[0], sdk, engine, ctl


def test_precheck_engine_unavailable_stops_before_any_hardware_action():
    started, result, sdk, _engine, _ctl = run(engine=NoEngine())
    assert started is False
    assert result.ok is False and result.reason == "engine_unavailable"
    assert sdk.closed == 0 and sdk.arm.disabled == 0 and sdk.arm.entered == 0


def test_precheck_from_dfu_requires_a_visible_device():
    started, result, sdk, _engine, _ctl = run(
        engine=fake.FakeEngine(present=False), from_dfu=True)
    assert started is False
    assert result.reason == "dfu_device_absent"
    assert sdk.closed == 0


def test_disarm_failure_is_reported_as_arm_enabled():
    arm = Arm()
    arm.disable_error = RuntimeError("boom")
    started, result, sdk, engine, _ctl = run(sdk=Sdk(arm))
    assert started is True
    assert result.ok is False and result.reason == "arm_enabled"
    assert "失能失败" in result.message
    assert arm.entered == 0
    assert engine.last is None            # 还没进 DFU, 不该有 detach


def test_enter_rejected_because_enabled_is_arm_enabled():
    arm = Arm()
    arm.enter_error = pa.InvalidCommandError("使能中不跳")
    started, result, sdk, _engine, _ctl = run(sdk=Sdk(arm))
    assert started is True
    assert result.ok is False and result.reason == "arm_enabled"
    # 固件拒绝说明设备没跳 —— 串口留着, 用户还能失能后重试。
    assert sdk.closed == 0


def test_enter_transport_error_closes_the_port_and_still_detaches():
    arm = Arm()
    arm.enter_error = pa.TransportError("ACK 丢了，但设备可能已经跳了")
    started, result, sdk, engine, _ctl = run(sdk=Sdk(arm))
    assert started is True
    assert result.ok is False and result.reason == "dfu_not_entered"
    assert sdk.closed >= 1
    assert engine.last is not None and engine.last.left is True


def test_a_successful_enter_releases_the_cdc_port():
    started, result, sdk, engine, _ctl = run()
    assert started is True
    assert result.ok is True
    assert sdk.closed >= 1
    assert engine.last is not None and engine.last.written is not None
    assert engine.last.left is True


def test_waiting_tolerates_a_device_that_is_not_openable_yet(monkeypatch):
    """存在 ≠ 可用：udev 还没 chmod 时继续等，不能一撞 EACCES 就放弃。"""
    engine = fake.FakeEngine(steps=1, deny_open_times=2)
    started, result, _sdk, engine, _ctl = run(engine=engine)
    assert started is True
    assert result.ok is True, result
    assert engine.devices_made == 3


def test_a_device_that_stays_unopenable_is_a_permission_error(monkeypatch):
    monkeypatch.setattr(controller, "DFU_APPEAR_TIMEOUT_S", 0.3)
    engine = fake.FakeEngine(steps=1, deny_open_times=10 ** 6)
    started, result, _sdk, _engine, _ctl = run(engine=engine)
    assert started is True
    assert result.ok is False and result.reason == "dfu_permission_denied"


def test_reconnect_failure_is_reported_after_the_image_was_written(monkeypatch):
    monkeypatch.setattr(controller, "UPGRADE_RECONNECT_WINDOW_S", 0.3)
    monkeypatch.setattr(controller, "RECONNECT_PERIOD_S", 0.05)

    def never(_hint):
        return (False, "", "", "COM9: 未发现设备")

    started, result, _sdk, engine, _ctl = run(
        engine=fake.FakeEngine(steps=1), reconnect=never)
    assert started is True
    assert result.ok is False and result.reason == "reconnect_failed"
    assert "固件已写入并通过读回校验" in result.message
    assert engine.last is not None and engine.last.written is not None
    assert engine.last.left is True
