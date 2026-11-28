"""页面共用件 —— pose 输入组 / 关节角输入组 / 分组框助手。"""
from __future__ import annotations

from typing import List, Sequence

from PyQt5.QtWidgets import (QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QVBoxLayout, QWidget)

from litetool import i18n
from litetool.gui.i18n_ui import TrGroupBox, TrLabel
from litetool.gui.widgets import Banner

#: 关节角输入范围 (rad) —— 只作 GUI 侧防手滑；真权威是固件软限位。
Q_RANGE = (-6.28, 6.28)
#: 固件 TCP 工作空间的大致包络 (m)。固件会拒绝不可达目标 (IKError)，这里只挡明显手滑。
XYZ_RANGE = ((-1.0, 1.0), (-1.0, 1.0), (-0.5, 1.2))
RPY_RANGE = (-3.15, 3.15)


def spin(lo: float, hi: float, val: float = 0.0, step: float = 0.01,
         decimals: int = 3) -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi)
    sp.setDecimals(decimals)
    sp.setSingleStep(step)
    sp.setValue(val)
    return sp


class PoseInput(QWidget):
    """末端位姿输入：x,y,z,r,p,y 六个分量。"""

    LABELS = ("x (m)", "y (m)", "z (m)", "roll (rad)", "pitch (rad)", "yaw (rad)")

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        self.spins: List[QDoubleSpinBox] = []
        for i, lab in enumerate(self.LABELS):
            lo, hi = (XYZ_RANGE[i] if i < 3 else RPY_RANGE)
            grid.addWidget(QLabel(lab), i // 3, (i % 3) * 2)
            sp = spin(lo, hi)
            grid.addWidget(sp, i // 3, (i % 3) * 2 + 1)
            self.spins.append(sp)

    def value(self) -> List[float]:
        return [sp.value() for sp in self.spins]

    def set_value(self, pose: Sequence[float]):
        if pose is None or len(pose) < 6:
            return
        for sp, v in zip(self.spins, pose):
            sp.setValue(float(v))

    def setEnabled(self, on: bool):  # noqa: N802 - Qt 命名
        super().setEnabled(on)
        for sp in self.spins:
            sp.setEnabled(on)


class JointRow(QWidget):
    """N 个关节角输入，**横排**成一行（J1..JN），关节数变化时重建。

    横排不只是紧凑：竖排 7 个 × 页面里好几组会把页面撑到 2500px，而
    `QStackedWidget` 的最小高度取**所有页的 max** —— 整个窗口会被顶到 2500px
    高，在笔记本上直接不可用。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)
        self.spins: List[QDoubleSpinBox] = []
        self._n = -1

    @property
    def n(self) -> int:
        return len(self.spins)

    def set_joints(self, n: int):
        if n == self._n:
            return
        self._n = n
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.spins = []
        if n == 0:
            return
        width = max(64, min(104, 640 // n))     # 关节多则收窄，整行始终放得下
        for j in range(n):
            self._lay.addWidget(QLabel(f"J{j + 1}"))
            sp = spin(*Q_RANGE)
            sp.setFixedWidth(width)
            self._lay.addWidget(sp)
            self.spins.append(sp)
        self._lay.addStretch(1)

    def value(self) -> List[float]:
        return [sp.value() for sp in self.spins]

    def set_value(self, qs: Sequence[float]):
        for sp, v in zip(self.spins, qs or []):
            sp.setValue(float(v))

    def setEnabled(self, on: bool):  # noqa: N802 - Qt 命名
        super().setEnabled(on)
        for sp in self.spins:
            sp.setEnabled(on)


def group(title: str, *children, **fmt) -> QGroupBox:
    """竖排分组框；children 可以是 widget 或 layout，``fmt`` 给标题占位符。"""
    box = TrGroupBox(title, **fmt)
    lay = QVBoxLayout(box)
    for ch in children:
        if hasattr(ch, "addWidget") and not isinstance(ch, QWidget):
            lay.addLayout(ch)
        else:
            lay.addWidget(ch)
    return box


def row(*widgets) -> QHBoxLayout:
    lay = QHBoxLayout()
    for w in widgets:
        if hasattr(w, "addWidget") and not isinstance(w, QWidget):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    lay.addStretch(1)
    return lay


def note(text: str, **fmt) -> QLabel:
    lb = TrLabel(text, **fmt)
    lb.setWordWrap(True)
    lb.setStyleSheet("color:#8a97a4;font-size:12px;")
    return lb


def hint(text: str, **fmt) -> QLabel:
    lb = TrLabel(text, **fmt)
    lb.setWordWrap(True)
    lb.setStyleSheet("color:#ffd166;font-size:12px;")
    return lb


UNLOCK_HINT = "运动已锁定 — 请勾选顶栏的「我已确认机械臂周围无障碍、急停可及」"


class LockBanner(Banner):
    """运动页顶部的**闸门状态条** —— 灰按钮必须自己解释为什么灰。

    用户看到 [回零] 点不动时，唯一的线索就是这片横幅；四态各自说清下一步做什么：
    未连接 / 故障锁存 / 运动未解锁 / 已解锁。

    `set_gate()` 的返回值与各页按钮的可用性判定**同源** —— 横幅说"已解锁"而按钮
    还是灰的（或反过来）是最糟的情况，所以两边从同一个表达式取值。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_locked(True, i18n.tr("未连接 — 连接后才可操作"))

    def set_gate(self, *, online: bool, can_move: bool,
                 fault_blocked: bool = False) -> bool:
        """`online` / `can_move` 由**各页自己给**，且必须是它们判定按钮可用性的
        同一个表达式 —— 横幅只负责把"为什么不行"说清楚，不自己另立一套规则
        （否则就会出现"横幅说已解锁、按钮还是灰的"）。

        ⚠ `fault_blocked` 只在**说不出更好理由时**才作为解释：零重力在拖动中
        `can_move` 恒为真（退出必须永远可行），此时即便固件锁存着也不能拦住退出。
        """
        if not online:
            self.set_locked(True, i18n.tr("未连接 — 连接后才可操作"))
            return False
        if can_move:
            self.set_locked(False)
            return True
        if fault_blocked:
            self.set_locked(True, i18n.tr("FAULT / 急停锁存中 — 先 [清故障] 或 [复位]"))
        else:
            self.set_locked(True, i18n.tr(UNLOCK_HINT))
        return False
