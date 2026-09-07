"""监控页 —— 状态条（模式/6 flag 灯/seq 丢帧/帧率/坏帧）+ 逐关节表格。

设计要点（用户反馈）：
- 布局固定：静态文字与其位置不变；数值放固定宽度等宽小格，只变数字不挤动相邻控件。
- 最小重绘：值/颜色真正变化才更新（setText/setStyleSheet/背景），避免整行 50ms 闪烁。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from litetool import protocol as P

_MODE_COLOR = {"INIT": "#b0b0b0", "MOVE_J": "#6fdd8b", "MOVE_P": "#6fdd8b",
               "MOVE_JS": "#6fdd8b", "MOVE_MIT": "#6fdd8b", "MIT_ALL": "#6fdd8b",
               "EMERGENCY": "#ff6b6b"}
_CHIP_ON = "QLabel{background:#ff6b6b;color:#ffffff;border-radius:4px;padding:2px 8px;font-size:11px;}"
_CHIP_OFF = "QLabel{background:#3a3a3a;color:#b0b0b0;border-radius:4px;padding:2px 8px;font-size:11px;}"
_MONO = QFont("DejaVu Sans Mono", 11)


def _num_label(width: int) -> QLabel:
    """固定宽度、等宽、左对齐的数值小格：数字变化不挤动相邻控件。"""
    lb = QLabel("—")
    lb.setFont(_MONO)
    lb.setFixedWidth(width)
    lb.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return lb


def _static(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet("color:#a0a0a0;")
    return lb


class MonitorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._temp_alert = 85.0
        self._n = 0

        # ---- 状态条（布局固定） ----
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(_static("模式"))
        self.mode_lbl = QLabel("—")
        self.mode_lbl.setFont(_MONO)
        self.mode_lbl.setFixedWidth(76)
        row.addWidget(self.mode_lbl)

        # 6 个 flag 灯：等宽固定，仅颜色随置位变化
        self.flag_chips = []
        self._chip_on = [False] * 6
        for bit in range(6):
            chip = QLabel(P.FLAG_NAMES[bit])
            chip.setFixedWidth(88)
            chip.setAlignment(Qt.AlignCenter)
            chip.setStyleSheet(_CHIP_OFF)
            self.flag_chips.append(chip)
            row.addWidget(chip)
        row.addStretch(1)

        # 数值指标：静态 caption + 固定宽度数值格
        self.seq_val = _num_label(44)
        self.drops_val = _num_label(56)
        self.fps_val = _num_label(48)
        self.bad_val = _num_label(44)
        for cap, val in (("seq", self.seq_val), ("丢帧", self.drops_val),
                         ("帧率", self.fps_val), ("坏帧", self.bad_val)):
            row.addSpacing(10)
            row.addWidget(_static(cap))
            row.addWidget(val)
        self._last = {"seq": None, "drops": None, "fps": None, "bad": None,
                      "mode": None}

        # ---- 逐关节表格 ----
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["关节", "q (rad)", "dq (rad/s)", "tau (Nm)",
             "T_mos (°C)", "T_coil (°C)", "err"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._cell_text = {}          # (row,col) -> 上次文本
        self._cell_bg = {}            # (row,col) -> 上次背景名(normal/warn/err)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(row)
        lay.addWidget(self.table)

    def set_temp_alert(self, c: float):
        self._temp_alert = c

    def _reset_table(self, n: int):
        self.table.setRowCount(n)
        self._cell_text.clear()
        self._cell_bg.clear()
        for i in range(n):
            idx = QTableWidgetItem(f"J{i + 1}")
            idx.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, idx)
            self._cell_text[(i, 0)] = idx.text()
            for col in range(1, 7):
                it = QTableWidgetItem("—")
                it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, col, it)
                self._cell_text[(i, col)] = "—"
                self._cell_bg[(i, col)] = "normal"

    def _set_cell(self, i: int, col: int, text: str, bg: str):
        key = (i, col)
        item = self.table.item(i, col)
        if item is None:
            return
        changed = False
        if self._cell_text.get(key) != text:
            self._cell_text[key] = text
            item.setText(text)
            changed = True
        if self._cell_bg.get(key) != bg:            # 背景只在状态变化时重设
            self._cell_bg[key] = bg
            if bg == "err":
                item.setBackground(QBrush(QColor("#8b3a3a")))
            elif bg == "warn":
                item.setBackground(QBrush(QColor("#8a7a2a")))
            else:
                item.setBackground(QBrush(QColor("transparent")))
            changed = True

    def update_from(self, view, bad_frames: int, fps: float, seq_drops: int):
        """view: client.StatusView | None；fps 为主线程按 seq 差分估算值。"""
        if view is None:
            if self.mode_lbl.text() != "—":
                self.mode_lbl.setText("—")
            return
        n = view.n
        if n != self._n:
            self._n = n
            self._reset_table(n)

        # 模式（含颜色）只在变化时更新；文字在固定宽度格内不变位置
        if view.mode_name != self._last["mode"]:
            self._last["mode"] = view.mode_name
            self.mode_lbl.setText(view.mode_name)
            self.mode_lbl.setStyleSheet(
                f"color:{_MODE_COLOR.get(view.mode_name, '#b0b0b0')}; font-weight:bold;")

        # flag 灯：只对置位变化的灯改样式
        for bit, chip in enumerate(self.flag_chips):
            on = bool(view.flags & (1 << bit))
            if on != self._chip_on[bit]:
                self._chip_on[bit] = on
                chip.setStyleSheet(_CHIP_ON if on else _CHIP_OFF)

        # 数值：只在变化时写（值都是等宽小格，文字位置稳定）
        seq = str(view.seq)
        if seq != self._last["seq"]:
            self._last["seq"] = seq
            self.seq_val.setText(seq)
        drops = str(seq_drops)
        if drops != self._last["drops"]:
            self._last["drops"] = drops
            self.drops_val.setText(drops)
        fps_s = f"{fps:.0f}"
        if fps_s != self._last["fps"]:
            self._last["fps"] = fps_s
            self.fps_val.setText(fps_s)
        bad = str(bad_frames)
        if bad != self._last["bad"]:
            self._last["bad"] = bad
            self.bad_val.setText(bad)

        # 表格：逐格只在文本/背景变化时更新
        for i, js in enumerate(view.joints):
            warn = js.t_mos > self._temp_alert or js.t_coil > self._temp_alert
            err = js.err != 0
            cells = ((1, f"{js.q:.3f}", "err" if err else "normal"),
                     (2, f"{js.dq:.3f}", "err" if err else "normal"),
                     (3, f"{js.tau:.3f}", "err" if err else "normal"),
                     (4, f"{js.t_mos:.1f}", "warn" if warn else "normal"),
                     (5, f"{js.t_coil:.1f}", "warn" if warn else "normal"),
                     (6, f"0x{js.err:02X}", "normal"))
            for col, text, bg in cells:
                self._set_cell(i, col, text, bg)
