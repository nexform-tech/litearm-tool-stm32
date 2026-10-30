"""PlotModel —— 状态环形缓冲（线程安全，曲线页数据源）。

SDK 所有者线程以 ~100Hz push 全部状态（不抽稀），曲线组件用 QTimer 周期
snapshot 重绘；只保留最近 window_s 秒数据，内存有界。
"""
from __future__ import annotations

import collections
import threading
import time


class PlotModel:
    def __init__(self, window_s: float = 30.0, clock=time.monotonic):
        self._window = window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._t0 = None
        self._times: list = []
        self._q: list = []
        self._dq: list = []
        self._tau: list = []
        #: 最近若干次 push 的时刻 —— 用来算**实测**帧率（固件推多快，不是轮询多快）
        self._recent = collections.deque(maxlen=200)

    def reset(self):
        with self._lock:
            self._t0 = None
            self._times.clear()
            self._q.clear()
            self._dq.clear()
            self._tau.clear()
            self._recent.clear()

    def push(self, st):
        """st: `litearm.RobotState`。"""
        now = self._clock()
        with self._lock:
            if self._t0 is None:
                self._t0 = now
            t = now - self._t0
            self._times.append(t)
            self._q.append([j.q for j in st.joints])
            self._dq.append([j.dq for j in st.joints])
            self._tau.append([j.tau for j in st.joints])
            self._recent.append(now)
            # 剪除窗口外旧样本（每样本只被删一次, 摊还 O(1)）
            cutoff = t - self._window
            while self._times and self._times[0] < cutoff:
                del self._times[0]
                del self._q[0]
                del self._dq[0]
                del self._tau[0]

    def rate(self) -> float:
        """最近一段窗口的实测状态帧率 (Hz)。样本不足时返回 0。"""
        with self._lock:
            n = len(self._recent)
            if n < 2:
                return 0.0
            span = self._recent[-1] - self._recent[0]
            return 0.0 if span <= 0 else (n - 1) / span

    @property
    def n_joints(self) -> int:
        with self._lock:
            return len(self._q[0]) if self._q else 0

    def snapshot(self):
        """返回 (times, q, dq, tau) 的浅拷贝快照；q/dq/tau 为 [样本][关节] 列表。"""
        with self._lock:
            return (list(self._times), list(self._q), list(self._dq), list(self._tau))
