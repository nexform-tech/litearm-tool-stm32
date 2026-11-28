"""关节显隐开关 —— q / dq / tau 三张图共用一条彩色勾选行。

勾选文字与曲线同色，一处开关同时控制三张图的同一关节。图内不再放图例：
三个子图的高度放不下 J1..J7，图例会被截掉，而一个外部开关行没有这个问题。
"""
from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from litetool.gui.i18n_ui import TrLabel

#: 关节配色 —— 勾选文字与曲线同色，就是图例。
COLORS = ["#e8c547", "#e06c75", "#61afef", "#98c379", "#c678dd",
          "#56b6c2", "#d19a66"]


class JointSelector(QWidget):
    """一条 ``关节: [J1][J2]…`` 开关行，控制所有联动子图的同一关节。"""

    changed = pyqtSignal()

    def __init__(self, parent=None, *, label: str = "关节:"):
        super().__init__(parent)
        self.label = TrLabel(label)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self.label)
        self._row = QHBoxLayout()
        self._row.setSpacing(6)
        lay.addLayout(self._row)
        self._boxes: List[QCheckBox] = []

    @property
    def n(self) -> int:
        return len(self._boxes)

    def set_joints(self, n: int, *, default_first: Optional[int] = None):
        """重建开关行；``n`` 不变时保留用户当前的勾选。

        ``default_first=None`` 全部勾选；给整数时只勾前 N 个（实时曲线默认前 3
        个，避免过密）。重建时先 ``setChecked`` 再连 ``toggled``，不会触发一次
        假的 ``changed``。
        """
        n = max(0, int(n))
        if n == len(self._boxes):
            return
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._boxes = []
        for j in range(n):
            cb = QCheckBox(f"J{j + 1}")
            color = COLORS[j % len(COLORS)]
            # 文字保持黑色（页底是浅色），颜色放在复选框本身：空心=未选，
            # 实心=已选。这样彩色标记不再影响文字可读性。
            cb.setStyleSheet(
                "QCheckBox { color: #000000; spacing: 4px; }"
                f"QCheckBox::indicator {{ width: 12px; height: 12px; "
                f"border: 2px solid {color}; border-radius: 2px; }}"
                f"QCheckBox::indicator:checked {{ background-color: {color}; }}")
            cb.setChecked(default_first is None or j < default_first)
            cb.toggled.connect(self._emit_changed)
            self._row.addWidget(cb)
            self._boxes.append(cb)

    def _emit_changed(self, _on: bool):
        self.changed.emit()

    def enabled(self) -> List[bool]:
        return [cb.isChecked() for cb in self._boxes]

    def selected(self) -> List[int]:
        return [j for j, cb in enumerate(self._boxes) if cb.isChecked()]

    def set_enabled(self, j: int, on: bool):
        if 0 <= j < len(self._boxes):
            self._boxes[j].setChecked(bool(on))
