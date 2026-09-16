"""安装方向页 —— 换算正确性 + 三道闸（离线，无需硬件）。

页面策略是**硬拦**（armed / 状态未知时不发任何帧），比参数页的"确认框放行"更严 ——
所以这里的核心断言大多是 **`rec.sent == []`**（一帧都没发），而不只是"弹了窗"。
"""
from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from litetool.gui.pages import installation_page as IP  # noqa: E402
from tests.fake_arm import FakeArm, make_state  # noqa: E402

G0 = 9.81


# ---------------------------------------------------------------- 工具
class _Res:
    """替 `sdk_worker.TaskResult`（只需要 ok/value/error 三个字段）。"""

    def __init__(self, ok, value=None, error=None):
        self.ok, self.value, self.error = ok, value, error


class _Recorder:
    """替页面的 `submit`。

    ⚠ **必须始终回调 `on_done`** —— 真实 `SdkWorker` 的契约是"回调必达"（未连接也会
    合成一个 `ok=False`）。替身若不回调，页面的 `_busy` 会永久卡住，后面所有 `_pre_op`
    都被"忙"挡住 —— 那会掩盖真正的闸门行为（本文件第一版就栽在这）。
    """

    def __init__(self, arm=None):
        self.sent = []
        self.arm = arm

    def __call__(self, name, fn, on_done=None):
        self.sent.append(name)
        if on_done is None:
            return
        if self.arm is None:
            on_done(_Res(False, None, RuntimeError("未连接")))
            return
        try:
            on_done(_Res(True, fn(self.arm)))
        except BaseException as e:      # noqa: BLE001 - 模拟 worker 的异常回传
            on_done(_Res(False, None, e))


def _armed_arm() -> FakeArm:
    """已读到基线（失能）的假臂 —— 闸门用例的前置。"""
    arm = FakeArm()
    arm.ff_scalar[(6, 0)] = 0.0
    arm.ff_scalar[(6, 1)] = 0.0
    arm.ff_scalar[(6, 2)] = -G0
    return arm


#: ⚠ 必须用模块级变量**强引用**住 QApplication。写成 `QApplication.instance() or
#: QApplication([])` 而不接住返回值时，新建的 app 会被 GC 掉，随后 QWidget 构造就是
#: `QWidget: Must construct a QApplication before a QWidget` -> qFatal -> SIGABRT
#: （在 pytest 里表现为 "Fatal Python error: Aborted"，不是可捕获的异常）。
_APP = None


def _app():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _page(arm=None, st=None) -> tuple:
    _app()
    p = IP.InstallationPage()
    rec = _Recorder(arm)
    p.set_submit(rec)
    p.set_online(True)
    p.update_from(st if st is not None else make_state(flags=0))   # 默认：失能
    return p, rec


def _dialogs(monkeypatch, answer=QMessageBox.Ok):
    """拦掉所有 QMessageBox.warning，返回记录到的 (title, text) 列表。"""
    calls = []

    def fake(_parent, title, text, *a, **kw):
        calls.append((title, text))
        return answer

    monkeypatch.setattr(IP.QMessageBox, "warning", fake)
    return calls


def _read_ok(p, rec):
    """走一遍"读当前"并确认成功（后续用例的前置）。"""
    p._on_read()
    assert p._device_synced, "读当前应当成功"


# ---------------------------------------------------------------- 换算
def test_presets_agree_with_the_conversion_formula():
    """预设表里写死的向量必须等于公式算出来的 —— 防"改了公式没改表"。"""
    for name, rpy, vec in IP.PRESETS:
        got = IP.gravity_from_rpy(rpy)
        assert all(abs(got[i] - vec[i]) < 1e-6 for i in range(3)), \
            f"{name}: 表 {vec} != 公式 {got}"


@pytest.mark.parametrize("name,vec", [
    ("正装", (0.0, 0.0, -G0)),
    ("倒装", (0.0, 0.0, G0)),
    ("侧装 +x", (G0, 0.0, 0.0)),
    ("侧装 -x", (-G0, 0.0, 0.0)),
    ("侧装 +y", (0.0, G0, 0.0)),
    ("侧装 -y", (0.0, -G0, 0.0)),
])
def test_preset_vectors(name, vec):
    """六个装向的向量值 —— 同时钉住"哪个方向是哪个"（用户最容易搞反的地方）。"""
    table = {n: v for n, _r, v in IP.PRESETS}
    assert table[name] == vec


