"""曲线页 —— pyqtgraph 三联动子图（q/dq/tau），30s 滚动窗口。"""
import numpy as np
from PyQt5.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)
import pyqtgraph as pg

COLORS = ["#e8c547", "#e06c75", "#61afef", "#98c379", "#c678dd",
          "#56b6c2", "#d19a66"]
FIELD_TITLES = ["关节位置 q (rad)", "关节速度 dq (rad/s)", "关节力矩 tau (Nm)"]


class PlotPage(QWidget):
    def __init__(self, window_s: float = 30.0, parent=None):
        super().__init__(parent)
        self._window = window_s
        self._n = 0
        self._enabled: list[bool] = []
        self._joint_boxes: list[QCheckBox] = []
        self.frozen = False

        self.gw = pg.GraphicsLayoutWidget()
        self.plots = []
        for r in range(3):
            pi = self.gw.addPlot(row=r, col=0)
            pi.showGrid(x=True, y=True, alpha=0.2)
            pi.setLabel("left", FIELD_TITLES[r])
            pi.addLegend(offset=(10, 10))
            pi.setXRange(-self._window, 0, padding=0)
            self.plots.append(pi)
        # 三图联动 x 轴
        for pi in self.plots[1:]:
            pi.setXLink(self.plots[0])
        self.curves = {}          # (field, joint) -> PlotDataItem

        top = QHBoxLayout()
        top.addWidget(QLabel("关节:"))
        self.box_row = QHBoxLayout()
        top.addLayout(self.box_row)
        top.addStretch(1)
        self.freeze_btn = QPushButton("❚❚ 冻结")
        self.freeze_btn.setCheckable(True)
        self.freeze_btn.toggled.connect(self._on_freeze)
        top.addWidget(self.freeze_btn)
        self.clear_btn = QPushButton("清屏")
        self.clear_btn.clicked.connect(self.clear_all)
        top.addWidget(self.clear_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(top)
        lay.addWidget(self.gw)

    def _on_freeze(self, on: bool):
        self.frozen = on
        self.freeze_btn.setText("▶ 继续" if on else "❚❚ 冻结")

    def clear_all(self):
        for pi in self.plots:
            pi.clear()
            pi.addLegend(offset=(10, 10))
        self.curves.clear()

    def set_joints(self, n: int):
        if n == self._n:
            return
        self._n = n
        self.clear_all()
        # 重建关节勾选
        while self.box_row.count():
            item = self.box_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._joint_boxes = []
        self._enabled = []
        for j in range(n):
            cb = QCheckBox(f"J{j + 1}")
            default = j < 3 if n > 3 else True   # 默认高亮前 3 关节，避免过密
            cb.setChecked(default)
            cb.toggled.connect(lambda on, jj=j: self._set_enabled(jj, on))
            self.box_row.addWidget(cb)
            self._joint_boxes.append(cb)
            self._enabled.append(default)

    def _set_enabled(self, j: int, on: bool):
        if 0 <= j < len(self._enabled):
            self._enabled[j] = on

    def refresh(self, model):
        if self.frozen or self._n == 0:
            return
        times, q, dq, tau = model.snapshot()
        if not times:
            return
        # 时间原点对齐"现在"(最新样本), 使窗口固定显示最近 window 秒
        x = np.asarray(times, dtype=float) - times[-1]
        for field, series in enumerate((q, dq, tau)):
            mat = np.asarray(series, dtype=float)     # (样本, 关节)
            pi = self.plots[field]
            n_show = min(self._n, mat.shape[1])       # 重连窗口内样本关节数可能小于 UI 值
            for j in range(n_show):
                key = (field, j)
                curve = self.curves.get(key)
                color = COLORS[j % len(COLORS)]
                if not self._enabled[j]:
                    if curve is not None:
                        curve.setVisible(False)
                    continue
                y = mat[:, j]
                if curve is None:
                    curve = pi.plot(x, y, pen=pg.mkPen(color, width=1.5),
                                    name=f"J{j + 1}")
                    self.curves[key] = curve
                else:
                    curve.setData(x, y)
                    curve.setVisible(True)
