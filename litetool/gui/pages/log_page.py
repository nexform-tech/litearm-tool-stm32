"""日志页 —— 结构化 JSONL 的实时视图 + 历史回读。

底部日志面板是"刚才几行"的快捷视图；本页是它的完整版：按级别/类别/文本筛选、
选中一条看原始 JSON、把当前筛选结果导出成 JSONL。

历史来自 `StructuredLogger` 的文件（当前文件 + 轮转备份），所以**重启之后**还能
看到上一次会话的记录，而不是只剩内存里的最近 200 行。
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                             QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from litetool import i18n, obs
from litetool.gui.i18n_ui import TrButton, TrLabel, tr_header, tr_placeholder

_COLUMNS = ("时间", "级别", "类别", "内容")
_LEVEL_COLOR = {"WARN": "#d8a13a", "ERROR": "#ff6b6b", "FATAL": "#ff4d4d"}


def _category(rec: dict) -> str:
    fields = rec.get("fields") or {}
    return str(fields.get("category") or
               str(rec.get("event", "")).split(".")[0] or "app")


def _local_time(rec: dict) -> str:
    raw = rec.get("ts")
    if isinstance(raw, str):
        try:
            dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%H:%M:%S.%f")[:-3]
        except ValueError:
            pass
    ts_ns = rec.get("ts_ns")
    if isinstance(ts_ns, (int, float)) and ts_ns > 0:
        return _dt.datetime.fromtimestamp(ts_ns / 1e9).strftime("%H:%M:%S.%f")[:-3]
    return "—"


class LogPage(QWidget):
    """筛选 + 表格 + 原始 JSON 详情。数据源是 `StructuredLogger`。"""

    def __init__(self, slog: obs.StructuredLogger, history_limit: int = 2000, parent=None):
        super().__init__(parent)
        self.slog = slog
        self._history_limit = int(history_limit)
        self._records = collections.deque(slog.read_history(self._history_limit),
                                          maxlen=obs.RING_SIZE)
        self._visible: list = []
        self._category_choices: list = []

        # ---------------- 筛选条 ----------------
        self.level = QComboBox()
        self.level.addItem(i18n.tr("全部"), None)
        for name in obs.SEVERITY_NAMES:
            self.level.addItem(name, name)
        self.level.currentTextChanged.connect(lambda _=None: self._rebuild())
        self.category = QComboBox()
        self.category.currentTextChanged.connect(lambda _=None: self._rebuild())
        self.search = QLineEdit()
        tr_placeholder(self.search, "文本 / 事件名 / 字段…")
        self.search.textChanged.connect(lambda _=None: self._rebuild())

        self.btn_refresh = TrButton("刷新历史")
        self.btn_refresh.clicked.connect(self.refresh_history)
        self.btn_export = TrButton("导出 JSONL…")
        self.btn_export.clicked.connect(self._on_export)

        bar = QHBoxLayout()
        bar.addWidget(TrLabel("最低级别"))
        bar.addWidget(self.level)
        bar.addWidget(TrLabel("类别"))
        bar.addWidget(self.category)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.btn_refresh)
        bar.addWidget(self.btn_export)

        # ---------------- 表格 ----------------
        self.table = QTableWidget(0, len(_COLUMNS))
        tr_header(self.table, _COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._show_selected)
        self.table.setColumnWidth(0, 108)
        self.table.setColumnWidth(1, 64)
        self.table.setColumnWidth(2, 96)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumBlockCount(4000)
        self.detail.setStyleSheet(
            "QPlainTextEdit{background:#1e1e1e;color:#c8c8c8;"
            "font-family:'DejaVu Sans Mono','Courier New',monospace;font-size:12px;}")

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 2)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#a0a0a0;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addLayout(bar)
        lay.addWidget(split, 1)
        lay.addWidget(self.status)

        self._sync_categories()
        self._rebuild()

    # ---------------- 外部 ----------------
    def append(self, rec: dict):
        """实时追加一条（主窗口的 `sig_log_record` 连到这里，GUI 线程）。"""
        if not isinstance(rec, dict):
            return
        self._records.append(rec)
        added = self._sync_categories()
        if not self._matches(rec):
            self._update_status()
            return
        self._visible.insert(0, rec)
        if added:
            self._rebuild()          # 类别下拉变了，整表重建一次保持排序/编号一致
            return
        self._insert_row(0, rec)
        self._trim_rows()
        self._update_status()

    def refresh_history(self):
        """从文件重新读回历史（含轮转备份），并保留实时追加的语义。"""
        self._records = collections.deque(self.slog.read_history(self._history_limit),
                                          maxlen=obs.RING_SIZE)
        self._sync_categories()
        self._rebuild()

    # ---------------- 筛选 ----------------
    def _matches(self, rec: dict) -> bool:
        level = self.level.currentData()
        if level and obs.severity_number(rec.get("severity")) < \
                obs.severity_number(level):
            return False
        cat = self.category.currentData()
        if cat and _category(rec) != cat:
            return False
        needle = self.search.text().strip().lower()
        if needle:
            blob = " ".join((i18n.tr(str(rec.get("body", ""))),
                             str(rec.get("body", "")),
                             str(rec.get("event", "")),
                             json.dumps(rec.get("fields") or {}, ensure_ascii=False)))
            if needle not in blob.lower():
                return False
        return True

    def _sync_categories(self) -> bool:
        """把新出现的类别补进下拉框；返回是否新增。"""
        cats = sorted({_category(r) for r in self._records})
        if cats == self._category_choices:
            return False
        current = self.category.currentData()
        self._category_choices = cats
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem(i18n.tr("全部"), None)
        for cat in cats:
            self.category.addItem(cat, cat)
        idx = self.category.findData(current)
        self.category.setCurrentIndex(idx if idx >= 0 else 0)
        self.category.blockSignals(False)
        return True

    def _rebuild(self):
        rows = [r for r in reversed(self._records) if self._matches(r)]
        self._visible = rows
        self.table.setRowCount(0)
        for i, rec in enumerate(rows):
            self._insert_row(i, rec)
        if rows:
            self.table.selectRow(0)
        else:
            self.detail.clear()
        self._update_status()

    def _insert_row(self, row: int, rec: dict):
        self.table.insertRow(row)
        # 历史/切语言前的记录：body 若正好是翻译表的源串就按当前语言显示；
        # 详情面板仍给原始 JSON（诊断要的是原样字节）。
        values = (_local_time(rec), str(rec.get("severity", "")),
                  _category(rec), i18n.tr(str(rec.get("body", ""))))
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            if col == 1:
                color = _LEVEL_COLOR.get(values[1])
                if color:
                    item.setForeground(QBrush(QColor(color)))
            self.table.setItem(row, col, item)

    def _trim_rows(self):
        """表格最多展示 `history_limit` 行；内存里保留得更多，刷新可回看。"""
        while self.table.rowCount() > self._history_limit:
            self.table.removeRow(self.table.rowCount() - 1)
            if self._visible:
                self._visible.pop()

    def _update_status(self):
        self.status.setText(i18n.tr(
            "显示 {shown} / 共 {total} 条 · 文件 {path}",
            shown=len(self._visible), total=len(self._records),
            path=self.slog.path))

    def _show_selected(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self._visible):
            return
        self.detail.setPlainText(
            json.dumps(self._visible[row], ensure_ascii=False, indent=2))

    # ---------------- 导出 ----------------
    def _on_export(self):
        if not self._visible:
            QMessageBox.information(self, i18n.tr("导出日志"),
                                    i18n.tr("当前筛选结果为空。"))
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("导出筛选后的日志"), f"litearm_log_{stamp}.jsonl",
            i18n.tr("JSON Lines (*.jsonl);;全部 (*)"))
        if not path:
            return
        # 表格是新→旧，文件按时间顺序写。
        rows = list(reversed(self._visible))
        try:
            n = obs.export_jsonl(path, rows)
        except Exception as e:  # noqa: BLE001 - 导出失败不该拖垮界面
            QMessageBox.warning(self, i18n.tr("导出失败"), str(e))
            return
        QMessageBox.information(self, i18n.tr("导出完成"),
                                i18n.tr("已写出 {n} 条 → {path}", n=n, path=path))

    def retranslate(self):
        if self.level.count():
            self.level.setItemText(0, i18n.tr("全部"))
        if self.category.count():
            self.category.setItemText(0, i18n.tr("全部"))
        self._rebuild()          # 重渲染历史记录里的 body（能翻的按当前语言显示）
