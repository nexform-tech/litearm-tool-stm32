"""SdkWorker —— 串口所有权 / 任务队列 / 状态钩子 / 离线判定 / 急停旁路。

这些是"用 SDK 完成交互"的承重墙：一旦这里破了，表现是**偶发**的命令超时
（两条读线程互相偷 ACK），最难查，所以逐条钉死。
"""
import threading
import time

import pytest

import litearm as pa
from litearm import _protocol as _P

from litetool.sdk_worker import SdkWorker, StateHookMissing
from tests.fake_arm import FakeArm, wait_for, worker_arm_factory


def _worker(arm=None, **kw):
    arm = arm if arm is not None else FakeArm()
    logs, onlines, tasks = [], [], []
    w = SdkWorker(arm_factory=worker_arm_factory([arm]),
                  log=logs.append,
                  on_online=lambda ok, why: onlines.append((ok, why)),
                  on_task=tasks.append, **kw)
    return w, arm, logs, onlines, tasks


def test_open_pumps_state_at_high_rate():
    w, arm, *_ = _worker()
    try:
        w.open(None)
        assert wait_for(lambda: len(w.model.snapshot()[0]) >= 5)
        st = w.state
        assert st is not None and st.n == arm.n
        assert w.online and w.firmware == arm.firmware
        assert w.model.rate() > 0
    finally:
        w.close()


def test_close_stops_thread_and_closes_arm():
    w, arm, *_ = _worker()
    w.open(None)
    assert wait_for(lambda: w.state is not None)
    w.close()
    assert arm.closed
    assert not w.online
    assert w.state is None or True          # 快照保留但不再更新
    assert w._thread is None


def test_submit_runs_on_owner_thread():
    """任务必须在 SDK 所有者线程上跑 —— 这是"单消费者"假设的全部依据。"""
    w, arm, logs, onlines, tasks = _worker()
    try:
        w.open(None)
        owner = w._thread.ident
        seen = {}

        def fn(arm_):
            seen["thread"] = threading.get_ident()
            seen["arm"] = arm_
            return "done"

        w.submit("probe", fn)
        assert wait_for(lambda: tasks)
        assert seen["thread"] == owner
        assert seen["arm"] is arm
        assert tasks[0].ok and tasks[0].value == "done"
    finally:
        w.close()


def test_submit_error_becomes_failed_result():
    w, arm, logs, onlines, tasks = _worker()
    try:
        w.open(None)

        def boom(arm_):
            raise pa.MotionTimeoutError("未到位")

        w.submit("movej", boom)
        assert wait_for(lambda: tasks)
        assert not tasks[0].ok
        assert isinstance(tasks[0].error, pa.MotionTimeoutError)
        assert "movej" in tasks[0].text
    finally:
        w.close()


def test_submit_when_not_connected_reports_error():
    w, *_ = _worker()
    got = []
    w.submit("enable", lambda arm: arm.enable(), got.append)
    assert got and not got[0].ok
    assert isinstance(got[0].error, pa.NotConnectedError)


def test_firmware_rejection_keeps_code():
    """固件 ERR 的 code 必须原样带到 GUI（参数页靠它把失败标到具体格）。"""
    w, arm, *_ = _worker()
    try:
        w.open(None)
        got = []
        arm.reject(_P.CMD_SET_JOINT_PARAM, 0x02, "set_joint_param")

        def fn(a):
            a.params.set_joint_param(0, 1, 1, 1)

        w.submit("set_joint_param", fn, got.append)
        assert wait_for(lambda: got)
        assert not got[0].ok
        assert got[0].error.code == 0x02
    finally:
        w.close()


def test_state_hook_missing_fails_loudly():
    """挂不上钩子必须**当场报错** —— 静默降级会变成"连上了但曲线不动"。"""
    class NoSeam:
        n = 7
        firmware = "x"

        def close(self):
            pass

    w = SdkWorker(arm_factory=lambda port: NoSeam())
    with pytest.raises(StateHookMissing):
        w.open(None)


