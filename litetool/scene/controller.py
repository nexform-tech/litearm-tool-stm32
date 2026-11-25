"""关节角的显示平滑 —— 100 Hz 状态 → 60 Hz 画面。

直接把每帧状态硬塞给渲染会在 20/50/100 Hz 之间产生台阶。这里用一阶低通
（指数趋近）在**渲染线程**上把目标角平滑到显示角：目标随状态快照更新，
显示值按渲染节奏逼近，CPU 只做一次 7 维向量运算。
"""
from __future__ import annotations

import time
from typing import Optional, Sequence

import numpy as np


class JointSmoother:
    """一阶低通；`tau_s` 是时间常数（约 50 ms 视觉上不拖沓）。"""

    def __init__(self, n: int, tau_s: float = 0.05, snap_after_s: float = 0.5):
        if n <= 0:
            raise ValueError("n 需 > 0")
        self.n = int(n)
        self.tau_s = max(float(tau_s), 1e-3)
        self.snap_after_s = max(float(snap_after_s), 0.0)
        self._display: Optional[np.ndarray] = None
        self._target: Optional[np.ndarray] = None
        self._last: Optional[float] = None

    @property
    def settled(self) -> bool:
        if self._display is None or self._target is None:
            return True
        return bool(np.max(np.abs(self._target - self._display)) < 1e-4)

    def reset(self, q: Optional[Sequence[float]] = None) -> None:
        self._display = None if q is None else self._as_q(q)
        self._target = None if q is None else self._display.copy()
        self._last = None

    def set_target(self, q: Sequence[float]) -> None:
        arr = self._as_q(q)
        self._target = arr
        if self._display is None:
            self._display = arr.copy()

    def sample(self, now: Optional[float] = None) -> Optional[np.ndarray]:
        if self._target is None or self._display is None:
            return None
        now = time.monotonic() if now is None else float(now)
        if self._last is None:
            self._last = now
            return self._display.copy()
        dt = max(0.0, now - self._last)
        self._last = now
        if dt <= 0.0:
            return self._display.copy()
        if self.snap_after_s and dt > self.snap_after_s:
            # 页面隐藏/卡顿后恢复：直接对齐目标，避免慢慢追赶。
            self._display = self._target.copy()
        else:
            alpha = 1.0 - np.exp(-dt / self.tau_s)
            self._display = self._display + (self._target - self._display) * alpha
        return self._display.copy()

    def _as_q(self, q: Sequence[float]) -> np.ndarray:
        arr = np.asarray(q, dtype=float).reshape(-1)
        if len(arr) != self.n:
            raise ValueError(f"需要 {self.n} 个关节角 (给的是 {len(arr)})")
        return arr
