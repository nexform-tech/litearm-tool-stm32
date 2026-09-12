"""控制页 —— enable/disable/clear_faults/home/reset + 速度倍率 + GET_TCP。"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QSlider, QVBoxLayout, QWidget)


class ControlPage(QWidget):
    cmd = pyqtSignal(str)        # 'enable'|'disable'|'clear_faults'|'home'|'reset'
    set_speed = pyqtSignal(int)
    tcp_req = pyqtSignal()
    zero_g = pyqtSignal(bool)    # [段②] 进入(True)/退出(False) 零重力拖动

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
        row2.addWidget(QLabel("全局限速(调速器):"))
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(0, 100)
        self.speed.setValue(100)
        self.speed.setMinimumWidth(220)
        self.speed_label = QLabel("100%")
        self.speed.valueChanged.connect(
            lambda v: self.speed_label.setText(f"{v}%"))
        btn_spd = QPushButton("应用")   # [1.5.1/L5] 调速器=全局封顶: 实际速度=min(命令sp, 本值)
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

        # ---- [段②] 零重力拖动 (拖动示教) ----
        row4 = QHBoxLayout()
        self.btn_zg = QPushButton("进入零重力拖动")
        self.btn_zg.setMinimumHeight(34)
        self.btn_zg.setCheckable(True)
        self.btn_zg.setToolTip(
            "进入后臂进入重力补偿状态, 可用手自由拖动; 松手由虚拟弹簧保持位置。\n\n"
            "⚠ 固件侧靠看门狗保活: 本工具在进入期间以 20Hz 自动重发命令\n"
            "   (每条在固件内都会 kick 看门狗), 因此界面卡死/拔线时臂会\n"
            "   自动落到 fail-soft 持位, 不会失控。\n"
            "⚠ 退出前先把关节推回软限位内 —— 零重力会跳过位置越限锁存,\n"
            "   但一旦退出该锁存立刻生效, 且关节停在限外时重启会重新锁死。")
        self.btn_zg.clicked.connect(self._on_zg_clicked)
        self.zg_lbl = QLabel("")
        self.zg_lbl.setStyleSheet("color:#888;")
        row4.addWidget(self.btn_zg)
        row4.addWidget(self.zg_lbl)
        row4.addStretch(1)
        g.addLayout(row4)

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
        self.btn_zg.setEnabled(onl)          # 保活期间不禁用, 否则退不出去

    # ---- [段②] 零重力拖动 ----
    def _on_zg_clicked(self, checked: bool):
        self.zero_g.emit(bool(checked))

    def set_zero_g_state(self, on: bool, text: str = ""):
        """由主窗口回写【实际】状态 (以固件 mode 为准, 不只跟随按钮)。

        例如固件因看门狗/急停退出零重力时, 主窗口会把按钮复位回去。
        """
        self.btn_zg.blockSignals(True)
        self.btn_zg.setChecked(on)
        self.btn_zg.blockSignals(False)
        self.btn_zg.setText("退出零重力拖动" if on else "进入零重力拖动")
        self.zg_lbl.setText(text)

    def set_tcp_text(self, text: str):
        self.tcp_lbl.setText(text)

    def refresh_fault_hint(self, status):
        """FAULT/EMERGENCY 时提示需先 reset；enable 按钮据此禁用。"""
        if status is None:
            self.hint_lbl.setText("")
            return
        if status.mode == 6:   # EMERGENCY
            self.hint_lbl.setText("⚠ 急停锁存中 —— 仅 [复位 reset] 可退出 EMERGENCY"
                                  "（固件 1.5.0/M3：失能不再解除锁存）")
            self.btn_enable.setEnabled(False)
        elif status.has_fault:
            self.hint_lbl.setText("⚠ 检测到故障位 —— 建议先 [清故障 clear_faults]，仍不行则 [复位 reset]")
            self.btn_enable.setEnabled(False)
        else:
            self.hint_lbl.setText("")
            if self._online and not getattr(self, "_busy", False):
                self.btn_enable.setEnabled(True)
