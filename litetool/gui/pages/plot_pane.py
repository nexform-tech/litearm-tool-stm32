"""曲线组件 —— pyqtgraph 三段联动子图（q / dq / tau），滚动窗口。

数据源是 `litetool.plot_model.PlotModel`（100Hz 全量入缓冲，本组件按 30Hz 重绘
不抽稀）。被「总览」页复用；曲线页不再单独存在 —— 它与状态表本就吃同一份流。
"""
from __future__ import annotations

from typing import List

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QVBoxLayout, QWidget)

from litetool import csv_export, i18n
from litetool.gui.i18n_ui import TrButton, tr_tooltip
from litetool.gui.joint_selector import COLORS, JointSelector

#: 轴标签要**短** —— 竖排文字比图高时会压到相邻子图的刻度上
FIELD_TITLES = ["q (rad)", "dq (rad/s)", "tau (Nm)"]


class PlotPane(QWidget):
    def __init__(self, window_s: float = 30.0, parent=None):
        super().__init__(parent)
        self._window = window_s
        self._n = 0
        self.frozen = False
        self._model = None
        self._frozen_snapshot = None
        self._firmware = ""

        self.curves: dict = {}                    # (field, joint) -> PlotDataItem
        self.joints = JointSelector()
        self.joints.changed.connect(self._apply_visibility)
        self.gw = pg.GraphicsLayoutWidget()
        self.plots = []
        for r in range(3):
            pi = self.gw.addPlot(row=r, col=0)
            pi.showGrid(x=True, y=True, alpha=0.2)
            pi.setLabel("left", FIELD_TITLES[r])
            # 关掉自动 SI 前缀：否则 0.2 Nm 会被标成 "200 m"，小数值图上误导性极强
            pi.getAxis("left").enableAutoSIPrefix(False)
            pi.getAxis("left").setWidth(56)     # 给刻度+标签留位，否则标签被截断
            pi.setXRange(-self._window, 0, padding=0)
            self.plots.append(pi)
        for pi in self.plots[1:]:                 # 三图联动 x 轴
            pi.setXLink(self.plots[0])

        top = QHBoxLayout()
        top.addWidget(self.joints)
        top.addStretch(1)
        self.freeze_btn = TrButton("❚❚ 冻结")
        self.freeze_btn.setCheckable(True)
        self.freeze_btn.toggled.connect(self._on_freeze)
        top.addWidget(self.freeze_btn)
        self.clear_btn = TrButton("清屏")
        self.clear_btn.clicked.connect(self.clear_all)
        top.addWidget(self.clear_btn)
        self.export_btn = TrButton("导出 CSV…")
        tr_tooltip(
            self.export_btn,
            "导出当前窗口里勾选的关节：时间、q/dq/tau、MOS/线圈温度、驱动错误码。\n"
            "冻结状态下导出的是冻结那一刻的窗口。")
        self.export_btn.clicked.connect(self._on_export)
        top.addWidget(self.export_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(top)
        lay.addWidget(self.gw)

    def _on_freeze(self, on: bool):
        self.frozen = on
        # 冻结时把窗口定格下来：之后模型继续滚动，导出的仍是用户眼前这一屏。
        self._frozen_snapshot = (self._model.snapshot_full()
                                 if on and self._model is not None else None)
        self.freeze_btn.setText(i18n.tr("▶ 继续") if on else i18n.tr("❚❚ 冻结"))

    def clear_all(self):
        self._frozen_snapshot = None
        self.curves.clear()
        for pi in self.plots:
            pi.clear()

    def retranslate(self):
        self._on_freeze(self.frozen)

    def set_context(self, firmware: str):
        """主窗口在连接后注入固件版本 —— 导出文件名带它。"""
        self._firmware = str(firmware or "")

    def selected_joints(self) -> List[int]:
        """曲线上勾选可见的关节（0 基）。"""
        return self.joints.selected()

    def _on_export(self):
        if self.frozen:
            snap = self._frozen_snapshot
        elif self._model is not None:
            snap = self._model.snapshot_full()
        else:
            snap = None
        if not snap or not snap.get("times"):
            QMessageBox.information(self, i18n.tr("导出 CSV"),
                                    i18n.tr("当前窗口里没有数据 —— 先连接设备等几帧。"))
            return
        joints = self.selected_joints()
        if not joints:
            QMessageBox.information(self, i18n.tr("导出 CSV"),
                                    i18n.tr("请至少勾选一个关节。"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("导出曲线窗口 CSV"),
            csv_export.timestamped_name("plot", self._firmware),
            "CSV (*.csv);;全部 (*)")
        if not path:
            return
        try:
            rows = csv_export.write_plot_csv(path, snap, joints=joints,
                                             firmware=self._firmware)
        except Exception as e:  # noqa: BLE001 - 导出失败不该拖垮界面
            QMessageBox.warning(self, i18n.tr("导出失败"),
                                i18n.safe_detail(e) or i18n.tr("未知错误"))
            return
        QMessageBox.information(self, i18n.tr("导出完成"),
                                i18n.tr("已写出 {n} 行 → {path}", n=rows, path=path))

    def set_joints(self, n: int):
        if n == self._n:
            return
        self._n = n
        self.clear_all()
        self.joints.set_joints(n, default_first=3)   # 默认前 3 关节，避免过密

    def _apply_visibility(self):
        """一次开关同步三张图；冻结时也立即生效（refresh 此时不再跑）。"""
        enabled = self.joints.enabled()
        for (_field, j), curve in self.curves.items():
            curve.setVisible(j < len(enabled) and enabled[j])

    def refresh(self, model):
        self._model = model
        if self.frozen or self._n == 0:
            return
        times, q, dq, tau = model.snapshot()
        if not times:
            return
        # 时间原点对齐"现在"(最新样本)，使窗口固定显示最近 window 秒
        x = np.asarray(times, dtype=float) - times[-1]
        enabled = self.joints.enabled()
        for field, series in enumerate((q, dq, tau)):
            mat = np.asarray(series, dtype=float)      # (样本, 关节)
            pi = self.plots[field]
            n_show = min(self._n, mat.shape[1])        # 重连后窗口内关节数可能小于 UI 值
            for j in range(n_show):
                key = (field, j)
                curve = self.curves.get(key)
                color = COLORS[j % len(COLORS)]
                if j >= len(enabled) or not enabled[j]:
                    if curve is not None:
                        curve.setVisible(False)
                    continue
                y = mat[:, j]
                if curve is None:
                    curve = pi.plot(x, y, pen=pg.mkPen(color, width=1.5))
                    self.curves[key] = curve
                else:
                    curve.setData(x, y)
                    curve.setVisible(True)
