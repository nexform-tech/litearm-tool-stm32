"""Session —— Qt-free 会话控制器，串起 传输层 / 客户端 / 曲线模型。

GUI 只持有 Session，并通过 Session.log 回调（线程安全地）输出日志。
"""
import time

from litetool import client, protocol as P
from litetool.gui.plot_model import PlotModel
from litetool.transport import SerialLink


class Session:
    def __init__(self, log=None, clock=time.monotonic):
        self._log = log if log is not None else (lambda msg: None)
        self._clock = clock
        self.link: SerialLink | None = None
        self.client: client.LiteArmClient | None = None
        self.model = PlotModel(clock=clock)
        self._prev_seq = None
        self._drops = 0

    # ---- 连接生命周期 ----
    def connect(self, port: str):
        """打开串口。失败抛异常（由 GUI 捕获并提示）。"""
        self.close()
        self.model.reset()
        self._prev_seq = None
        self._drops = 0
        link = SerialLink(port, on_frame=self._on_frame, on_error=self._on_error)
        cli = client.LiteArmClient(link, log=self._log, clock=self._clock)
        link.connect()
        self.link, self.client = link, cli

    def close(self):
        if self.link is not None:
            self.link.close()
        self.link = None
        self.client = None

    # ---- 帧分发（读线程上下文） ----
    def _on_frame(self, cmd: int, payload: bytes):
        cli = self.client
        if cli is None:
            return
        cli.handle_frame(cmd, payload)
        if cmd == P.RSP_STATUS:
            view = cli.status
            if view is not None:
                self.model.push(view)
                self._count_drops(view.seq)

    def _count_drops(self, seq: int):
        """在读线程按 seq 差分统计丢帧（固件每帧 seq+1, seq 为 8 位回绕）。"""
        if self._prev_seq is not None:
            gap = (seq - self._prev_seq) & (P.SEQ_MOD - 1)
            if gap > 1:
                self._drops += gap - 1
        self._prev_seq = seq

    def drops(self) -> int:
        return self._drops

    def _on_error(self, msg: str):
        self._log(f"[ERR] {msg}")

    # ---- 便捷属性 ----
    @property
    def online(self) -> bool:
        return bool(self.client is not None and self.client.online)

    @property
    def status(self):
        return self.client.status if self.client is not None else None

    def bad_frames(self) -> int:
        if self.link is not None:
            return self.link.stats["bad_crc"] + self.link.stats["discarded"]
        return 0
