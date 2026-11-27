"""笛卡尔页 —— 末端位姿：get_tcp / ik / move_p / move_l / 点动 / 受控停止。

对应 SDK：`get_tcp` `ik`（固件后台 IK，seed 恒为模型 7 轴）`move_p`（固件 IK +
S 曲线）`move_l`（固件笛卡尔直线规划）。

三条运动入口的区别（别混）：

* `move_p`：关节空间插值到目标位姿，不是直线；不需要固件笛卡尔规划；
* `move_l`：末端沿起点→目标走直线，姿态 slerp；需要固件 `LITEARM_CART_PLAN`；
* 点动：每一段都是"读当前 TCP → 算一小步 → `move_l`"，按住连续续段，松手
  用 `movej` 到当前关节角受控收口。同样需要笛卡尔规划。

⚠ 点动的每一段都从**实测** TCP 起步，不做积分；段与段之间会停一下（到位判据），
这是固件单槽位规划的代价。急停始终走顶栏的旁路，不受本页状态影响。
"""
from __future__ import annotations

import math

import litearm as pa
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QLabel,
                             QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from litetool import pose_math
from litetool.gui.pages.common import (LockBanner, PoseInput, group, hint, note,
                                       row, spin)

#: 平移步长（mm）/ 旋转步长（度）—— 下拉框里显示的就是它。
TRANS_STEPS = (1, 5, 10, 50)
ROT_STEPS = (1, 5, 10, 30)

_AXES = (("X", "X"), ("Y", "Y"), ("Z", "Z"))


def _jog_label(axis: str, sign: int, kind: str) -> str:
    prefix = "R" if kind == "rotate" else ""
    return f"{prefix}{axis}{'+' if sign > 0 else '−'}"


