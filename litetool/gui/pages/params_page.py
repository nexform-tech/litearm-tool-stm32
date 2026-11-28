"""参数调参页 —— 逐关节参数表 + 全局标量 + ff_mask 复选框 + yaml/json 批量导入导出。

架构:
- 数据镜像表在 litetool/param_catalog.py (纯 Python, 供测试/yaml/UI 共用)。
- 本页**不自建线程**: 每个操作经 `set_submit` 注入的投递函数排到 SDK 所有者线程,
  写口顺序执行、逐个等 ACK; 结果经 Qt 信号回主线程着色。
- 安全: GUI 先按目录钳幅校验并提示范围 (固件仍兜底); 未 [刷新当前] 前禁一切下发;
  ff_mask 改动 / param_save / 恢复出厂 / 批量应用 发送前均弹确认。界面中文。
"""

import os

import yaml
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QPlainTextEdit,
                             QDoubleSpinBox, QFileDialog, QGridLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                             QMessageBox, QPushButton, QScrollArea,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from litetool import hyy_config as HY
from litetool import i18n
from litetool import model_io as MIO
from litetool import param_catalog as C
from litetool import params_io as PIO
from litetool.gui.i18n_ui import (TrButton, TrGroupBox, TrLabel, tr_header,
                                  tr_items, tr_tooltip)

ROLE_VAL = Qt.UserRole + 1          # 单元格 float 值 (显示文本只作编辑入口)
BG = {0: QColor("#ffffff"), 1: QColor("#fff3bf"),
      2: QColor("#ffd9d9"), 3: QColor("#ffcccc")}   # 0常规 1改未发 2越界 3下发失败
FG_INVALID = QColor("#b00020")
JOINT_KEYS = [p.key for p in C.JOINT_PARAMS]
GROUP_KEYS = {"ctrl": ("kp", "kd", "tau_max"), "limits": ("q_min", "q_max")}


