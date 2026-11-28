"""调参指南页 —— 公式/须知/速查表 (HTML) + 可展开/收起的逐参数详解。

- 公式/符号映射/读前须知/症状速查/ff 位脚注: 纯内容来自 litetool.tuning_guide。
- 逐参数详解与参数页 tooltip 同源: 全部取自 param_catalog 的 role/hint/detail
  (含 GlobalParam 与 ff_mask 位 FF_BIT_DETAIL), 避免两处不一致。
- reveal(key): 展开对应参数所属分组并滚动定位, 供"参数页选中行 → 指南详解"直达。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFrame, QLabel, QScrollArea,
                             QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from litetool import i18n
from litetool import param_catalog as C
from litetool import tuning_guide as G
from litetool.gui.i18n_ui import TrLabel, forget_tree

# 分组: (组标题, [关节参数 key 列表])
GROUPS = [
    ("关节控制 / 软限位 (kp,kd,tau_max,q_min,q_max)",
     ["kp", "kd", "tau_max", "q_min", "q_max"]),
    ("摩擦 v1 / 积分 / 限位墙",
     ["friction", "ki", "i_max", "wall_stiff", "wall_damp", "wall_tau_max"]),
    ("动力学缩放 (gs / is)",
     ["gravity_scale", "inertia_scale"]),
    ("摩擦 v2 (friction_model=1 时生效)",
     ["friction_v", "friction_fc0", "friction_fc1"]),
]


def _plain(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class _CollapsibleBox(QFrame):
    """标题可点击、内容可收起/展开的分组框。"""

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self._source = title
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(2)
        self.btn = QToolButton()
        self.btn.setText("▸ " + i18n.tr(title))
        self.btn.setCheckable(True)
        self.btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn.setStyleSheet("QToolButton{border:none;font-weight:bold;"
                               "text-align:left;padding:4px 2px;}"
                               "QToolButton::menu-indicator{image:none;}")
        self.btn.clicked.connect(self._toggle)
        self._content = content
        self._content.setVisible(False)
        lay.addWidget(self.btn)
        lay.addWidget(content)

    def _toggle(self):
        on = self.btn.isChecked()
        self.btn.setText(("▾ " if on else "▸ ") + self.btn.text()[2:])
        self._content.setVisible(on)

    def expand(self):
        if not self.btn.isChecked():
            self.btn.setChecked(True)
            self.btn.setText("▾ " + i18n.tr(self._source))
            self._content.setVisible(True)

    def retranslate(self):
        arrow = "▾ " if self.btn.isChecked() else "▸ "
        self.btn.setText(arrow + i18n.tr(self._source))


def _detail_label(title: str, role: str, hint: str, detail: str,
                  extra: str = "") -> QLabel:
    # 目录里的 role/hint/detail 已经按语言选好；这里不再二次翻译。
    txt = (f"<b>{_plain(title)}</b><br><i>{_plain(role)}</i>"
           f"<br>{_plain(hint)}<br><br>{_plain(detail)}")
    if extra:
        txt += f"<br><span style='color:#666;'>{_plain(i18n.tr(extra))}</span>"
    lab = QLabel(txt)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.RichText)
    return lab


class TuningGuidePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._key_widget = {}        # 参数 key / ff 位名 -> 详解块 QWidget
        self._collapsibles = {}      # 组标题 -> _CollapsibleBox

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(6)

        self._content = content
        self._lay = lay
        self._populate()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _populate(self) -> None:
        lay = self._lay
        self._key_widget = {}
        self._collapsibles = {}
        # (1) 公式/须知/速查 (HTML)
        self.browser = QTextBrowser()
        self.browser.setHtml(G.build_guide_html())
        self.browser.setMinimumHeight(360)
        self.browser.setOpenExternalLinks(False)
        lay.addWidget(self.browser)

        # (2) 逐参数详解 —— 可收起/展开分组, 与参数页 tooltip 同源
        head = TrLabel("<h3>参数逐项详解</h3><span style='color:#666;'>"
                       "内容与参数页悬停提示同源 (param_catalog role/hint/detail); "
                       "点分组标题收起/展开。</span>")
        head.setTextFormat(Qt.RichText)
        head.setWordWrap(True)
        lay.addWidget(head)

        for title, keys in GROUPS:
            inner = self._build_joint_group(keys)
            box = _CollapsibleBox(title, inner)
            self._collapsibles[title] = box
            lay.addWidget(box)

        # 全局标量组
        inner_g = self._build_global_group()
        self._collapsibles["global"] = _CollapsibleBox(
            "全局标量 (fric_db/wall_margin/friction_slew/payload_mass/"
            "payload_com/gravity/friction_model/fric_v2_eps)", inner_g)
        lay.addWidget(self._collapsibles["global"])

        # ff_mask 位组
        inner_f = self._build_ff_group()
        self._collapsibles["ff"] = _CollapsibleBox("ff_mask 使能位", inner_f)
        lay.addWidget(self._collapsibles["ff"])

        lay.addStretch(1)

    def retranslate(self) -> None:
        """整块重建 —— 详解文字来自目录表，逐条重译比改控件少错。"""
        forget_tree(self._content)
        while self._lay.count():
            item = self._lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # 先摘掉再延迟删除：deleteLater 要等事件循环，而启动时紧接着
                # 就会重建；不摘掉会看到新旧两份标题叠在一起。
                widget.setParent(None)
                widget.deleteLater()
        self._populate()

    # ---- 详解块构建 ----
    def _joint_block(self, key: str) -> QWidget:
        p = C.JOINT_BY_KEY[key]
        extra = i18n.tr("范围 {range} · 写口 {write}",
                        range=p.range_text(), write=_params_write_desc(p))
        return self._mk_block(key, p.label_text(), p.role_text(), p.hint_text(),
                              p.detail_text(), extra)

    def _mk_block(self, key, title, role, hint, detail, extra="") -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 1, 4, 1)
        v.setSpacing(1)
        lab = _detail_label(title, role, hint, detail, extra)
        lab.setStyleSheet("border-left:3px solid #c8d6e5;padding-left:8px;"
                          "color:#333;")
        v.addWidget(lab)
        self._key_widget[key] = w
        return w

    def _build_joint_group(self, keys) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 0, 0, 0)
        v.setSpacing(6)
        for k in keys:
            v.addWidget(self._joint_block(k))
        return w

    def _build_global_group(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 0, 0, 0)
        v.setSpacing(6)
        for gp in C.GLOBAL_PARAMS:
            extra = i18n.tr("范围 {range}", range=gp.range_text())
            v.addWidget(self._mk_block(gp.key, gp.label_text(), gp.role_text(),
                                       gp.hint_text(), gp.detail_text(), extra))
        return w

    def _build_ff_group(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 0, 0, 0)
        v.setSpacing(6)
        for i, (mask, name, label) in enumerate(C.FF_BITS):
            detail = C.ff_detail_text(i) if i < len(C.FF_BITS) else label
            extra = i18n.tr("ff_mask 位 bit{bit} = 0x{mask:02X}", bit=i, mask=mask)
            v.addWidget(self._mk_block(name, i18n.tr("{name} 位", name=name),
                                       C.ff_label_text(i), "", detail, extra))
        return w

    # ---- reveal: 从参数页直达某参数详解 ----
    def reveal(self, key: str):
        if not key:
            return
        w = self._key_widget.get(key)
        if w is None:
            return
        # 先展开其所属分组 (若尚未展开)
        for box in self._collapsibles.values():
            if box._content is not None and self._find_child(box._content, w):
                box.expand()
        # 滚动定位
        self._scroll.ensureWidgetVisible(w, 0, 120)

    @staticmethod
    def _find_child(root, target) -> bool:
        if root is target:
            return True
        for ch in root.children():
            if isinstance(ch, QWidget) and TuningGuidePage._find_child(ch, target):
                return True
        return False


def _params_write_desc(p):
    """简短写口描述 (与 params_page._write_desc 同文案, 避免 import 循环)。"""
    if p.kind == "ctrl":
        return i18n.tr("0x22 (kp/kd/tau_max 成组)")
    if p.kind == "limits":
        return i18n.tr("0x23 (q_min/q_max 成组)")
    return i18n.tr("0x26 item {item} (7 关节整组)", item=p.item)
