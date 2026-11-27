"""关节页 —— 关节空间的运动命令：movej / move_js / move_mit / move_mit_all。

对应 SDK：`movej` `move_js` `send_mit` `send_mit_all`（`home` 在整机页）。
本页只取值发信号；Δq 确认与解锁由 MainWindow 收口。
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

from litetool.gui.pages.common import (JointRow, LockBanner, group, hint, note,
                                       row, spin)

#: 就绪姿态（与 studio 同名常量）。按当前轴数裁剪，缺的补 0。
READY_POSE = (0.0, 0.5, 0.0, -1.0, 0.0, 0.6, 0.0)


class JointPage(QWidget):
    movej = pyqtSignal(list, float)                                  # qs, speed
    move_js = pyqtSignal(list, list, object)                         # q, dq, tau_ff|None
    mit_one = pyqtSignal(int, float, float, float, float, float)     # idx,q,dq,kp,kd,tau
    mit_all = pyqtSignal(list, list, list, list, list)               # q,dq,kp,kd,tau

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._online = False
        self._busy = False
        self._armed = False
        self._fault_blocked = False
        self._seeded = False        # 目标输入框是否已用实测位填过一次
        self._n = 0

        # ---------------- movej ----------------
        self.mj_row = JointRow()
        self.mj_speed = spin(0.01, settings.speed_max_ui, settings.default_speed, 0.05)
        self.btn_mj = QPushButton("下发 movej")
        self.btn_mj.clicked.connect(
            lambda: self.movej.emit(self.mj_row.value(), self.mj_speed.value()))
        self.btn_ready = QPushButton("就绪姿态")
        self.btn_ready.setToolTip(
            "把目标填成就绪姿态 [0, 0.5, 0, -1, 0, 0.6, 0]（按轴数裁剪/补 0）\n"
            "并立即下发 movej。仍走运动解锁与 Δq 确认。")
        self.btn_ready.clicked.connect(self._emit_ready)
        g_mj = group("move_j —— 关节轨迹（绝对角 rad，固件 S 曲线自完成 + 到位静止保持）",
                     self.mj_row,
                     row(QLabel("速度倍率 (0..1)"), self.mj_speed,
                         self.btn_ready, self.btn_mj))

        # ---------------- move_js ----------------
        self.js_q = JointRow()
        self.js_dq = JointRow()
        self.js_tau = JointRow()
        self.js_use_tau = QCheckBox("带 tau_ff 前馈")
        self.btn_js = QPushButton("单发 move_js")
        self.btn_js.clicked.connect(self._emit_js)
        g_js = group("move_js —— 连续伺服透传（单发）",
                     self.js_q, row(QLabel("dq (rad/s)")), self.js_dq,
                     row(self.js_use_tau), self.js_tau,
                     row(self.btn_js),
                     hint("⚠ 固件 0.1s 看门狗：连续伺服须以 ≥10Hz 重发，"
                          "否则 0.1s 后掉 fail-soft 持位。本页只做单发。"))

        # ---------------- move_mit 单关节 ----------------
        self.mm_idx = QComboBox()
        self.mm_spins = {}
        mm = QGridLayout()
        mm.addWidget(QLabel("关节"), 0, 0)
        mm.addWidget(self.mm_idx, 0, 1)
        fields = (("q (rad)", -6.28, 6.28, 0.0),
                  ("dq (rad/s)", -30.0, 30.0, 0.0),
                  ("kp", 0.0, 500.0, settings.mit_kp_default),
                  ("kd", 0.0, 5.0, settings.mit_kd_default),
                  ("tau (Nm)", -120.0, 120.0, settings.mit_tau_default))
        for c, (lab, lo, hi, val) in enumerate(fields, start=2):
            mm.addWidget(QLabel(lab), 0, c)
            sp = spin(lo, hi, val)
            self.mm_spins[lab.split()[0]] = sp
            mm.addWidget(sp, 1, c)
        self.btn_mm = QPushButton("下发 move_mit 单帧")
        self.btn_mm.clicked.connect(self._emit_mit)
        mm.addWidget(self.btn_mm, 1, len(fields) + 2)
        g_mm = group("move_mit —— 单关节 MIT 透传（单帧，无保活）", mm)

        # ---------------- move_mit_all ----------------
        self.ma_q = JointRow()
        self.ma_dq = JointRow()
        self.ma_tau = JointRow()
        self.ma_kp = spin(0.0, 500.0, settings.mit_kp_default)
        self.ma_kd = spin(0.0, 5.0, settings.mit_kd_default)
        self.btn_ma = QPushButton("下发整臂 MIT 单帧")
        self.btn_ma.clicked.connect(self._emit_mit_all)
        g_ma = group("move_mit_all —— 整臂 MIT 透传（单帧）",
                     self.ma_q, row(QLabel("dq")), self.ma_dq,
                     row(QLabel("kp(统一)"), self.ma_kp, QLabel("kd(统一)"), self.ma_kd),
                     row(QLabel("tau")), self.ma_tau,
                     row(self.btn_ma),
                     note("kp/kd 对全部关节统一；要逐关节不同请用单关节 move_mit。"))

        self.banner = LockBanner()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.banner)
        lay.addWidget(g_mj)
        lay.addWidget(g_js)
        lay.addWidget(g_mm)
        lay.addWidget(g_ma)
        lay.addStretch(1)

    # ---------------- 关节数 ----------------
    def set_joints(self, n: int):
        if n == self._n:
            return
        self._n = n
        for r in (self.mj_row, self.js_q, self.js_dq, self.js_tau,
                  self.ma_q, self.ma_dq, self.ma_tau):
            r.set_joints(n)
        self.mm_idx.clear()
        self.mm_idx.addItems([f"J{j + 1}" for j in range(n)])

    # ---------------- 外部状态 ----------------
    def set_online(self, onl: bool):
        self._online = onl
        if not onl:
            self._seeded = False        # 下次连接重新带入当前姿态
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
        ready = self.banner.set_gate(
            online=self._online,
            can_move=self._armed and not self._fault_blocked,
            fault_blocked=self._fault_blocked)
        can = ready and not self._busy
        for b in (self.btn_mj, self.btn_ready, self.btn_js, self.btn_mm, self.btn_ma):
            b.setEnabled(can and self._n > 0)
        # ⚠ **输入控件始终可编辑**：填目标角/参数不是危险动作，运动闸门只拦
        # "执行"（按钮）。原实现把它们一起禁掉，导致"没解锁时连数字都输不进去"
        # —— 用户看到的不是"需要解锁"，而是"这个页面坏了"。
        for w in (self.mj_row, self.js_q, self.js_dq, self.js_tau,
                  self.ma_q, self.ma_dq, self.ma_tau, self.mm_idx,
                  self.js_use_tau, self.ma_kp, self.ma_kd, self.mj_speed):
            w.setEnabled(True)
        for sp in self.mm_spins.values():
            sp.setEnabled(True)

    # ---------------- 取值 ----------------
    def _emit_ready(self):
        target = [READY_POSE[i] if i < len(READY_POSE) else 0.0
                  for i in range(self._n)]
        self.mj_row.set_value(target)      # 让操作员看见将要下发的目标
        self.movej.emit(target, self.mj_speed.value())

    def _emit_js(self):
        tau = self.js_tau.value() if self.js_use_tau.isChecked() else None
        self.move_js.emit(self.js_q.value(), self.js_dq.value(), tau)

    def _emit_mit(self):
        i = self.mm_idx.currentIndex()
        if i < 0:
            return
        g = self.mm_spins
        self.mit_one.emit(i, g["q"].value(), g["dq"].value(),
                          g["kp"].value(), g["kd"].value(), g["tau"].value())

    def _emit_mit_all(self):
        n = self._n
        self.mit_all.emit(self.ma_q.value(), self.ma_dq.value(),
                          [self.ma_kp.value()] * n, [self.ma_kd.value()] * n,
                          self.ma_tau.value())

    # ---------------- 便捷：把当前实测角灌进目标输入 ----------------
    def fill_from(self, st):
        """只在**首次**收到状态时把实测位填进目标输入框。

        ⚠ 这些框是**指令**，不是遥测。原实现每 50 ms 无条件覆写 —— 用户敲进去的
        数字还没松开键盘就被实测值盖掉，表现是"根本无法输入"（现场实测）。
        要刷新显示请用总览页的状态表；目标值只由用户或显式按钮决定。
        """
        if st is None or st.n == 0 or self._seeded:
            return
        qs = st.q
        self.mj_row.set_value(qs)
        self.js_q.set_value(qs)
        self.ma_q.set_value(qs)
        self._seeded = True
