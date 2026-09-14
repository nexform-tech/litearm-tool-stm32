"""参数页安全流测试 —— 审查修复覆盖（2026-09-13 改接 pylitearm_stm32 后重验）:

- Critical-1: 未成功"刷新当前"前禁下发全局/全部 (默认 spin 值不盲发)
- Critical-4: 导入/整套下发同样必须先刷新
- Important-2: enable 态控制律写二次确认; 0x23 限位写前当前 q 越界拒绝
- Important-3: `send_global` 的 ff_mask(0x27) 只发一次 —— 见 test_params_io.py
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

import yaml
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from litetool import param_catalog as C
from litetool.gui.pages import params_page as PP

REPO = Path(__file__).resolve().parents[1]
ZERO_Q = [0.0] * 7


def load_snap():
    raw = yaml.safe_load((REPO / "templates" / "params_example.yaml").read_text("utf-8"))
    return C.normalize_snapshot(raw)


class _J:
    def __init__(self, q):
        self.q = q


class _St:
    """够用的 RobotState 桩：限位校验与 enable 态确认只读这三个字段。"""

    def __init__(self, qs=ZERO_Q, enabled=False):
        self.joints = [_J(q) for q in qs]
        self.n = len(qs)
        self.enabled = enabled


class _Recorder:
    """注入给页面的 `submit`：只记录，不真的下发。"""

    def __init__(self):
        self.sent = []

    def __call__(self, name, fn, on_done=None):
        self.sent.append(name)


def _page(snap=None, st=None):
    _app = QApplication.instance() or QApplication([])
    pg = PP.ParamsPage()
    rec = _Recorder()
    pg.set_submit(rec)
    pg.set_online(True)
    pg.update_from(st if st is not None else _St())
    if snap is not None:
        pg._on_refreshed(snap)          # 刷新成功 -> 允许下发
    return _app, pg, rec


# ---------------- Critical-1: 未刷新拒下发 ----------------
def test_send_disabled_until_refresh():
    _app, pg, rec = _page(snap=None, st=_St())
    assert pg._device_synced is False
    assert not pg.btn_apply_row.isEnabled()
    assert not pg.btn_apply_all.isEnabled()
    assert not pg.btn_global.isEnabled()
    assert pg.btn_refresh.isEnabled()
    # 即便直接调 handler 也拒绝（不触碰默认控件值）
    pg._on_apply_global()
    assert "未读取设备数据" in pg.status.text()
    pg._apply_rows_selected(all_rows=True)
    assert "未读取设备数据" in pg.status.text()
    assert not rec.sent
    # 刷新成功后才放行
    pg._on_refreshed(load_snap())
    assert pg._device_synced is True
    assert pg.btn_apply_all.isEnabled() and pg.btn_global.isEnabled()


# ---------------- Important-2a: enable 态写二次确认 ----------------
def test_enabled_write_requires_confirm(monkeypatch):
    calls = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg, rec = _page(snap=load_snap(), st=_St(ZERO_Q, enabled=True))
    pg._apply_rows_selected(all_rows=True)
    assert calls, "enable 态应弹确认"
    assert "臂已使能" in calls[-1][1]
    assert "已取消" in pg.status.text()
    assert not rec.sent


def test_ffmask_write_when_enabled_requires_confirm(monkeypatch):
    calls = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg, rec = _page(snap=load_snap(), st=_St(ZERO_Q, enabled=True))
    pg._on_apply_global()
    assert calls and "臂已使能" in calls[0][1]
    assert not rec.sent


# ---------------- Important-2b: 0x23 限位写前当前 q 越界拒绝 ----------------
def test_limits_write_rejected_when_q_outside(monkeypatch):
    calls = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg, rec = _page(snap=load_snap(), st=_St(ZERO_Q, enabled=False))
    ri = next(i for i, p in enumerate(C.JOINT_PARAMS) if p.key == "q_max")
    pg.table.item(ri, 1 + 1).setText("-0.5")     # J2 当前 q=0 不在新上限内
    pg._apply_rows_selected(all_rows=True)
    assert any("限位" in a[1] for a in calls)
    assert "J2" in pg.status.text()
    assert not rec.sent


def test_limits_write_allowed_when_q_inside(monkeypatch):
    calls = []
    starts = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg, rec = _page(snap=load_snap(), st=_St(ZERO_Q, enabled=False))
    monkeypatch.setattr(pg, "_start", lambda *a, **k: starts.append(a))
    pg._apply_rows_selected(all_rows=True)
    assert not any((a[1] or "").startswith("限位写被拒绝") for a in calls)
    assert starts, "合法限位应放行到 _start"


# ---------------- Critical-4: 导入/整套下发也必须先刷新 ----------------
def test_full_snapshot_apply_requires_device_sync(monkeypatch):
    """导入路径若绕过 `_device_synced`，diff 对话框的"设备当前值"列会全空，
    用户无法核对将被覆盖的真实值 —— 与"下发全部/全局"同一道闸。"""
    monkeypatch.setattr(PP.QMessageBox, "warning", lambda *a, **k: QMessageBox.Cancel)
    _app, pg, rec = _page(snap=None, st=_St())
    assert pg._device_synced is False
    pg._apply_full_snapshot(load_snap(), flash_save=False)
    assert "未读取设备数据" in pg.status.text()
    assert not rec.sent, f"未刷新却已下发: {rec.sent}"


def test_full_snapshot_apply_allowed_after_refresh(monkeypatch):
    monkeypatch.setattr(PP.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    _app, pg, rec = _page(snap=load_snap(), st=_St())
    assert pg._device_synced is True
    started = []
    monkeypatch.setattr(pg, "_start", lambda *a, **k: started.append(a))
    pg._apply_full_snapshot(load_snap(), flash_save=False)
    assert started, "刷新成功后导入仍被拒 —— 闸门过严"
    assert "未读取设备数据" not in pg.status.text()


# ---------------- 断链/离线下页面不可操作 ----------------
def test_offline_disables_ops():
    _app = QApplication.instance() or QApplication([])
    pg = PP.ParamsPage()
    pg.set_submit(_Recorder())
    pg.set_online(False)
    assert not pg.btn_refresh.isEnabled()
    pg.set_online(True)
    assert pg.btn_refresh.isEnabled()


# ---------------- 恢复出厂 (0x36) ----------------
def _confirm_all(monkeypatch, answer=QMessageBox.Ok):
    monkeypatch.setattr(PP.QMessageBox, "warning", lambda *a, **k: answer)


def test_factory_reset_requires_double_confirmation(monkeypatch):
    """恢复出厂是二阶确认：第一问取消就什么都不做。"""
    calls = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg, rec = _page(snap=load_snap(), st=_St())
    pg._on_reset_factory()
    assert len(calls) == 1 and not rec.sent

    # 第二问取消 -> 同样不下发
    calls.clear()
    answers = iter((QMessageBox.Ok, QMessageBox.Cancel))

    def answer(*a, **k):
        calls.append(a)
        return next(answers)

    monkeypatch.setattr(PP.QMessageBox, "warning", answer)
    pg._on_reset_factory()
    assert len(calls) == 2 and not rec.sent


def test_factory_reset_sends_and_invalidates_baseline(monkeypatch):
    """成功后必须作废设备基线 —— 否则用户会拿旧值把出厂参数又改回去。"""
    _confirm_all(monkeypatch)
    _app, pg, rec = _page(snap=load_snap(), st=_St())
    assert pg._device_synced is True
    pg._on_reset_factory()
    assert any("恢复出厂" in n for n in rec.sent)
    pg._on_factory_done(True, "已恢复出厂默认")
    assert pg._device_synced is False
    assert pg._baseline is None and pg._synced == {} and pg._synced_glob is None
    assert "重新 [刷新当前]" in pg.status.text()
    assert not pg.btn_apply_all.isEnabled()


# ---------------- 台架 1J：参数页不能整页挂掉 ----------------
class _BenchSt(_St):
    def __init__(self):
        super().__init__([0.0])
        self.n = 1


def _bench_snap():
    from tests.fake_arm import FakeArm
    from litetool import params_io as PIO
    return PIO.read_snapshot(FakeArm(n=1))


def test_bench_page_shows_missing_columns_readonly():
    _app = QApplication.instance() or QApplication([])
    pg = PP.ParamsPage()
    pg.set_submit(_Recorder())
    pg.set_online(True)
    pg.update_from(_BenchSt())
    pg._on_refreshed(_bench_snap())

    assert pg._device_synced is True
    ri = next(i for i, p in enumerate(C.JOINT_PARAMS) if p.key == "kp")
    assert pg.table.item(ri, 1).text() != "—"        # J1 有数
    assert pg.table.item(ri, 2).text() == "—"        # J2 无此关节
    assert not (pg.table.item(ri, 2).flags() & Qt.ItemIsEditable)


def test_bench_matrix_skips_missing_joints(monkeypatch):
    monkeypatch.setattr(PP.QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    _app = QApplication.instance() or QApplication([])
    pg = PP.ParamsPage()
    rec = _Recorder()
    pg.set_submit(rec)
    pg.set_online(True)
    pg.update_from(_BenchSt())
    pg._on_refreshed(_bench_snap())

    mat = pg._ui_matrix()                    # 不该因 J2..J7 是 None 而抛
    assert len(mat) == C.NUM_JOINTS
    assert pg._present_joints(mat) == [0]

    ops = PP.ParamsPage._build_row_ops(set(PP.JOINT_KEYS), mat)
    for op in ops:
        assert all(j == 0 for (_k, j, _v) in op["cells"]), op["cells"]


def test_bench_joint_limits_check_skips_missing_joints():
    _app = QApplication.instance() or QApplication([])
    pg = PP.ParamsPage()
    pg.set_submit(_Recorder())
    pg.set_online(True)
    pg.update_from(_BenchSt())
    pg._on_refreshed(_bench_snap())
    mat = pg._ui_matrix()
    assert pg._limits_error(mat) is None


# ---------------- 无基线不免检（与运动侧同一条原则） ----------------
def test_limits_write_refused_without_current_q():
    """拿不到当前 q 就不许写限位 —— 限位一旦即刻越限会直接 POS_VIOL/FAULT。"""
    _app, pg, rec = _page(snap=load_snap(), st=_St())
    pg._st = None                       # 状态帧暂时没到手
    mat = pg._ui_matrix()
    assert pg._limits_error(mat) is not None


def test_enabled_write_confirms_when_enable_state_unknown(monkeypatch):
    """使能态未知时也弹确认 —— "不知道"不等于"安全"。"""
    calls = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg, rec = _page(snap=load_snap(), st=_St())
    pg._st = None
    # 走全局下发：不含 0x23 限位写，因此先撞上的是使能态确认（限位校验优先级更高）
    pg._on_apply_global()
    assert calls and "臂已使能" in calls[0][1]
    assert not rec.sent


# ---------------- [2026-09-14] 忙态不残留 (死锁修复) ----------------
def test_busy_is_cleared_on_disconnect():
    """断开会让在途任务的回调失效 ⇒ 页面必须自己清忙态, 否则按钮全灰只能重启进程。

    真机路径: 点[刷新当前](页面置忙) → 拔线/崩连接 → `set_online(False)`。
    修 `SdkWorker` 的回调必达之后, 正常情况下回调会来解忙; 这里是第二道保险
    (回调要过一次 Qt 事件循环, 可能晚于离线事件到达)。
    """
    _app, pg, rec = _page(snap=load_snap(), st=_St())
    pg._busy = True                      # 模拟"任务在途"
    assert not pg._can_run()
    pg.set_online(False)
    assert pg._busy is False, "离线必须清忙态 —— 否则重连后页面仍是灰的"
    pg.set_online(True)
    assert pg._can_run(), "重连后应恢复可用"


def test_busy_is_cleared_on_new_session():
    """换会话(重连注入新 submit)同理: 旧会话的回调不会再来本页。"""
    _app, pg, rec = _page(snap=load_snap(), st=_St())
    pg._busy = True
    pg.set_submit(rec)                   # 主窗口重连时会重新注入
    assert pg._busy is False


def test_emergency_drop_pending_keeps_page_usable():
    """急停 → `drop_pending()` 丢任务 → 被丢的任务必须回调 → 页面不卡死。

    这条串起两侧: `SdkWorker.drop_pending` 补回调 + 页面 `_on_refreshed` 解忙。
    """
    from litetool.sdk_worker import SdkWorker, TaskResult
    from tests.fake_arm import FakeArm, worker_arm_factory

    arm = FakeArm()
    w = SdkWorker(arm_factory=worker_arm_factory([arm]))
    w._arm = arm
    _app, pg, rec = _page(snap=load_snap(), st=_St())
    pg._busy = True

    # 页面把任务投进 worker 队列, 但所有者线程没起 -> 任务躺在队列里
    w.submit("调参[测试]", lambda a: None, lambda res: pg._on_refreshed(None))
    assert pg._busy is True, "置忙 (模拟 _start)"
    assert w.drop_pending() == 1
    # 关键: 被丢的任务**回调了**, 且页面的处理器把它解了忙。
    # 修复前这里是 False 永真 —— 页面就只能重启进程。
    assert pg._busy is False, "drop_pending 后页面仍卡在忙态 = 回调没送达"
