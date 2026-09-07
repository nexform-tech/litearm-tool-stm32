"""运动页 —— move_j / move_mit 单帧下发，默认锁定 + 勾选确认解锁。

安全模型（意图层，权威仍在固件）：本页只负责"操作意图"确认—— 解锁勾选 +
Δq 确认框（后者在 MainWindow 侧用 checks.plan_motion 实现，弹窗后放行）。
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox,
                             QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

Q_RANGE = (-6.28, 6.28)          # 目标角输入范围(rad)
STEP = 0.01


class MotionPage(QWidget):
    move_j = pyqtSignal(list, float)                 # qs, speed
    move_mit = pyqtSignal(int, float, float, float, float, float)  # idx,q,dq,kp,kd,tau

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._locked = True
        self._online = False
        self._busy = False
        self._n = 0
        self._qs = []
        self._joint_labels = []

        # 横幅 + 解锁
        self.banner = QLabel()
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setMinimumHeight(36)
        self.banner.setStyleSheet(
            "font-weight:bold;font-size:15px;border-radius:4px;")
        self.unlock_cb = QCheckBox("我已确认机械臂周围无障碍、急停按钮可及")
        self.unlock_cb.toggled.connect(self._on_unlock_toggled)

        self.mj_group = QGroupBox("move_j —— 关节轨迹(绝对角, rad) + 速度倍率")
        mj = QVBoxLayout(self.mj_group)
        self.mj_grid = QGridLayout()
        mj.addLayout(self.mj_grid)
        row = QHBoxLayout()
        row.addWidget(QLabel("速度倍率:"))
        self.spin_spd = QDoubleSpinBox()
        self.spin_spd.setRange(0.01, settings.speed_max_ui)
        self.spin_spd.setValue(settings.default_speed)
        self.spin_spd.setSingleStep(0.05)
        row.addWidget(self.spin_spd)
        self.btn_mj = QPushButton("下发 move_j")
        self.btn_mj.clicked.connect(self._emit_mj)
        row.addWidget(self.btn_mj)
        row.addStretch(1)
        mj.addLayout(row)

        self.mm_group = QGroupBox("move_mit —— 单关节 MIT 透传单帧")
        mm = QGridLayout(self.mm_group)
        mm.addWidget(QLabel("关节"), 0, 0)
        self.mm_idx = QComboBox()
        mm.addWidget(self.mm_idx, 0, 1)
        fields = [("q 目标 (rad)", -6.28, 6.28, 0.0),
                  ("dq (rad/s)", -30.0, 30.0, 0.0),
                  ("kp", 0.0, 500.0, settings.mit_kp_default),
                  ("kd", 0.0, 5.0, settings.mit_kd_default),
                  ("tau (Nm)", -10.0, 10.0, settings.mit_tau_default)]
        self.mm_spins = {}
        for c, (lab, lo, hi, val) in enumerate(fields, start=2):
            mm.addWidget(QLabel(lab), 0, c)
        for r in range(1, 2):
            for c, (lab, lo, hi, val) in enumerate(fields, start=2):
                sp = QDoubleSpinBox()
                sp.setRange(lo, hi)
                sp.setValue(val)
                sp.setDecimals(3)
                sp.setSingleStep(STEP)
                self.mm_spins[lab.split()[0]] = sp
                mm.addWidget(sp, r, c)
        self.btn_mm = QPushButton("下发 move_mit 单帧")
        self.btn_mm.clicked.connect(self._emit_mm)
        mm.addWidget(self.btn_mm, r, len(fields) + 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.banner)
        lay.addWidget(self.unlock_cb)
        lay.addWidget(self.mj_group)
        lay.addWidget(self.mm_group)
        lay.addStretch(1)
        self._apply_locked_state()

    def set_joints(self, n: int):
        if n == self._n:
            return
        self._n = n
        # 重建 move_j 输入行
        while self.mj_grid.count():
            item = self.mj_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._qs = []
        for j in range(n):
            self.mj_grid.addWidget(QLabel(f"J{j + 1}"), j, 0)
            sp = QDoubleSpinBox()
            sp.setRange(*Q_RANGE)
            sp.setDecimals(3)
            sp.setSingleStep(STEP)
            self.mj_grid.addWidget(sp, j, 1)
            self._qs.append(sp)
        self.mm_idx.clear()
        self.mm_idx.addItems([f"J{j + 1}" for j in range(n)])

    # ---- 在线 / 忙状态 ----
    def set_online(self, onl: bool):
        self._online = onl
        self.unlock_cb.setEnabled(onl)
        self._apply_locked_state()

    def set_busy(self, busy: bool):
        self._busy = busy
        self._apply_locked_state()

    # ---- 锁定/解锁 ----
    def _on_unlock_toggled(self, checked: bool):
        if checked:
            self._locked = False
            self._apply_locked_state()
        else:
            self._locked = True
            self._apply_locked_state()

    def lock(self, reason: str = "未知原因"):
        """强制锁定（急停/离线/故障/复位后调用）。"""
        self._locked = True
        self.unlock_cb.blockSignals(True)
        self.unlock_cb.setChecked(False)
        self.unlock_cb.blockSignals(False)
        self._lock_reason = reason
        self._apply_locked_state()

    def _apply_locked_state(self):
        locked = self._locked or not self._online or self._busy
        if self._locked:
            reason = getattr(self, "_lock_reason", "安全横幅提示")
            self.banner.setText(f"⛔ 运动控制已锁定 — {reason}")
            self.banner.setStyleSheet(
                "background:#5a4a2a;color:#ffd166;font-weight:bold;"
                "font-size:15px;border-radius:4px;")
        else:
            self.banner.setText("✔ 运动控制已解锁 — 请谨慎操作，急停随时可用")
            self.banner.setStyleSheet(
                "background:#2a5a3a;color:#6fdd8b;font-weight:bold;"
                "font-size:15px;border-radius:4px;")
        can_use = not locked
        self.btn_mj.setEnabled(can_use and self._qs)
        self.btn_mm.setEnabled(can_use)
        for sp in self._qs:
            sp.setEnabled(can_use)
        self.spin_spd.setEnabled(can_use)

    # ---- 取值发射 ----
    def _emit_mj(self):
        self.move_j.emit([sp.value() for sp in self._qs], self.spin_spd.value())

    def _emit_mm(self):
        idx = self.mm_idx.currentIndex()
        if idx < 0:
            return
        g = self.mm_spins
        self.move_mit.emit(idx, g["q"].value(), g["dq"].value(),
                           g["kp"].value(), g["kd"].value(), g["tau"].value())
