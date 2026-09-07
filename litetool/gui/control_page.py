"""控制页 —— enable/disable/clear_faults/home/reset + 速度倍率 + GET_TCP。"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QSlider, QVBoxLayout, QWidget)


class ControlPage(QWidget):
    cmd = pyqtSignal(str)        # 'enable'|'disable'|'clear_faults'|'home'|'reset'
    set_speed = pyqtSignal(int)
    tcp_req = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ops = []
        self._online = False

        grp = QGroupBox("基础控制")
        g = QVBoxLayout(grp)

        row1 = QHBoxLayout()
        self.btn_enable = self._mk(row1, "使能 enable", "enable")
        self.btn_disable = self._mk(row1, "失能 disable", "disable")
        self.btn_clear = self._mk(row1, "清故障 clear_faults", "clear_faults")
        self.btn_home = self._mk(row1, "回零 home", "home")
        self.btn_reset = self._mk(row1, "复位 reset *", "reset")
        row1.addStretch(1)
        g.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("速度倍率:"))
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(0, 100)
        self.speed.setValue(100)
        self.speed.setMinimumWidth(220)
        self.speed_label = QLabel("100%")
        self.speed.valueChanged.connect(
            lambda v: self.speed_label.setText(f"{v}%"))
        btn_spd = QPushButton("应用")
        btn_spd.clicked.connect(lambda: self.set_speed.emit(self.speed.value()))
        row2.addWidget(self.speed)
        row2.addWidget(self.speed_label)
        row2.addWidget(btn_spd)
        row2.addStretch(1)
        g.addLayout(row2)

        row3 = QHBoxLayout()
        btn_tcp = QPushButton("读取末端位姿 (GET_TCP)")
        btn_tcp.clicked.connect(self.tcp_req.emit)
        self.tcp_lbl = QLabel("—")
        self.tcp_lbl.setStyleSheet("color:#61afef;")
        row3.addWidget(btn_tcp)
        row3.addWidget(self.tcp_lbl)
        row3.addStretch(1)
        g.addLayout(row3)

        self.hint_lbl = QLabel("")
        self.hint_lbl.setWordWrap(True)
        g.addWidget(self.hint_lbl)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(grp)
        lay.addStretch(1)
        self._ops = [self.btn_enable, self.btn_disable, self.btn_clear,
                     self.btn_home, self.btn_reset]

    def _mk(self, lay, text, name):
        b = QPushButton(text)
        b.setMinimumHeight(34)
        b.clicked.connect(lambda: self.cmd.emit(name))
        lay.addWidget(b)
        return b

    def set_online(self, onl: bool):
        self._online = onl
        self._refresh_ops()

    def set_busy(self, busy: bool):
        self._busy = busy
        self._refresh_ops()

    def _refresh_ops(self):
        onl = getattr(self, "_online", False)
        busy = getattr(self, "_busy", False)
        for b in self._ops:
            b.setEnabled(onl and not busy)

    def set_tcp_text(self, text: str):
        self.tcp_lbl.setText(text)

    def refresh_fault_hint(self, status):
        """FAULT/EMERGENCY 时提示需先 reset；enable 按钮据此禁用。"""
        if status is None:
            self.hint_lbl.setText("")
            return
        if status.mode == 6:   # EMERGENCY
            self.hint_lbl.setText("⚠ 急停锁存中 —— 需先 [失能 disable] 或 [复位 reset] 退出 EMERGENCY，然后重新使能")
            self.btn_enable.setEnabled(False)
        elif status.has_fault:
            self.hint_lbl.setText("⚠ 检测到故障位 —— 建议先 [清故障 clear_faults]，仍不行则 [复位 reset]")
            self.btn_enable.setEnabled(False)
        else:
            self.hint_lbl.setText("")
            if self._online and not getattr(self, "_busy", False):
                self.btn_enable.setEnabled(True)
