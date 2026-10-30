"""诊断页 —— `diag.kin_bench()` 自检 + 启动原因 + 链路计数。

对应 SDK：`arm.diag.kin_bench()`、`arm.last_reset_reason`、`RobotState.seq`（丢帧差分）。
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QGridLayout, QPlainTextEdit, QPushButton,
                             QVBoxLayout, QWidget)

from litetool.gui.pages.common import group, note, row
from litetool.gui.widgets import mono_label, static_label


class DiagPage(QWidget):
    bench_req = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._online = False
        self._busy = False

        self.btn_bench = QPushButton("运行 KIN_BENCH 自检")
        self.btn_bench.setToolTip(
            "触发固件运动学/动力学单拍开销自测（固件侧最长窗口 5s，期间控制循环\n"
            "心跳监督豁免）。注意：该命令不检查载荷长度，发出即产生一次真实测量。")
        self.btn_bench.clicked.connect(self.bench_req.emit)

        grid = QGridLayout()
        self.vals = {}
        for r, (key, label) in enumerate((
                ("crc_errors", "固件累计 CRC 坏帧"),
                ("reply_dropped", "应答 FIFO 队满丢弃"),
                ("can_tx_fail", "CAN 发送失败"),
                ("loop_max_kcycle", "控制拍峰值 (kcycle)"),
                ("loop_overruns", "控制拍超预算次数"),
                ("drops", "上位机接收侧丢帧"),
                ("fps", "状态帧率 (Hz)"),
                ("firmware", "固件版本"),
                ("n_joints", "关节数"),
                ("reset_reason", "上次启动原因"))):
            grid.addWidget(static_label(label), r // 2, (r % 2) * 2)
            lb = mono_label(150)
            self.vals[key] = lb
            grid.addWidget(lb, r // 2, (r % 2) * 2 + 1)
        g_num = group("链路与运行计数", grid,
                      note("CRC/队满/CAN 失败来自固件侧计数器（KIN_BENCH 回执里的 LINK 行）；"
                           "丢帧是上位机按 seq 差分算的接收侧数字。"))

        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setPlaceholderText("KIN_BENCH 原文（含逐项计时与 LINK 诊断行）会显示在这里")
        g_raw = group("KIN_BENCH 回执原文", self.raw)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addLayout(row(self.btn_bench))
        lay.addWidget(g_num)
        lay.addWidget(g_raw, 1)

    # ---------------- 外部状态 ----------------
    def set_online(self, onl: bool):
        self._online = onl
        self._refresh()

    def set_busy(self, busy: bool):
        self._busy = busy
        self._refresh()

    def _refresh(self):
        self.btn_bench.setEnabled(self._online and not self._busy)

    def set_metrics(self, *, drops, fps, firmware, n_joints, reset_reason):
        for key, val in (("drops", drops), ("fps", f"{fps:.0f}"),
                         ("firmware", firmware or "—"), ("n_joints", n_joints),
                         ("reset_reason", "—" if reset_reason is None else reset_reason)):
            self.vals[key].setText(str(val))

    def set_bench(self, res):
        """res: `litearm.KinBenchResult`。"""
        self.raw.setPlainText(res.raw)
        for key, val in (("crc_errors", res.crc_errors),
                         ("reply_dropped", res.reply_dropped),
                         ("can_tx_fail", res.can_tx_fail),
                         ("loop_max_kcycle", res.loop_max_kcycle),
                         ("loop_overruns", res.loop_overruns)):
            self.vals[key].setText(str(val))

    def set_bench_error(self, msg: str):
        self.raw.setPlainText(f"失败：{msg}")