def test_rpy_conversion_by_axis():
    """绕单轴 90°/180° —— 与 R(rpy)ᵀ·(0,0,-9.81) 逐项核对。"""
    # 绕 x (roll)
    assert IP.gravity_from_rpy((math.pi / 2, 0, 0)) == pytest.approx((0, -G0, 0), abs=1e-9)
    assert IP.gravity_from_rpy((-math.pi / 2, 0, 0)) == pytest.approx((0, G0, 0), abs=1e-9)
    # 绕 y (pitch)
    assert IP.gravity_from_rpy((0, math.pi / 2, 0)) == pytest.approx((G0, 0, 0), abs=1e-9)
    assert IP.gravity_from_rpy((0, -math.pi / 2, 0)) == pytest.approx((-G0, 0, 0), abs=1e-9)
    # 绕 z (yaw) 不改变重力方向
    for y in (0.3, math.pi / 2, math.pi):
        assert IP.gravity_from_rpy((0, 0, y)) == pytest.approx((0, 0, -G0), abs=1e-9)


def test_conversion_preserves_magnitude():
    for rpy in ((0.4, -0.7, 1.2), (math.pi / 3, math.pi / 5, -2.0), (0, 0, 0)):
        assert IP._mag(IP.gravity_from_rpy(rpy)) == pytest.approx(G0, abs=1e-9)


def test_label_of_recognises_presets_and_custom():
    assert IP._label_of((0.0, 0.0, -G0)) == "正装"
    assert IP._label_of((-G0, 0.0, 0.0)) == "侧装 -x"
    assert IP._label_of((1.0, 2.0, 3.0)) == "(自定义)"


# ---------------------------------------------------------------- 闸门
def test_read_required_before_apply(monkeypatch):
    """未 [读当前] → 拒下发，且**一帧不发**。"""
    calls = _dialogs(monkeypatch)
    p, rec = _page()
    p._on_apply()
    assert rec.sent == [], "未读当前就下发 —— 应一帧不发"
    assert any("先读取设备参数" in t for t, _ in calls) or "读当前" in p.status.text()


def test_armed_is_hard_blocked(monkeypatch):
    """使能态 → 弹窗 + 一帧不发（**不是**确认框放行）。"""
    calls = _dialogs(monkeypatch)
    p, rec = _page(arm=_armed_arm(), st=make_state(flags=0x200))     # bit9 = enabled
    p._on_read()
    rec.sent.clear()
    assert p._st is not None and p._st.enabled
    p._on_apply()
    assert rec.sent == [], "使能态必须硬拦（本固件 1.5.3 也会回 0x04，但旧固件会默默写）"
    assert any("须先失能" in t for t, _ in calls)


def test_unknown_state_is_blocked(monkeypatch):
    """状态没到手 == 不知道，不等于安全 —— 同样硬拦。"""
    calls = _dialogs(monkeypatch)
    p, rec = _page(arm=_armed_arm())
    p._on_read()
    rec.sent.clear()
    p.update_from(None)          # 离线喂 None
    p._on_apply()
    assert rec.sent == [], "状态未知时必须硬拦"
    assert any("须先失能" in t for t, _ in calls)


def test_offline_none_clears_stale_enabled_snapshot(monkeypatch):
    """离线喂 None 后，别拿上一条连接的 enabled 快照放行。"""
    _dialogs(monkeypatch)
    p, rec = _page(arm=_armed_arm(), st=make_state(flags=0x200))     # 先给一个"使能"快照
    assert p._st.enabled
    p.update_from(None)
    assert p._st is None
    p._on_read()
    rec.sent.clear()
    p._on_apply()
    assert rec.sent == []


def test_disabled_and_synced_allows_apply(monkeypatch):
    """失能 + 已读基线 → 真的把三条分量发出去。"""
    _dialogs(monkeypatch)
    p, rec = _page(arm=_armed_arm(), st=make_state(flags=0))
    _read_ok(p, rec)
    rec.sent.clear()
    p._on_apply()
    assert rec.sent == ["安装方向[下发安装方向]"]


def test_magnitude_mismatch_needs_confirm(monkeypatch):
    """|g| 偏离 9.81 超 1% → 二次确认；Cancel 则不发。"""
    _dialogs(monkeypatch, answer=QMessageBox.Cancel)
    p, rec = _page(arm=_armed_arm(), st=make_state(flags=0))
    _read_ok(p, rec)
    for s in p._g_spins:                 # 三个都填 9.81 → |g| = 16.99
        s.setValue(G0)
    rec.sent.clear()
    p._on_apply()
    assert rec.sent == [], "模长偏离未确认时不该发"


