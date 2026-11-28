"""静态界面文案的切换支持 —— 控件在构造时登记"源文案"，切语言时统一重写。

为什么不让每个页面自己遍历控件
------------------------------
页面里动态值（UID、固件号、实测角）和静态文案混在一起，靠 ``text()`` 反查
"这句该不该翻"必然误判。所以静态文案在**构造那一刻**登记：``TrLabel`` /
``TrButton`` / ``tr_tooltip()`` / ``tr_header()`` 记下源串与属性，动态文案则
在赋值处直接 ``i18n.tr(...)``，永远不登记。

约定
----
* 静态按钮/标题 → ``TrButton`` / ``TrLabel`` / ``TrGroupBox`` / ``TrCheckBox``。
* 会随状态变化的控件仍可用 ``Tr*`` 起一个初始文案，但页面必须实现
  ``retranslate()`` 把当前状态重新写一遍 —— 登记表先统一重写，页面钩子后跑，
  所以最终显示的是状态文案，而不是构造时的占位文案。
* 组合框的静态条目用 ``tr_item()`` / ``tr_items()``；动态重建的（日志类别）由
  页面自己处理。
"""
from __future__ import annotations

import weakref

from PyQt5.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QGroupBox,
                             QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                             QToolButton, QWidget)

from litetool import i18n

#: (weakref, attr, index, source) —— index 只对表头/下拉条目有意义。
_BINDINGS: list = []


def _remember(widget: QWidget, attr: str, source: str, index=None,
              fmt=None) -> None:
    if widget is None or not source:
        return
    binding = (attr, index, str(source), dict(fmt) if fmt else None)
    stored = getattr(widget, "_i18n_bindings", None)
    if stored is None:
        stored = []
        setattr(widget, "_i18n_bindings", stored)
        _BINDINGS.append(weakref.ref(widget))
    if binding not in stored:
        stored.append(binding)


def bind(widget: QWidget, attr: str, source: str, index=None, fmt=None) -> None:
    """登记一条静态文案并立即按当前语言写入。``fmt`` 是命名占位符的值。"""
    _remember(widget, attr, source, index, fmt)
    _apply(widget, attr, index, str(source), fmt)


def _apply(widget, attr: str, index, source: str, fmt=None) -> None:
    text = i18n.tr(source, **(fmt or {}))
    if attr == "text":
        widget.setText(text)
    elif attr == "title":
        widget.setTitle(text)
    elif attr == "toolTip":
        widget.setToolTip(text)
    elif attr == "placeholder":
        if hasattr(widget, "setPlaceholderText"):
            widget.setPlaceholderText(text)
    elif attr == "windowTitle":
        widget.setWindowTitle(text)
    elif attr == "header" and index is not None:
        widget.setHorizontalHeaderItem(index, QTableWidgetItem(text))
    elif attr == "item" and index is not None:
        widget.setItemText(index, text)


def retranslate_all() -> None:
    """按登记表重写全部静态文案；已销毁的控件自动跳过。"""
    alive = []
    for ref in _BINDINGS:
        widget = ref()
        if widget is None:
            continue
        alive.append(ref)
        for attr, index, source, fmt in list(getattr(widget, "_i18n_bindings", [])):
            try:
                _apply(widget, attr, index, source, fmt)
            except RuntimeError:
                # 底层 C++ 对象已销毁（页面重建/关闭）—— 丢掉这条登记。
                break
    _BINDINGS[:] = alive


def forget_tree(root: QWidget) -> None:
    """页面整块重建前丢掉其子控件的登记，避免登记表一直涨。"""
    removed = {id(w) for w in [root, *root.findChildren(QWidget)]}
    _BINDINGS[:] = [ref for ref in _BINDINGS if id(ref()) not in removed]


# ---------------------------------------------------------------------------
# 控件包装
# ---------------------------------------------------------------------------
class TrLabel(QLabel):
    def __init__(self, source: str, parent=None, **fmt):
        super().__init__("", parent)
        bind(self, "text", source, fmt=fmt or None)


class TrButton(QPushButton):
    def __init__(self, source: str, parent=None):
        super().__init__("", parent)
        bind(self, "text", source)


class TrToolButton(QToolButton):
    def __init__(self, source: str, parent=None):
        super().__init__(parent)
        bind(self, "text", source)


class TrCheckBox(QCheckBox):
    def __init__(self, source: str, parent=None):
        super().__init__("", parent)
        bind(self, "text", source)


class TrGroupBox(QGroupBox):
    def __init__(self, source: str, parent=None, **fmt):
        super().__init__("", parent)
        bind(self, "title", source, fmt=fmt or None)


def tr_tooltip(widget: QWidget, source: str, **fmt) -> None:
    bind(widget, "toolTip", source, fmt=fmt or None)


def tr_placeholder(widget: QWidget, source: str, **fmt) -> None:
    bind(widget, "placeholder", source, fmt=fmt or None)


def tr_window_title(widget: QWidget, source: str) -> None:
    bind(widget, "windowTitle", source)


def tr_header(table: QTableWidget, sources) -> None:
    for col, source in enumerate(sources):
        bind(table, "header", source, index=col)


def tr_item(combo: QComboBox, source: str, data=None) -> None:
    combo.addItem("", data)
    bind(combo, "item", source, index=combo.count() - 1)


def tr_items(combo: QComboBox, items) -> None:
    for source, data in items:
        tr_item(combo, source, data)


# ---------------------------------------------------------------------------
# 活语言切换
# ---------------------------------------------------------------------------
def retranslate(language=None) -> None:
    """``set_language`` + 重写登记表；返回实际语言。"""
    lang = i18n.set_language(language if language is not None else i18n.language())
    retranslate_all()
    return lang
