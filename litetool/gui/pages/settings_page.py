"""设置页 —— 目前只有界面语言（后续主题等也放这里）。

语言选项三档：跟随系统 / 简体中文 / English。选中即生效（不重启），选择由主窗口
写进 ``QSettings``；选"跟随系统"会清掉保存的选择，回到 ``config.yaml`` 的
``language``，再回落到系统检测。语言名保持各语言自称，不在中英文之间互译。
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from litetool import i18n
from litetool.gui.i18n_ui import TrGroupBox, TrLabel, tr_tooltip

AUTO = ""
OPTIONS = (AUTO, "zh", "en")


class SettingsPage(QWidget):
    language_changed = pyqtSignal(str)

    def __init__(self, preference: str = "", default_language: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._preference = preference if preference in OPTIONS else AUTO
        #: `auto` 实际会落到哪种语言（config.yaml 的 language，否则系统检测）。
        self._default_language = i18n.normalize_language(default_language) or \
            i18n.DEFAULT_LANGUAGE
        self._loading = False

        self.title = TrLabel("界面语言")
        self.title.setStyleSheet("font-weight:bold;font-size:14px;")
        self.combo = QComboBox()
        self.combo.setMinimumWidth(240)
        self.combo.currentIndexChanged.connect(self._on_changed)
        tr_tooltip(self.combo,
                   "切换后立即生效，并记住这台机器上的选择。\n"
                   "「跟随系统」= 按桌面语言自动选择；config.yaml 的 language 可改默认。")
        self.state_lbl = QLabel("")
        self.state_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")
        self.state_lbl.setWordWrap(True)

        box = TrGroupBox("语言")
        lay = QVBoxLayout(box)
        lay.addWidget(self.title)
        lay.addWidget(self.combo)
        lay.addWidget(self.state_lbl)
        note = TrLabel(
            "默认跟随系统：中文桌面显示中文，其余显示英文。除非这里选过，"
            "否则以 config.yaml 的 language 为准（auto = 跟随系统）。")
        note.setWordWrap(True)
        lay.addWidget(note)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(box)
        outer.addStretch(1)
        self._fill()
        self._update_state()

    # ------------------------------------------------------------------ 状态
    def set_state(self, preference: str, default_language: str | None = None) -> None:
        self._preference = preference if preference in OPTIONS else AUTO
        if default_language:
            self._default_language = i18n.normalize_language(default_language) or \
                i18n.DEFAULT_LANGUAGE
        self._fill()
        self._update_state()

    def _fill(self) -> None:
        self._loading = True
        try:
            self.combo.clear()
            self.combo.addItem("", AUTO)
            self.combo.addItem("简体中文", "zh")
            self.combo.addItem("English", "en")
            self.retranslate_labels()
            idx = self.combo.findData(self._preference)
            self.combo.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._loading = False

    def retranslate_labels(self) -> None:
        """只重写"跟随系统"这一项 —— 另外两项是语言自称，不翻。"""
        auto = i18n.tr("跟随系统") + f"（{i18n.LANGUAGE_NAMES[self._default_language]}）"
        if self.combo.count():
            self.combo.setItemText(0, auto)

    def default_language(self) -> str:
        return self._default_language

    def _update_state(self) -> None:
        effective = i18n.resolve_language(self._preference,
                                          ui_languages=[self._default_language])
        self.state_lbl.setText(i18n.tr(
            "当前界面语言：{name}（{code}）",
            name=i18n.LANGUAGE_NAMES.get(effective, effective), code=effective))

    def _on_changed(self, _idx: int) -> None:
        if self._loading:
            return
        value = self.combo.currentData() or AUTO
        if value == self._preference:
            return
        self._preference = value
        self._update_state()
        self.language_changed.emit(value)

    # 主窗口切语言后调用 —— 登记表已重写静态文案，这里补动态项与状态行。
    def retranslate(self) -> None:
        self.retranslate_labels()
        self._update_state()
