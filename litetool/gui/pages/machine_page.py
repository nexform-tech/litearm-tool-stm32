"""整机页 —— 臂级命令：使能/失能/复位/清故障/回零 + 全局限速 + park + 读状态。

对应 SDK：`enable` `disable` `reset` `clear_faults` `home` `set_speed` `park`
`set_motion_mode` `get_status_now` `last_reset_reason`。
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QLabel, QPushButton, QSlider,
                             QVBoxLayout, QWidget)

from litetool import i18n
from litetool.gui.i18n_ui import TrButton, TrLabel, tr_tooltip
from litetool.gui.pages.common import LockBanner, group, hint, note, row

_MOVE_OPS = ("home",)          # 会动臂的按钮 —— 运动解锁才放行


class MachinePage(QWidget):
    cmd = pyqtSignal(str)              # enable/disable/reset/clear_faults
    home_req = pyqtSignal()
    set_speed = pyqtSignal(int)
    park_req = pyqtSignal()
    status_now = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._online = False
        self._busy = False
        self._armed = False
        self._fault_blocked = False
        self._st = None
        self._metrics = None

        self.btn_enable = self._btn("使能 enable", "enable")
        self.btn_disable = self._btn("失能 disable", "disable")
        self.btn_clear = self._btn("清故障 clear_faults", "clear_faults")
        self.btn_reset = self._btn("复位 reset", "reset")
        self.btn_home = TrButton("回零 home")
        self.btn_home.setMinimumHeight(34)
        tr_tooltip(
            self.btn_home,
            "固件 CMD_HOME 0x2A：各轴低速(固件写死 0.10)回 URDF 零位。\n"
            "与 movej(0) 同一条路径，只是速度更低。需先使能。")
        self.btn_home.clicked.connect(self.home_req.emit)

        g_ctrl = group("臂级控制", row(self.btn_enable, self.btn_disable,
                                       self.btn_clear, self.btn_reset,
                                       self.btn_home))

        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(0, 100)
        self.speed.setValue(100)
        self.speed.setMinimumWidth(240)
        self.speed_lbl = QLabel("100%")
        self.speed.valueChanged.connect(lambda v: self.speed_lbl.setText(f"{v}%"))
        self.btn_speed = TrButton("应用")
        self.btn_speed.clicked.connect(lambda: self.set_speed.emit(self.speed.value()))
        self.btn_park = TrButton("park（静止保持用全刚度）")
        self.btn_park.clicked.connect(self.park_req.emit)
        g_speed = group(
            "全局调速器（0..100 整数百分比）",
            row(TrLabel("限速"), self.speed, self.speed_lbl, self.btn_speed, self.btn_park),
            note("实际速度 = min(单条 movej 的 speed, 本值)。注意这里是百分比："
                 "填 1 就是 1% 速度（爬行），不是 0..1 倍率。"),
        )

        self.btn_status = TrButton("读取状态 GET_STATUS")
        self.btn_status.clicked.connect(self.status_now.emit)
        self.status_lbl = QLabel("—")
        self.status_lbl.setStyleSheet("color:#61afef;")
        self.reset_lbl = QLabel("—")
        self.reset_lbl.setStyleSheet("color:#c8c8c8;")
        g_status = group("链路与启动信息",
                         row(self.btn_status, self.status_lbl),
                         row(TrLabel("上次启动原因"), self.reset_lbl),
                         note("固件开机签名里的 IWDG 标注 —— 若为 iwdg-rst 说明上电是看门狗复位，"
                              "排查完再动臂。"))

        self.hint_lbl = hint("")
        self.hint_lbl.setVisible(False)

        # 灰按钮必须自己解释为什么灰 —— [回零] 点不动时用户只有这一条线索
        self.banner = LockBanner()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.banner)
        lay.addWidget(self.hint_lbl)
        lay.addWidget(g_ctrl)
        lay.addWidget(g_speed)
        lay.addWidget(g_status)
        lay.addStretch(1)
        self._ops = [self.btn_enable, self.btn_disable, self.btn_clear, self.btn_reset]

    def _btn(self, text: str, name: str) -> QPushButton:
        b = TrButton(text)
        b.setMinimumHeight(34)
        b.clicked.connect(lambda: self.cmd.emit(name))
        return b

    # ---- 外部状态 ----
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
        """主窗口按状态帧推过来（本页 `update_from` 也会从同一来源推导，两者同值）。"""
        self._fault_blocked = blocked
        self._refresh()

    def update_from(self, st):
        """状态帧驱动：EMERGENCY 锁存/故障位时禁用 enable 并给提示。"""
        self._st = st
        if st is None:
            # 离线：故障锁存未知，别让上一条连接的状态残留着挡住按钮
            self._fault_blocked = False
            self.hint_lbl.setVisible(False)
            self._refresh()
            return
        if st.mode_name == "EMERGENCY":
            self._fault_blocked = True
            self.hint_lbl.setText(i18n.tr(
                "⚠ 急停锁存中 —— 仅 [复位 reset] 可退出 EMERGENCY（固件 1.5.0/M3："
                "失能不再解除锁存）"))
        elif st.faulted:
            self._fault_blocked = True
            axes = "".join(f" J{a + 1}" for a in st.fault_axes)
            self.hint_lbl.setText(i18n.tr(
                "⚠ 检测到故障位（{detail}）—— 建议先 [清故障 clear_faults]，"
                "仍不行则 [复位 reset]。{axes}",
                detail=st.fault_detail,
                axes=(i18n.tr(" 断轴:{axes}", axes=axes) if axes else "")))
        else:
            self._fault_blocked = False
            self.hint_lbl.setVisible(False)
        if self._fault_blocked:
            self.hint_lbl.setVisible(True)
        self._refresh()

    def set_metrics(self, drops: int, fps: float, reset_reason):
        self._metrics = (drops, fps, reset_reason)
        self.reset_lbl.setText("—" if reset_reason is None else str(reset_reason))

    def retranslate(self):
        self.update_from(self._st)
        self.speed_lbl.setText(f"{self.speed.value()}%")
        if self._metrics is not None:
            self.set_metrics(*self._metrics)

    def set_status_text(self, text: str):
        self.status_lbl.setText(text)

    def _refresh(self):
        can = self._online and not self._busy
        for b in self._ops:
            b.setEnabled(can)
        # 回零会动臂：横幅与按钮取**同一判定**，不会出现"说解锁了却点不动"
        ready = self.banner.set_gate(
            online=self._online,
            can_move=self._armed and not self._fault_blocked,
            fault_blocked=self._fault_blocked)
        self.btn_home.setEnabled(ready and not self._busy)
        self.btn_park.setEnabled(can)
        self.btn_status.setEnabled(can)
        # 限速是输入，不是动作：始终可编辑
        self.speed.setEnabled(True)
        self.btn_speed.setEnabled(can)
        self.btn_enable.setEnabled(can and not self._fault_blocked)