def test_magnitude_mismatch_confirmed_goes_through(monkeypatch):
    _dialogs(monkeypatch, answer=QMessageBox.Ok)
    p, rec = _page(arm=_armed_arm(), st=make_state(flags=0))
    _read_ok(p, rec)
    for s in p._g_spins:
        s.setValue(G0)
    rec.sent.clear()
    p._on_apply()
    assert rec.sent == ["安装方向[下发安装方向]"]


def test_save_also_requires_disabled(monkeypatch):
    calls = _dialogs(monkeypatch)
    p, rec = _page(arm=_armed_arm(), st=make_state(flags=0x200))
    p._on_read()
    rec.sent.clear()
    p._on_save()
    assert rec.sent == []
    assert any("须先失能" in t for t, _ in calls)


# ---------------------------------------------------------------- 端到端渲染
def test_read_fills_ui_from_device():
    arm = FakeArm()
    arm.ff_scalar[(6, 0)] = 0.0
    arm.ff_scalar[(6, 1)] = 0.0
    arm.ff_scalar[(6, 2)] = -G0
    p, _rec = _page(arm=arm, st=make_state(flags=0))
    p._on_read()
    assert p._device_synced
    assert p._vector() == pytest.approx((0.0, 0.0, -G0), abs=1e-6)
    assert "正装" in p.lbl_dev.text()


def test_firmware_rejection_shows_err_text(monkeypatch):
    """固件回 ERR{0x28,0x04} → UI 显示中文文案，不误报成功。"""
    _dialogs(monkeypatch)
    arm = FakeArm()
    p, rec = _page(arm=arm, st=make_state(flags=0))
    _read_ok(p, rec)
    for _ in range(3):
        arm.reject(0x28, 0x04, "set_ff_scalar")
    p._on_apply()
    txt = p.status.text()
    assert "失败" in txt
    assert "disable" in txt.lower() or "失能" in txt, f"应显示 err_text(0x04) 文案: {txt}"


def test_readback_mismatch_is_reported(monkeypatch):
    """写进去了但回读不一致 → 必须报出来，不能静默当成功。"""
    _dialogs(monkeypatch)
    arm = FakeArm()
    p, rec = _page(arm=arm, st=make_state(flags=0))
    _read_ok(p, rec)
    # 让写入变成 no-op：回读仍是旧值 -> 与写入不一致
    arm.set_ff_scalar = lambda item, sub, value: None      # type: ignore[assignment]
    for s in p._g_spins:
        s.setValue(G0 / 2)                                  # 与设备旧值不同
    p._on_apply()
    assert "不一致" in p.status.text() or "失败" in p.status.text()


def test_successful_apply_reports_consistent_readback(monkeypatch):
    """正常路径：读回一致 + |g| 正确 + G(q) 自比结论都进 status。"""
    _dialogs(monkeypatch)
    arm = FakeArm()
    arm.state = make_state(flags=0)
    p, rec = _page(arm=arm, st=make_state(flags=0))
    _read_ok(p, rec)
    p._apply_preset((0.0, 0.0, G0), (0.0, math.pi, 0.0))    # 倒装（|g| 仍 = 9.81）
    p._on_apply()
    txt = p.status.text()
    assert "✅" in txt, f"读回一致应打 ✅: {txt}"
    assert "G(q)" in txt, f"应含 G(q) 前后自比结论: {txt}"


# ---------------------------------------------------------------- 界面契约
def test_page_has_no_motion_gate():
    """写参数**不是**运动命令 —— 不该占用运动解锁/故障锁存那套接口。"""
    p, _ = _page()
    for name in ("set_armed", "set_fault_blocked"):
        assert not hasattr(p, name), f"本页不该实现 {name}（那是运动页的契约）"


def test_preset_click_updates_vector_without_sending():
    p, rec = _page()
    p._preset_btns["倒装"].click()
    assert p._vector() == pytest.approx((0.0, 0.0, G0), abs=1e-6)
    assert rec.sent == [], "选预设只是填控件，不该下发"
    assert p.lbl_rpy_state.text() == ""


def test_editing_vector_marks_custom():
    p, rec = _page()
    p._preset_btns["正装"].click()
    p._g_spins[0].setValue(1.0)
    assert p.lbl_rpy_state.text() == "(自定义)"
    assert rec.sent == []
