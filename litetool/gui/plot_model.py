"""PlotModel —— 状态环形缓冲（线程安全，GUI 曲线页数据源）。

读线程以 100Hz push 全部状态（不抽稀），曲线页用 QTimer 周期 snapshot 重绘；
只保留最近 window_s 秒数据，内存有界。
"""
import threading
import time


class PlotModel:
    def __init__(self, window_s: float = 30.0, clock=time.monotonic):
        self._window = window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._t0 = None
        self._times: list[float] = []
        self._q: list[list[float]] = []
        self._dq: list[list[float]] = []
        self._tau: list[list[float]] = []

    def reset(self):
        with self._lock:
            self._t0 = None
            self._times.clear()
            self._q.clear()
            self._dq.clear()
            self._tau.clear()

    def push(self, view):
        """view: client.StatusView（含逐关节 joints）。"""
        now = self._clock()
        with self._lock:
            if self._t0 is None:
                self._t0 = now
            t = now - self._t0
            self._times.append(t)
            self._q.append([j.q for j in view.joints])
            self._dq.append([j.dq for j in view.joints])
            self._tau.append([j.tau for j in view.joints])
            # 剪除窗口外旧样本（每样本只被删一次, 摊还 O(1)）
            cutoff = t - self._window
            while self._times and self._times[0] < cutoff:
                del self._times[0]
                del self._q[0]
                del self._dq[0]
                del self._tau[0]

    @property
    def n_joints(self) -> int:
        with self._lock:
            return len(self._q[0]) if self._q else 0

    def snapshot(self):
        """返回 (times, q, dq, tau) 的浅拷贝快照；q/dq/tau 为 [样本][关节] 列表。"""
        with self._lock:
            return (list(self._times), list(self._q), list(self._dq), list(self._tau))
