"""日志页 —— 历史加载、实时追加、级别/类别/文本筛选、详情、导出。"""
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication                      # noqa: E402

from litetool import obs                                      # noqa: E402
from litetool.gui.pages.log_page import LogPage               # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _seed(tmp_path):
    log = obs.StructuredLogger(tmp_path)
    log.info("连接成功", category="session", event="session.connect.succeeded")
    log.warn("命令超时", category="command", event="command.failed",
             fields={"name": "movej"})
    log.error("J4 断线", category="fault", event="fault.detected",
              fields={"joint": 4, "reason": 1})
    return log


def test_page_loads_history_and_filters(app, tmp_path):
    log = _seed(tmp_path)
    page = LogPage(log)
    try:
        assert page.table.rowCount() == 3

        page.level.setCurrentText("ERROR")
        assert page.table.rowCount() == 1, "级别是最低门槛：ERROR 只留 ERROR/FATAL"
        assert page._visible[0]["body"] == "J4 断线"

        page.level.setCurrentText("全部")
        page.category.setCurrentText("command")
        assert page.table.rowCount() == 1
        assert page._visible[0]["body"] == "命令超时"

        page.category.setCurrentText("全部")
        page.search.setText("movej")
        assert page.table.rowCount() == 1, "文本要能搜到 fields 里的命令名"

        page.search.clear()
        assert page.table.rowCount() == 3
        assert "tool.jsonl" in page.status.text()
    finally:
        page.close()
        log.close()


def test_live_append_updates_table_and_categories(app, tmp_path):
    log = _seed(tmp_path)
    page = LogPage(log)
    try:
        rec = log.info("新类别", category="activation", event="activation.succeeded")
        page.append(rec)
        assert page.table.rowCount() == 4
        assert page.category.findText("activation") >= 0
    finally:
        page.close()
        log.close()


def test_selected_row_shows_the_raw_record(app, tmp_path):
    log = _seed(tmp_path)
    page = LogPage(log)
    try:
        page.table.selectRow(1)
        raw = page.detail.toPlainText()
        assert '"event"' in raw
        assert '"fields"' in raw
        json.loads(raw)          # 详情必须是合法 JSON
    finally:
        page.close()
        log.close()


def test_history_reload_after_restart(app, tmp_path):
    log = _seed(tmp_path)
    log.close()
    log2 = obs.StructuredLogger(tmp_path)
    page = LogPage(log2)
    try:
        assert page.table.rowCount() == 3, "重启后必须从 JSONL 读回历史"
    finally:
        page.close()
        log2.close()


def test_export_writes_the_filtered_view(app, tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QFileDialog, QMessageBox

    log = _seed(tmp_path)
    page = LogPage(log)
    try:
        page.level.setCurrentText("WARN")     # WARN + ERROR => 2 条
        target = tmp_path / "filtered.jsonl"
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (str(target), "")))
        seen = []
        monkeypatch.setattr(QMessageBox, "information",
                            staticmethod(lambda *a, **k: seen.append(a[2])))
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: seen.append(a[2])))
        page._on_export()
        lines = [json.loads(x) for x in target.read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 2
        # 文件按时间顺序写：先 WARN 后 ERROR
        assert [r["body"] for r in lines] == ["命令超时", "J4 断线"]
        assert any("已写出 2 条" in str(m) for m in seen)
    finally:
        page.close()
        log.close()
