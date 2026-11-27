"""采集页 —— 固件 300Hz 控制拍采集（`arm.log.*`）。

对应 SDK：`log.start` `log.stop` `log.reader` `log.capture` `log.dump`、
`LogReader.total/wait_for/iter_chunks/read_all/samples`。

固件侧是**逐拍**记录（`LOG_MAX_SAMPLES=2400` ≈ 8s@300Hz，记满自停），`start(n)`
返回时缓冲里还没有数据 —— 故有「录满进度」一栏。读回走按字节游标的 `LOG_READ`
分块（规避 CDC 间歇掉帧），大缓冲读回要几百次往返，故 `capture()` 的等待预算做成了
可调项。
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (QFileDialog, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from litetool import csv_export
from litetool.gui.pages.common import group, hint, note, row, spin
from litetool.gui.widgets import mono_label

CTRL_HZ = 300
LOG_MAX_SAMPLES = 2400
FIELD_TITLES = ("执行参考 q_ref (rad)", "执行速度 dq (rad/s)", "实测力矩 tau (Nm)")
COLORS = ["#e8c547", "#e06c75", "#61afef", "#98c379", "#c678dd", "#56b6c2", "#d19a66"]


class CapturePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._submit = None
        self._online = False
        self._busy = False
        self._recording = False
        self._samples: list = []          # 最近一次 [读回并预览] 的解析结果
        self._firmware = ""               # 导出文件名用

        # ---------------- 录制控制 ----------------
        self.n_ticks = spin(1, LOG_MAX_SAMPLES, 600, 50, decimals=0)
        self.n_ticks.valueChanged.connect(self._refresh_eta)
        self.eta_lbl = mono_label(120)

        self.btn_start = QPushButton("开始记录")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop = QPushButton("停止/清空")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_read = QPushButton("读回并预览")
        self.btn_read.clicked.connect(self._on_read)
        self.btn_capture = QPushButton("采集全程（等录满后读回）")
        self.btn_capture.setToolTip(
            "`log.capture(n)`：开始记录 → 等录满 n 拍 → 读回 → 解析。\n"
            "n 拍要 n/300 秒才录满，故会阻塞 SDK 所有者线程（界面不卡）。")
        self.btn_capture.clicked.connect(self._on_capture)
        self.btn_prog = QPushButton("查进度")
        self.btn_prog.clicked.connect(self._on_progress)
        self.btn_dump = QPushButton("导出原始字节…")
        self.btn_dump.clicked.connect(self._on_dump)
        self.btn_csv = QPushButton("导出解析 CSV…")
        self.btn_csv.setToolTip(
            "把最近一次读回的样本写成 CSV：tick、时间、q_ref/dq/tau。\n"
            "采集缓冲里没有温度与错误码 —— 那些请到总览页导出曲线 CSV。")
        self.btn_csv.clicked.connect(self._on_csv)

        self.prog_lbl = mono_label(240)

        g_rec = group(
            "录制",
            row(QLabel("拍数"), self.n_ticks, QLabel("预计"), self.eta_lbl),
            row(self.btn_start, self.btn_stop, self.btn_read, self.btn_dump),
            row(self.btn_capture, self.btn_prog, self.btn_csv),
            row(QLabel("进度"), self.prog_lbl),
            note(f"固件缓冲上限 {LOG_MAX_SAMPLES} 拍（≈{LOG_MAX_SAMPLES / CTRL_HZ:.1f}s @ {CTRL_HZ}Hz），"
                 "记满自停。可导出原始字节，也可把最近一次读回的样本写成解析 CSV。"),
            hint("⚠ 固件是逐拍记录的：点开始后缓冲里还没有数据，要等 n/300 秒才录满。"
                 "读回在未录满时也能拿到已录部分。"),
            note("采集缓冲只有 tick/q_ref/dq/tau —— 温度与错误码在 100Hz 状态流里，"
                 "请到「总览」页用曲线右上角的 [导出 CSV…]。"),
        )

        # ---------------- 预览 ----------------
        self.gw = pg.GraphicsLayoutWidget()
        self.plots = []
        for r in range(3):
            pi = self.gw.addPlot(row=r, col=0)
            pi.showGrid(x=True, y=True, alpha=0.2)
            pi.setLabel("left", FIELD_TITLES[r])
            pi.addLegend(offset=(10, 10))
            if r:
                pi.setXLink(self.plots[0])
            self.plots.append(pi)
        self.plots[-1].setLabel("bottom", "时间 (s)")
        self.curves: list = []
        g_plot = group("预览（读回后绘制）", self.gw)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(g_rec)
        lay.addWidget(g_plot, 1)
        self._refresh_eta()
        self._refresh()            # 初始全灰：连接前不暗示可以录制

    # ---------------- 外部接线 ----------------
    def set_submit(self, fn):
        """由主窗口注入 `fn(name, callable, on_done)` —— 在 SDK 所有者线程上执行。"""
        self._submit = fn

    def set_online(self, onl: bool):
        self._online = onl
        self._refresh()

    def set_busy(self, busy: bool):
        self._busy = busy
        self._refresh()

    def set_firmware(self, firmware: str):
        """主窗口在连接后注入固件版本 —— 导出文件名带它。"""
        self._firmware = str(firmware or "")

    def _refresh(self):
        can = self._online and not self._busy and self._submit is not None
        self.btn_start.setEnabled(can and not self._recording)
        self.btn_stop.setEnabled(can)
        self.btn_read.setEnabled(can)
        self.btn_capture.setEnabled(can)
        self.btn_prog.setEnabled(can)
        self.btn_dump.setEnabled(can)
        # 导出已读回的数据是纯本地操作：断线/忙态都不该拦着现场留档。
        self.btn_csv.setEnabled(bool(self._samples))
        self.n_ticks.setEnabled(can and not self._recording)

    def _refresh_eta(self):
        n = int(self.n_ticks.value())
        self.eta_lbl.setText(f"{n / CTRL_HZ:.2f} s")

    # ---------------- 动作 ----------------
    def _on_start(self):
        n = int(self.n_ticks.value())
        self._do("log.start", lambda arm: arm.log.start(n),
                 lambda res: self._after_start(res, n))

    def _after_start(self, res, n):
        if res.ok:
            self._recording = True
            self.prog_lbl.setText(f"已开始记录 {n} 拍 …")
        self._refresh()

    def _on_stop(self):
        self._do("log.stop", lambda arm: arm.log.stop(),
                 lambda res: self._after_stop(res))

    def _after_stop(self, res):
        self._recording = False
        if res.ok:
            self.prog_lbl.setText("已停止/清空")
        self._refresh()

    def _on_capture(self):
        """`log.capture(n)`：开始 → 等录满 → 读回 → 解析，一次到底。"""
        n = int(self.n_ticks.value())
        self._do("log.capture", lambda arm: arm.log.capture(n),
                 self._after_capture)

    def _after_capture(self, res):
        if res.ok:
            self._recording = False
            self._after_read(res)
        self._refresh()

    def _on_progress(self):
        """`LogReader.total()` —— 固件侧已录了多少拍（不读全量、不等）。"""
        self._do("log.total", lambda arm: arm.log.reader().total(),
                 lambda res: self.prog_lbl.setText(
                     f"已记录 {res.value} 拍" if res.ok else f"查进度失败：{res.error}"))

    def _on_read(self):
        self._do("log.reader", lambda arm: arm.log.reader().samples(),
                 self._after_read)

    def _after_read(self, res):
        if not res.ok:
            self.prog_lbl.setText(f"读回失败：{res.error}")
            return
        samples = res.value or []
        self._samples = list(samples)
        self.prog_lbl.setText(f"读回 {len(samples)} 拍")
        self._draw(samples)
        self._refresh()

    def _on_dump(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出采集原始字节", "log_capture.bin",
                                              "二进制 (*.bin);;全部 (*)")
        if not path:
            return
        self._do("log.dump", lambda arm: arm.log.dump(path, wait=False),
                 lambda res: self.prog_lbl.setText(
                     f"已导出 {res.value} 字节 → {path}" if res.ok
                     else f"导出失败：{res.error}"))

    def _on_csv(self):
        """把最近一次读回的样本写成 CSV（纯本地，不再碰串口）。"""
        if not self._samples:
            self.prog_lbl.setText("还没有可导出的样本 —— 先读回并预览")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出采集解析 CSV",
            csv_export.timestamped_name("capture", self._firmware),
            "CSV (*.csv);;全部 (*)")
        if not path:
            return
        try:
            rows = csv_export.write_capture_csv(path, self._samples,
                                                firmware=self._firmware, hz=CTRL_HZ)
        except Exception as e:  # noqa: BLE001 - 导出失败不该拖垮界面
            self.prog_lbl.setText(f"导出失败：{e}")
            return
        self.prog_lbl.setText(f"已导出 {rows} 行 → {path}")

    def _do(self, name, fn, cb):
        if self._submit is None:
            return
        self.prog_lbl.setText(f"{name} …")
        self._submit(name, fn, cb)

    # ---------------- 预览绘制 ----------------
    def _draw(self, samples):
        for pi in self.plots:
            pi.clear()
            pi.addLegend(offset=(10, 10))
        self.curves = []
        if not samples:
            return
        ticks = np.asarray([s.tick for s in samples], dtype=float)
        t = (ticks - ticks[0]) / CTRL_HZ
        for f, attr in enumerate(("q_ref", "dq", "tau")):
            mat = np.asarray([getattr(s, attr) for s in samples], dtype=float)
            pi = self.plots[f]
            for j in range(mat.shape[1]):
                pi.plot(t, mat[:, j], pen=pg.mkPen(COLORS[j % len(COLORS)], width=1.5),
                        name=f"J{j + 1}")
