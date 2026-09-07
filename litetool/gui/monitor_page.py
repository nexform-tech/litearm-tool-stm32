"""监控页 —— 状态条（模式/6 flag 灯/seq 丢帧/帧率/坏帧）+ 逐关节表格。"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from litetool import protocol as P


class MonitorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._temp_alert = 85.0
        self._n = 0

        # 状态条
        self.mode_lbl = QLabel("—")
        self.flag_chips = []
        row = QHBoxLayout()
        row.addWidget(QLabel("模式:"))
        row.addWidget(self.mode_lbl)
        row.addSpacing(16)
        for bit in range(6):
            chip = QLabel(P.FLAG_NAMES[bit])
            chip.setStyleSheet(
                "QLabel{background:#3a3a3a;color:#b0b0b0;border-radius:4px;"
                "padding:2px 8px;font-size:11px;}")
            self.flag_chips.append(chip)
            row.addWidget(chip)
        row.addStretch(1)
        self.seq_lbl = QLabel("seq: —")
        self.fps_lbl = QLabel("帧率: —")
        self.bad_lbl = QLabel("坏帧: 0")
        for w in (self.seq_lbl, self.fps_lbl, self.bad_lbl):
            row.addWidget(w)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["关节", "q (rad)", "dq (rad/s)", "tau (Nm)",
             "T_mos (°C)", "T_coil (°C)", "err"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(row)
        lay.addWidget(self.table)

    def set_temp_alert(self, c: float):
        self._temp_alert = c

    def _reset_table(self, n: int):
        self.table.setRowCount(n)
        for i in range(n):
            idx = QTableWidgetItem(f"J{i + 1}")
            idx.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, idx)
            for col in range(1, 7):
                it = QTableWidgetItem("—")
                it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, col, it)

    def update_from(self, view, bad_frames: int, fps: float, seq_drops: int):
        """view: client.StatusView | None；fps 为主线程按 seq 差分估算值。"""
        if view is None:
            self.mode_lbl.setText("—")
            return
        n = view.n
        if n != self._n:
            self._n = n
            self._reset_table(n)

        # 模式
        mode = view.mode
        color = {"INIT": "#b0b0b0", "MOVE_J": "#6fdd8b", "MOVE_P": "#6fdd8b",
                 "MOVE_JS": "#6fdd8b", "MOVE_MIT": "#6fdd8b", "MIT_ALL": "#6fdd8b",
                 "EMERGENCY": "#ff6b6b"}.get(view.mode_name, "#b0b0b0")
        self.mode_lbl.setText(view.mode_name)
        self.mode_lbl.setStyleSheet(f"color:{color}; font-weight:bold;")

        # flag 灯
        for bit, chip in enumerate(self.flag_chips):
            on = bool(view.flags & (1 << bit))
            chip.setStyleSheet(
                "QLabel{background:%s;color:%s;border-radius:4px;padding:2px 8px;"
                "font-size:11px;}" % (
                    ("#ff6b6b" if on else "#3a3a3a"),
                    ("#ffffff" if on else "#b0b0b0")))
        self.seq_lbl.setText(f"seq: {view.seq}  丢帧: {seq_drops}")
        self.fps_lbl.setText(f"帧率: {fps:.0f}Hz")
        self.bad_lbl.setText(f"坏帧: {bad_frames}")

        # 表格逐关节
        for i, js in enumerate(view.joints):
            vals = [f"{js.q:.3f}", f"{js.dq:.3f}", f"{js.tau:.3f}",
                    f"{js.t_mos:.1f}", f"{js.t_coil:.1f}", f"0x{js.err:02X}"]
            warn = js.t_mos > self._temp_alert or js.t_coil > self._temp_alert
            err = js.err != 0
            for col, text in enumerate(vals, start=1):
                it = self.table.item(i, col)
                it.setText(text)
                if err and col in (1, 2, 3):
                    it.setBackground(QBrush(QColor("#8b3a3a")))
                elif warn and col in (4, 5):
                    it.setBackground(QBrush(QColor("#8a7a2a")))
                else:
                    it.setBackground(QBrush(QColor("transparent")))
