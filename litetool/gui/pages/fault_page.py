"""故障页 —— 一屏回答"哪根轴、为什么、怎么办"。

内容:
  * 顶部: 当前模式/使能/整臂持位 + 故障摘要
  * 逐轴表: 轴 / 状态 / 原因 / 处置
  * 事件历史: 本次会话内每根轴**首次**出现新原因时记一行
  * 操作: 清故障 / 复位 / 复制诊断包

数据全部来自 SDK 的 `RobotState.fault_reason` 与 `describe_fault()`；
本页不自己写文案。旧固件 reason 为空时只显示"断轴/原因不可知"。
"""
from __future__ import annotations

import datetime as _dt

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from litetool.gui.pages.common import group, note, row


def _fault_text(reason: int):
    """reason -> (title, action)。SDK 不可用时降级，不抛。"""
    try:
        import litearm as pa
        t = pa.describe_fault(reason)
        return t.title, t.action
    except Exception:  # noqa: BLE001 - 老 SDK / 未导出
        return f"原因 {reason}", ""


class FaultPage(QWidget):
    cmd = pyqtSignal(str)          # "clear_faults" / "reset"
    diag_req = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._online = False

        self.head = QLabel("无故障")
        self.head.setStyleSheet("font-size:15px;font-weight:bold;color:#6fdd8b;")
        self.detail = QLabel("—")
        self.detail.setStyleSheet("color:#bbb;")

        head_box = QVBoxLayout()
        head_box.addWidget(self.head)
        head_box.addWidget(self.detail)
        g_head = group("当前状态", head_box, note(
            "故障锁存后运动页面会被禁用；必须清故障或复位才能恢复出力。"))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["轴", "状态", "原因", "处置"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setMinimumHeight(300)      # 7 轴一屏可见，不靠滚动
        g_table = group("逐轴故障", self.table)

        self.hist = QPlainTextEdit()
        self.hist.setReadOnly(True)
        self.hist.setMaximumBlockCount(200)
        self.hist.setPlaceholderText("本次会话内新出现的故障会按时间记录在这里")
        g_hist = group("事件历史", self.hist)

        self.btn_clear = QPushButton("清故障 clear_faults")
        self.btn_reset = QPushButton("复位 reset")
        self.btn_diag = QPushButton("复制诊断包")
        self.btn_clear.clicked.connect(lambda: self.cmd.emit("clear_faults"))
        self.btn_reset.clicked.connect(lambda: self.cmd.emit("reset"))
        self.btn_diag.clicked.connect(self.diag_req.emit)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(g_head)
        lay.addWidget(g_table, 1)
        lay.addWidget(g_hist, 1)
        lay.addLayout(row(self.btn_clear, self.btn_reset, self.btn_diag))

    # ---------------- 外部状态 ----------------
    def set_online(self, onl: bool):
        self._online = onl
        for b in (self.btn_clear, self.btn_reset, self.btn_diag):
            b.setEnabled(onl)

    def add_event(self, text: str):
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        self.hist.appendPlainText(f"{ts}  {text}")

    def update_from(self, st, detail=None):
        if st is None:
            self.head.setText("未连接")
            self.head.setStyleSheet("font-size:15px;font-weight:bold;color:#888;")
            self.detail.setText("—")
            self.table.setRowCount(0)
            return

        # [1.12.3] 优先用按需查询到的 detail；旧固件/1.12.2 回退状态帧自带字段
        reasons = list(getattr(detail, "fault_reason", None) or []) if detail else []
        if not reasons:
            reasons = list(getattr(st, "fault_reason", []) or [])
        faults = []
        for i in range(getattr(st, "n", len(st.joints))):
            bit = bool(st.joint_fault & (1 << i))
            if not bit:
                continue
            r = reasons[i] if i < len(reasons) else 0
            faults.append((i, r))

        if faults:
            axes = "、".join(f"J{i + 1}" for i, _ in faults)
            self.head.setText(f"故障锁存：{axes}")
            self.head.setStyleSheet("font-size:15px;font-weight:bold;color:#ff6b6b;")
        else:
            self.head.setText("无故障")
            self.head.setStyleSheet("font-size:15px;font-weight:bold;color:#6fdd8b;")

        drop = int(getattr(detail, "drop_hold_reason", 0) or 0) if detail else 0
        if not drop:
            drop = int(getattr(st, "drop_hold_reason", 0) or 0)
        drop_txt = "无"
        if drop:
            drop_txt = _fault_text(drop)[0]
        self.detail.setText(
            f"模式 {st.mode_name} · {'已使能' if st.enabled else '未使能'}"
            f" · 整臂持位：{drop_txt}")

        n = getattr(st, "n", 0)
        self.table.setRowCount(n)
        for i in range(n):
            bit = bool(st.joint_fault & (1 << i))
            r = reasons[i] if i < len(reasons) else 0
            if bit:
                title, action = _fault_text(r) if r else ("原因不可知（旧固件）", "")
                cells = (f"J{i + 1}", "断轴", title, action)
                color = "#ff6b6b"
            else:
                cells = (f"J{i + 1}", "正常", "—", "—")
                color = None
            for col, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignCenter if col < 2 else
                                    Qt.AlignLeft | Qt.AlignVCenter)
                if color:
                    if col == 1:                      # 状态列：红底白字
                        it.setBackground(QBrush(QColor("#8b3a3a")))
                        it.setForeground(Qt.white)
                    elif col == 0:                    # 轴号：红字
                        it.setForeground(QColor("#ff6b6b"))
                    # 原因/处置保持默认深色 —— 白字配白底会看不见（实测踩过）
                self.table.setItem(i, col, it)
