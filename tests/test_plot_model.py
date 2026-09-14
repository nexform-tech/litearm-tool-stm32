"""plot_model.py 测试 —— 状态环形缓冲（纯 Python，供曲线组件读取）。"""
import pytest

from litetool import plot_model
from tests.fake_arm import make_state


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
        m.push(make_state(n=1, seq=i, q=[float(i)]))
        clock.advance(0.01)
    t, q, dq, tau = m.snapshot()
    assert len(t) == 10
    assert len(q) == 10 and q[3][0] == 3.0
    assert len(dq[0]) == 1 and dq[0][0] == 0.0
    assert tau[0][0] == 0.0
    assert m.n_joints == 1


def test_window_trims_old_samples():
    clock = _Clock()
    m = plot_model.PlotModel(window_s=1.0, clock=clock)
    for i in range(10):
        m.push(make_state(n=1, q=[float(i)]))
        clock.advance(0.01)
    clock.advance(5.0)
    for i in range(10, 15):
        m.push(make_state(n=1, q=[float(i)]))
        clock.advance(0.01)
    t, q, _, _ = m.snapshot()
    assert len(t) == 5
    assert q[0][0] == 10.0 and q[-1][0] == 14.0


def test_reset_clears_and_restarts_clock():
    clock = _Clock()
    m = plot_model.PlotModel(clock=clock)
    m.push(make_state(n=1, q=[1.0]))
    clock.advance(0.5)
    m.reset()
    assert m.snapshot() == ([], [], [], [])
    assert m.rate() == 0.0
    m.push(make_state(n=1, q=[2.0]))
    t, q, _, _ = m.snapshot()
    assert len(t) == 1 and q[0][0] == 2.0 and t[0] == 0.0


def test_rate_measures_actual_frame_rate():
    """帧率必须是**实测**（固件推多快），不是 GUI 轮询多快。"""
    clock = _Clock()
    m = plot_model.PlotModel(clock=clock)
    assert m.rate() == 0.0                      # 样本不足
    m.push(make_state(n=1))
    assert m.rate() == 0.0
    for _ in range(9):
        clock.advance(0.01)                     # 100Hz
        m.push(make_state(n=1))
    assert m.rate() == pytest.approx(100.0, rel=0.01)
