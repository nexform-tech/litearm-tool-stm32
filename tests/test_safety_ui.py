"""意图层安全的 UI 行为 —— 急停如实回显 / 危险命令二次确认 / 解锁自动收回。

背景（2026-09-13 评审）：急停按钮原先丢弃 `emergency_now()` 的返回值，失败时横幅
仍宣称"所有电机已失能" —— 横幅与日志相反，而现场用户只看显眼处。改造后急停改成
**只写不读**的插队通道，于是"帧发出了"与"固件已执行"更是两件事，文案必须分开。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")

from PyQt5.QtWidgets import QApplication, QMessageBox     # noqa: E402

import litearm as pa                              # noqa: E402

from litetool import settings as settings_mod             # noqa: E402
from litetool.gui import main_window as MW                # noqa: E402
from tests.fake_arm import make_state                     # noqa: E402


@pytest.fixture
def win():
    app = QApplication.instance() or QApplication([])
    _ = app
    w = MW.MainWindow(settings_mod.Settings.load(None))
    yield w
    w.close()


def _estop_text(w) -> str:
    return w.estop_lbl.text()


# ---------------------------------------------------------------- 急停
def test_emergency_success_does_not_overclaim(win, monkeypatch):
    """帧发出 ≠ 固件已执行 —— 不能宣称"已失能"，只能请用户目视确认。"""
    monkeypatch.setattr(win.worker, "emergency_now",
                        lambda: (True, "急停帧已发出"))
    win._emergency()
    t = _estop_text(win)
    assert "已失能" not in t, f"只发了帧却宣称已失能: {t}"
    assert "已发出" in t


def test_emergency_failure_does_not_claim_disabled(win, monkeypatch):
    monkeypatch.setattr(win.worker, "emergency_now",
                        lambda: (False, "串口 write timeout"))
    win._emergency()
    t = _estop_text(win)
    assert "已失能" not in t, f"失败却宣称已失能: {t}"
    assert "未发出" in t


def test_emergency_without_connection_does_not_claim_disabled(win):
    """未连接时压根不发帧（走真实 worker 分支）—— 同样不能宣称已失能。"""
    win._emergency()
    t = _estop_text(win)
    assert "已失能" not in t, f"未连接却宣称已失能: {t}"
    assert "未发出" in t


def test_emergency_exception_does_not_claim_disabled(win, monkeypatch):
    def boom():
        raise RuntimeError("driver exploded")

    monkeypatch.setattr(win.worker, "emergency_now", boom)
    win._emergency()
    t = _estop_text(win)
    assert "已失能" not in t, f"异常却宣称已失能: {t}"
    assert "未发出" in t


def test_emergency_relocks_motion(win, monkeypatch):
    monkeypatch.setattr(win.worker, "emergency_now", lambda: (True, "ok"))
    win._connected = True
    win.unlock_cb.setChecked(True)
    assert win._armed
    win._emergency()
    assert not win._armed and not win.unlock_cb.isChecked()


# ---------------------------------------------------------------- 解锁
def test_unlock_refused_when_offline(win):
    assert not win._connected
    win.unlock_cb.setChecked(True)
    assert not win._armed, "未连接时不该解锁"
    assert not win.unlock_cb.isChecked()


def test_fault_relocks(win):
    win._connected = True
    win.unlock_cb.setChecked(True)
    assert win._armed
    win.worker._state = make_state(flags=0x201, joint_fault=0)   # FAULT 位
    win._tick()
    assert not win._armed, "出现故障位后必须收回解锁"
    assert "FAULT" in win.pages["machine"].hint_lbl.text()


def test_disconnect_relocks(win):
    win._connected = True
    win.unlock_cb.setChecked(True)
    win._apply_online(False, "拔线")
    assert not win._armed


# ---------------------------------------------------------------- home 确认
def _spy_submit(win, monkeypatch):
    sent = []
    monkeypatch.setattr(win, "_submit", lambda name, fn, cb=None: sent.append(name))
    return sent


def _arm(win):
    """把窗口置成「已连接 + 已解锁」。

    下面这些用例验的是**确认框 / Δq 判断**，不是运动闸门（闸门由本文件末尾的
    `test_motion_refused_*` 专测）。不先解锁的话闸门会先一步拒掉，测不到想测的东西。
    """
    win._connected = True
    win.unlock_cb.setChecked(True)
    assert win._armed


def test_home_requires_confirmation(win, monkeypatch):
    seen = []
    monkeypatch.setattr(MW.QMessageBox, "question",
                        lambda *a, **k: seen.append(a) or QMessageBox.Cancel)
    sent = _spy_submit(win, monkeypatch)
    _arm(win)
    win._on_ctrl_cmd("home")
    assert seen, "回零未弹确认框"
    assert not sent, "取消后仍下发了回零"


def test_home_confirmed_sends(win, monkeypatch):
    monkeypatch.setattr(MW.QMessageBox, "question", lambda *a, **k: QMessageBox.Ok)
    sent = _spy_submit(win, monkeypatch)
    _arm(win)
    win._on_ctrl_cmd("home")
    assert len(sent) == 1 and "home" in sent[0]


def test_home_confirm_works_without_status_frame(win, monkeypatch):
    """无状态帧时也不能崩（取不到当前角 -> 文案降级）。"""
    monkeypatch.setattr(MW.QMessageBox, "question", lambda *a, **k: QMessageBox.Ok)
    sent = _spy_submit(win, monkeypatch)
    _arm(win)
    assert win.worker.state is None
    win._on_ctrl_cmd("home")
    assert sent


# ---------------------------------------------------------------- clear_faults 确认
def test_clear_faults_lists_axes_and_requires_confirmation(win, monkeypatch):
    """使能态清故障会让被锁轴恢复出力 —— 必须确认，并列出将恢复的轴。"""
    seen = []
    monkeypatch.setattr(MW.QMessageBox, "question",
                        lambda *a, **k: seen.append(a) or QMessageBox.Cancel)
    sent = _spy_submit(win, monkeypatch)
    win.worker._state = make_state(joint_fault=0b0001010)      # J2 / J4
    win._on_ctrl_cmd("clear_faults")
    assert seen, "清故障未弹确认框"
    assert not sent
    text = seen[-1][2]
    assert "J2" in text and "J4" in text, text
    assert "J1" not in text, "未断轴的关节不该被列出"


def test_reset_requires_confirmation(win, monkeypatch):
    seen = []
    monkeypatch.setattr(MW.QMessageBox, "question",
                        lambda *a, **k: seen.append(a) or QMessageBox.Cancel)
    sent = _spy_submit(win, monkeypatch)
    win._on_ctrl_cmd("reset")
    assert seen and not sent


# ---------------------------------------------------------------- Δq 确认
def test_movej_over_threshold_requires_confirm(win, monkeypatch):
    seen = []
    monkeypatch.setattr(MW.QMessageBox, "warning",
                        lambda *a, **k: seen.append(a) or QMessageBox.Cancel)
    sent = _spy_submit(win, monkeypatch)
    _arm(win)
    win.worker._state = make_state(q=[0.0] * 7)
    win._on_movej([1.5, 0, 0, 0, 0, 0, 0], 0.2)
    assert seen and "确认运动幅度" == seen[-1][1]
    assert not sent, "取消后仍下发了运动"


def test_movej_small_delta_sends_directly(win, monkeypatch):
    seen = []
    monkeypatch.setattr(MW.QMessageBox, "warning",
                        lambda *a, **k: seen.append(a) or QMessageBox.Cancel)
    sent = _spy_submit(win, monkeypatch)
    _arm(win)
    win.worker._state = make_state(q=[0.0] * 7)
    win._on_movej([0.05] * 7, 0.2)
    assert not seen, "小幅运动不该弹确认"
    assert len(sent) == 1


def test_move_mit_checks_single_joint_delta(win, monkeypatch):
    seen = []
    monkeypatch.setattr(MW.QMessageBox, "warning",
                        lambda *a, **k: seen.append(a) or QMessageBox.Cancel)
    sent = _spy_submit(win, monkeypatch)
    _arm(win)
    win.worker._state = make_state(q=[0.0] * 7)
    win._on_mit_one(3, 2.0, 0.0, 30.0, 2.0, 0.0)
    assert seen and not sent


# ---------------------------------------------------------------- 零重力委托
def test_zero_g_delegates_to_sdk_keepalive(win, monkeypatch):
    """保活归 SDK 的后台线程 —— GUI 不再自己发心跳帧。"""
    names = []
    monkeypatch.setattr(win, "_submit",
                        lambda name, fn, cb=None: names.append(name))
    _arm(win)
    win._on_zero_g(True)
    assert any("零重力进入" in n for n in names), names
    win._on_zero_g(False)
    assert any("零重力退出" in n for n in names), names


def test_zero_g_button_follows_actual_state(win):
    """固件可能因看门狗/急停自行退出 —— 按钮必须跟实际状态走。"""
    page = win.pages["zerog"]
    page.set_state(True)
    assert page.btn.isChecked()
    assert "退出" in page.btn.text()

    class _Arm:
        zero_g_active = False
        zero_g_error = pa.TransportError("写失败")

    win.worker._arm = _Arm()
    win._sync_zero_g(None)
    assert not page.btn.isChecked()
    assert "写失败" in page.err_lbl.text()


# ---------------------------------------------------------------- 运动闸门（唯一收口）
MOTION_CALLS = [
    ("movej", lambda w: w._on_movej([0.5] * 7, 0.2)),
    ("ready_pose", lambda w: w._on_ready_pose(0.2)),
    ("move_js", lambda w: w._on_move_js([0.5] * 7, [0.0] * 7, None)),
    ("move_mit", lambda w: w._on_mit_one(0, 0.5, 0.0, 30.0, 2.0, 0.0)),
    ("move_mit_all", lambda w: w._on_mit_all([0.5] * 7, [0.0] * 7,
                                             [30.0] * 7, [2.0] * 7, [0.0] * 7)),
    ("movep", lambda w: w._on_movep([0.35, 0.0, 0.30, 0.0, 0.0, 0.0], 0.2)),
    ("home", lambda w: w._on_ctrl_cmd("home")),
    ("zero_g", lambda w: w._on_zero_g(True)),
]


@pytest.mark.parametrize("name,call", MOTION_CALLS, ids=[n for n, _ in MOTION_CALLS])
def test_motion_refused_while_locked(win, monkeypatch, name, call):
    """锁定态下**任何一条**运动命令都不能下发。

    按钮的 setEnabled(False) 只是 UX：本测试绕过控件、直接调处理函数，模拟
    "某页漏禁一个控件 / 代码里直接 emit / 快捷键"这些路径。守卫只做在控件状态上
    就等于没有守卫。
    """
    monkeypatch.setattr(MW.QMessageBox, "question", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(MW.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    sent = _spy_submit(win, monkeypatch)
    win._connected = True
    win.worker._state = make_state(q=[0.0] * 7)
    assert not win._armed
    call(win)
    assert not sent, f"{name} 在锁定态下仍被下发: {sent}"


@pytest.mark.parametrize("name,call", MOTION_CALLS, ids=[n for n, _ in MOTION_CALLS])
def test_motion_refused_while_offline(win, monkeypatch, name, call):
    """未连接时同样拒绝（即便解锁态残留）。"""
    monkeypatch.setattr(MW.QMessageBox, "question", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(MW.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    sent = _spy_submit(win, monkeypatch)
    win._armed = True                 # 直接置位，模拟"解锁态没被收回"的最坏情形
    assert not win._connected
    call(win)
    assert not sent, f"{name} 在未连接时仍被下发: {sent}"


@pytest.mark.parametrize("name,call", MOTION_CALLS, ids=[n for n, _ in MOTION_CALLS])
def test_motion_refused_while_fault_latched(win, monkeypatch, name, call):
    """FAULT/急停锁存中拒绝（锁存时解锁会被收回，但闸门不该依赖那条路径）。"""
    monkeypatch.setattr(MW.QMessageBox, "question", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(MW.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    sent = _spy_submit(win, monkeypatch)
    win._connected = True
    win._armed = True
    win._fault_blocked = True
    call(win)
    assert not sent, f"{name} 在故障锁存中仍被下发: {sent}"


@pytest.mark.parametrize("name,call", MOTION_CALLS, ids=[n for n, _ in MOTION_CALLS])
def test_motion_allowed_when_armed(win, monkeypatch, name, call):
    """反向对照：闸门不能把正常路径也堵死。"""
    monkeypatch.setattr(MW.QMessageBox, "question", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(MW.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    sent = _spy_submit(win, monkeypatch)
    win._connected = True
    win.unlock_cb.setChecked(True)
    win.worker._state = make_state(q=[0.0] * 7)
    assert win._armed
    call(win)
    assert sent, f"{name} 解锁后仍被拒 —— 闸门过严"


def test_zero_g_exit_allowed_while_locked(win, monkeypatch):
    """退出零重力**永远**放行 —— 把用户锁在拖动示教里比放行更危险。"""
    sent = _spy_submit(win, monkeypatch)
    win._connected = True
    win._armed = False
    win._on_zero_g(False)
    assert sent, "锁定态下无法退出零重力"


def test_emergency_uses_bypass_even_with_queued_tasks(win):
    """急停不能被排队任务挡住：它走旁路直接写帧，并把队列清空。"""
    from tests.fake_arm import FakeArm
    arm = FakeArm()
    arm.zero_g_start()
    win.worker._arm = arm
    win.worker.submit("queued-movej", lambda a: None)
    win.worker.submit("queued-params", lambda a: None)

    win._emergency()

    # 帧发出去了（旁路）
    from litearm import _protocol as P
    assert (P.CMD_EMERGENCY_STOP, b"", False) in arm.frames
    # 零重力会话收了
    assert not arm.zero_g_active
    assert any(c[0] == "zero_g_stop" for c in arm.calls)
    # 队列清了
    assert win.worker.drop_pending() == 0


def test_emergency_reports_dropped_and_zero_g_errors(win, monkeypatch):
    """收尾出问题要如实记日志，不能静默。"""
    msgs = []
    monkeypatch.setattr(win, "_log", lambda m, **kw: msgs.append(m))

    class _Arm:
        zero_g_active = True

        def zero_g_stop(self, raise_on_lost=False):
            raise RuntimeError("端口没了")

    win.worker._arm = _Arm()
    win.worker.submit("x", lambda a: None)
    win._emergency()
    assert any("丢弃 1 条排队" in m for m in msgs), msgs
    assert any("零重力会话未能正常收尾" in m for m in msgs), msgs


def test_status_strip_goes_blank_on_disconnect(win):
    """断线后状态条必须留白 —— 20Hz 的 tick 不能把陈旧帧填回去。"""
    win.worker._state = make_state(mode=1, q=[0.5] * 7)
    win._connected = True
    win._tick()
    assert "MOVE_J" in win.strip.mode_lbl.text()

    win.worker._state = None          # 模拟 worker 断线时丢弃快照
    win._apply_online(False, "拔线")
    win._tick()
    assert win.strip.mode_lbl.text() == "—", win.strip.mode_lbl.text()
    assert win.strip.drops_val.text() == "—"
    assert win.strip.fps_val.text() == "—"


def test_status_strip_shows_drops_and_fps_but_not_raw_seq(win):
    """seq 只是帧序号；状态条显示它差分出的丢帧和帧率，原始值去整机页看。"""
    st = make_state(mode=1, q=[0.5] * 7)
    win.strip.update_from(st, drops=3, fps=99.6)
    assert win.strip.drops_val.text() == "3"
    assert win.strip.fps_val.text() == "100"
    assert not hasattr(win.strip, "seq_val")
    assert "seq" in win.strip.drops_val.toolTip()


def test_fault_flag_cleared_on_disconnect(win):
    """离线后故障锁存未知，不该让上一条连接的状态残留着继续挡按钮。"""
    win._connected = True
    win.unlock_cb.setChecked(True)
    win.worker._state = make_state(flags=0x201)
    win._tick()
    assert win._fault_blocked
    win.worker._state = None
    win._apply_online(False, "拔线")
    win._tick()
    assert not win._fault_blocked
    assert not win.pages["machine"]._fault_blocked


# ---------------------------------------------------------------- 幅度闸门不能因"无基线"失效
def test_movej_refused_without_state_baseline(win, monkeypatch):
    """连上后第一帧状态还没到时，movej 必须被拒 —— 不能因为判不了幅度就免检。"""
    monkeypatch.setattr(MW.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    sent = _spy_submit(win, monkeypatch)
    win._connected = True
    win.unlock_cb.setChecked(True)
    win.worker._state = None
    win._on_movej([0.5] * 7, 0.2)
    assert not sent, "无基线却下发了 movej"


def test_mit_refused_without_state_baseline(win, monkeypatch):
    monkeypatch.setattr(MW.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    sent = _spy_submit(win, monkeypatch)
    win._connected = True
    win.unlock_cb.setChecked(True)
    win.worker._state = None
    win._on_mit_one(0, 0.5, 0.0, 30.0, 2.0, 0.0)
    win._on_move_js([0.5] * 7, [0.0] * 7, None)
    assert not sent, "无基线却下发了 MIT/move_js"


def test_movep_reads_tcp_first_when_no_baseline(win, monkeypatch):
    """没有位姿基线 -> 先读 TCP 再判幅度，而不是免检放行。"""
    from litetool.sdk_worker import TaskResult
    submitted, cbs = [], {}

    def submit(name, fn, cb=None):
        submitted.append(name)
        cbs[name] = cb

    monkeypatch.setattr(win, "_submit", submit)
    monkeypatch.setattr(MW.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    win._connected = True
    win.unlock_cb.setChecked(True)
    win.pages["cart"]._tcp = None

    win._on_movep([0.35, 0.0, 0.30, 0.0, 0.0, 0.0], 0.2)
    assert submitted == ["读 TCP（movep 前置）"], submitted

    cbs["读 TCP（movep 前置）"](
        TaskResult("tcp", True, value=(0.3, 0.0, 0.35, 0.0, 0.0, 0.0)))
    assert submitted[-1].startswith("movep"), submitted


def test_movep_refused_when_tcp_unreadable(win, monkeypatch):
    """读不回 TCP 就拒绝下发 —— 没有基线意味着幅度完全未知。"""
    from litetool.sdk_worker import TaskResult
    submitted, cbs = [], {}

    def submit(name, fn, cb=None):
        submitted.append(name)
        cbs[name] = cb

    monkeypatch.setattr(win, "_submit", submit)
    monkeypatch.setattr(MW.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    win._connected = True
    win.unlock_cb.setChecked(True)
    win.pages["cart"]._tcp = None

    win._on_movep([0.35, 0.0, 0.30, 0.0, 0.0, 0.0], 0.2)
    cbs["读 TCP（movep 前置）"](TaskResult("tcp", True, value=None))
    assert not any(n.startswith("movep") for n in submitted), submitted


def test_movep_with_baseline_asks_confirmation_when_over_threshold(win, monkeypatch):
    """有基线且幅度超阈值 -> 弹确认；取消则不下发。"""
    seen = []
    monkeypatch.setattr(MW.QMessageBox, "warning",
                        lambda *a, **k: seen.append(a) or QMessageBox.Cancel)
    sent = _spy_submit(win, monkeypatch)
    win._connected = True
    win.unlock_cb.setChecked(True)
    win.pages["cart"]._tcp = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    win._on_movep([0.5, 0.0, 0.30, 0.0, 0.0, 0.0], 0.2)
    assert seen and not sent


# ---------------------------------------------------------------- 闸门横幅
def test_motion_pages_explain_why_buttons_are_grey(win):
    """灰按钮必须自己解释为什么灰 —— 2026-09-13 用户实测：「回零为什么是灰的」，
    当时界面上没有任何一条线索说明缺的是"勾选顶栏的运动解锁"。"""
    win._connected = True
    for key in ("machine", "joint", "cart", "zerog"):
        page = win.pages[key]
        page.set_online(True)
        page.set_armed(False)
        win.pages["joint"].set_fault_blocked(False)
        win.pages["cart"].set_fault_blocked(False)
        txt = page.banner.text()
        assert "锁定" in txt and "勾选" in txt, f"{key}: {txt!r}"

        page.set_armed(True)
        assert "已解锁" in page.banner.text(), key


def test_banner_reports_offline_and_fault_states(win):
    for key in ("machine", "joint", "cart", "zerog"):
        page = win.pages[key]
        page.set_online(False)
        assert "未连接" in page.banner.text(), key
    win.pages["machine"].set_online(True)
    win.pages["machine"].set_armed(True)
    win.pages["machine"].set_fault_blocked(True)
    assert "锁存" in win.pages["machine"].banner.text()


def test_banner_and_button_agree(win):
    """横幅说"已解锁"而按钮还是灰的（或反过来）是最糟的情况 —— 两者必须同源。"""
    win._connected = True
    m = win.pages["machine"]
    m.set_online(True)
    for armed in (False, True):
        m.set_armed(armed)
        unlocked = "已解锁" in m.banner.text()
        assert m.btn_home.isEnabled() == unlocked, (
            f"armed={armed}: 横幅 {m.banner.text()!r} 与按钮 {m.btn_home.isEnabled()} 不一致")


def test_zero_g_banner_allows_exit_while_locked(win):
    """零重力：进不去时横幅要说锁定，但**退出**永远放行。"""
    z = win.pages["zerog"]
    z.set_online(True)
    z.set_armed(False)
    assert "锁定" in z.banner.text()
    assert not z.btn.isEnabled()
    z.set_state(True)                       # 已在拖动中（armed 可能已被收回）
    assert z.btn.isEnabled(), "锁定态下无法退出零重力"
    assert "已解锁" in z.banner.text()