class ParamsPage(QWidget):
    show_guide = pyqtSignal(str)          # 请求打开调参指南并跳转到指定参数 key (''=只开页)
    _sig_refreshed = pyqtSignal(object)
    _sig_rows_done = pyqtSignal(object)
    _sig_global_done = pyqtSignal(object)
    _sig_batch_done = pyqtSignal(object)
    _sig_saved = pyqtSignal(bool, str)
    _sig_factory_done = pyqtSignal(bool, str)
    _sig_busy = pyqtSignal(bool)
    _sig_model_probe = pyqtSignal(object)     # [2026-09-14] 模型能力探测回调
    _sig_hyy_done = pyqtSignal(object)        # HYY 导入下发完成
    _sig_model_revert = pyqtSignal(object)    # 0x37 回退模型完成
    _sig_model_after_revert = pyqtSignal(object)  # 回退后重读模型

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log = lambda msg: None
        self._submit = None
        self._st = None
        self._online = False
        self._busy = False
        self._ext_busy = False          # MainWindow 侧运动/控制命令在途
        self._loading = False
        self._device_synced = False     # 成功"刷新当前"后置 True —— 此前禁止任何下发
                                        # (防 QDoubleSpinBox 默认=range 下限被盲发)
        self._baseline = None           # 最近设备读回/整发成功快照 (diff 的"旧")
        self._synced = {}               # {row_key: {joint: float}}
        self._synced_glob = None        # global 基线 (含 ff_mask)
        self._pending_export = None     # 导出流程: 待读回完成后写入的 yaml 路径
        #: 板子**实测支持**的 item 集合 (来自 read_snapshot 的 supported)。None = 尚未
        #: 读到 —— 此时全部显示(目录全集), 读到后不支持的项隐藏且不参与下发。
        self._sup_vec = None
        self._sup_scalar = None
        #: 全局参数每个格子的容器 (用于按 supported 隐藏); key -> QWidget
        self._g_cells = {}
        # ---- [2026-09-14] 动力学模型在线导入 ----
        #: 模型基线**三态**: `_model_supported` = None(未知)/False(老固件)/True(支持);
        #: 只用一个 None 会把"还没读过"与"固件无能力"混为一谈, 导致首次导入被误阻断。
        self._model_supported = None
        self._model_baseline = None     # read_model() 的结果 (dict) 或 None
        self._pending_import = None     # 探测→对话框的两跳之间暂存 (path, snap, model, notes)
        self._build_ui()
        self._sig_refreshed.connect(self._on_refreshed)
        self._sig_rows_done.connect(self._on_rows_done)
        self._sig_global_done.connect(self._on_global_done)
        self._sig_batch_done.connect(self._on_batch_done)
        self._sig_saved.connect(self._on_saved)
        self._sig_factory_done.connect(self._on_factory_done)
        self._sig_busy.connect(self._set_busy_ui)
        self._sig_model_probe.connect(self._on_model_probe)
        self._sig_hyy_done.connect(self._on_hyy_done)
        self._sig_model_revert.connect(self._on_model_revert_done)
        self._sig_model_after_revert.connect(self._on_model_after_revert)
        self._refresh_state()

    # ================= 界面 =================
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        bar = QHBoxLayout()
        self.btn_refresh = TrButton("刷新当前")
        self.btn_refresh.clicked.connect(self._on_refresh)
        self.btn_apply_row = TrButton("下发选中行")
        self.btn_apply_row.clicked.connect(lambda: self._apply_rows_selected())
        self.btn_apply_all = TrButton("下发全部")
        self.btn_apply_all.clicked.connect(lambda: self._apply_rows_selected(all_rows=True))
        self.btn_import = TrButton("导入…")
        tr_tooltip(self.btn_import, "从 YAML/JSON 导入整套参数（须先 [刷新当前]）")
        self.btn_import.clicked.connect(self._on_import)
        self.btn_import_hyy = TrButton("从 HYY 配置导入…")
        tr_tooltip(
            self.btn_import_hyy,
            "解析 HYY/SE1 控制器辨识出的 DeviceConfig.yaml, 把参数 + 动力学模型\n"
            "写进固件 (无需重新编译固件)。\n"
            "映射: 摩擦三元组 / 软限位(与 URDF 硬限位取交集) / tau_max / 重力向量\n"
            "      + 模型段 (m/com/I/jm)。\n"
            "需先 [刷新当前] 建立基线 (未映射字段从基线取)。")
        self.btn_import_hyy.clicked.connect(self._on_import_hyy)
        self.btn_revert_model = TrButton("回退模型")
        tr_tooltip(
            self.btn_revert_model,
            "CMD_REVERT_MODEL (0x37): 只把动力学模型回退到出厂编译期常量,\n"
            "不动其它参数、也不动 flash。\n"
            "⚠ 需失能; 且 flash 里的导入模型仍在 (重新上电会复活),\n"
            "   此后**不要再点固化** —— 那会永久删除它。")
        self.btn_revert_model.clicked.connect(self._on_revert_model)
        self.btn_export = TrButton("导出当前")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_save = TrButton("固化 Flash…")
        self.btn_save.clicked.connect(self._on_save_flash)
        self.btn_reset = TrButton("恢复出厂…")
        tr_tooltip(
            self.btn_reset,
            "固件 PARAM_RESET (0x36)：恢复出厂默认 + 失效 flash。\n"
            "固件要求失能态（擦写窗口 CPU 停顿），enable 态会回 ERR 0x04。")
        self.btn_reset.clicked.connect(self._on_reset_factory)
        self.btn_guide = TrButton("❓ 调参指南")
        tr_tooltip(self.btn_guide,
                   "打开[调参指南]页并跳到选中行的参数详解 (纯说明, 无需连接)")
        self.btn_guide.clicked.connect(self._on_open_guide)
        for b in (self.btn_refresh, self.btn_apply_row, self.btn_apply_all,
                  self.btn_import, self.btn_import_hyy, self.btn_revert_model,
                  self.btn_export, self.btn_save, self.btn_reset):
            bar.addWidget(b)
        bar.addWidget(self.btn_guide)
        bar.addStretch(1)
        lay.addLayout(bar)

        body = QScrollArea()
        body.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 0, 0)

        # 逐关节表
        g1 = TrGroupBox("逐关节参数 (双击编辑; 黄=已改未下发; 红=越界/下发失败)")
        v1 = QVBoxLayout(g1)
        self.table = QTableWidget(len(C.JOINT_PARAMS), 1 + C.NUM_JOINTS)
        tr_header(self.table, ["参数"] + [f"J{i + 1}" for i in range(C.NUM_JOINTS)])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked
                                   | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in range(1, 1 + C.NUM_JOINTS):
            hdr.setSectionResizeMode(c, QHeaderView.Stretch)
        for ri, p in enumerate(C.JOINT_PARAMS):
            head = QTableWidgetItem(p.label_text())
            head.setFlags(Qt.ItemIsEnabled)
            head.setToolTip(self._row_tooltip(p))
            head.setBackground(QColor("#eceff4"))
            self.table.setItem(ri, 0, head)
            for j in range(C.NUM_JOINTS):
                it = QTableWidgetItem("")
                it.setData(ROLE_VAL, None)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
                it.setToolTip(self._param_tooltip(p))
                it.setBackground(BG[0])
                self.table.setItem(ri, 1 + j, it)
        self.table.itemChanged.connect(self._on_cell_changed)
        v1.addWidget(self.table)
        tip = TrLabel("提示: [kp/kd/tau_max] 与 [q_min/q_max] 成组下发 (选中任一组员即整组下发);"
                      " 标 (v2) 的摩擦参数在 friction_model=1 时生效; 行首悬停见写口/范围。")
        tip.setWordWrap(True)
        v1.addWidget(tip)
        col.addWidget(g1)

        # 全局标量 —— 紧凑多列网格 (每格=小标题+控件; 悬停有详解)
        g2 = TrGroupBox("全局参数 (写 0x28 / 读 0x2C) — 悬停各项看详解")
        gg = QGridLayout(g2)
        gg.setHorizontalSpacing(8)
        gg.setVerticalSpacing(6)
        self._g_spins = {}
        self._g_captions = {}
        self._g_model = None
        NCOL = 3

        def _cap(text, tt) -> QLabel:
            lab = QLabel(text)
            lab.setStyleSheet("color:#444;font-size:11px;")
            lab.setToolTip(tt)
            return lab

        def _mk_global_cell(gp):
            """建一格: 小标题(带详解 tooltip) + 控件; 返回用于放 grid 的 QWidget。"""
            cell = QWidget()
            cv = QVBoxLayout(cell)
            cv.setContentsMargins(2, 2, 2, 2)
            cv.setSpacing(2)
            tt = self._param_tooltip(gp)
            if gp.key == "friction_model":
                cap = _cap("friction_model 0=v1 / 1=v2 / 2=drag", tt)
                self._g_model = QComboBox()
                tr_items(self._g_model, [
                    ("v1 — 误差方向 tanh", 0),
                    ("v2 — SE1 速度方向", 1),
                    ("v2-drag — 拖动专用(零速无增益)", 2)])
                self._g_model.setToolTip(tt)
                cv.addWidget(cap)
                cv.addWidget(self._g_model)
            elif gp.is_array:
                cap = _cap(i18n.tr("{label}  (x, y, z)", label=gp.label_text()), tt)
                hb = QHBoxLayout()
                hb.setContentsMargins(0, 0, 0, 0)
                hb.setSpacing(2)
                spins = []
                for ax in ("x", "y", "z"):
                    sp = self._mk_spin(gp)
                    sp.setFixedWidth(100)
                    sp.setObjectName(ax)
                    sp.setToolTip(i18n.tr("{axis} 分量\n\n{detail}\n\n范围 {range}",
                                          axis=ax, detail=tt,
                                          range=gp.range_text()))
                    spins.append(sp)
                    hb.addWidget(sp)
                self._g_spins[gp.key] = spins
                cv.addWidget(cap)
                cv.addLayout(hb)
            else:
                cap = _cap(gp.label_text(), tt)
                sp = self._mk_spin(gp)
                sp.setFixedWidth(150)
                self._g_spins[gp.key] = sp
                cv.addWidget(cap)
                cv.addWidget(sp)
            self._g_captions[gp.key] = cap
            return cell

        for k, gp in enumerate(C.GLOBAL_PARAMS):
            cell = _mk_global_cell(gp)
            self._g_cells[gp.key] = cell
            gg.addWidget(cell, k // NCOL, k % NCOL)
        self.btn_global = TrButton("下发全局\n(含 ff_mask)")
        self.btn_global.setMinimumHeight(44)
        self.btn_global.clicked.connect(self._on_apply_global)
        tr_tooltip(self.btn_global,
                   "把上表全局标量 + 右侧 ff_mask 一次性下发 RAM (0x28/0x27, 每写等 ACK)")
        gg.addWidget(self.btn_global, len(C.GLOBAL_PARAMS) // NCOL,
                     len(C.GLOBAL_PARAMS) % NCOL, Qt.AlignTop)
        col.addWidget(g2)

        # ff_mask 位 —— 一排小复选框, 缩写显示, 悬停看全名+含义
        g3 = TrGroupBox("ff_mask 前馈使能位 (写 0x27) — 缩写 M/G/I/C/F/Intg/Wall/Q/V, 悬停看含义")
        ffg = QHBoxLayout(g3)
        ffg.setSpacing(8)
        shorts = {"MASTER": "M", "G": "G", "INERTIA": "I", "CORIOLIS": "C",
                  "FRICTION": "F", "INTEGRAL": "Intg", "WALL": "Wall",
                  "QUANT": "Q", "VELREF": "V"}
        self._ff_cbs = []
        for i, (mask, name, label) in enumerate(C.FF_BITS):
            cb = QCheckBox(shorts.get(name, name))
            cb.setToolTip(self._ff_tooltip(i, mask, name, label))
            cb.toggled.connect(lambda _on, j=i: self._on_ff_toggled(j))
            self._ff_cbs.append(cb)
            ffg.addWidget(cb)
        ffg.addStretch(1)
        col.addWidget(g3)

        # [2026-09-14] "模型来源"常驻显示 —— 操作员唯一能看见"当前在用什么模型"的地方
        # (`store_from_flash` 只在 KIN_BENCH 文本应答里, 不在 100Hz 状态帧)。
        self.lbl_model = QLabel("模型: — (未读)")
        tr_tooltip(
            self.lbl_model,
            "动力学模型来源。\n"
            "  出厂 = 编译期常量 (dyn_model_data.h / dyn_jm_default.h)\n"
            "  导入 = 经 0x30/0x32/0x33 写入的辨识参数\n"
            "  staged = 已写入暂存区但尚未 commit 的项数\n"
            "  未固化 = RAM 与 flash 不一致 (掉电会回退)")
        self.lbl_model.setStyleSheet("color:#9aa0b0;padding:0 8px;")
        col.addWidget(self.lbl_model)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(
            "background:#23232a;color:#d8d8e0;padding:5px 8px;border-radius:3px;")
        col.addWidget(self.status)

        body.setWidget(inner)
        lay.addWidget(body, 1)

    @staticmethod
    def _write_desc(p) -> str:
        if p.kind == "ctrl":
            return i18n.tr("0x22 (kp/kd/tau_max 按关节成组)")
        if p.kind == "limits":
            return i18n.tr("0x23 (q_min/q_max 成组, 须 q_min<q_max)")
        return i18n.tr("0x26 item {item} (7 关节整组)", item=p.item)

    @staticmethod
    def _param_tooltip(p) -> str:
        """role/hint/detail 三合一详细悬停 (与[调参指南]逐项同源)。"""
        return "\n".join(x for x in (p.role_text(), p.hint_text(),
                                      p.detail_text()) if x)

    def _row_tooltip(self, p) -> str:
        return i18n.tr("{label} ({key}) · 写口 {write} · 范围 {range}\n\n{detail}",
                       label=p.label_text(), key=p.key,
                       write=self._write_desc(p), range=p.range_text(),
                       detail=self._param_tooltip(p))

    def _cell_tooltip(self, p, v) -> str:
        base = self._param_tooltip(p)
        return (i18n.tr("{key} = {value}\n\n{detail}", key=p.key,
                        value=repr(v), detail=base)
                if v is not None else base)

    @staticmethod
    def _ff_tooltip(i, mask, name, label) -> str:
        detail = C.ff_detail_text(i) if i < len(C.FF_BITS) else label
        return i18n.tr(
            "{name}  (bit{bit} · 0x{mask:02X})\n{label}\n\n{detail}\n\n"
            "改后需 [下发全局] 才生效 (发送前有确认)",
            name=name, bit=i, mask=mask, label=C.ff_label_text(i),
            detail=detail)

    def _mk_spin(self, gp) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(gp.lo, gp.hi)
        sp.setDecimals(gp.decimals)
        sp.setSingleStep(max((gp.hi - gp.lo) / 100.0, 1e-4))
        tt = self._param_tooltip(gp)
        sp.setToolTip(i18n.tr("{detail}\n\n范围 {range}",
                              detail=tt, range=gp.range_text()))
        return sp

    # ================= 状态 / 会话 =================
    def set_log(self, fn):
        self._log = fn

    def set_submit(self, fn):
        """由主窗口注入 `fn(name, callable, on_done)` —— 在 SDK 所有者线程上执行。"""
        self._submit = fn
        # 会话(重)建后设备参数未知 -> 禁下发, 待 [刷新当前] 成功
        self._device_synced = False
        # [2026-09-14] 换会话 = 旧会话在途任务的回调不会再到达本页 ⇒ 清忙态,
        # 否则新会话一进来页面就是灰的 (`_can_run` 恒 False)。
        self._busy = False
        self._refresh_state()

    def update_from(self, st):
        """主窗口周期喂当前 RobotState —— 限位写校验与 enable 态写确认要用它。"""
        self._st = st

    def _invalidate_baselines(self):
        """作废所有"设备当前值"缓存 —— **单一收口**。
        [2026-09-14] 抽成一个函数是因为这类"改了 A 漏改 B"已经复发过:
        `_on_factory_done` 原本只清四个字段, 漏了模型相关状态; 断开/重连更是完全没清
        (换板后闸门会静默重开)。现在所有作废点都调这里。
        """
        self._device_synced = False
        self._baseline = None
        self._synced = {}
        self._synced_glob = None
        # [2026-09-14] 模型三态也必须一起作废 —— 否则"上一块是新固件 → 换成老固件板"时
        # `_model_supported=True` 存活, 跳过 probe 直接撞 0x34 失败,
        # 操作员看到的是"超时/无应答"而不是设计好的"请先升级固件"。
        self._model_supported = None
        self._model_baseline = None
        self._model_source_text("")

    def set_online(self, onl: bool):
        if onl != self._online:
            self._online = onl
            if not onl:
                # 断开/重连/换端口一律作废 —— 换板后设备已不是同一台, 旧基线是错的
                self._invalidate_baselines()
                # [2026-09-14] 同时清忙态。`SdkWorker` 现在保证"回调必达"(断开时投递
                # ok=False), 但那里到这里的投递要过一次 Qt 事件循环 —— 若本页在回调
                # 到达前就已经收到 set_online(False), 忙态会短暂卡住; 显式清一次是
                # 零成本的保险 (本项目已被"页面永久卡死只能重启进程"坑过一次)。
                self._busy = False
                self.status.setText(i18n.tr(
                    "离线 — 断开或 500ms 无状态帧; 重连后自动恢复"))
            self._refresh_state()

    def _model_source_text(self, text: str):
        if getattr(self, "lbl_model", None) is not None:
            self.lbl_model.setText(text)

    def _can_run(self) -> bool:
        return bool(self._submit is not None and self._online
                    and not self._busy and not self._ext_busy)

    def set_busy(self, busy: bool):
        """MainWindow 命令在途时调用 (叠加到本页忙态, 禁用操作按钮)。"""
        if busy != self._ext_busy:
            self._ext_busy = busy
            self._refresh_state()

    def _refresh_state(self):
        if self._submit is None:
            self.status.setText(i18n.tr("未连接 — 连接后可用（参数读写经 litearm）"))
            self._set_ops_enabled(False)
            return
        if not self._online:
            self._set_ops_enabled(False)
            return
        idle = self._can_run()
        self._set_ops_enabled(idle)
        if idle and not self._device_synced:
            # Critical-1: 未读回设备数据前禁一切下发 (防控件默认值盲发)
            self.status.setText(i18n.tr(
                "已连接 — 尚未读取设备参数, 请先 [刷新当前]; 在此之前禁下发/编辑"))

    def _set_ops_enabled(self, on: bool):
        """on=在线且空闲; 还需 _device_synced 才允许需要设备基线的下发/编辑。"""
        # 恢复出厂**不**依赖设备基线（它用的是固件默认值, 不是当前控件值）,
        # 但成功后会把基线作废 —— 见 _on_saved。
        for b in (self.btn_refresh, self.btn_import, self.btn_export,
                  self.btn_save, self.btn_reset):
            b.setEnabled(on)
        # 新导入/回退**要求设备基线** (未映射字段从基线取; 回退要读状态)
        for b in (self.btn_import_hyy, self.btn_revert_model):
            b.setEnabled(on and self._device_synced)
        ready = on and self._device_synced
        for b in (self.btn_apply_row, self.btn_apply_all, self.btn_global):
            b.setEnabled(ready)
        self.table.setEnabled(ready)
        for cb in self._ff_cbs:
            cb.setEnabled(ready)
        for w in self._g_spins.values():
            for s in (w if isinstance(w, list) else [w]):
                s.setEnabled(ready)
        if self._g_model is not None:
            self._g_model.setEnabled(ready)

    def _set_busy_ui(self, busy: bool):
        self._busy = busy
        self._refresh_state()

    def _pre_op(self, what: str) -> bool:
        if self._submit is None:
            self.status.setText(i18n.tr("未连接"))
            return False
        if not self._online:
            self.status.setText(i18n.tr("离线, 忽略操作"))
            return False
        if self._busy:
            self.status.setText(i18n.tr("忙: 前一条调参操作仍在执行, 已忽略 {what}",
                                        what=what))
            return False
        if self._ext_busy:
            self.status.setText(i18n.tr(
                "忙: 运动/控制命令在途 (MainWindow), 已忽略调参操作"))
            return False
        return True

    def _start(self, what, worker, sig):
        """投到 SDK 所有者线程执行 `worker(arm)`；结果经 sig 回主线程。
        失败发 `None` —— 下游各 `_on_*_done` 处理器保持原签名不变。
        """
        if not self._pre_op(what):
            return
        self._set_busy_ui(True)
        self.status.setText(i18n.tr("执行中: {what} …", what=what))
        self._submit(i18n.tr("调参[{what}]", what=what), worker,
                     lambda res: self._unpack(res, what, sig))

    def _unpack(self, res, what, sig):
        if res is None or not res.ok:
            self._log(i18n.tr("[ERR] 调参[{what}] 失败: {err}", what=what,
                              err=res.error if res is not None else i18n.tr("未执行")))
            sig.emit(None)
            return
        sig.emit(res.value)

    # ================= 读回 =================
    # ================= [2026-09-14] 从 HYY 配置导入 =================
    def _on_import_hyy(self):
        if not self._pre_op(i18n.tr("导入 HYY 配置")):
            return
        if not self._require_device_sync(i18n.tr("导入 HYY 配置")):
            return
        self._model_supported = self._model_supported   # 保留既有三态
        if self._model_supported is False:
            QMessageBox.critical(
                self, i18n.tr("固件不支持"),
                i18n.tr("本固件的动力学模型是编译期常量, 没有在线导入能力 (0x34 不可用)。"
                        "\n\n请先升级固件到含 0x30/0x32/0x33/0x34/0x35 命令的版本。"))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("选择 HYY/SE1 辨识配置"), "",
            i18n.tr("DeviceConfig (*.yaml *.yml);;所有文件 (*)"))
        if not path:
            return
        try:
            cfg = HY.parse_hyy_config(path)
        except Exception as e:                      # noqa: BLE001
            QMessageBox.critical(self, i18n.tr("配置解析失败"), str(e))
            self._log(i18n.tr("[ERR] 调参[导入HYY] {err}", err=e))
            return
        try:
            snap, model, notes = HY.to_snapshot(cfg, self._baseline)
        except Exception as e:                      # noqa: BLE001
            QMessageBox.critical(self, i18n.tr("映射失败"), str(e))
            self._log(i18n.tr("[ERR] 调参[导入HYY] {err}", err=e))
            return
        errs = MIO.validate_model(model)
        if errs:
            QMessageBox.critical(self, i18n.tr("模型参数非法"),
                                 i18n.tr("以下项不合法, 已拒绝导入:\n  {items}",
                                         items="\n  ".join(errs[:12])))
            return
        unmapped = HY.unmapped_report(cfg)

        # 机械健康哨兵 —— `|fc0|` 与 `|fc1|` 是同一关节正/反两向的库仑摩擦, 健康臂
        # 应大致对称。相差悬殊通常指向机械问题, 或辨识时被外力干扰。
        # **不阻断**: 参数本身合法, 拦住写入也修不好机械, 反而会逼出绕过手段;
        # 但默认按钮设为「取消」, 不让它被条件反射点掉。
        asym = HY.suspicious_joints(cfg)
        if asym:
            if not self._confirm_friction_asymmetry(asym):
                self.status.setText(i18n.tr("导入已取消 —— 摩擦不对称告警"))
                self._log(i18n.tr(
                    "[WARN] 调参[导入HYY] 操作员因摩擦不对称**取消**导入: {joints}",
                    joints=", ".join(f"J{x.joint}" for x in asym)))
                return
            notes = list(notes) + [
                i18n.tr("⚠ 摩擦严重不对称 (操作员已确认继续): {items}",
                        items=" · ".join(f"J{x.joint} {x.ratio:.2f}×" for x in asym))]

        with open(path, "r", encoding="utf-8") as f:
            src_text = f.read()
        self._log(i18n.tr(
            "[INFO] 调参[导入HYY] {name} sha={sha} v{version} — 未映射 {n} 项",
            name=os.path.basename(path), sha=cfg.sha256_16,
            version=cfg.version, n=len(unmapped)))
        self._do_import_hyy(path, snap, model, notes, unmapped)

    def _confirm_friction_asymmetry(self, items) -> bool:
        """大红弹窗: 摩擦不对称 ⇒ 机械可能已损坏。**返回 True 表示操作员坚持继续**。

        默认按钮是「取消」且绑了 Esc —— 这个弹窗的全部价值在于让人**停下来看一眼**,
        一个回车就能过掉的弹窗等于没有。
        """
        head, detail = HY.asymmetry_message(items)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle(i18n.tr("⚠ 机械臂硬件可能异常"))
        box.setText(head)
        # 全是富文本: `detail` 由 asymmetry_message 产出 (已含 <br>/<b>), 故此处的
        # 换行也必须用 <br> —— 见该函数 docstring 里的说明 (纯文本模式 vs 富文本模式)。
        box.setInformativeText(
            detail + "<br><br>" + i18n.tr(
                "同一关节正、反两向的摩擦力本应大致对称。相差超过一倍, 通常意味着"
                "机械上已经出了问题:"
                "<br>&nbsp;&nbsp;&nbsp;&nbsp;· 轴承发卡 / 减速器磨损 / 异物"
                "<br>&nbsp;&nbsp;&nbsp;&nbsp;· 预紧异常"
                "<br>&nbsp;&nbsp;&nbsp;&nbsp;· 或辨识时该关节被外力干扰 "
                "—— 那种情况下本次参数本身也不可信"
                "<br><br><b>⚠ 导入参数不会修好机械问题。</b>"
                "<br>建议先人工检查这些关节 (手动转动感受阻力、听异响、测温升), "
                "再决定是否继续。"
                "<br><br>继续导入不会造成额外损害; 取消则可先去排查。"))
        btn_go = box.addButton(i18n.tr("我已知晓，仍要导入"), QMessageBox.AcceptRole)
        btn_cancel = box.addButton(i18n.tr("取消 (先去排查)"), QMessageBox.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.setEscapeButton(btn_cancel)
        # 把「继续」做得不像是随手可点的那一个
        box.setStyleSheet("QPushButton{min-width:170px;padding:6px 10px;}"
                          "QLabel{font-size:13px;}")
        box.exec_()
        go = box.clickedButton() is btn_go
        self._log(i18n.tr(
            "[WARN] 调参[导入HYY] 摩擦不对称 {choice}: {items}",
            choice=(i18n.tr("—— 操作员选择**继续**") if go
                    else i18n.tr("—— 操作员选择取消")),
            items=", ".join(f"J{x.joint}({x.ratio:.2f}×)" for x in items)))
        return go

    def _do_import_hyy(self, path, snap, model, notes, unmapped):
        """diff 预览 -> 预检 -> 下发。"""
        # 1) 预检: 模型 commit 要求失能 (固件 0x32 的 ctrl_is_armed 门控)。
        #    工具侧只能查 `st.enabled` —— `enable_pending` 不在状态帧里, 真正的门在固件。
        st = self._st
        if st is not None and getattr(st, "enabled", False):
            QMessageBox.warning(
                self, i18n.tr("需先失能"),
                i18n.tr("动力学模型 commit 要求失能态 (固件 0x32 门控)。\n\n"
                        "请先在 [控制] 页失能, 再重跑导入。\n"
                        "（本次未发出任何 0x30 帧, 暂存区未被污染。）"))
            return

        # 2) 三段 diff (关节 / 全局 / 模型)
        mdiff = MIO.model_diff(self._model_baseline, model)
        dlg = ParamDiffDialog(self, self._baseline, snap,
                              model_diffs=mdiff, model_baseline=self._model_baseline,
                              model_new=model, notes=notes, unmapped=unmapped)
        if dlg.exec_() != QDialog.Accepted:
            self.status.setText(i18n.tr("导入已取消"))
            return
        flash_save = dlg.save_checkbox.isChecked()
        self._log(i18n.tr(
            "[INFO] 调参[导入HYY] 差异 {diffs} 项 + 模型 {models} 项, 固化={save}",
            diffs=len(dlg.diffs), models=len(mdiff), save=flash_save))
        self._apply_hyy_snapshot(snap, model, flash_save=flash_save)

    def _on_revert_model(self):
        if not self._pre_op(i18n.tr("回退模型")):
            return
        if not self._require_device_sync(i18n.tr("回退模型")):
            return
        if QMessageBox.warning(
                self, i18n.tr("确认回退模型"),
                i18n.tr("把动力学模型回退到**出厂编译期常量** (含 jm)。\n\n"
                        "· 不动其它参数、不动 flash\n"
                        "· ⚠ flash 里的导入模型仍在 —— **重新上电会复活**\n"
                        "· ⚠ 此后不要再点 [固化 Flash] —— 那会永久删除 flash 里的导入模型\n"
                        "· 需失能态"),
                QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Ok:
            return
        self._start(i18n.tr("回退模型"), lambda arm: MIO.revert_model(arm),
                    self._sig_model_revert)

    def _on_model_revert_done(self, res):
        self._set_busy_ui(False)
        ok, code = res if isinstance(res, tuple) else (False, None)
        if ok:
            self.status.setText(i18n.tr(
                "模型已回退到出厂编译期常量 (RAM)。⚠ 不要再点固化 —— "
                "那会永久删除 flash 里的导入模型。"))
            self._log(i18n.tr("[OK] 调参[回退模型] 完成"))
        else:
            self.status.setText(i18n.tr("回退失败: {err}", err=MIO.err_text(code)))
            self._log(i18n.tr("[ERR] 调参[回退模型] {err}", err=MIO.err_text(code)))
        self._model_baseline = None
        self._start(i18n.tr("读模型状态"), MIO.read_model, self._sig_model_after_revert)

    def _on_model_after_revert(self, m):
        self._set_busy_ui(False)
        if m is not None:
            self._model_baseline = m
        self._update_model_label()

    def _on_refresh(self):
        def worker(arm):
            snap = PIO.read_snapshot(arm)
            # [2026-09-14] 模型基线并进同一次 worker —— 避免"读完参数再排队读模型"的两跳。
            # `read_model_safe` 在老固件下回 None (不打挂刷新): 参数读回的契约是
            # "任何一项读不到即抛 OSError ⇒ 整页死掉", 而模型是**可选**能力,
            # 不能让它把 [刷新当前] 拖垮 (那是 D14 的教训)。
            return {"snap": snap, "model": MIO.read_model_safe(arm)}
        self._start(i18n.tr("刷新当前"), worker, self._sig_refreshed)

    def _on_refreshed(self, res):
        self._set_busy_ui(False)
        # worker 回 `{"snap":..., "model":...}`; 也接受**裸快照** (测试与既有调用方的形状)
        if isinstance(res, dict) and "snap" in res:
            self._model_baseline = res.get("model")
            self._model_supported = res.get("model") is not None
            self._update_model_label()
            res = res["snap"]
        snap = res
        if snap is None:
            if self._pending_export:
                self.status.setText(i18n.tr("导出失败 — 读回为空 (固件需 27961a1+)"))
                self._pending_export = None
            else:
                self.status.setText(i18n.tr(
                    "刷新失败 — 请检查串口/固件 (读回需固件 27961a1+);"
                    " 设备参数未确认前禁下发"))
            return
        self._apply_supported(snap.get("supported"))
        self._loading = True
        try:
            for p in C.JOINT_PARAMS:
                ri = JOINT_KEYS.index(p.key)
                for j in range(C.NUM_JOINTS):
                    self._set_table_val(ri, j, snap["joints"][j][p.key])
            self._apply_global_to_ui(snap["global"])
        finally:
            self._loading = False
        # Minor-4/Critical-1: 读回成功 = 设备基线有效, 重置 per-cell _synced 与下发许可
        self._sync_from_snapshot(snap)
        self._device_synced = True
        self._baseline = snap
        self._refresh_state()
        if self._pending_export:
            path, self._pending_export = self._pending_export, None
            try:
                PIO.dump_snapshot(snap, path)
                self.status.setText(i18n.tr(
                    "已导出到 {path} — 同文件再导入时 diff 应为空", path=path))
                self._log(i18n.tr("[OK] 调参[导出] 写 {path}", path=path))
            except Exception as e:  # noqa: BLE001
                self.status.setText(i18n.tr("导出写入失败: {err}", err=e))
                self._log(i18n.tr("[ERR] 调参[导出] {err}", err=e))
            return
        n_j = len([r for r in snap["joints"] if r.get("kp") is not None])
        self.status.setText(i18n.tr(
            "刷新完成 — {n} 关节 × {params} 项 + 全局"
            " (ff_mask={mask} = 0x{mask_hex}); 已允许编辑/下发",
            n=n_j, params=len(C.JOINT_PARAMS),
            mask=snap['global']['ff_mask'],
            mask_hex=f"{snap['global']['ff_mask']:X}"))
        self._log(i18n.tr("[OK] 调参[刷新] 读回全量完成"))

    def _on_model_probe(self, val):
        """模型能力探测回调 —— 保留 (当前实现把读模型并进了 [刷新当前] 的 worker)。"""
        self._set_busy_ui(False)
        self._model_supported = bool(val)
        self._update_model_label()

    def _update_model_label(self):
        """刷新"模型来源"标签 —— 读 0x38 的钱不能白花, 这是操作员唯一的可见面。"""
        st = None
        if self._model_baseline is not None:
            st = self._model_baseline.get("status")
        if self._model_supported is False:
            self._model_source_text(i18n.tr(
                "模型: 固件不支持在线导入 (0x34 不可用) —— 请升级固件"))
            return
        if st is None:
            self._model_source_text(i18n.tr("模型: — (未读)"))
            return
        src = i18n.tr("导入/覆盖") if st.override else i18n.tr("出厂(编译期常量)")
        extra = []
        if st.staged_mask:
            extra.append(i18n.tr("暂存 0x{mask:03X}", mask=st.staged_mask))
        if st.dirty:
            extra.append(i18n.tr("未固化"))
        self._model_source_text(
            i18n.tr("模型: {src}", src=src)
            + (i18n.tr(" · {extra}", extra=" · ".join(extra)) if extra else ""))

    def retranslate(self) -> None:
        """切语言：重写行标题/单元格 tooltip/全局格标题，再按状态刷新标签。"""
        for ri, p in enumerate(C.JOINT_PARAMS):
            head = self.table.item(ri, 0)
            if head is not None:
                head.setText(p.label_text())
                head.setToolTip(self._row_tooltip(p))
            for j in range(C.NUM_JOINTS):
                val = self._cell_val(ri, j)
                item = self.table.item(ri, 1 + j)
                if item is not None:
                    item.setToolTip(self._cell_tooltip(p, val) if val is not None
                                    else (self._param_tooltip(p)
                                          if not item.text() == "—" else
                                          i18n.tr("本机没有这个关节（台架 1J 只有 J1）")))
        if self._g_model is not None:
            self._g_model.setToolTip(self._param_tooltip(C.GLOBAL_BY_KEY["friction_model"]))
        for gp in C.GLOBAL_PARAMS:
            cap = self._g_captions.get(gp.key)
            if cap is None:
                continue
            if gp.key == "friction_model":
                cap.setText("friction_model 0=v1 / 1=v2 / 2=drag")
            elif gp.is_array:
                cap.setText(i18n.tr("{label}  (x, y, z)", label=gp.label_text()))
            else:
                cap.setText(gp.label_text())
            cap.setToolTip(self._param_tooltip(gp))
            spins = self._g_spins.get(gp.key)
            for sp in (spins if isinstance(spins, list) else [spins]):
                if sp is None:
                    continue
                if gp.is_array:
                    sp.setToolTip(i18n.tr(
                        "{axis} 分量\n\n{detail}\n\n范围 {range}",
                        axis=sp.objectName() or "x", detail=self._param_tooltip(gp),
                        range=gp.range_text()))
                else:
                    sp.setToolTip(i18n.tr("{detail}\n\n范围 {range}",
                                          detail=self._param_tooltip(gp),
                                          range=gp.range_text()))
        for i, (mask, name, label) in enumerate(C.FF_BITS):
            self._ff_cbs[i].setToolTip(self._ff_tooltip(i, mask, name, label))
        self._update_model_label()
        self._refresh_state()
        if self._device_synced:
            # 上一层操作的结果文案可能是旧语言；用状态事实重写一条，避免残留。
            self.status.setText(i18n.tr("已连接 — 参数已读取，可编辑/下发"))

    def _apply_global_to_ui(self, g: dict):
        self._synced_glob = {k: (list(v) if isinstance(v, list) else v)
                             for k, v in g.items()}
        for gp in C.GLOBAL_PARAMS:
            if gp.key not in g:
                continue          # 本板不支持
            v = g[gp.key]
            if gp.key == "friction_model":
                if self._g_model is not None:
                    self._g_model.blockSignals(True)
                    self._g_model.setCurrentIndex(int(v))
                    self._g_model.blockSignals(False)
                continue
            w = self._g_spins[gp.key]
            for s in (w if isinstance(w, list) else [w]):
                s.blockSignals(True)
            if gp.is_array:
                for k, s in enumerate(w):
                    s.setValue(float(v[k]))
            else:
                w.setValue(float(v))
            for s in (w if isinstance(w, list) else [w]):
                s.blockSignals(False)
        if g.get("ff_mask") is not None:
            bits = C.mask_to_bits(g["ff_mask"])
            for cb, on in zip(self._ff_cbs, bits):
                cb.blockSignals(True)
                cb.setChecked(on)
                cb.blockSignals(False)

    # ================= 板子能力 (supported) =================
    def _vec_supported(self, p) -> bool:
        """板子是否支持这个 0x2B item。None = 还没读到 ⇒ 先按目录全集显示。"""
        return self._sup_vec is None or p.item in self._sup_vec

    def _scalar_supported(self, gp) -> bool:
        return self._sup_scalar is None or gp.item in self._sup_scalar

    def _supported_joint_keys(self) -> list:
        return [p.key for p in C.JOINT_PARAMS
                if p.kind != "vec" or self._vec_supported(p)]

    def _apply_supported(self, sup) -> None:
        """按读回的 `supported` 隐藏板子没有的参数行/控件。

        不支持的项**不显示**(按需求"板子里有什么就显示什么"), 并且同时从下发路径里
        排除 —— 只藏不排会让 [下发全部] 发出一个没有值的项。
        """
        if not sup:
            return
        self._sup_vec = set(sup.get("vec", []))
        self._sup_scalar = set(sup.get("scalar", []))
        for ri, p in enumerate(C.JOINT_PARAMS):
            if p.kind == "vec":
                self.table.setRowHidden(ri, not self._vec_supported(p))
        for key, cell in self._g_cells.items():
            cell.setVisible(self._scalar_supported(C.GLOBAL_BY_KEY[key]))

    def _set_table_val(self, ri, j, val):
        """val=None 表示**本机没有这个关节**（台架 1J 上的 J2..J7）—— 显示 "—" 且封禁编辑。"""
        p = C.JOINT_PARAMS[ri]
        it = self.table.item(ri, 1 + j)
        if val is None:
            it.setText("—")
            it.setData(ROLE_VAL, None)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)   # 去掉 Editable
            it.setForeground(QColor("#9aa4ae"))
            it.setBackground(QColor("#f2f4f6"))
            it.setToolTip(i18n.tr("本机没有这个关节（台架 1J 只有 J1）"))
            return
        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
        it.setText(f"{float(val):.{p.decimals}f}")
        it.setData(ROLE_VAL, float(val))
        it.setForeground(QColor("#000000"))
        it.setBackground(BG[0])
        it.setToolTip(self._cell_tooltip(p, float(val)))

    # ================= 单元格编辑 =================
    def _cell_val(self, ri, j):
        it = self.table.item(ri, 1 + j)
        if it is None:
            return None
        v = it.data(ROLE_VAL)
        return float(v) if v is not None else None

    def _refresh_cell_color(self, ri, j):
        v = self._cell_val(ri, j)
        p = C.JOINT_PARAMS[ri]
        if v is None:
            self._paint(ri, j, 2)
            return
        if C.check_joint(p, v, joint_idx=j):
            self._paint(ri, j, 2)
            return
        base = self._synced.get(p.key, {}).get(j)
        self._paint(ri, j, 0 if base == v else 1)

    def _paint(self, ri, j, state):
        it = self.table.item(ri, 1 + j)
        it.setBackground(BG[state])
        it.setForeground(FG_INVALID if state in (2, 3) else QColor("#000000"))

    def _on_cell_changed(self, it):
        if self._loading or it is None or self._submit is None:
            return
        col, ri = it.column(), it.row()
        if col == 0 or ri >= len(C.JOINT_PARAMS):
            return
        j = col - 1
        try:
            v = float(it.text().strip())
            if v != v:
                raise ValueError
        except ValueError:
            it.setData(ROLE_VAL, None)
            it.setBackground(BG[2])
            it.setForeground(FG_INVALID)
            return
        p = C.JOINT_PARAMS[ri]
        err = C.check_joint(p, v, joint_idx=j)
        it.setData(ROLE_VAL, v)
        if err:
            it.setToolTip(f"{err}\n\n{self._param_tooltip(p)}")
            it.setBackground(BG[2])
            it.setForeground(FG_INVALID)
        else:
            it.setToolTip(self._cell_tooltip(p, v))
            self._refresh_cell_color(ri, j)

    def _on_ff_toggled(self, _idx):
        if self._loading:
            return
        cur = C.bits_to_mask([cb.isChecked() for cb in self._ff_cbs])
        base = self._synced_glob["ff_mask"] if self._synced_glob else None
        if base is not None and cur != base:
            self.status.setText(i18n.tr("ff_mask 已改动 — 下发全局时将弹确认框"))

    # ================= 逐关节矩阵 & 下发 =================
    def _ui_matrix(self) -> list:
        """逐关节参数矩阵（长度恒 `C.NUM_JOINTS`）。
        本机没有的关节（台架 1J 上的 J2..J7）整行填 `None` —— 由 `_build_row_ops`
        跳过，不算"缺少数据"，也不参与合法性校验。
        """
        mat = []
        for j in range(C.NUM_JOINTS):
            row = {p.key: self._cell_val(ri, j)
                   for ri, p in enumerate(C.JOINT_PARAMS)}
            if all(v is None for v in row.values()):
                mat.append(row)               # 本机没有这个关节
                continue
            for p in C.JOINT_PARAMS:
                if p.kind == "vec" and not self._vec_supported(p):
                    continue          # 板子没有这项: 不显示也不校验
                v = row[p.key]
                if v is None:
                    raise ValueError(i18n.tr(
                        "J{axis}.{key} 为空 — 请先 [刷新当前]",
                        axis=j + 1, key=p.key))
                err = C.check_joint(p, v, joint_idx=j)
                if err:
                    raise ValueError(err)
            rel = C.check_joint_limits_relation(row)
            if rel:
                raise ValueError(i18n.tr("J{axis}: {detail}", axis=j + 1,
                                         detail=rel))
            mat.append(row)
        return mat

    @staticmethod
    def _present_joints(mat: list) -> list:
        """本机存在的关节下标（整行非 None 的那些）。"""
        return [j for j, row in enumerate(mat)
                if row and any(v is not None for v in row.values())]

    def _selected_row_keys(self) -> list:
        sel = sorted({i.row() for i in self.table.selectedIndexes()})
        return [C.JOINT_PARAMS[ri].key for ri in sel if ri < len(C.JOINT_PARAMS)]

    def _on_open_guide(self):
        keys = self._selected_row_keys()
        self.show_guide.emit(keys[0] if keys else "")

    def _require_device_sync(self, what: str) -> bool:
        if not self._device_synced:
            self.status.setText(i18n.tr(
                "未读取设备数据 — 请先 [刷新当前], 已拒绝 {what}", what=what))
            return False
        return True

    def _confirm_enabled_write(self, desc: str) -> bool:
        """臂 enable 态下的控制律写二次确认 (0x22/0x23/0x26/0x27/0x28 等实时生效)。"""
        st = self._st
        # 使能态**未知**时也确认：与"无基线不放行"同一条原则 —— 状态没到手
        # 不等于安全，只等于"不知道"。（状态流 100Hz，实践中几乎不会走到这里。）
        if st is None or st.enabled:
            if QMessageBox.warning(
                    self, i18n.tr("臂已使能 — 写确认"),
                    i18n.tr("{desc}\n\n机械臂处于 enable 态, "
                            "该写入会立即作用于控制律/前馈"
                            " (限位墙/积分/摩擦等随写即变)。\n确认继续?",
                            desc=desc),
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel) != QMessageBox.Ok:
                self.status.setText(i18n.tr("已取消 — enable 态写确认未通过"))
                return False
        return True

    def _limits_error(self, mat: list) -> str | None:
        """0x23 限位写前: 校验当前 q 在新 [q_min,q_max] 内, 越界返回错误文案。"""
        st = self._st
        if st is None or not st.joints:
            # 拿不到当前 q 就没法确认新限位包含它 —— 拒绝，而不是"交给固件"。
            # 限位写一旦即刻越限会直接 POS_VIOL/FAULT，不能靠猜。
            return i18n.tr(
                "拿不到当前关节角，无法校验新限位是否包含当前 q — 等一帧状态再试")

        n = min(st.n, C.NUM_JOINTS, len(mat))
        for j in range(n):
            if mat[j]["q_min"] is None:      # 本机没有这个关节（台架 1J）
                continue
            qmin, qmax = mat[j]["q_min"], mat[j]["q_max"]
            q = st.joints[j].q
            if not (qmin <= q <= qmax):
                return i18n.tr(
                    "J{axis} 当前 q={q:.4f} rad 不在新限位 [{qmin:.4f}, {qmax:.4f}]"
                    " 内 — 拒绝下发 (防即时 POS_VIOL/FAULT)",
                    axis=j + 1, q=q, qmin=qmin, qmax=qmax)
        return None

    def _apply_rows_selected(self, all_rows: bool = False):
        if not self._require_device_sync("下发"):
            return
        keys = self._supported_joint_keys() if all_rows else self._selected_row_keys()
        if not keys:
            self.status.setText(i18n.tr(
                "未选中行 — 请先点选一行 (或用 [下发全部])"))
            return
        try:
            mat = self._ui_matrix()
        except ValueError as e:
            QMessageBox.warning(self, i18n.tr("下发校验未通过"), str(e))
            self.status.setText(i18n.tr("校验未通过: {err}", err=e))
            return
        group = set(keys)
        for k in list(keys):
            p = C.JOINT_BY_KEY[k]
            if p.kind in GROUP_KEYS:
                group |= set(GROUP_KEYS[p.kind])
        kinds = {C.JOINT_BY_KEY[k].kind for k in group}
        if "limits" in kinds:
            err = self._limits_error(mat)
            if err:
                QMessageBox.warning(self, i18n.tr("限位写被拒绝"), err)
                self.status.setText(err)
                return
        if not self._confirm_enabled_write(
                i18n.tr("逐关节/成组参数下发 (0x22/0x23/0x26)")):
            return
        ops = self._build_row_ops(group, mat, self._sup_vec)
        self._start(i18n.tr("下发 {n} 行", n=len(group)),
                    lambda arm: PIO.run_ops(arm, ops), self._sig_rows_done)

    @staticmethod
    def _build_row_ops(keys: set, mat: list, sup_vec: set | None = None) -> list:
        """按行生成下发操作; 每项 {cells:[(rk,j,val)...], run(cli)->(ok,code)}。

        `sup_vec` = 板子支持的 0x2B item 集合; None 表示不筛 (未读到能力/测试直接调用)。
        """
        ops = []
        active = set(C.JOINT_BY_KEY[k].kind for k in keys)
        present = ParamsPage._present_joints(mat)
        if "ctrl" in active:
            for j in present:
                a = (mat[j]["kp"], mat[j]["kd"], mat[j]["tau_max"])
                cells = [(k, j, mat[j][k]) for k in GROUP_KEYS["ctrl"]]
                ops.append({"cells": cells,
                            "run": lambda arm, jj=j, aa=a: PIO.set_joint_param(arm, jj, *aa)})
        if "limits" in active:
            for j in present:
                a = (mat[j]["q_min"], mat[j]["q_max"])
                cells = [(k, j, mat[j][k]) for k in GROUP_KEYS["limits"]]
                ops.append({"cells": cells,
                            "run": lambda arm, jj=j, aa=a: PIO.set_joint_limits(arm, jj, *aa)})
        for p in C.JOINT_PARAMS:
            if p.kind != "vec" or p.key not in keys:
                continue
            if sup_vec is not None and p.item not in sup_vec:
                continue
            vals = [mat[j][p.key] for j in present]
            cells = [(p.key, j, mat[j][p.key]) for j in present]
            ops.append({"cells": cells,
                        "run": lambda arm, it=p.item, aa=vals: PIO.set_ff_vec(arm, it, aa)})
        return ops

    # ================= 结果处理 (逐关节/批量共用) =================
    def _sync_from_snapshot(self, snap: dict):
        """读回/整发成功后, 以设备值为基线重置 per-cell _synced (Minor-4)。"""
        self._synced = {}
        for j, d in enumerate(snap["joints"]):
            for k, v in d.items():
                if v is not None:
                    self._synced.setdefault(k, {})[j] = float(v)

    def _commit_row_success(self, ok_cells):
        for (rk, j), val in ok_cells.items():
            self._synced.setdefault(rk, {})[j] = float(val)
            if self._baseline is not None:
                self._baseline["joints"][j][rk] = float(val)
            self._refresh_cell_color(JOINT_KEYS.index(rk), j)

    def _on_rows_done(self, res):
        self._set_busy_ui(False)
        if res is None:
            return
        okc, failc = res["ok"], res["fail"]
        self._commit_row_success(okc)
        for (rk, j), code in failc.items():
            self._paint(JOINT_KEYS.index(rk), j, 3)
            txt = PIO.err_text(code)
            self._log(i18n.tr("[ERR] 调参[下发] {key} J{axis}: {text}",
                              key=rk, axis=j + 1, text=txt))
        if failc:
            self.status.setText(i18n.tr(
                "下发完成: 成功 {ok} 项, 失败 {fail} 项 (格已标红)",
                ok=len(okc), fail=len(failc)))
        else:
            self.status.setText(i18n.tr("下发完成 — {n} 项全部 ACK", n=len(okc)))
            self._log(i18n.tr("[OK] 调参[下发] {n} 项全部 ACK", n=len(okc)))

    # ================= 全局下发 =================
    def _global_from_ui(self) -> dict:
        g = {}
        for gp in C.GLOBAL_PARAMS:
            if not self._scalar_supported(gp):
                continue          # 板子没有这项 —— 不显示, 也不能被"全量下发"带出去
            if gp.key == "friction_model":
                g[gp.key] = self._g_model.currentIndex()
            elif gp.is_array:
                g[gp.key] = [s.value() for s in self._g_spins[gp.key]]
            else:
                g[gp.key] = self._g_spins[gp.key].value()
        g["ff_mask"] = C.bits_to_mask([cb.isChecked() for cb in self._ff_cbs])
        return g

    def _on_apply_global(self):
        if not self._require_device_sync(i18n.tr("下发全局")):
            return
        g = self._global_from_ui()
        if not self._confirm_enabled_write(
                i18n.tr("全局参数/前馈下发 (0x28 + ff_mask 0x27)")):
            return
        base = self._synced_glob
        mask_changed = base is None or base["ff_mask"] != g["ff_mask"]
        if mask_changed:
            if QMessageBox.warning(
                    self, i18n.tr("确认 ff_mask 改动"),
                    i18n.tr("ff_mask 将改为 {mask} (0x{mask_hex})\n\n"
                            "前馈位改动会立即影响控制律输出, 确认下发?",
                            mask=g['ff_mask'], mask_hex=f"{g['ff_mask']:X}"),
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel) != QMessageBox.Ok:
                self.status.setText(i18n.tr("已取消 ff_mask 下发"))
                return
        self._start(i18n.tr("下发全局"),
                    lambda arm: PIO.send_global(arm, g), self._sig_global_done)

    def _on_global_done(self, res):
        self._set_busy_ui(False)
        if res is None:
            return
        g, leaf_ok, fre_model_ok, mask_ok = res
        # 合并同步基线 (仅成功叶)
        if self._synced_glob is None:
            sg = {k: (list(v) if isinstance(v, list) else v) for k, v in g.items()}
        else:
            sg = {k: (list(v) if isinstance(v, list) else v)
                  for k, v in self._synced_glob.items()}
        for gp in C.GLOBAL_PARAMS:
            if gp.key not in g:
                continue          # 本板不支持
            if gp.key == "friction_model":
                if fre_model_ok:
                    sg[gp.key] = g[gp.key]
                continue
            if leaf_ok.get(gp.key):
                sg[gp.key] = (list(g[gp.key]) if isinstance(g[gp.key], list)
                              else g[gp.key])
        if mask_ok and "ff_mask" in g:
            sg["ff_mask"] = g["ff_mask"]
        self._loading = True
        try:
            self._apply_global_to_ui(sg)
        finally:
            self._loading = False
        if self._baseline is not None:
            self._baseline["global"] = {k: (list(v) if isinstance(v, list) else v)
                                        for k, v in sg.items()}
        fails = [k for k, ok in leaf_ok.items() if not ok]
        if not fre_model_ok:
            fails.append("friction_model")
        if not mask_ok:
            fails.append("ff_mask")
        if not fails:
            self.status.setText(i18n.tr("全局下发完成 — 全部 ACK"))
            self._log(i18n.tr("[OK] 调参[全局] 全部 ACK"))
        else:
            self.status.setText(i18n.tr("全局下发部分失败: {items}",
                                        items=", ".join(fails)))
            self._log(i18n.tr("[ERR] 调参[全局] 失败项: {items}",
                              items=", ".join(fails)))

    # ================= 导入 / 批量 =================
    def _on_import(self):
        if not self._pre_op(i18n.tr("导入")):
            return
        # 先把闸门说清楚, 别等用户选完文件、看完 diff 才拒绝
        if not self._require_device_sync(i18n.tr("导入")):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("选择参数文件"), "",
            i18n.tr("参数文件 (*.yaml *.yml *.json);;所有文件 (*)"))
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            snap = C.normalize_snapshot(raw)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, i18n.tr("导入失败"), str(e))
            return
        dlg = ParamDiffDialog(self, self._baseline, snap)
        if dlg.exec_() != QDialog.Accepted:
            self.status.setText(i18n.tr("导入已取消"))
            return
        flash_save = dlg.save_checkbox.isChecked()
        if flash_save:
            if QMessageBox.warning(
                    self, i18n.tr("确认下发后固化 Flash"),
                    i18n.tr("将先下发整套参数到 RAM, 随后调用 param_save 固化到 Flash。"
                            "\n\n固件要求关节处于 disable 态才会执行擦写 "
                            "(enable 态返回 ERR 0x04)。\n"
                            "请确认已先在 [控制] 页 [失能]?"),
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel) != QMessageBox.Ok:
                flash_save = False
                self.status.setText(i18n.tr("已取消固化选项, 仅下发 RAM"))
        self._log(i18n.tr(
            "[INFO] 调参[导入] {path}: 差异 {n} 项, 固化={save}",
            path=path, n=len(dlg.diffs), save=flash_save))
        self._apply_full_snapshot(snap, flash_save=flash_save)

    def _apply_hyy_snapshot(self, snap: dict, model: dict, flash_save: bool = False):  # noqa: D401
        """HYY 导入的下发: 与 `_apply_full_snapshot` 同一道闸, **多一段模型 + 读回闸**。"""
        if not self._require_device_sync(i18n.tr("HYY 导入下发")):
            return
        if QMessageBox.warning(
                self, i18n.tr("确认导入下发"),
                i18n.tr(
                    "**只导动力学辨识的产物**, 其余一项不碰:\n"
                    "  · 摩擦三元组 fv/fc0/fc1 (0x26 item 9/10/11, {joints} 轴各一组)\n"
                    "  · **动力学模型** body1..7 + jm (0x30/0x33) → commit (0x32, 须失能)\n"
                    "  · 读回逐项比对 (不一致则**中止, 不固化**)\n"
                    "{save_line}"
                    "\n"
                    "不动: kp/kd/tau_max/软限位/全局标量/ff_mask —— 它们是设备自身口径,\n"
                    "      yaml 里对应的 smin-smax / torque_max / gravity 是 HYY 控制器配置,\n"
                    "      不是辨识结果 (见未映射清单)。\n\n"
                    "模型是力矩前馈的输入 —— 请确认臂已失能且有人看护。",
                    joints=C.NUM_JOINTS,
                    save_line=(
                        i18n.tr("  · **随后固化到 Flash** "
                                "(param_save, 须失能, 擦写期间 CPU 停 ~1s)\n")
                        if flash_save else
                        i18n.tr("  · ⚠ **不会固化到 Flash** —— "
                                "本次改动只在 RAM, 掉电即回退\n"))),
                QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Ok:
            self.status.setText(i18n.tr("导入下发已取消"))
            return
        mat = snap["joints"]
        if not self._confirm_enabled_write(
                i18n.tr("HYY 导入 (0x26 item9-11 + 0x30/0x33/0x32)")):
            return
        # [2026-09-14 范围收窄] 只发**实际变了的那几项**: 摩擦三元组。
        # 不发 kp/kd/tau_max/限位 (0x22/0x23) —— 它们与设备当前值相同, 重写一遍是纯粹的
        # 额外风险 (基线若陈旧就会把旧值写回设备), 且与"只导辨识产物"的裁决不符。
        ops = self._build_row_ops({"friction_v", "friction_fc0", "friction_fc1"},
                                  mat, self._sup_vec)

        def worker(arm):
            # ① 摩擦三元组 (0x26 item 9/10/11)
            rowres = PIO.run_ops(arm, ops)
            # ② 模型 (7×0x30 + 0x33 + 0x32 commit) —— 任一帧失败即中止且不 commit
            mres = MIO.send_model(arm, model, MIO.MASK_WRITTEN)
            # ④ **读回闸, 必须在固化之前**: 0x25 会把"当时"的 bank 落盘,
            #    先固化则不一致时错的模型已在 flash 里, 掉电还会被装回来。
            diffs = []
            if mres["commit"][0]:
                try:
                    diffs = MIO.readback_compare(arm, model, MIO.MASK_WRITTEN)
                except Exception as e:              # noqa: BLE001
                    diffs = [(i18n.tr("读回失败"), None, str(e))]
            # ⑤ 只有闸全绿才固化
            save_ok = None
            if flash_save and mres["commit"][0] and not diffs:
                save_ok = bool(PIO.save_params(arm, 6.0)[0])
            # ⑥ 读回生效模型, 供基线重建
            mnow = MIO.read_model_safe(arm)
            # glob/leaf_ok/... 置空: 本次不写 global, `_on_batch_done` 据此跳过全局统计
            return {"row": rowres, "glob": None, "mat": mat,
                    "leaf_ok": {}, "fre_model_ok": True, "mask_ok": True,
                    "dyn_model": mres, "model_diffs": diffs, "model_now": mnow,
                    "save_ok": save_ok}

        self._start(i18n.tr("HYY 导入下发"), worker, self._sig_hyy_done)

    def _on_hyy_done(self, res):
        self._on_batch_done(res)

    def _apply_full_snapshot(self, snap: dict, flash_save: bool = False):
        # 与 [下发全部]/[下发全局] 同一道闸: 未成功 [刷新当前] 前不整套下发。
        # 否则导入路径可绕过安全闸, 且 diff 对话框的"设备当前值"列全空, 用户
        # 无法核对将被覆盖的真实值 (默认控件值盲发的同类风险)。
        if not self._require_device_sync(i18n.tr("整套下发")):
            return
        if QMessageBox.warning(
                self, i18n.tr("确认批量下发"),
                i18n.tr(
                    "将按固件写口顺序逐条下发整套参数\n"
                    "  · 关节 {joints} × {params} 项 (0x22/0x23/0x26)\n"
                    "  · 全局标量 + friction_model + ff_mask (0x28/0x27)\n\n"
                    "下发生效为即时 RAM 修改 (刚度/限位/前馈), 请确认当前安全。",
                    joints=C.NUM_JOINTS, params=len(C.JOINT_PARAMS)),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            self.status.setText(i18n.tr("批量下发已取消"))
            return
        mat = snap["joints"]
        # 限位写前: 新 [q_min,q_max] 必须包含当前 q (全量必含 0x23 组)
        err = self._limits_error(mat)
        if err:
            QMessageBox.warning(self, i18n.tr("限位写被拒绝"), err)
            self.status.setText(err)
            return
        if not self._confirm_enabled_write(
                i18n.tr("批量整套参数下发 (0x22/0x23/0x26/0x28/0x27)")):
            return
        ops = self._build_row_ops(set(self._supported_joint_keys()), mat, self._sup_vec)
        glob = snap["global"]

        def worker(arm):
            rowres = PIO.run_ops(arm, ops)
            g, leaf_ok, fre_model_ok, mask_ok = PIO.send_global(arm, glob)
            save_ok = None
            if flash_save:
                save_ok = bool(PIO.save_params(arm, 6.0)[0])
            return {"row": rowres, "glob": glob, "mat": mat,
                    "leaf_ok": leaf_ok, "fre_model_ok": fre_model_ok, "mask_ok": mask_ok,
                    "save_ok": save_ok}

        self._start(i18n.tr("批量下发"), worker, self._sig_batch_done)

    def _rebuild_baseline(self, mat, sg, model_now):
        """基线重建的**单一收口** —— 手写字面量最容易漏键。
        [2026-09-14] 此前 `_on_batch_done` 的成功分支手写了一个只有 `joints` + `global`
        的 dict ⇒ 模型段永远没有基线 ⇒ 下一次导入时模型段**全部显示"新增"、旧值列全空**
        (正是本项目 Critical-4 花力气防的那个反模式), 而且不会自愈。
        """
        self._baseline = {
            "joints": [{k: float(v) for k, v in d.items() if v is not None}
                       for d in mat],
            "global": {k: (list(v) if isinstance(v, list) else v) for k, v in sg.items()}}
        if model_now is not None:
            self._model_baseline = model_now
        self._update_model_label()

    def _on_batch_done(self, res):
        self._set_busy_ui(False)
        if res is None:
            return
        okc = res["row"]["ok"]
        failc = res["row"]["fail"]
        self._commit_row_success(okc)
        for (rk, j), code in failc.items():
            self._paint(JOINT_KEYS.index(rk), j, 3)
            txt = PIO.err_text(code)
            self._log(i18n.tr("[ERR] 调参[批量] {key} J{axis}: {text}",
                              key=rk, axis=j + 1, text=txt))
        # `glob is None` = 本次**没写 global** (HYY 导入只发摩擦三元组 + 模型段)。
        # 那就一个 global 叶也不动 —— 不碰 `_synced_glob`、不碰 `_baseline["global"]`,
        # 也不重建 UI 控件 (它们的值本来就是对的)。
        g = res.get("glob")
        leaf_ok = res.get("leaf_ok") or {}
        fre_model_ok = res.get("fre_model_ok", True)
        mask_ok = res.get("mask_ok", True)
        wrote_global = g is not None
        sg = None
        if wrote_global:
            old = self._synced_glob
            sg = {k: (list(v) if isinstance(v, list) else v)
                  for k, v in (old if old is not None else g).items()}
            for gp in C.GLOBAL_PARAMS:
                if gp.key not in g:
                    continue      # 本板不支持
                if gp.key == "friction_model":
                    if fre_model_ok:
                        sg[gp.key] = g[gp.key]
                    continue
                if leaf_ok.get(gp.key):
                    sg[gp.key] = (list(g[gp.key]) if isinstance(g[gp.key], list)
                                  else g[gp.key])
            if mask_ok and "ff_mask" in g:
                sg["ff_mask"] = g["ff_mask"]
            self._loading = True
            try:
                self._apply_global_to_ui(sg)
            finally:
                self._loading = False
            # baseline: 关节成功项已并入; global 更新
            if self._baseline is not None:
                self._baseline["global"] = {k: (list(v) if isinstance(v, list) else v)
                                            for k, v in sg.items()}
        # [2026-09-14] 动力学模型的结果 —— 独立键 `dyn_model`。
        # ⚠ 上面那个 `fre_model_ok` 是 **friction_model** 的写结果 (旧名 `fre_model_ok`
        #   与"动力学模型"同义, 会造成误读; 已改名)。
        dyn_model = res.get("dyn_model")
        model_diffs = res.get("model_diffs") or []
        dyn_ok = True if dyn_model is None else bool(dyn_model["commit"][0])
        if not dyn_ok:
            self._log(i18n.tr(
                "[ERR] 调参[模型] commit 被拒: {err}{aborted}",
                err=MIO.err_text(dyn_model['commit'][1]),
                aborted=(f" ({dyn_model['aborted']})"
                         if dyn_model.get('aborted') else "")))
        for lab, want, got in model_diffs:
            self._log(i18n.tr(
                "[ERR] 调参[模型] 读回不一致 {label}: 期望 {want} 实际 {got}",
                label=lab, want=repr(want), got=repr(got)))
        gfail = sum(1 for k, ok in leaf_ok.items() if not ok) \
            + (0 if fre_model_ok else 1) + (0 if mask_ok else 1) \
            + (0 if dyn_ok else 1) + (1 if model_diffs else 0)
        if not failc and gfail == 0:
            # 全量成功 = 设备状态已知 (整发快照), 允许后续下发并建立基线
            mat = res["mat"]
            self._device_synced = True
            self._sync_from_snapshot({"joints": mat})
            # `sg is None` 时保留既有 global 基线 (`_rebuild_baseline` 会照抄)
            self._rebuild_baseline(mat, sg if sg is not None else
                                   (self._baseline or {}).get("global", {}),
                                   res.get("model_now"))
            for ri in range(len(C.JOINT_PARAMS)):
                for j in range(C.NUM_JOINTS):
                    self._refresh_cell_color(ri, j)
            self._refresh_state()
        msg = (i18n.tr("批量下发完成: 关节成功 {ok}/失败 {fail}, 全局失败 {gfail}",
                       ok=len(okc), fail=len(failc), gfail=gfail)
               if wrote_global else
               i18n.tr("导入下发完成: 摩擦项成功 {ok}/失败 {fail}, 模型 {model}",
                       ok=len(okc), fail=len(failc),
                       model=i18n.tr("成功") if dyn_ok else i18n.tr("失败")))
        # [2026-09-14] 固化的三种结局都要说清楚 —— 尤其**未固化**这一支。
        # 固件侧 0x30/0x32/0x33/0x26 全都只写 RAM (0x32 只 flash_store_mark_dirty() 标脏),
        # 唯一的落盘入口是 0x25 PARAM_SAVE。所以"没勾固化"= 掉电即回退整次导入,
        # 而原实现在这一支**什么都不说** —— 操作员会以为已经生效并归档。
        unsaved = False
        if res["save_ok"] is True:
            msg += i18n.tr("; 已固化到 Flash")
        elif res["save_ok"] is False:
            msg += i18n.tr("; 固化失败 (enable 态会返回 0x04 须先失能)")
        else:
            unsaved = True
            msg += i18n.tr("; ⚠ **未固化** —— 本次改动只在 RAM, 掉电即回退。"
                           "请勾选『下发后固化到 Flash』重跑, 或点 [固化 Flash…]")
        self.status.setText(msg)
        self.status.setStyleSheet(
            "background:#4a2020;color:#ffd0d0;padding:5px 8px;border-radius:3px;"
            if unsaved else
            "background:#23232a;color:#d8d8e0;padding:5px 8px;border-radius:3px;")
        self._log(f"[{'OK' if not failc and gfail == 0 else 'ERR'}] "
                  + i18n.tr("调参[批量] {msg}", msg=msg))

    # ================= 导出 =================
    def _on_export(self):
        if not self._pre_op(i18n.tr("导出")):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("导出当前参数"), "litearm_params.yaml",
            i18n.tr("参数文件 (*.yaml)"))
        if not path:
            return
        self._pending_export = os.path.abspath(path)
        # 复用刷新读回流程, 完成后由 _on_refreshed 写文件
        self._on_refresh()

    # ================= param_save (二次确认) =================
    def _on_save_flash(self):
        if not self._pre_op(i18n.tr("固化")):
            return
        if QMessageBox.question(
                self, i18n.tr("固化到 Flash (1/2)"),
                i18n.tr("将把当前 RAM 参数写入 Flash 持久化 (涉及扇区擦除)。\n\n"
                        "固件要求关节处于 disable 态 (enable 态返回 ERR 0x04)。"),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            return
        if QMessageBox.warning(
                self, i18n.tr("再次确认固化 (2/2)"),
                i18n.tr("Flash 参数在下电后仍生效, 固件会整体重钳一遍所有参数。"
                        "\n\n确认现在固化?"),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            self.status.setText(i18n.tr("固化已取消"))
            return
        def worker(arm):
            ok, code = PIO.save_params(arm, 6.0)
            if ok:
                return True, i18n.tr("固化成功 (已写 Flash)")
            return False, i18n.tr("固件拒绝: {err}", err=PIO.err_text(code))

        self._start(i18n.tr("固化到 Flash"), worker, self._sig_saved)

    # ================= 恢复出厂 (0x36) =================
    def _on_reset_factory(self):
        if not self._pre_op(i18n.tr("恢复出厂")):
            return
        if QMessageBox.warning(
                self, i18n.tr("恢复出厂 (1/2)"),
                i18n.tr("将把全部运行时参数改回固件出厂默认，并失效 Flash 里已保存的参数。"
                        "\n\n当前 RAM 与 Flash 的改动都会丢失。"
                        "固件要求关节处于 disable 态。"),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            return
        if QMessageBox.warning(
                self, i18n.tr("再次确认恢复出厂 (2/2)"),
                i18n.tr("确认现在恢复出厂？"),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            self.status.setText(i18n.tr("恢复出厂已取消"))
            return

        def worker(arm):
            ok, code = PIO.reset_factory(arm)
            if ok:
                return True, i18n.tr("已恢复出厂默认 (Flash 参数已失效)")
            return False, i18n.tr("固件拒绝: {err}", err=PIO.err_text(code))

        self._start(i18n.tr("恢复出厂"), worker, self._sig_factory_done)

    def _on_factory_done(self, ok: bool, text: str):
        """成功后**作废设备基线** —— 表里/控件里显示的都是已被覆盖的旧值。
        不作废的话，用户会拿着旧值去"下发"，把刚恢复的出厂参数又改回去。
        """
        self._set_busy_ui(False)
        if ok:
            self._invalidate_baselines()
        # 先刷控件可用性再写状态行 —— 反过来的话 _refresh_state 的
        # "请先 [刷新当前]" 提示会把这里的结论盖掉
        self._refresh_state()
        self.status.setText(text + i18n.tr(" —— 设备参数已变更, 请重新 [刷新当前]")
                            if ok else text)
        self._log(f"[{'OK' if ok else 'ERR'}] "
                  + i18n.tr("调参[恢复出厂] {text}", text=text))

    def _on_saved(self, ok, text):
        self._set_busy_ui(False)
        self.status.setText(text)
        self._log(f"[{'OK' if ok else 'ERR'}] "
                  + i18n.tr("调参[固化] {text}", text=text))


# ================= diff 预览对话框 =================
class ParamDiffDialog(QDialog):
    """导入差异预览。
    **公开契约** (调用方依赖, 改动需同步 `_on_import` / `_do_import_hyy`):
      `diffs`        —— 扁平 `list[(label, old, new)]`, 含三段全部叶 (标题行**不计入**)
      `has_model`    —— 本文件是否含动力学模型段 (决定顶部横幅文案)
      `save_checkbox`—— "下发后固化到 Flash" 勾选框

    [2026-09-14] 新增模型段。三条要点:
      1. **横幅恒定显示**「含/不含模型段」—— `templates/*.yaml` 与 `presets/*.yaml`
         都**没有** `model` 键, 操作员拿预设导入会以为"都导了", 而实际模型纹丝不动。
         同一按钮、同一类文件、语义完全不同, 界面必须说出来。
      2. 段标题行**不进入 `diffs`** —— 调用方用 `len(dlg.diffs)` 打日志。
      3. 安全类字段 (tau_max/q_min/q_max/gravity) 的变化**独立高亮**:
         yaml 的 torque_max (20,20,...) 与固件默认 (78,78,...) 相差极大,
         而范围校验不会响、比率型阈值也覆盖不到。
    """
    def __init__(self, parent, old_snap, new_snap, model_diffs=None,
                 model_baseline=None, model_new=None, notes=None, unmapped=None):
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("参数导入 — 差异预览"))
        self.resize(880, 560)
        self.new_snap = new_snap
        self.diffs = C.diff_snapshots(old_snap, new_snap)
        self.model_diffs = list(model_diffs or [])
        self.has_model = model_new is not None

        lay = QVBoxLayout(self)

        # --- 恒定横幅 ---
        banner = QLabel()
        if self.has_model:
            banner.setText(i18n.tr(
                "本文件**含动力学模型段** —— 将写入连杆动力学 (m/com/I) 与电机转子惯量 jm。"))
            banner.setStyleSheet("background:#2a3a2a;color:#c8f0c8;padding:6px 8px;border-radius:3px;")
        else:
            banner.setText(i18n.tr(
                "本文件**不含动力学模型段** —— 关节与全局参数会下发，"
                "**动力学模型不会被改动**。"))
            banner.setStyleSheet("background:#3a3320;color:#f0e0b0;padding:6px 8px;border-radius:3px;")
        banner.setWordWrap(True)
        lay.addWidget(banner)

        if old_snap is None:
            tip = QLabel(i18n.tr(
                "尚无设备基线 (未刷新过) — 下表为待导入全量参数, 请逐项核对。"))
            tip.setWordWrap(True)
            lay.addWidget(tip)

        # --- 表格 (三段, 标题行不计入 self.diffs) ---
        rows = []
        joint_sub = [d for d in self.diffs if d[0].startswith("J")]
        glob_sub = [d for d in self.diffs if d[0].startswith("global.")]
        for grp, sub in ((i18n.tr("关节参数"), joint_sub),
                         (i18n.tr("全局参数"), glob_sub)):
            if sub:
                rows.append(("__hdr__", grp, None, None))
                rows.extend((d[0], d[1], d[2], None) for d in sub)
        if self.model_diffs:
            rows.append(("__hdr__",
                         i18n.tr("动力学模型 ({n} 项)", n=len(self.model_diffs)),
                         None, None))
            rows.extend((lab, old, new, None) for lab, old, new in self.model_diffs)

        tb = QTableWidget(len(rows), 4)
        tb.setHorizontalHeaderLabels([i18n.tr("参数"), i18n.tr("旧值 (设备当前)"),
                                      i18n.tr("新值 (导入)"), i18n.tr("说明")])
        tb.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tb.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        tb.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        tb.verticalHeader().setVisible(False)
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for ri, (lab, old, new, _) in enumerate(rows):
            if lab == "__hdr__":
                it = QTableWidgetItem(old)
                f = it.font()
                f.setBold(True)
                it.setFont(f)
                it.setBackground(QColor("#2b2b33"))
                tb.setItem(ri, 0, it)
                tb.setSpan(ri, 0, 1, 4)
                continue
            is_safety = bool(C.IS_SAFETY_KEY.get(lab.split(".", 1)[-1], False))
            note = i18n.tr("新增") if old is None else i18n.tr("修改")
            if is_safety:
                note = i18n.tr("⚠ {kind} — 安全类字段 (控制包络)", kind=note)
            row = [QTableWidgetItem(lab),
                   QTableWidgetItem(C.fmt_value(lab, old)),
                   QTableWidgetItem(C.fmt_value(lab, new)),
                   QTableWidgetItem(note)]
            for c, it in enumerate(row):
                if c == 2:
                    it.setBackground(QColor("#f6e3e3") if is_safety else QColor("#e3f6e3"))
                tb.setItem(ri, c, it)
        lay.addWidget(tb, 1)

        # --- 提示 / 未映射清单 ---
        extra = list(notes or [])
        if unmapped:
            lines = [f"  · {k}  →  {r}" for k, r in unmapped]
            extra.append(i18n.tr(
                "未映射字段 {n} 项 (yaml 里有、stm32 无处落, 未导入):",
                n=len(unmapped)))
            extra.extend(lines)
        if extra:
            txt = QPlainTextEdit("\n".join(extra))
            txt.setReadOnly(True)
            txt.setMaximumHeight(120)
            lay.addWidget(txt)

        bottom = QHBoxLayout()
        # [2026-09-14 用户裁决] **默认勾选**。
        # 理由: 固件侧 0x30/0x32/0x33/0x26 全都只写 RAM (0x32 只标脏), 唯一的落盘入口是
        # 0x25; 而产线上"导入完就是要固化"是常态 —— 默认不勾时一次漏勾就白做一台。
        # 代价: 擦写 sector 7 有 ~1s 的 CPU 停顿且须失能, 所以**保留**下发前的二次确认
        # (见 _on_import / _apply_hyy_snapshot 的确认框文案)。
        self.save_checkbox = QCheckBox(i18n.tr(
            "下发后固化到 Flash (param_save; 须先失能)"))
        self.save_checkbox.setChecked(True)
        bottom.addWidget(self.save_checkbox)
        bottom.addStretch(1)
        b_ok = QPushButton(i18n.tr("应用"))
        b_ok.clicked.connect(self.accept)
        b_cancel = QPushButton(i18n.tr("取消"))
        b_cancel.clicked.connect(self.reject)
        bottom.addWidget(b_ok)
        bottom.addWidget(b_cancel)
        lay.addLayout(bottom)
