"""零重力退出后的「保持」—— `exit_zero_g_and_hold` 的最小判据。

背景：`zero_g_stop()` 只发一帧 `0x06 off`，之后没有命令；固件 0.1 s 命令看门狗
会进入 fail-soft hold（tau=0, kp=0.6×），臂按 G/(0.6·kp) 下沉。显式退出不是 PC
掉线，退出后应补一条零位移 `movej` 把模式留在 MOVE_J（每拍自动 kick + 重力前馈）。

判据必须能区分：
  (1) 退出后是 INIT -> 必须 movej 到当前实测 q；
  (2) 退出后已是 MOVE_J（越限回程已启动）-> **不得**再发 movej 覆盖它；
  (3) 一直停在 ZERO_G（退出帧未生效）-> 超时返回，不发 movej；
  (4) zero_g_stop 抛错 -> 原样上抛，不发 movej。
"""
from __future__ import annotations

import litearm as pa
import pytest

from litetool.sdk_worker import exit_zero_g_and_hold


class _J:
    def __init__(self, q):
        self.q = q


class _St:
    def __init__(self, mode, q):
        self.mode_name = mode
        self.joints = [_J(x) for x in q]


class _Arm:
    def __init__(self, modes, q, stop_raises=False):
        self._modes = list(modes)
        self._q = list(q)
        self._i = 0
        self._stop_raises = stop_raises
        self.calls = []

    def zero_g_stop(self, raise_on_lost=False):
        self.calls.append(("zero_g_stop", raise_on_lost))
        if self._stop_raises:
            raise RuntimeError("exit frame failed")

    def get_state(self):
        mode = self._modes[min(self._i, len(self._modes) - 1)]
        self._i += 1
        return pa.Msg(value=_St(mode, self._q), hz=0.0, timestamp=0.0)

    def movej(self, q, speed=1.0):
        self.calls.append(("movej", list(q), speed))
        return _St("MOVE_J", q)


def test_exit_init_then_zero_motion_movej():
    q = [0.1, -0.8, 0.2, -0.5, 0.0, 0.1, 0.0]
    arm = _Arm(["ZERO_G", "ZERO_G", "INIT"], q)
    st = exit_zero_g_and_hold(arm, speed=0.15)
    assert arm.calls[0] == ("zero_g_stop", True)
    assert ("movej", q, 0.15) in arm.calls
    assert st.mode_name == "MOVE_J"


def test_exit_already_movej_does_not_override_return():
    """越限回程已把模式切到 MOVE_J —— 不能再发一条覆盖它。"""
    arm = _Arm(["ZERO_G", "MOVE_J"], [0.0] * 7)
    st = exit_zero_g_and_hold(arm)
    assert not any(c[0] == "movej" for c in arm.calls)
    assert st.mode_name == "MOVE_J"


def test_exit_stuck_in_zero_g_times_out_without_movej():
    arm = _Arm(["ZERO_G"], [0.0] * 7)
    st = exit_zero_g_and_hold(arm, timeout=0.03)
    assert not any(c[0] == "movej" for c in arm.calls)
    assert st.mode_name == "ZERO_G"


def test_exit_frame_failure_propagates_without_movej():
    arm = _Arm(["INIT"], [0.0] * 7, stop_raises=True)
    with pytest.raises(RuntimeError, match="exit frame failed"):
        exit_zero_g_and_hold(arm)
    assert not any(c[0] == "movej" for c in arm.calls)
