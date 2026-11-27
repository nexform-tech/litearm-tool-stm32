"""笛卡尔点动 / movel / 受控停止 —— 页面状态机、worker 旁路帧、主窗口接线。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

import litearm as pa
from litearm import _protocol as _P
from PyQt5.QtWidgets import QApplication

from litetool import settings as settings_mod
from litetool.gui.pages.cart_page import CartPage
from litetool.sdk_worker import SdkWorker, TaskResult
from tests.fake_arm import FakeArm, make_state


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _page():
    return CartPage(settings_mod.Settings.load(None))


def _plan():
    return object()


def _ok_result(gen_target=(0.1, 0.0, 0.0, 0.0, 0.0, 0.0)):
    return TaskResult("点动", True,
                      value=((0.3, 0.0, 0.35, 3.1416, 0.0, 0.0),
                             gen_target, _plan()))


# ------------------------------------------------------------ 页面状态机
def test_unsupported_firmware_disables_jog_and_movel(app):
    page = _page()
    try:
        page.set_online(True)
        page.set_armed(True)
        page.set_cart_supported(False, silent=False)
        assert not any(b.isEnabled() for b in page._jog_buttons)
        assert not page.btn_ml.isEnabled()
        assert "笛卡尔规划" in page.cart_hint.text()

        page.set_cart_supported(False, silent=True)
        assert "未获确认" in page.cart_hint.text()

        page.set_cart_supported(True)
        assert all(b.isEnabled() for b in page._jog_buttons)
        assert page.btn_ml.isEnabled()
        assert page.cart_hint.text() == ""
    finally:
        page.close()


def test_press_starts_a_segment_and_release_stops_it(app):
    page = _page()
    try:
        page.set_online(True)
        page.set_armed(True)
        page.set_cart_supported(True)
        steps, stops = [], []
        page.jog_step.connect(lambda *a: steps.append(a))
        page.stop_req.connect(lambda: stops.append(1))

        page._jog_press("Y", "translate", -1)
        assert len(steps) == 1
        axis, kind, amount, frame, speed, gen = steps[0]
        assert (axis, kind, frame) == ("Y", "translate", "base")
        assert amount == pytest.approx(-0.005)
        assert speed == pytest.approx(settings_mod.Settings.load(None).default_speed)

        # 一段成功 → 按住时自动续段
        page.jog_result(gen, _ok_result())
        assert len(steps) == 2
        assert page._jog_holding and page._jog_in_flight

        page._jog_release()
        assert stops == [1], "松手必须发受控停止"
        assert page._jog_stop_requested

        page.jog_result(steps[1][-1],
                        TaskResult("点动", False,
                                   error=pa.MotionSupersededError("superseded")))
        assert not page._jog_active and not page._jog_in_flight
    finally:
        page.close()


def test_rotation_step_is_converted_to_radians_and_tool_frame(app):
    page = _page()
    try:
        page.set_online(True)
        page.set_armed(True)
        page.set_cart_supported(True)
        page.frame.setCurrentIndex(1)          # tool
        page.rot_step.setCurrentIndex(2)       # 10°
        steps = []
        page.jog_step.connect(lambda *a: steps.append(a))
        page._jog_press("Z", "rotate", 1)
        axis, kind, amount, frame, _, _ = steps[0]
        assert (axis, kind, frame) == ("Z", "rotate", "tool")
        assert amount == pytest.approx(10 * 3.141592653589793 / 180)
    finally:
        page.close()


def test_stop_button_ends_the_session_when_the_inflight_result_arrives(app):
    page = _page()
    try:
        page.set_online(True)
        page.set_armed(True)
        page.set_cart_supported(True)
        steps, stops = [], []
        page.jog_step.connect(lambda *a: steps.append(a))
        page.stop_req.connect(lambda: stops.append(1))

        page._jog_press("X", "translate", 1)
        gen = page._jog_gen
        page._on_stop_clicked()
        assert stops == [1]
        page.jog_result(gen, TaskResult("点动", False,
                                        error=pa.MotionSupersededError("superseded")))
        assert not page._jog_active
    finally:
        page.close()


def test_disarming_or_disconnect_aborts_without_sending(app):
    for action in ("disarm", "offline", "fault"):
        page = _page()
        try:
            page.set_online(True)
            page.set_armed(True)
            page.set_cart_supported(True)
            stops = []
            page.stop_req.connect(lambda: stops.append(1))
            page._jog_press("X", "translate", 1)
            if action == "disarm":
                page.set_armed(False)
            elif action == "offline":
                page.set_online(False)
            else:
                page.set_fault_blocked(True)
            assert not page._jog_active
            assert stops == [], "断线/失锁/故障时不要补发停止帧"
        finally:
            page.close()


# ------------------------------------------------------------ worker 旁路
def test_worker_reports_cart_capability():
    arm = FakeArm()
    w = SdkWorker(arm_factory=lambda p: arm)
    assert w.cart_supported is None
    w._arm = arm
    assert w.cart_supported is True
    assert w.cart_probe_silent is False
    arm._cart_supported = False
    arm._cart_probe_silent = True
    assert w.cart_supported is False and w.cart_probe_silent is True


def test_takeover_movej_writes_the_frame_without_queueing():
    arm = FakeArm()
    w = SdkWorker(arm_factory=lambda p: arm)
    w._arm = arm
    ok, why = w.takeover_movej([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], 0.25)
    assert ok, why
    cmd, payload, guarded = arm.frames[-1]
    assert cmd == _P.CMD_MOVE_J
    assert guarded is True, "接管 movej 必须保留 SDK 的零重力守卫"
    assert list(_P.unpack_f32s(payload, 0, 7)) == pytest.approx(
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])


def test_stop_jog_uses_the_current_joint_angles():
    arm = FakeArm()
    w = SdkWorker(arm_factory=lambda p: arm)
    w._arm = arm
    w._state = make_state(n=7, q=[0.1 * i for i in range(7)])
    ok, why = w.stop_jog_now()
    assert ok, why
    cmd, payload, _ = arm.frames[-1]
    assert cmd == _P.CMD_MOVE_J
    assert list(_P.unpack_f32s(payload, 0, 7)) == pytest.approx(
        [0.1 * i for i in range(7)])


def test_stop_jog_refuses_without_a_state_frame():
    arm = FakeArm()
    w = SdkWorker(arm_factory=lambda p: arm)
    w._arm = arm
    ok, why = w.stop_jog_now()
    assert not ok and "状态帧" in why


# ------------------------------------------------------------ 主窗口接线
def _win():
    from litetool.gui.main_window import MainWindow
    return MainWindow(settings_mod.Settings.load(None))


def test_main_window_routes_a_jog_step_through_the_motion_gate(app):
    w = _win()
    try:
        arm = FakeArm()
        w.worker._arm = arm
        w.worker._state = make_state(n=7, q=[0.1] * 7)
        w._connected = True
        w._armed = True
        page = w.pages["cart"]
        page.set_online(True)
        page.set_armed(True)
        page.set_cart_supported(True)

        captured = []
        w._submit = lambda name, fn, cb=None: captured.append((name, fn, cb))
        page._jog_press("X", "translate", 1)
        assert len(captured) == 1
        name, fn, cb = captured[0]
        assert name.startswith("点动")

        res = fn(arm)
        assert len(res) == 3
        cb(TaskResult(name, True, value=res))
        assert len(captured) == 2, "按住时必须自动续段"

        page._jog_release()
        assert arm.frames and arm.frames[-1][0] == _P.CMD_MOVE_J, \
            "松手必须受控停止（movej 到当前关节角）"
    finally:
        w.close()


def test_main_window_denies_jog_when_locked(app):
    w = _win()
    try:
        w.worker._arm = FakeArm()
        w.worker._state = make_state(n=7)
        w._connected = True
        w._armed = False
        page = w.pages["cart"]
        page.set_online(True)
        page.set_armed(True)          # 页面自己的按钮误开也不能绕过主窗口
        page.set_cart_supported(True)
        captured = []
        w._submit = lambda name, fn, cb=None: captured.append(name)
        page._jog_press("X", "translate", 1)
        assert captured == []
        assert not page._jog_active
    finally:
        w.close()


def test_main_window_movel_is_gated_and_reads_tcp_afterwards(app):
    w = _win()
    try:
        arm = FakeArm()
        w.worker._arm = arm
        w.worker._state = make_state(n=7)
        w._connected = True
        w._armed = True
        page = w.pages["cart"]
        page.set_online(True)
        page.set_armed(True)
        page.set_cart_supported(True)
        page._tcp = (0.30, 0.0, 0.35, 3.1416, 0.0, 0.0)

        captured = []
        w._submit = lambda name, fn, cb=None: captured.append((name, fn, cb))
        target = (0.31, 0.0, 0.35, 3.1416, 0.0, 0.0)
        w._on_movel(target, 0.1)
        assert len(captured) == 1
        name, fn, cb = captured[0]
        assert name.startswith("movel")
        res = fn(arm)
        cb(TaskResult(name, True, value=res))
        assert any(c[0] == "move_l" for c in arm.calls)
        assert len(captured) == 2
        assert captured[1][0].startswith("读 TCP")
    finally:
        w.close()
