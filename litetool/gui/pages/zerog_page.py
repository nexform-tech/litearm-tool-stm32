"""零重力页 —— 拖动示教（`zero_g` / `zero_g_start` / `zero_g_stop` / `zero_g_error`）。

保活由 SDK 的后台线程维持（固件靠"重发即 kick 看门狗"活着，周期须 <0.10s），
本页只负责进出与显示 —— **不**自己发心跳帧。
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QLabel, QPushButton, QVBoxLayout, QWidget)

from litetool.gui.pages.common import LockBanner, group, hint, note, row, spin


class ZeroGPage(QWidget):
    zg = pyqtSignal(bool)            # True=进入 / False=退出

    def __init__(self, parent=None):
        super().__init__(parent)
        self._online = False
        self._busy = False
        self._armed = False
        self._fault_blocked = False
        self._active = False

        self.btn = QPushButton("进入零重力拖动")
        self.btn.setMinimumHeight(40)
        self.btn.setCheckable(True)
        self.btn.clicked.connect(lambda: self.zg.emit(self.btn.isChecked()))

        self.period = spin(0.005, 0.099, 0.04, 0.005)
        self.period.setToolTip(
            "保活周期。固件看门狗超时 0.10s，必须 <0.10 才有余量；\n"
            "SDK 默认 0.04s（2.5 倍余量）。")

        self.state_lbl = QLabel("未进入")
        self.state_lbl.setStyleSheet("color:#b0b0b0;font-weight:bold;")
        self.err_lbl = QLabel("")
        self.err_lbl.setWordWrap(True)
        self.err_lbl.setStyleSheet("color:#ff6b6b;")

        g = group("零重力拖动（拖动示教）",
                  row(self.btn),
                  row(QLabel("保活周期 (s)"), self.period),
                  row(QLabel("状态"), self.state_lbl),
                  self.err_lbl,
                  note("进入后臂进入重力补偿，可用手自由拖动；松手由虚拟弹簧保持位置。"),
                  note("⚠ 固件侧靠看门狗保活：SDK 后台线程按上面的周期重发命令，"
                       "界面卡死/拔线时臂会自动落到 fail-soft 持位，不会失控。"),
                  hint("⚠ 退出前先把关节推回软限位内 —— 零重力会跳过位置越限锁存，"
                       "但一旦退出该锁存立刻生效，关节停在限外时重启会重新锁死。"),
                  note("保活期间 SDK 会拒绝其它动作类命令（查询类不受限）；"
                       "急停/失能永远可达。"))

        self.banner = LockBanner()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.banner)
        lay.addWidget(g)
        lay.addStretch(1)

    # ---------------- 外部状态 ----------------
    def set_online(self, onl: bool):
        self._online = onl
        self._refresh()

    def set_busy(self, busy: bool):
        self._busy = busy
        self._refresh()

    def set_armed(self, armed: bool):
        self._armed = armed
        self._refresh()

    def set_fault_blocked(self, blocked: bool):
        self._fault_blocked = blocked
        self._refresh()

    def _refresh(self):
        can = self._online and not self._busy
        # 进入要走解锁；退出**永远**放行，否则会把人锁在里面 —— 所以判定里带上 _active
        ready = self.banner.set_gate(
            online=self._online, can_move=self._active or self._armed,
            fault_blocked=self._fault_blocked)
        self.btn.setEnabled(ready and not self._busy)
        self.period.setEnabled(can and not self._active)

    def set_state(self, active: bool, error=None):
        """由主窗口按**实际**状态回写（固件可能因看门狗/急停自行退出）。"""
        self._active = bool(active)
        self.btn.blockSignals(True)
        self.btn.setChecked(self._active)
        self.btn.blockSignals(False)
        self.btn.setText("退出零重力拖动" if self._active else "进入零重力拖动")
        self.state_lbl.setText("拖动中（保活运行）" if self._active else "未进入")
        self.state_lbl.setStyleSheet(
            "color:#61afef;font-weight:bold;" if self._active
            else "color:#b0b0b0;font-weight:bold;")
        self.err_lbl.setText("" if error is None else f"⚠ 保活中断: {error}")
        self._refresh()

    def period_value(self) -> float:
        return self.period.value()
