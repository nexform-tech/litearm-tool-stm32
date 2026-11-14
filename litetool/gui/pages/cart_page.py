"""笛卡尔页 —— 末端位姿：get_tcp / ik / move_p。

对应 SDK：`get_tcp` `ik`（固件后台 IK，seed 恒为模型 7 轴）`move_p`（固件 IK + S 曲线）。
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QLabel, QPlainTextEdit, QPushButton,
                             QVBoxLayout, QWidget)

from litetool.gui.pages.common import (LockBanner, PoseInput, group, hint, note,
                                       row, spin)


class CartPage(QWidget):
    tcp_req = pyqtSignal()
    ik_req = pyqtSignal(list, object)        # pose, q_seed|None
    movep = pyqtSignal(list, float)          # pose, speed

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._online = False
        self._busy = False
        self._armed = False
        self._fault_blocked = False
        self._tcp = None
        self._seed_q = None

        # ---------------- 当前位姿 ----------------
        self.btn_tcp = QPushButton("读取当前末端位姿 (GET_TCP)")
        self.btn_tcp.clicked.connect(self.tcp_req.emit)
        self.btn_fill = QPushButton("填入下方目标位姿")
        self.btn_fill.clicked.connect(lambda: self.pose.set_value(self._tcp))
        self.tcp_lbl = QLabel("—")
        self.tcp_lbl.setStyleSheet("color:#61afef;font-family:'DejaVu Sans Mono';")
        g_now = group("当前末端位姿 pos[3] + rpy[3]",
                      row(self.btn_tcp, self.btn_fill),
                      self.tcp_lbl)

        # ---------------- 目标位姿（movep 与 ik 共用同一组输入） ----------------
        self.pose = PoseInput()
        self.speed = spin(0.01, settings.speed_max_ui, settings.default_speed, 0.05)
        self.btn_mp = QPushButton("下发 movep")
        self.btn_mp.clicked.connect(lambda: self.movep.emit(self.pose.value(),
                                                            self.speed.value()))
        self.btn_ik = QPushButton("求解 IK（只算不动）")
        self.btn_ik.clicked.connect(self._emit_ik)
        self.seed_cb = QCheckBox("用当前实测关节角作 IK 种子")
        self.seed_cb.setChecked(True)
        self.ik_out = QPlainTextEdit()
        self.ik_out.setReadOnly(True)
        self.ik_out.setMaximumHeight(80)

        g_tgt = group("目标位姿（movep 与 ik 共用这组数值）",
                      self.pose,
                      row(QLabel("速度倍率 (0..1)"), self.speed, self.btn_mp),
                      row(self.btn_ik, self.seed_cb),
                      self.ik_out,
                      note("move_p：固件后台 IK → S 曲线 → 按 TCP 到位判定。"
                           "ik：只求解不动臂；种子恒为**模型 7 轴**（与关节数解耦）。"))

        self.hint_lbl = hint("⚠ movep 按输入框里的位姿运动 —— 下发前请核对数值。")

        self.banner = LockBanner()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.banner)
        lay.addWidget(g_now)
        lay.addWidget(g_tgt)
        lay.addWidget(self.hint_lbl)
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
        move_can = self.banner.set_gate(
            online=self._online,
            can_move=self._armed and not self._fault_blocked,
            fault_blocked=self._fault_blocked) and not self._busy
        self.btn_tcp.setEnabled(can)
        self.btn_fill.setEnabled(can)
        self.btn_ik.setEnabled(can)
        self.seed_cb.setEnabled(can)
        self.btn_mp.setEnabled(move_can)
        # 速度是输入，不是动作：始终可编辑（同关节页）
        self.speed.setEnabled(True)
        # 输入框始终可编辑 —— 否则离线时连"先把目标算好"都做不到
        self.pose.setEnabled(True)

    # ---------------- 回填 ----------------
    def show_tcp(self, tcp):
        self._tcp = tcp
        self.tcp_lbl.setText("—" if tcp is None
                             else "  ".join(f"{v:+.4f}" for v in tcp))

    def show_ik(self, qs):
        self.ik_out.setPlainText("  ".join(f"{v:+.4f}" for v in qs))

    def show_ik_error(self, msg: str):
        self.ik_out.setPlainText(f"失败：{msg}")

    def set_seed_q(self, qs):
        """主窗口把当前实测角灌进来，作为可选 IK 种子。"""
        self._seed_q = list(qs) if qs else None

    def _emit_ik(self):
        self.ik_req.emit(self.pose.value(),
                         self._seed_q if self.seed_cb.isChecked() else None)