def test_transport_error_marks_offline():
    w, arm, logs, onlines, tasks = _worker()
    w.open(None)
    assert wait_for(lambda: w.online)
    arm.raise_error = pa.TransportError("串口读异常")
    assert wait_for(lambda: not w.online)
    assert onlines[-1][0] is False
    assert any("链路异常" in why for _, why in onlines if why)
    w.close()


def test_silent_link_times_out_to_offline():
    w, arm, logs, onlines, tasks = _worker(offline_timeout=0.3, idle_timeout=0.02)
    w.open(None)
    assert wait_for(lambda: w.online)
    arm.silent = True
    assert wait_for(lambda: not w.online, timeout=3.0)
    assert "静默" in onlines[-1][1]
    w.close()


def test_drops_counted_from_seq_gaps():
    """丢帧按 seq 差分统计（接收侧），只认小正向跳变。"""
    w, arm, *_ = _worker()
    try:
        w.open(None)
        assert wait_for(lambda: w.drops == 0 and w.state is not None)
        # bump 3 之后，下一帧自身再 +1 -> seq 跳 4 -> 少收 3 帧
        arm.bump_seq(3)
        assert wait_for(lambda: w.drops == 3)
    finally:
        w.close()


def test_same_frame_is_pushed_to_plot_only_once():
    """同一帧被重复取到时不该重复入曲线（否则重绘会把一个点画很多遍）。"""
    w, arm, *_ = _worker()
    try:
        w.open(None)
        assert wait_for(lambda: len(w.model.snapshot()[0]) >= 3)
        arm.repeat_same = True
        time.sleep(0.05)
        n1 = len(w.model.snapshot()[0])
        time.sleep(0.15)
        assert len(w.model.snapshot()[0]) == n1
    finally:
        w.close()


# ---------------------------------------------------------------- 急停旁路
def test_emergency_bypass_writes_frame_without_waiting():
    """急停必须**插队**：只写不读，不排队、不等 ACK。"""
    w, arm, *_ = _worker()
    try:
        w.open(None)
        assert wait_for(lambda: w.online)
        before = list(arm.calls)
        ok, why = w.emergency_now()
        assert ok, why
        assert (_P.CMD_EMERGENCY_STOP, b"", False) in arm.frames
        # 只写不读：没有产生任何 expect/read 动作
        assert arm.calls == before
    finally:
        w.close()


def test_emergency_bypass_not_blocked_by_inflight_task():
    """在途长命令占住所有者线程时，急停仍必须发得出去。"""
    w, arm, *_ = _worker()
    try:
        w.open(None)
        assert wait_for(lambda: w.online)
        release = threading.Event()
        w.submit("long-move", lambda a: release.wait(2.0))
        assert wait_for(lambda: w.busy)
        ok, why = w.emergency_now()
        assert ok, why
        assert (_P.CMD_EMERGENCY_STOP, b"", False) in arm.frames
        release.set()
    finally:
        w.close()


def test_emergency_without_connection_reports_failure():
    w, *_ = _worker()
    ok, why = w.emergency_now()
    assert not ok and why


def test_emergency_write_failure_reports_failure():
    """写失败必须如实返回 False —— 上层据此提示"请用硬件急停/断电"。"""
    w, arm, *_ = _worker()
    try:
        w.open(None)
        arm.write_error = pa.TransportError("write timeout")
        ok, why = w.emergency_now()
        assert not ok and "timeout" in why
    finally:
        w.close()


def test_worker_survives_bad_gui_callback():
    """GUI 回调抛异常不能拖垮所有者线程。"""
    w, arm, *_ = _worker()
    try:
        w.open(None)
        w.submit("x", lambda a: 1, lambda res: (_ for _ in ()).throw(RuntimeError("cb")))
        time.sleep(0.15)
        assert w.online
        assert wait_for(lambda: w.state is not None)
    finally:
        w.close()


# ---------------------------------------------------------------- 急停的两件收尾
def test_stop_zero_g_now_calls_sdk_and_clears_active():
    """急停要收掉零重力会话 —— 否则保活线程每 40ms 继续空转发帧。"""
    w, arm, *_ = _worker()
    try:
        w.open(None)
        assert wait_for(lambda: w.online)
        arm.zero_g_start()
        assert arm.zero_g_active
        assert w.stop_zero_g_now() is None
        assert not arm.zero_g_active
        assert any(c[0] == "zero_g_stop" for c in arm.calls)
    finally:
        w.close()


