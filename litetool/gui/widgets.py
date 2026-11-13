"""共用小部件 —— 日志面板 / 常驻状态条 / 横幅 / 左侧分组导航。

这些件被多个页面复用，故与页面解耦：只吃 `litearm.RobotState`，
不依赖 `SdkWorker` 或 MainWindow。
"""
from __future__ import annotations

import time
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QTableWidget,
                             QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

MONO = QFont("DejaVu Sans Mono", 11)

MODE_COLOR = {"INIT": "#b0b0b0", "MOVE_J": "#6fdd8b", "MOVE_P": "#6fdd8b",
              "MOVE_JS": "#6fdd8b", "MOVE_MIT": "#6fdd8b", "MIT_ALL": "#6fdd8b",
              "ZERO_G": "#61afef", "EMERGENCY": "#ff6b6b"}

CHIP_ON = "QLabel{background:#ff6b6b;color:#ffffff;border-radius:4px;padding:2px 8px;font-size:11px;}"
CHIP_OFF = "QLabel{background:#3a3a3a;color:#b0b0b0;border-radius:4px;padding:2px 8px;font-size:11px;}"

# DM 电机状态字节: 0=失能 1=使能 13=CAN 超时保护 (1.5.2/M6b 真机 halt 实测);
# 其余为未知/故障码 -> 红底
ERR_STATE = {0: "失能", 1: "使能", 13: "超时保护"}

#: 固件故障原因码 -> 表格短名（完整文案走 SDK `describe_fault`）。
FAULT_SHORT = {1: "断线", 2: "越限", 3: "超速", 4: "电机", 5: "过温",
               6: "跟随", 7: "非有限"}


def mono_label(width: Optional[int] = None, text: str = "—") -> QLabel:
    """固定宽度等宽小格 —— 数字变化不挤动相邻控件。"""
    lb = QLabel(text)
    lb.setFont(MONO)
    if width:
        lb.setFixedWidth(width)
    lb.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return lb


def static_label(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet("color:#a0a0a0;")
    return lb


class StatusStrip(QWidget):
    """**常驻**状态条：模式 / 臂使能 / 6 个安全 flag 灯 / seq / 丢帧 / 帧率。

    钉在顶栏下方，切页时不消失 —— 状态是操作的前提，不该要求用户先切到某页才看得见。
    更新策略：值/颜色**真正变化**才写控件，避免 20Hz 全量重绘导致整行闪烁。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chips = []
        self._chip_on = [False] * 6
        self._last: dict = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(6)

        row.addWidget(static_label("模式"))
        self.mode_lbl = mono_label(78)
        row.addWidget(self.mode_lbl)

        row.addWidget(static_label("臂"))
        self.arm_lbl = mono_label(50)
        row.addWidget(self.arm_lbl)

        from litearm import _protocol as _P
        for bit in range(6):
            chip = QLabel(_P.FLAG_NAMES.get(bit, f"bit{bit}"))
            chip.setFixedWidth(88)
            chip.setAlignment(Qt.AlignCenter)
            chip.setStyleSheet(CHIP_OFF)
            self._chips.append(chip)
            row.addWidget(chip)
        row.addStretch(1)

        self.seq_val = mono_label(50)
        self.drops_val = mono_label(56)
        self.fps_val = mono_label(44)
        for cap, val in (("seq", self.seq_val), ("丢帧", self.drops_val),
                         ("帧率", self.fps_val)):
            row.addSpacing(10)
            row.addWidget(static_label(cap))
            row.addWidget(val)

    def reset(self):
        self._last.clear()
        self._chip_on = [False] * 6
        for chip in self._chips:
            chip.setStyleSheet(CHIP_OFF)
        self.mode_lbl.setText("—")
        self.mode_lbl.setStyleSheet("")
        self.arm_lbl.setText("—")
        self.arm_lbl.setStyleSheet("")
        for lb in (self.seq_val, self.drops_val, self.fps_val):
            lb.setText("—")

    def update_from(self, st, drops: int, fps: float):
        if st is None:
            return
        if st.mode_name != self._last.get("mode"):
            self._last["mode"] = st.mode_name
            self.mode_lbl.setText(st.mode_name)
            self.mode_lbl.setStyleSheet(
                f"color:{MODE_COLOR.get(st.mode_name, '#b0b0b0')};font-weight:bold;")

        en = bool(st.enabled)
        if en != self._last.get("enabled"):
            self._last["enabled"] = en
            self.arm_lbl.setText("使能" if en else "失能")
            self.arm_lbl.setStyleSheet(
                f"color:{'#6fdd8b' if en else '#a0a0a0'};font-weight:bold;")

        for bit, chip in enumerate(self._chips):
            on = bool(st.flags & (1 << bit))
            if on != self._chip_on[bit]:
                self._chip_on[bit] = on
                chip.setStyleSheet(CHIP_ON if on else CHIP_OFF)

        for key, val, text in (("seq", self.seq_val, str(st.seq)),
                               ("drops", self.drops_val, str(drops)),
                               ("fps", self.fps_val, f"{fps:.0f}")):
            if text != self._last.get(key):
                self._last[key] = text
                val.setText(text)


class JointTable(QWidget):
    """逐关节表：q/dq/tau/温度/状态。超温黄底、异常码或断轴红底。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["关节", "q (rad)", "dq (rad/s)", "tau (Nm)",
             "T_mos (°C)", "T_coil (°C)", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._temp_alert = 85.0
        self._n = 0
        self._cell_text: dict = {}
        self._cell_bg: dict = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table)

    def set_temp_alert(self, c: float):
        self._temp_alert = c

    def update_from(self, st):
        if st is None:
            return
        if st.n != self._n:
            self._n = st.n
            self.table.setRowCount(st.n)
            self._cell_text.clear()
            self._cell_bg.clear()
            for i in range(st.n):
                it = QTableWidgetItem(f"J{i + 1}")
                it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 0, it)
                self._cell_text[(i, 0)] = it.text()
                for col in range(1, 7):
                    it = QTableWidgetItem("—")
                    it.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(i, col, it)
                    self._cell_text[(i, col)] = "—"
                    self._cell_bg[(i, col)] = "normal"
        for i, js in enumerate(st.joints):
            warn = js.t_mos > self._temp_alert or js.t_coil > self._temp_alert
            # 0/1 为正常状态; 其余(含 13=超时保护)一律异常码 -> 红底
            unknown = js.err not in (0, 1)
            faulted = bool(st.joint_fault & (1 << i))     # 固件 G7 断轴锁存
            if faulted:
                # 固件 1.12.2 起带原因码；旧固件为空列表 -> 只显示"断轴"
                reasons = getattr(st, "fault_reason", []) or []
                r = reasons[i] if i < len(reasons) else 0
                st_text = f"断轴·{FAULT_SHORT.get(r, '?')}" if r else "断轴"
            else:
                st_text = ERR_STATE.get(js.err, f"0x{js.err:02X}")
            bad = unknown or faulted
            for col, text, bg in ((1, f"{js.q:.3f}", "err" if bad else "normal"),
                                  (2, f"{js.dq:.3f}", "err" if bad else "normal"),
                                  (3, f"{js.tau:.3f}", "err" if bad else "normal"),
                                  (4, f"{js.t_mos:.1f}", "warn" if warn else "normal"),
                                  (5, f"{js.t_coil:.1f}", "warn" if warn else "normal"),
                                  (6, st_text, "err" if bad else "normal")):
                self._set_cell(i, col, text, bg)

    def _set_cell(self, i: int, col: int, text: str, bg: str):
        key = (i, col)
        item = self.table.item(i, col)
        if item is None:
            return
        if self._cell_text.get(key) != text:
            self._cell_text[key] = text
            item.setText(text)
        if self._cell_bg.get(key) != bg:
            self._cell_bg[key] = bg
            if bg == "err":
                item.setBackground(QBrush(QColor("#8b3a3a")))
            elif bg == "warn":
                item.setBackground(QBrush(QColor("#8a7a2a")))
            else:
                item.setBackground(QBrush(QColor("transparent")))


