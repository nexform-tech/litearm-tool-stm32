"""plot_model.py 测试 —— 状态环形缓冲（纯 Python，供曲线页读取）。"""
import time

from litetool import client as C
from litetool.gui import plot_model


def _view(seq, joints):
    st = C.StatusView(flags=0, mode=1, seq=seq, joints=joints, received=0.0)
    return st


def _one_joint(q):
    return [C.JointState(0, q, 0.1, 0.2, 30.0, 40.0, 0)]


class _Clock:
    """可控时钟。"""
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_push_and_snapshot_shape():
    clock = _Clock()
    m = plot_model.PlotModel(window_s=30.0, clock=clock)
    for i in range(10):
        m.push(_view(i, _one_joint(float(i))))
        clock.advance(0.01)
    t, q, dq, tau = m.snapshot()
    assert len(t) == 10
    assert len(q) == 10 and q[3][0] == 3.0
    assert len(dq[0]) == 1 and dq[0][0] == 0.1
    assert tau[0][0] == 0.2
    assert m.n_joints == 1


def test_window_trims_old_samples():
    clock = _Clock()
    m = plot_model.PlotModel(window_s=1.0, clock=clock)
    # 前 10 帧落在 0~0.1s
    for i in range(10):
        m.push(_view(i, _one_joint(float(i))))
        clock.advance(0.01)
    # 快速推进到 5s 后（当前窗口外）
    clock.advance(5.0)
    for i in range(10, 15):
        m.push(_view(i, _one_joint(float(i))))
        clock.advance(0.01)
    t, q, _, _ = m.snapshot()
    # 保留最近窗口内的 5 帧
    assert len(t) == 5
    assert q[0][0] == 10.0 and q[-1][0] == 14.0


def test_reset_clears_and_restarts_clock():
    clock = _Clock()
    m = plot_model.PlotModel(clock=clock)
    m.push(_view(0, _one_joint(1.0)))
    clock.advance(0.5)
    m.reset()
    assert m.snapshot() == ([], [], [], [])
    m.push(_view(1, _one_joint(2.0)))
    t, q, _, _ = m.snapshot()
    assert len(t) == 1 and q[0][0] == 2.0 and t[0] == 0.0   # 时钟从 0 重新计
