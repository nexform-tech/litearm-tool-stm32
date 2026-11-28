"""总览页 —— 逐关节状态表 + 100Hz 曲线（原「监控」与「曲线」两页合并）。

两页本就吃同一份状态流，拆开只会让人来回切。这里上下分割，并给一个
「曲线放大」把状态表收起来，兼顾"看数"和"看波形"两种用法。
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSplitter,
                             QVBoxLayout, QWidget)

from litetool import i18n
from litetool.gui.i18n_ui import TrButton, TrLabel
from litetool.gui.pages.plot_pane import PlotPane
from litetool.gui.widgets import JointTable

class OverviewPage(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.table = JointTable()
        self.table.set_temp_alert(settings.temp_alert_c)
        self.plot = PlotPane(window_s=settings.plot_window_s)

        self.btn_zoom = TrButton("曲线放大")
        self.btn_zoom.setCheckable(True)
        self.btn_zoom.toggled.connect(self._on_zoom)

        head = QHBoxLayout()
        head.addWidget(TrLabel("逐关节状态（超温黄底 / 异常码或断轴红底）"))
        head.addStretch(1)
        self.fault_lbl = QLabel("")
        self.fault_lbl.setStyleSheet("color:#ff6b6b;font-weight:bold;")
        head.addWidget(self.fault_lbl)
        head.addWidget(self.btn_zoom)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addLayout(head)
        tl.addWidget(self.table)

        self.split = QSplitter(Qt.Vertical)
        self.split.addWidget(top)
        self.split.addWidget(self.plot)
        self.split.setStretchFactor(0, 2)
        self.split.setStretchFactor(1, 3)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.split)

    def _on_zoom(self, on: bool):
        self.split.widget(0).setVisible(not on)
        self.btn_zoom.setText(i18n.tr("显示状态表") if on else i18n.tr("曲线放大"))

    def retranslate(self):
        self._on_zoom(self.btn_zoom.isChecked())

    def set_joints(self, n: int):
        self.plot.set_joints(n)
        # 让状态表放得下全部关节行 —— 否则 7J 只露 3 行，要滚动才看得到 J7
        row_h = self.table.table.verticalHeader().defaultSectionSize()
        self.table.setMinimumHeight(40 + row_h * max(n, 1))

    def update_from(self, st):
        self.table.update_from(st)
        if st is None:
            return
        if st.faulted:
            self.fault_lbl.setText(f"⚠ {st.fault_detail}")
        elif self.fault_lbl.text():
            self.fault_lbl.setText("")

    def refresh_plot(self, model):
        self.plot.refresh(model)

    def set_context(self, firmware: str):
        """连接上下文（固件版本）—— 曲线 CSV 的文件名用它。"""
        self.plot.set_context(firmware)

    def clear_plot(self):
        self.plot.clear_all()
