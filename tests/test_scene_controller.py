"""3D 显示平滑 —— 100Hz 状态到 60Hz 画面，不允许出现瞬时台阶。"""
from __future__ import annotations

import pytest

from litetool.scene.controller import JointSmoother


def test_first_sample_starts_at_target_without_jump():
    s = JointSmoother(2, tau_s=0.05)
    s.set_target([1.0, -1.0])
    out = s.sample(now=10.0)
    assert out.tolist() == [1.0, -1.0]


def test_step_response_is_smooth_and_converges():
    s = JointSmoother(2, tau_s=0.05)
    s.set_target([0.0, 0.0])
    s.sample(now=0.0)
    s.set_target([1.0, 2.0])
    prev = s.sample(now=0.016)
    assert 0.0 < prev[0] < 1.0
    assert 0.0 < prev[1] < 2.0
    for i in range(1, 120):
        cur = s.sample(now=0.016 + i * 0.016)
        # 每个渲染帧都只前进一小步，不能出现硬跳
        assert abs(cur[0] - prev[0]) < 0.25
        assert abs(cur[1] - prev[1]) < 0.5
        prev = cur
    assert s.settled
    assert prev[0] == pytest.approx(1.0, abs=1e-3)
    assert prev[1] == pytest.approx(2.0, abs=1e-3)


def test_long_gap_snaps_to_target():
    s = JointSmoother(1, tau_s=0.05, snap_after_s=0.5)
    s.set_target([0.0])
    s.sample(now=0.0)
    s.set_target([1.0])
    out = s.sample(now=1.0)
    assert out[0] == 1.0


def test_wrong_length_raises():
    s = JointSmoother(2)
    with pytest.raises(ValueError):
        s.set_target([1.0])