class CartPage(QWidget):
    tcp_req = pyqtSignal()
    ik_req = pyqtSignal(list, object)        # pose, q_seed|None
    movep = pyqtSignal(list, float)          # pose, speed
    movel = pyqtSignal(list, float)          # pose, speed
    #: 点动一步：axis, kind(translate/rotate), amount(SI), frame(base/tool), speed, gen
    jog_step = pyqtSignal(str, str, float, str, float, int)
    #: 受控停止点动（movej 到当前关节角；旁路，不排队）
    stop_req = pyqtSignal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._online = False
        self._busy = False
        self._armed = False
        self._fault_blocked = False
        self._tcp = None
        self._seed_q = None
        self._cart_ok = None             # True/False/None（未知）
        self._cart_silent = False

        self._jog_holding = False
        self._jog_active = False         # 一次点动会话（按下到收口）
        self._jog_in_flight = False      # 已发一段、结果未回
        self._jog_stop_requested = False
        self._jog_gen = 0
        self._jog_params = ("X", "translate", 1)
        self._jog_buttons = []

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

        # ---------------- 点动 ----------------
        self.frame = QComboBox()
        self.frame.addItem("基座系", "base")
        self.frame.addItem("工具系", "tool")
        self.trans_step = QComboBox()
        for mm in TRANS_STEPS:
            self.trans_step.addItem(f"{mm} mm", mm)
        self.trans_step.setCurrentIndex(1)          # 5 mm
        self.rot_step = QComboBox()
        for deg in ROT_STEPS:
            self.rot_step.addItem(f"{deg}°", deg)
        self.rot_step.setCurrentIndex(1)            # 5°
        self.btn_stop = QPushButton("停止点动（受控停止）")
        self.btn_stop.setToolTip(
            "写一条 movej 到**当前实测关节角**，作废在途点动/直线规划。\n"
            "走旁路，不排在在途命令后面。")
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.jog_status = QLabel("—")
        self.jog_status.setStyleSheet("color:#a0a0a0;")

        jog_grid = QGridLayout()
        jog_grid.setHorizontalSpacing(6)
        jog_grid.setVerticalSpacing(6)
        left = QGridLayout()
        right = QGridLayout()
        for r, (axis, _) in enumerate(_AXES):
            for c, sign in enumerate((-1, 1)):
                b = QPushButton(_jog_label(axis, sign, "translate"))
                b.setMinimumHeight(34)
                b.pressed.connect(lambda a=axis, s=sign: self._jog_press(a, "translate", s))
                b.released.connect(self._jog_release)
                left.addWidget(b, r, c)
                self._jog_buttons.append(b)
        for r, (axis, _) in enumerate(_AXES):
            for c, sign in enumerate((-1, 1)):
                b = QPushButton(_jog_label(axis, sign, "rotate"))
                b.setMinimumHeight(34)
                b.pressed.connect(lambda a=axis, s=sign: self._jog_press(a, "rotate", s))
                b.released.connect(self._jog_release)
                right.addWidget(b, r, c)
                self._jog_buttons.append(b)
        jog_grid.addLayout(left, 0, 0)
        jog_grid.addLayout(right, 0, 1)

        self.cart_hint = QLabel("")
        self.cart_hint.setStyleSheet("color:#d8a13a;")
        self.cart_hint.setWordWrap(True)

        g_jog = group(
            "点动（按住连续趋近，松手受控停止）",
            row(QLabel("坐标系"), self.frame,
                QLabel("平移步长"), self.trans_step,
                QLabel("旋转步长"), self.rot_step,
                self.btn_stop),
            jog_grid,
            self.jog_status,
            self.cart_hint,
            hint("⚠ 点动与 movel 需要固件编入笛卡尔规划；固件不支持时按钮保持灰色。"
                 "每一段都从实测 TCP 重新起步，段间会停一下。"))

        # ---------------- 目标位姿（movel/movep 与 ik 共用同一组输入） ----------------
        self.pose = PoseInput()
        self.speed = spin(0.01, settings.speed_max_ui, settings.default_speed, 0.05)
        self.btn_mp = QPushButton("下发 movep")
        self.btn_mp.setToolTip("关节空间插值到目标位姿；不是直线，不需要笛卡尔规划。")
        self.btn_mp.clicked.connect(lambda: self.movep.emit(self.pose.value(),
                                                            self.speed.value()))
        self.btn_ml = QPushButton("下发 movel（直线）")
        self.btn_ml.setToolTip(
            "固件笛卡尔直线：末端沿起点→目标直线运动，姿态 slerp。\n"
            "到位判据 6mm / 0.03rad；需要固件支持 LITEARM_CART_PLAN。")
        self.btn_ml.clicked.connect(lambda: self.movel.emit(self.pose.value(),
                                                            self.speed.value()))
        self.btn_ik = QPushButton("求解 IK（只算不动）")
        self.btn_ik.clicked.connect(self._emit_ik)
        self.seed_cb = QCheckBox("用当前实测关节角作 IK 种子")
        self.seed_cb.setChecked(True)
        self.ik_out = QPlainTextEdit()
        self.ik_out.setReadOnly(True)
        self.ik_out.setMaximumHeight(80)

        g_tgt = group("目标位姿（movel / movep 与 ik 共用这组数值）",
                      self.pose,
                      row(QLabel("速度倍率 (0..1)"), self.speed,
                          self.btn_mp, self.btn_ml),
                      row(self.btn_ik, self.seed_cb),
                      self.ik_out,
                      note("move_p：固件后台 IK → S 曲线 → 按 TCP 到位判定。"
                           "move_l：固件笛卡尔直线规划（需 LITEARM_CART_PLAN）。"
                           "ik：只求解不动臂；种子恒为**模型 7 轴**（与关节数解耦）。"))

        self.hint_lbl = hint("⚠ 运动按输入框里的位姿下发 —— 下发前请核对数值。")

        self.banner = LockBanner()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.banner)
        lay.addWidget(g_now)
        lay.addWidget(g_jog)
        lay.addWidget(g_tgt)
        lay.addWidget(self.hint_lbl)
        lay.addStretch(1)

    # ---------------- 外部状态 ----------------
    def set_online(self, onl: bool):
        self._online = onl
        if not onl:
            self._abort_jog("已离线")
        self._refresh()

    def set_busy(self, busy: bool):
        self._busy = busy
        self._refresh()

    def set_armed(self, armed: bool):
        self._armed = armed
        if not armed:
            self._abort_jog("运动已锁定")
        self._refresh()

    def set_fault_blocked(self, blocked: bool):
        self._fault_blocked = blocked
        if blocked:
            self._abort_jog("FAULT/急停锁存")
        self._refresh()

    def set_cart_supported(self, ok, silent: bool = False):
        """主窗口在连接后注入固件能力（None = 未知/未连接）。"""
        self._cart_ok = ok
        self._cart_silent = bool(silent)
        if ok is True:
            text = ""
        elif ok is False and self._cart_silent:
            text = ("笛卡尔能力探测未获确认（上行无应答）—— 点动/movel 已禁用；"
                    "请重连或检查链路")
        elif ok is False:
            text = "固件未编入笛卡尔规划（LITEARM_CART_PLAN）—— 点动/movel 不可用"
        else:
            text = "未连接 —— 点动/movel 需要先连接设备"
        self.cart_hint.setText(text)
        self._refresh()

    def _refresh(self):
        can = self._online and not self._busy
        move_can = self.banner.set_gate(
            online=self._online,
            can_move=self._armed and not self._fault_blocked,
            fault_blocked=self._fault_blocked) and not self._busy
        cart_can = move_can and self._cart_ok is True
        jog_can = (self._online and self._armed and not self._fault_blocked
                   and self._cart_ok is True)
        self.btn_tcp.setEnabled(can)
        self.btn_fill.setEnabled(can)
        self.btn_ik.setEnabled(can)
        self.seed_cb.setEnabled(can)
        self.btn_mp.setEnabled(move_can)
        self.btn_ml.setEnabled(cart_can)
        for b in self._jog_buttons:
            b.setEnabled(jog_can)
        self.btn_stop.setEnabled(self._jog_active or self._jog_in_flight)
        # 速度/步长/坐标系是输入，不是动作：始终可编辑（同关节页）
        for w in (self.speed, self.frame, self.trans_step, self.rot_step):
            w.setEnabled(True)
        self.pose.setEnabled(True)

    # ---------------- 点动 ----------------
    def _jog_ready(self) -> bool:
        return (self._online and self._armed and not self._fault_blocked
                and self._cart_ok is True)

    def _step_amount(self, kind: str, sign: int) -> float:
        if kind == "translate":
            mm = float(self.trans_step.currentData() or 5)
            return sign * mm / 1000.0
        deg = float(self.rot_step.currentData() or 5)
        return sign * math.radians(deg)

    def _jog_press(self, axis: str, kind: str, sign: int):
        if not self._jog_ready():
            self.jog_status.setText("点动不可用：未连接/未解锁/固件不支持")
            return
        if self._jog_holding:
            return                     # 不支持同时按两个方向；松开再按
        if self._busy and not self._jog_active:
            self.jog_status.setText("忙：等当前命令结束再点动")
            return
        self._jog_holding = True
        self._jog_stop_requested = False
        self._jog_params = (axis, kind, sign)
        self._jog_gen += 1
        self._jog_active = True
        self._start_segment(self._jog_gen)

    def _start_segment(self, gen: int):
        if not self._jog_holding or gen != self._jog_gen:
            return
        axis, kind, sign = self._jog_params
        amount = self._step_amount(kind, sign)
        self._jog_in_flight = True
        self.jog_status.setText(f"点动 {_jog_label(axis, sign, kind)} …")
        self.jog_step.emit(axis, kind, amount, self.frame.currentData(),
                           self.speed.value(), gen)

    def jog_result(self, gen: int, res):
        """主窗口在一步点动的任务结束后回调（GUI 线程）；`res=None` 表示被闸门拒绝。"""
        if gen != self._jog_gen:
            return
        self._jog_in_flight = False
        if res is None:
            self._end_jog("点动未下发（运动未解锁/未连接）")
            return
        if not res.ok:
            superseded = isinstance(getattr(res, "error", None),
                                    getattr(pa, "MotionSupersededError", ()))
            if superseded or self._jog_stop_requested:
                self._end_jog("已停止")
            else:
                self._end_jog(f"点动失败：{res.error}")
            return
        try:
            _start, target, _plan = res.value
            self.show_tcp(target)
        except Exception:  # noqa: BLE001 - 结果形状变了也不能卡住点动状态
            pass
        if self._jog_holding and not self._jog_stop_requested:
            self._start_segment(gen)
        else:
            self._end_jog("已停止" if self._jog_stop_requested else "完成")

    def _jog_release(self):
        if not self._jog_holding:
            return
        self._jog_holding = False
        if self._jog_in_flight:
            # 松手立即受控停止：作废在途续段，movej 到当前实测角。
            self._jog_stop_requested = True
            self.jog_status.setText("受控停止…")
            self.stop_req.emit()
        else:
            self._end_jog("已停止")

    def _on_stop_clicked(self):
        self._jog_holding = False
        self._jog_stop_requested = True
        self.jog_status.setText("受控停止…")
        self.stop_req.emit()

    def _end_jog(self, text: str):
        self._jog_holding = False
        self._jog_active = False
        self._jog_in_flight = False
        self.jog_status.setText(text)
        self._refresh()

    def _abort_jog(self, why: str):
        if self._jog_active or self._jog_holding or self._jog_in_flight:
            self._jog_gen += 1
            self._end_jog(why)

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