class Banner(QLabel):
    """锁定/告警横幅。语义固定：locked 为真时是"禁止操作"，为假时是"已放行"。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(34)
        self.setWordWrap(True)

    def set_locked(self, locked: bool, reason: str = ""):
        if locked:
            self.setText(f"⛔ {reason}" if reason else "⛔ 已锁定")
            self.setStyleSheet("background:#5a4a2a;color:#ffd166;font-weight:bold;"
                               "font-size:14px;border-radius:4px;")
        else:
            self.setText("✔ 已解锁 — 请谨慎操作，急停随时可用")
            self.setStyleSheet("background:#2a5a3a;color:#6fdd8b;font-weight:bold;"
                               "font-size:14px;border-radius:4px;")

    def set_warn(self, text: str):
        self.setText(text)
        self.setStyleSheet("background:#5a3a2a;color:#ffb266;font-weight:bold;"
                           "font-size:14px;border-radius:4px;")

    def set_ok(self, text: str):
        self.setText(text)
        self.setStyleSheet("background:#2a3f5a;color:#8fc7ff;"
                           "font-size:13px;border-radius:4px;")


class NavList(QTreeWidget):
    """左侧分组导航。顶层项是分组标题（不可选中），子项是页面。

    `current_key` 为子项 `data(0, Qt.UserRole)`。切页由 `navigated(str)` 通知。
    """

    navigated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setIndentation(18)
        self.setFixedWidth(168)
        self._items: dict = {}
        self.itemClicked.connect(self._on_clicked)

    def add_group(self, title: str):
        """分组标题：不可选、带底色 —— 分组得看得出来，否则导航就退化成一张平表。"""
        item = QTreeWidgetItem([title])
        item.setFlags(Qt.ItemIsEnabled)
        item.setForeground(0, QColor("#4a6b8a"))
        item.setBackground(0, QColor("#e8eef5"))
        f = item.font(0)
        f.setBold(True)
        item.setFont(0, f)
        self.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    def add_page(self, group_item, key: str, title: str, tip: str = ""):
        item = QTreeWidgetItem([title])
        item.setData(0, Qt.UserRole, key)
        if tip:
            item.setToolTip(0, tip)
        group_item.addChild(item)
        self._items[key] = item
        return item

    def _on_clicked(self, item, _col):
        key = item.data(0, Qt.UserRole)
        if key:
            self.navigated.emit(str(key))

    def select(self, key: str):
        item = self._items.get(key)
        if item is not None:
            self.setCurrentItem(item)


class LogPanel(QPlainTextEdit):
    """带时间戳的日志面板；append_line 在 GUI 主线程调用（经信号桥转达）。"""

    _STYLE = (
        "QPlainTextEdit { background:#1e1e1e; color:#c8c8c8;"
        " font-family:'DejaVu Sans Mono','Courier New',monospace; font-size:12px; }"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self.setStyleSheet(self._STYLE)
        self._level_color = {
            "[OK]": "#6fdd8b",
            "[ERR]": "#ff6b6b",
            "[WARN]": "#ffd166",
            "[INFO]": "#c8c8c8",
        }

    def append_line(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        color = "#c8c8c8"
        for key, c in self._level_color.items():
            if msg.startswith(key):
                color = c
                break
        self.appendHtml(f'<span style="color:#808080">[{ts}]</span> '
                        f'<span style="color:{color}">{msg}</span>')

    def clear_log(self):
        self.clear()