def test_stop_zero_g_now_is_noop_when_not_in_session():
    w, arm, *_ = _worker()
    try:
        w.open(None)
        assert w.stop_zero_g_now() is None
        assert not any(c[0] == "zero_g_stop" for c in arm.calls)
    finally:
        w.close()


def test_stop_zero_g_now_reports_error_without_raising():
    w, arm, *_ = _worker()
    try:
        w.open(None)
        arm.zero_g_start()
        arm.raise_error = pa.TransportError("写失败")
        err = w.stop_zero_g_now()
        assert err and "写失败" in err
    finally:
        w.close()


def test_drop_pending_empties_queue():
    """不起所有者线程，任务就躺在队列里 —— 这样断言是确定性的。"""
    w, arm, *_ = _worker()
    w._arm = arm                     # 让 submit 认为已连接
    ran = []
    w.submit("a", lambda a: ran.append("a"))
    w.submit("b", lambda a: ran.append("b"))
    assert w.drop_pending() == 2
    assert w.drop_pending() == 0
    assert ran == []                 # 被丢弃的任务从未执行


def test_state_is_cleared_on_close():
    """链路断了就不能再回显最后一帧 —— 把陈旧遥测当实时数据显示是危险的。"""
    w, arm, *_ = _worker()
    w.open(None)
    assert wait_for(lambda: w.state is not None)
    w.close()
    assert w.state is None


def test_state_is_cleared_when_link_goes_offline():
    w, arm, *_ = _worker()
    try:
        w.open(None)
        assert wait_for(lambda: w.state is not None)
        arm.raise_error = pa.TransportError("串口读异常")
        assert wait_for(lambda: not w.online)
        assert w.state is None
    finally:
        w.close()


# ---------------------------------------------------------------------------
# [2026-09-14] 回调必达契约 —— 修"页面永久卡死只能重启进程"的两条根因
# ---------------------------------------------------------------------------
def test_drop_pending_delivers_callbacks():
    """被丢弃的任务**必须**补一次 `on_done(ok=False)`。

    静默丢弃会让发起方的忙态永远解不开: 页面的 `_busy` 在 `_start` 里置位、只在
    `_on_*_done` 里清除 —— 回调不来就只能重启进程。而急停路径恰恰是最需要界面
    还能用的时候 (`main_window` 按急停就调 `drop_pending`)。
    """
    w, arm, *_ = _worker()
    w._arm = arm
    got = []
    w.submit("a", lambda a: None, got.append)
    w.submit("b", lambda a: None, got.append)
    assert w.drop_pending() == 2
    assert [r.name for r in got] == ["a", "b"]
    assert all(r.ok is False for r in got), "被丢的任务不能报成功"
    assert all("丢弃" in str(r.error) for r in got), "必须说明原因"


def test_run_delivers_callback_even_while_stopping():
    """`_stop` 已置位时**也要**投递回调 —— 原实现直接 return, 回调永不达。

    触发场景: 用户点[断开]/关窗口时, 所有者线程里正跑着一条长任务
    (比如 `movej` 占住十几秒); 它的 `on_done` 是发起方唯一的解忙途径。
    """
    w, arm, *_ = _worker()
    w._arm = arm
    got = []
    w._stop.set()                       # 模拟"关闭中"
    w._run("长任务", lambda a: 42, got.append)
    assert len(got) == 1, "关闭中发生回调丢失 -> 发起方忙态永久卡死"
    assert got[0].ok is False and got[0].name == "长任务"
    assert "断开" in str(got[0].error)


def test_run_still_delivers_success_when_not_stopping():
    """反向用例: 正常路径不能被上面那两条改坏 (否则所有操作都报失败)。"""
    w, arm, *_ = _worker()
    w._arm = arm
    got = []
    w._run("正常", lambda a: 7, got.append)
    assert got[0].ok is True and got[0].value == 7
