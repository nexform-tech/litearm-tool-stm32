"""英文界面实建检查 —— 静态/动态文案都不许残留中文。

只钉"界面看得见的东西"：控件文本、tooltip、占位符、表头、下拉条目、导航。
语言名 ``简体中文`` 是刻意保留的自称，允许出现。深层异常文本（3D 资产解析、
DFU 引擎诊断）不在此列 —— 它们由各自的错误码文案/短码接管。
"""
from __future__ import annotations

import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")

from PyQt5.QtWidgets import (QAbstractButton, QComboBox, QGroupBox, QLabel,  # noqa: E402
                             QTableWidget, QWidget)

from litetool import i18n                                            # noqa: E402
from litetool import settings as settings_mod                        # noqa: E402
from litetool.gui.main_window import MainWindow                      # noqa: E402
from litetool.gui.prefs import UiPreferences                         # noqa: E402

_CJK = re.compile(r"[一-鿿]")
_ALLOWED = {"简体中文"}


def _win(tmp_path, preference: str = "en") -> MainWindow:
    from PyQt5.QtWidgets import QApplication
    _ = QApplication.instance() or QApplication([])
    prefs = UiPreferences(path=str(tmp_path / "ui.ini"))
    prefs.set_language(preference)
    return MainWindow(settings_mod.Settings.load(None), prefs=prefs)


def _visible_strings(root: QWidget):
    widgets = [root, *root.findChildren(QWidget)]
    for w in widgets:
        for attr in ("text", "toolTip", "placeholderText", "windowTitle"):
            getter = getattr(w, attr, None)
            if callable(getter):
                try:
                    value = getter()
                except Exception:  # noqa: BLE001 - 某些控件在 offscreen 下无值
                    continue
                if isinstance(value, str) and value:
                    yield type(w).__name__, attr, value
        if isinstance(w, QComboBox):
            for i in range(w.count()):
                yield "QComboBox", "item", w.itemText(i)
        plain = getattr(w, "toPlainText", None)
        if callable(plain):
            try:
                value = plain()
            except Exception:  # noqa: BLE001
                value = ""
            if value:
                yield type(w).__name__, "toPlainText", value
        if isinstance(w, QTableWidget):
            for c in range(w.columnCount()):
                item = w.horizontalHeaderItem(c)
                if item is not None and item.text():
                    yield "QTableWidget", "header", item.text()


def _chinese(values):
    out = []
    for kind, attr, text in values:
        cleaned = text.replace("简体中文", "")
        if _CJK.search(cleaned) and text not in _ALLOWED:
            out.append(f"{kind}.{attr}: {text[:100]!r}")
    return out


def test_english_window_has_no_chinese_static_text(tmp_path):
    w = _win(tmp_path, "en")
    try:
        leftover = _chinese(_visible_strings(w))
        assert leftover == [], "英文界面仍有中文:\n" + "\n".join(leftover)
    finally:
        w.close()


def test_english_window_stays_clean_with_live_state(tmp_path):
    """喂一帧真实形状的状态并跑一遍各页刷新，动态文案也不许出现中文。"""
    from tests.fake_arm import make_state

    w = _win(tmp_path, "en")
    try:
        w.worker._state = make_state(n=7, q=[0.1 * i for i in range(7)])
        w._tick()
        w._tick_plot()
        w.pages["cart"].set_cart_supported(False)
        w.pages["gripper"]._tick()
        w.pages["machine"].set_metrics(0, 100.0, "normal")
        leftover = _chinese(_visible_strings(w))
        assert leftover == [], "动态刷新后仍有中文:\n" + "\n".join(leftover)
    finally:
        w.close()


def test_english_guide_and_param_metadata_have_no_chinese(tmp_path):
    w = _win(tmp_path, "en")
    try:
        guide = w.pages["guide"]
        assert "动力学" not in guide.browser.toPlainText()
        assert "Dynamics" in guide.browser.toPlainText()

        params = w.pages["params"]
        for ri in range(params.table.rowCount()):
            item = params.table.item(ri, 0)
            assert item is not None and not _CJK.search(item.text()), item.text()
            assert not _CJK.search(item.toolTip()), item.toolTip()[:120]
        for p in ("kp", "gravity_scale"):
            assert not _CJK.search(str(params._row_tooltip(
                __import__("litetool.param_catalog", fromlist=["X"]).JOINT_BY_KEY[p])))
    finally:
        w.close()


def test_live_switch_updates_nav_and_top_bar(tmp_path):
    w = _win(tmp_path, "zh")
    try:
        assert w.nav.topLevelItem(0).text(0) == "监视"
        assert w.pages["overview"] is w.current_page()
        w._on_language_changed("en")
        assert i18n.language() == "en"
        assert w.nav.topLevelItem(0).text(0) == "Monitor"
        assert w.nav.topLevelItem(1).text(0) == "Operate"
        assert w.btn_conn.text() in ("Connect", "Disconnect")
        assert not _CJK.search(w.fw_lbl.text())
        w._on_language_changed("zh")
        assert w.nav.topLevelItem(0).text(0) == "监视"
    finally:
        w.close()


def test_settings_combo_switch_persists(tmp_path):
    w = _win(tmp_path, "zh")
    try:
        page = w.pages["settings"]
        page.combo.setCurrentIndex(page.combo.findData("en"))
        assert i18n.language() == "en"
        assert w._prefs.language() == "en"
        page.combo.setCurrentIndex(page.combo.findData(""))
        assert w._prefs.language() == ""
    finally:
        w.close()


def test_language_choice_persists_and_auto_clears(tmp_path):
    path = str(tmp_path / "ui.ini")
    prefs = UiPreferences(path=path)
    assert prefs.language() == ""
    prefs.set_language("en")
    assert UiPreferences(path=path).language() == "en"
    prefs.set_language("")
    assert UiPreferences(path=path).language() == ""


def test_settings_page_reports_effective_language(tmp_path):
    w = _win(tmp_path, "en")
    try:
        page = w.pages["settings"]
        page.set_state("", "zh")
        assert "简体中文" in page.combo.itemText(0)   # 跟随系统 → 简体中文
        page.set_state("en", "zh")
        assert page.combo.currentData() == "en"
    finally:
        w.close()


def test_firmware_reason_text_is_english_and_clean():
    from litetool.gui.pages import firmware_page
    try:
        i18n.set_language("en")
        for key in firmware_page._REASON_TEXT:
            text = firmware_page._reason_text(key, "engine said 中文")
            assert text and not _CJK.search(text), (key, text)
    finally:
        i18n.set_language("zh")


def test_english_confirmation_dialogs_are_clean(tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox

    from litetool import checks
    from tests.fake_arm import make_state

    w = _win(tmp_path, "en")
    captured = []

    def question(_parent, title, text, *_a, **_k):
        captured.append((title, text))
        return QMessageBox.Ok

    def warning(_parent, title, text, *_a, **_k):
        captured.append((title, text))
        return QMessageBox.Ok

    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    try:
        w.worker._state = make_state(n=7)
        assert w._confirm_home()
        assert w._confirm_clear_faults()
        assert w._confirm_motion(checks.plan_motion([0.0] * 7, [1.0] * 7, 0.5))
        assert captured
        for title, text in captured:
            assert not _CJK.search(title), title
            assert not _CJK.search(text), text
    finally:
        w.close()
