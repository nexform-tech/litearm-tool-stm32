"""params_page 安全流测试 —— 审查修复覆盖:

- Critical-1: 未成功"刷新当前"前禁下发全局/全部 (默认 spin 值不盲发)
- Important-2: enable 态控制律写二次确认; 0x23 限位写前当前 q 越界拒绝
- Important-3: _send_global 的 ff_mask(0x27) 只发一次
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

import yaml
from PyQt5.QtWidgets import QApplication, QMessageBox

from litetool import param_catalog as C
from litetool import client as CL
from litetool import protocol as P
from litetool.gui import params_page as PP

REPO = Path(__file__).resolve().parents[1]
ZERO_Q = [0.0] * 7


def load_snap():
    raw = yaml.safe_load((REPO / "templates" / "params_example.yaml").read_text("utf-8"))
    return C.normalize_snapshot(raw)


class _J:
    def __init__(self, q):
        self.q = q


class _St:
    def __init__(self, qs=ZERO_Q, enabled=False):
        self.joints = [_J(q) for q in qs]
        self.n = len(qs)
        self.enabled = enabled


class _Cli:
    """仅状态桩 —— 流测试都应在真正发送前中止。"""
    def __init__(self, st=None):
        self.status = st
        self.sent = []


def _page(snap=None, st=None):
    app = QApplication.instance() or QApplication([])
    pg = PP.ParamsPage()
    pg.set_client(_Cli(st))
    pg.set_online(True)
    if snap is not None:
        pg._on_refreshed(snap)          # 刷新成功 -> 允许下发
    return app, pg


# ---------------- Critical-1: 未刷新拒下发 ----------------
def test_send_disabled_until_refresh():
    _app, pg = _page(snap=None, st=_St())
    assert pg._device_synced is False
    # 三个下发按钮在成功刷新前禁用, 只读按钮可用
    assert not pg.btn_apply_row.isEnabled()
    assert not pg.btn_apply_all.isEnabled()
    assert not pg.btn_global.isEnabled()
    assert pg.btn_refresh.isEnabled()
    # 即便直接调 handler 也拒绝 (不触碰默认控件值)
    pg._on_apply_global()
    assert "未读取设备数据" in pg.status.text()
    pg._apply_rows_selected(all_rows=True)
    assert "未读取设备数据" in pg.status.text()
    # 刷新成功后才放行
    pg._on_refreshed(load_snap())
    assert pg._device_synced is True
    assert pg.btn_apply_all.isEnabled() and pg.btn_global.isEnabled()


# ---------------- Important-2a: enable 态写二次确认 ----------------
def test_enabled_write_requires_confirm(monkeypatch):
    calls = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg = _page(snap=load_snap(), st=_St(ZERO_Q, enabled=True))
    pg._apply_rows_selected(all_rows=True)
    assert calls, "enable 态应弹确认"
    assert "臂已使能" in calls[-1][1]           # 标题
    assert "已取消" in pg.status.text()          # 未发送


def test_ffmask_write_when_enabled_requires_confirm(monkeypatch):
    calls = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg = _page(snap=load_snap(), st=_St(ZERO_Q, enabled=True))
    pg._on_apply_global()
    assert calls and "臂已使能" in calls[0][1]


# ---------------- Important-2b: 0x23 限位写前当前 q 越界拒绝 ----------------
def test_limits_write_rejected_when_q_outside(monkeypatch):
    calls = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg = _page(snap=load_snap(), st=_St(ZERO_Q, enabled=False))
    ri = next(i for i, p in enumerate(C.JOINT_PARAMS) if p.key == "q_max")
    pg.table.item(ri, 1 + 1).setText("-0.5")     # J2 当前 q=0 不在新上限内
    pg._apply_rows_selected(all_rows=True)
    assert any("限位" in a[1] for a in calls)      # 弹"限位写被拒绝"
    assert "J2" in pg.status.text()
    assert not pg._client.sent                     # 未真正发送


def test_limits_write_allowed_when_q_inside(monkeypatch):
    calls = []
    starts = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        lambda *a, **k: calls.append(a) or QMessageBox.Cancel)
    _app, pg = _page(snap=load_snap(), st=_St(ZERO_Q, enabled=False))
    monkeypatch.setattr(pg, "_start", lambda *a, **k: starts.append(a))
    # q=0 在各关节默认限位内 -> 不应弹"限位写被拒绝", 直接进入下发(_start)
    pg._apply_rows_selected(all_rows=True)
    assert not any((a[1] or "").startswith("限位写被拒绝") for a in calls)
    assert starts, "合法限位应放行到 _start"


# ---------------- Important-3: ff_mask 单次发送 ----------------
class _AutoAckLink:
    """每次发送立即注入 ACK (同步, 无需后台线程)。"""
    def __init__(self):
        self.sent = []
        self.cli = None
        self.is_open = True

    def send_bytes(self, data):
        self.sent.append(data)
        self.cli.handle_frame(P.RSP_ACK, bytes([data[1]]))


def test_send_global_sends_ff_flags_once():
    link = _AutoAckLink()
    cli = CL.LiteArmClient(link)
    link.cli = cli
    g = load_snap()["global"]
    g, leaf_ok, model_ok, mask_ok = PP._send_global(cli, g)
    ff_cnt = [d for d in link.sent if d[1] == P.CMD_SET_FF_FLAGS]
    scalar_cnt = [d for d in link.sent if d[1] == P.CMD_SET_FF_SCALAR]
    assert len(ff_cnt) == 1                       # 0x27 只发一次
    assert scalar_cnt                              # 0x28 逐叶各一次
    assert all(leaf_ok.values()) and model_ok and mask_ok
    # 0x28 帧数 = 循环叶 (fric_db/wall_margin/friction_slew/payload_mass + payload_com[3]
    #            + gravity[3] + fric_v2_eps = 11) + friction_model(1) = 12
    assert len(scalar_cnt) == 12
