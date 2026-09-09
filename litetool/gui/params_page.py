"""参数调参页 —— 逐关节参数表 + 全局标量 + ff_mask 复选框 + yaml/json 批量导入导出。

架构:
- 数据镜像表在 litetool/param_catalog.py (纯 Python, 供测试/yaml/UI 共用)。
- 本页命令在工作线程按序执行、每个写口等 ACK; 结果经 Qt 信号回主线程着色。
- 与 client._tx_lock 天然串行; 本页自持忙态, 经 busy_changed 让 MainWindow 叠加。
- 安全: GUI 先按目录钳幅校验并提示范围 (固件仍兜底); ff_mask 改动 / param_save /
  批量应用 发送前均弹确认。界面中文。
"""
import os
import threading

import yaml
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QDoubleSpinBox, QFileDialog, QGridLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                             QMessageBox, QPushButton, QScrollArea,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from litetool import param_catalog as C
from litetool import protocol as P

ROLE_VAL = Qt.UserRole + 1          # 单元格 float 值 (显示文本只作编辑入口)
BG = {0: QColor("#ffffff"), 1: QColor("#fff3bf"),
      2: QColor("#ffd9d9"), 3: QColor("#ffcccc")}   # 0常规 1改未发 2越界 3下发失败
FG_INVALID = QColor("#b00020")
JOINT_KEYS = [p.key for p in C.JOINT_PARAMS]
GROUP_KEYS = {"ctrl": ("kp", "kd", "tau_max"), "limits": ("q_min", "q_max")}


class ParamsPage(QWidget):
    busy_changed = pyqtSignal(bool)       # 后台调参操作忙态 -> MainWindow 叠加
    _sig_refreshed = pyqtSignal(object)
    _sig_rows_done = pyqtSignal(object)
    _sig_global_done = pyqtSignal(object)
    _sig_batch_done = pyqtSignal(object)
    _sig_saved = pyqtSignal(bool, str)
    _sig_busy = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log = lambda msg: None
        self._client = None
        self._online = False
        self._busy = False
        self._ext_busy = False          # MainWindow 侧运动/控制命令在途
        self._loading = False
        self._baseline = None           # 最近设备读回/整发成功快照 (diff 的"旧")
        self._synced = {}               # {row_key: {joint: float}}
        self._synced_glob = None        # global 基线 (含 ff_mask)
        self._pending_export = None     # 导出流程: 待读回完成后写入的 yaml 路径
        self._build_ui()
        self._sig_refreshed.connect(self._on_refreshed)
        self._sig_rows_done.connect(self._on_rows_done)
        self._sig_global_done.connect(self._on_global_done)
        self._sig_batch_done.connect(self._on_batch_done)
        self._sig_saved.connect(self._on_saved)
        self._sig_busy.connect(self._set_busy_ui)
        self._refresh_state()

    # ================= 界面 =================
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        bar = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新当前")
        self.btn_refresh.clicked.connect(self._on_refresh)
        self.btn_apply_row = QPushButton("下发选中行")
        self.btn_apply_row.clicked.connect(lambda: self._apply_rows_selected())
        self.btn_apply_all = QPushButton("下发全部")
        self.btn_apply_all.clicked.connect(lambda: self._apply_rows_selected(all_rows=True))
        self.btn_import = QPushButton("导入 YAML/JSON…")
        self.btn_import.clicked.connect(self._on_import)
        self.btn_export = QPushButton("导出当前")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_save = QPushButton("固化到 Flash…")
        self.btn_save.clicked.connect(self._on_save_flash)
        for b in (self.btn_refresh, self.btn_apply_row, self.btn_apply_all,
                  self.btn_import, self.btn_export, self.btn_save):
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)

        body = QScrollArea()
        body.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 0, 0)

        # 逐关节表
        g1 = QGroupBox("逐关节参数 (双击编辑; 黄=已改未下发; 红=越界/下发失败)")
        v1 = QVBoxLayout(g1)
        self.table = QTableWidget(len(C.JOINT_PARAMS), 1 + C.NUM_JOINTS)
        self.table.setHorizontalHeaderLabels(["参数"] + [f"J{i + 1}" for i in range(C.NUM_JOINTS)])
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
            head = QTableWidgetItem(p.label)
            head.setFlags(Qt.ItemIsEnabled)
            head.setToolTip(f"{p.key}  范围 {p.range_text()}\n写口: {self._write_desc(p)}")
            head.setBackground(QColor("#eceff4"))
            self.table.setItem(ri, 0, head)
            for j in range(C.NUM_JOINTS):
                it = QTableWidgetItem("")
                it.setData(ROLE_VAL, None)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
                it.setBackground(BG[0])
                self.table.setItem(ri, 1 + j, it)
        self.table.itemChanged.connect(self._on_cell_changed)
        v1.addWidget(self.table)
        tip = QLabel("提示: [kp/kd/tau_max] 与 [q_min/q_max] 成组下发 (选中任一组员即整组下发);"
                     " 标 (v2) 的摩擦参数在 friction_model=1 时生效; 行首悬停见写口/范围。")
        tip.setWordWrap(True)
        v1.addWidget(tip)
        col.addWidget(g1)

        # 全局标量
        g2 = QGroupBox("全局参数 (写 0x28 item / 读 0x2C item)")
        gg = QGridLayout(g2)
        self._g_spins = {}
        self._g_model = None
        r = 0
        for gp in C.GLOBAL_PARAMS:
            if gp.key == "friction_model":
                gg.addWidget(QLabel(f"{gp.label}  {gp.range_text()}"), r, 0)
                self._g_model = QComboBox()
                self._g_model.addItem("v1 — 误差方向 tanh")
                self._g_model.addItem("v2 — SE1 速度方向")
                self._g_model.setToolTip("friction_model (0x28 item7): 0=v1 1=v2")
                gg.addWidget(self._g_model, r, 1, 1, 3)
                r += 1
            elif gp.is_array:
                for k, _sub in enumerate(gp.subs):
                    lab = f"{gp.label} {('X', 'Y', 'Z')[k]} ({gp.unit})"
                    gg.addWidget(QLabel(lab), r, 0)
                    sp = self._mk_spin(gp)
                    self._g_spins.setdefault(gp.key, []).append(sp)
                    gg.addWidget(sp, r, 1, 1, 3)
                    r += 1
            else:
                gg.addWidget(QLabel(f"{gp.label} ({gp.unit})  {gp.range_text()}"), r, 0)
                sp = self._mk_spin(gp)
                self._g_spins[gp.key] = sp
                gg.addWidget(sp, r, 1, 1, 3)
                r += 1
        self.btn_global = QPushButton("下发全局 (含 ff_mask)")
        self.btn_global.clicked.connect(self._on_apply_global)
        gg.addWidget(self.btn_global, r, 0, 1, 2)
        col.addWidget(g2)

        # ff_mask 位
        g3 = QGroupBox("ff_mask 前馈使能位 (固件 FF_*, 下发走 0x27; 改动需二次确认)")
        ffg = QHBoxLayout(g3)
        self._ff_cbs = []
        for i, (_bit, name, label) in enumerate(C.FF_BITS):
            cb = QCheckBox(name)
            cb.setToolTip(f"bit{i}: {label}")
            cb.toggled.connect(lambda _on, j=i: self._on_ff_toggled(j))
            self._ff_cbs.append(cb)
            ffg.addWidget(cb)
        ffg.addStretch(1)
        col.addWidget(g3)

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
            return "0x22 (kp/kd/tau_max 按关节成组)"
        if p.kind == "limits":
            return "0x23 (q_min/q_max 成组, 须 q_min<q_max)"
        return f"0x26 item {p.item} (7 关节整组)"

    def _mk_spin(self, gp) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(gp.lo, gp.hi)
        sp.setDecimals(gp.decimals)
        sp.setSingleStep(max((gp.hi - gp.lo) / 100.0, 1e-4))
        sp.setToolTip(f"范围 {gp.range_text()}")
        return sp

    # ================= 状态 / 会话 =================
    def set_log(self, fn):
        self._log = fn

    def set_client(self, client):
        self._client = client
        self._refresh_state()

    def set_online(self, onl: bool):
        if onl != self._online:
            self._online = onl
            if not onl:
                self.status.setText("离线 — 断开或 500ms 无状态帧; 重连后自动恢复")
            elif self._client is not None and not self._busy:
                self.status.setText("就绪 — 可 [刷新当前] / 编辑下发 / 导入导出")
            self._refresh_state()

    def _can_run(self) -> bool:
        return bool(self._client is not None and self._online
                    and not self._busy and not self._ext_busy)

    def set_busy(self, busy: bool):
        """MainWindow 命令在途时调用 (叠加到本页忙态, 禁用操作按钮)。"""
        if busy != self._ext_busy:
            self._ext_busy = busy
            self._refresh_state()

    def _refresh_state(self):
        if self._client is None:
            self.status.setText("未连接 — 连接后可用 (读回 0x2B/0x2C 需固件 27961a1+)")
            self._set_ops_enabled(False)
        else:
            self._set_ops_enabled(self._can_run())

    def _set_ops_enabled(self, on: bool):
        for b in (self.btn_refresh, self.btn_apply_row, self.btn_apply_all,
                  self.btn_import, self.btn_export, self.btn_save, self.btn_global):
            b.setEnabled(on)
        self.table.setEnabled(on)
        for cb in self._ff_cbs:
            cb.setEnabled(on)
        for w in self._g_spins.values():
            for s in (w if isinstance(w, list) else [w]):
                s.setEnabled(on)
        if self._g_model is not None:
            self._g_model.setEnabled(on)

    def _set_busy_ui(self, busy: bool):
        self._busy = busy
        self._refresh_state()
        self.busy_changed.emit(busy)

    def _pre_op(self, what: str) -> bool:
        if self._client is None:
            self.status.setText("未连接")
            return False
        if not self._online:
            self.status.setText("离线, 忽略操作")
            return False
        if self._busy:
            self.status.setText(f"忙: 前一条调参操作仍在执行, 已忽略 {what}")
            return False
        if self._ext_busy:
            self.status.setText("忙: 运动/控制命令在途 (MainWindow), 已忽略调参操作")
            return False
        return True

    def _start(self, what, worker, sig):
        """GUI 线程调用: 交后台线程执行 worker(), 结果(plain object)经 sig 回主线程。"""
        if not self._pre_op(what):
            return
        self._set_busy_ui(True)
        self.status.setText(f"执行中: {what} …")

        def target():
            try:
                res = worker()
            except Exception as e:  # noqa: BLE001
                self._log(f"[ERR] 调参[{what}] 异常: {e}")
                res = None
            sig.emit(res)

        threading.Thread(target=target, name=f"params-{what}", daemon=True).start()

    # ================= 读回 =================
    def _read_snapshot(self, cli) -> dict | None:
        joints = []
        for j in range(C.NUM_JOINTS):
            r = cli.get_joint_param(j)
            if r is None:
                raise OSError(f"J{j + 1} 读回失败 (0x24 无应答)")
            _idx, kp, kd, tau, q_min, q_max = r
            joints.append({"kp": kp, "kd": kd, "tau_max": tau,
                           "q_min": q_min, "q_max": q_max})
        for p in C.JOINT_PARAMS:
            if p.kind != "vec":
                continue
            r = cli.get_ff_vec(p.item)
            if r is None:
                raise OSError(f"{p.key} 读回失败 (0x2B item {p.item} 无应答)")
            _item, vals = r
            for j in range(min(len(vals), C.NUM_JOINTS)):
                joints[j][p.key] = vals[j]
        glob = {}
        for gp in C.GLOBAL_PARAMS:
            if gp.is_array:
                vals = []
                for sub in gp.subs:
                    r = cli.get_ff_scalar(gp.item, sub)
                    if r is None:
                        raise OSError(f"{gp.key} 读回失败 (0x2C 无应答)")
                    vals.append(r[2])
                glob[gp.key] = vals
            else:
                r = cli.get_ff_scalar(gp.item, gp.subs[0])
                if r is None:
                    raise OSError(f"{gp.key} 读回失败 (0x2C 无应答)")
                glob[gp.key] = int(round(r[2])) if gp.model else float(r[2])
        r = cli.get_ff_scalar(C.FF_MASK_SCALAR_ITEM, 0)
        if r is None:
            raise OSError("ff_mask 读回失败 (0x2C item 9 无应答)")
        glob["ff_mask"] = int(round(r[2])) & C.FF_ALL_MASK
        return {"joints": joints, "global": glob}

    def _on_refresh(self):
        cli = self._client

        def worker():
            return self._read_snapshot(cli)

        self._start("刷新当前", worker, self._sig_refreshed)

    def _on_refreshed(self, snap):
        self._set_busy_ui(False)
        if snap is None:
            if self._pending_export:
                self.status.setText("导出失败 — 读回为空 (固件需 27961a1+)")
                self._pending_export = None
            else:
                self.status.setText("刷新失败 — 请检查串口/固件 (读回需固件 27961a1+)")
            return
        self._loading = True
        try:
            for p in C.JOINT_PARAMS:
                ri = JOINT_KEYS.index(p.key)
                for j in range(C.NUM_JOINTS):
                    self._set_table_val(ri, j, snap["joints"][j][p.key])
            self._apply_global_to_ui(snap["global"])
        finally:
            self._loading = False
        self._baseline = snap
        if self._pending_export:
            path, self._pending_export = self._pending_export, None
            try:
                _dump_snapshot(snap, path)
                self.status.setText(f"已导出到 {path} — 同文件再导入时 diff 应为空")
                self._log(f"[OK] 调参[导出] 写 {path}")
            except Exception as e:  # noqa: BLE001
                self.status.setText(f"导出写入失败: {e}")
                self._log(f"[ERR] 调参[导出] {e}")
            return
        self.status.setText(f"刷新完成 — 7 关节 × {len(C.JOINT_PARAMS)} 项 + 全局"
                            f" (ff_mask={snap['global']['ff_mask']} = 0x"
                            f"{snap['global']['ff_mask']:X})")
        self._log("[OK] 调参[刷新] 读回全量完成")

    def _apply_global_to_ui(self, g: dict):
        self._synced_glob = {k: (list(v) if isinstance(v, list) else v)
                             for k, v in g.items()}
        for gp in C.GLOBAL_PARAMS:
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
        bits = C.mask_to_bits(g["ff_mask"])
        for cb, on in zip(self._ff_cbs, bits):
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)

    def _set_table_val(self, ri, j, val):
        p = C.JOINT_PARAMS[ri]
        it = self.table.item(ri, 1 + j)
        it.setText(f"{float(val):.{p.decimals}f}")
        it.setData(ROLE_VAL, float(val))
        it.setForeground(QColor("#000000"))
        it.setBackground(BG[0])
        it.setToolTip(f"{p.key} = {val!r}")

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
        if self._loading or it is None or self._client is None:
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
            it.setToolTip(err)
            it.setBackground(BG[2])
            it.setForeground(FG_INVALID)
        else:
            it.setToolTip(f"{p.key} = {v!r}")
            self._refresh_cell_color(ri, j)

    def _on_ff_toggled(self, _idx):
        if self._loading:
            return
        cur = C.bits_to_mask([cb.isChecked() for cb in self._ff_cbs])
        base = self._synced_glob["ff_mask"] if self._synced_glob else None
        if base is not None and cur != base:
            self.status.setText("ff_mask 已改动 — 下发全局时将弹确认框")

    # ================= 逐关节矩阵 & 下发 =================
    def _ui_matrix(self) -> list:
        mat = []
        for j in range(C.NUM_JOINTS):
            row = {}
            for ri, p in enumerate(C.JOINT_PARAMS):
                v = self._cell_val(ri, j)
                if v is None:
                    raise ValueError(f"J{j + 1}.{p.key} 为空 — 请先 [刷新当前]")
                err = C.check_joint(p, v, joint_idx=j)
                if err:
                    raise ValueError(err)
                row[p.key] = v
            rel = C.check_joint_limits_relation(row)
            if rel:
                raise ValueError(f"J{j + 1}: {rel}")
            mat.append(row)
        return mat

    def _selected_row_keys(self) -> list:
        sel = sorted({i.row() for i in self.table.selectedIndexes()})
        return [C.JOINT_PARAMS[ri].key for ri in sel if ri < len(C.JOINT_PARAMS)]

    def _apply_rows_selected(self, all_rows: bool = False):
        keys = list(JOINT_KEYS) if all_rows else self._selected_row_keys()
        if not keys:
            self.status.setText("未选中行 — 请先点选一行 (或用 [下发全部])")
            return
        try:
            mat = self._ui_matrix()
        except ValueError as e:
            QMessageBox.warning(self, "下发校验未通过", str(e))
            self.status.setText(f"校验未通过: {e}")
            return
        group = set(keys)
        for k in list(keys):
            p = C.JOINT_BY_KEY[k]
            if p.kind in GROUP_KEYS:
                group |= set(GROUP_KEYS[p.kind])
        cli = self._client
        ops = self._build_row_ops(group, mat)

        def worker():
            return _run_ops(cli, ops)

        self._start(f"下发 {len(group)} 行", worker, self._sig_rows_done)

    @staticmethod
    def _build_row_ops(keys: set, mat: list) -> list:
        """按行生成下发操作; 每项 {cells:[(rk,j,val)...], run(cli)->(ok,code)}"""
        ops = []
        active = set(C.JOINT_BY_KEY[k].kind for k in keys)
        if "ctrl" in active:
            for j in range(C.NUM_JOINTS):
                a = (mat[j]["kp"], mat[j]["kd"], mat[j]["tau_max"])
                cells = [(k, j, mat[j][k]) for k in GROUP_KEYS["ctrl"]]
                ops.append({"cells": cells,
                            "run": lambda cli, jj=j, aa=a: cli.set_joint_param(jj, *aa)})
        if "limits" in active:
            for j in range(C.NUM_JOINTS):
                a = (mat[j]["q_min"], mat[j]["q_max"])
                cells = [(k, j, mat[j][k]) for k in GROUP_KEYS["limits"]]
                ops.append({"cells": cells,
                            "run": lambda cli, jj=j, aa=a: cli.set_joint_limits(jj, *aa)})
        for p in C.JOINT_PARAMS:
            if p.kind != "vec" or p.key not in keys:
                continue
            vals = [mat[j][p.key] for j in range(C.NUM_JOINTS)]
            cells = [(p.key, j, vals[j]) for j in range(C.NUM_JOINTS)]
            ops.append({"cells": cells,
                        "run": lambda cli, it=p.item, aa=vals: cli.set_ff_vec(it, aa)})
        return ops

    # ================= 结果处理 (逐关节/批量共用) =================
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
            txt = P.ERR_TEXT.get(code, f"code 0x{code:02X}") if code is not None else "超时/无应答"
            self._log(f"[ERR] 调参[下发] {rk} J{j + 1}: {txt}")
        if failc:
            self.status.setText(f"下发完成: 成功 {len(okc)} 项, 失败 {len(failc)} 项 (格已标红)")
        else:
            self.status.setText(f"下发完成 — {len(okc)} 项全部 ACK")
            self._log(f"[OK] 调参[下发] {len(okc)} 项全部 ACK")

    # ================= 全局下发 =================
    def _global_from_ui(self) -> dict:
        g = {}
        for gp in C.GLOBAL_PARAMS:
            if gp.key == "friction_model":
                g[gp.key] = self._g_model.currentIndex()
            elif gp.is_array:
                g[gp.key] = [s.value() for s in self._g_spins[gp.key]]
            else:
                g[gp.key] = self._g_spins[gp.key].value()
        g["ff_mask"] = C.bits_to_mask([cb.isChecked() for cb in self._ff_cbs])
        return g

    def _on_apply_global(self):
        g = self._global_from_ui()
        base = self._synced_glob
        mask_changed = base is None or base["ff_mask"] != g["ff_mask"]
        if mask_changed:
            if QMessageBox.warning(
                    self, "确认 ff_mask 改动",
                    f"ff_mask 将改为 {g['ff_mask']} (0x{g['ff_mask']:X})\n\n"
                    "前馈位改动会立即影响控制律输出, 确认下发?",
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel) != QMessageBox.Ok:
                self.status.setText("已取消 ff_mask 下发")
                return
        cli = self._client

        def worker():
            return _send_global(cli, g)

        self._start("下发全局", worker, self._sig_global_done)

    def _on_global_done(self, res):
        self._set_busy_ui(False)
        if res is None:
            return
        g, leaf_ok, model_ok, mask_ok = res
        # 合并同步基线 (仅成功叶)
        if self._synced_glob is None:
            sg = {k: (list(v) if isinstance(v, list) else v) for k, v in g.items()}
        else:
            sg = {k: (list(v) if isinstance(v, list) else v)
                  for k, v in self._synced_glob.items()}
        for gp in C.GLOBAL_PARAMS:
            if gp.key == "friction_model":
                if model_ok:
                    sg[gp.key] = g[gp.key]
                continue
            if leaf_ok.get(gp.key):
                sg[gp.key] = (list(g[gp.key]) if isinstance(g[gp.key], list)
                              else g[gp.key])
        if mask_ok:
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
        if not model_ok:
            fails.append("friction_model")
        if not mask_ok:
            fails.append("ff_mask")
        if not fails:
            self.status.setText("全局下发完成 — 全部 ACK")
            self._log("[OK] 调参[全局] 全部 ACK")
        else:
            self.status.setText(f"全局下发部分失败: {', '.join(fails)}")
            self._log(f"[ERR] 调参[全局] 失败项: {', '.join(fails)}")

    # ================= 导入 / 批量 =================
    def _on_import(self):
        if not self._pre_op("导入"):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择参数文件", "", "参数文件 (*.yaml *.yml *.json);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            snap = C.normalize_snapshot(raw)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", str(e))
            return
        dlg = ParamDiffDialog(self, self._baseline, snap)
        if dlg.exec_() != QDialog.Accepted:
            self.status.setText("导入已取消")
            return
        flash_save = dlg.save_checkbox.isChecked()
        if flash_save:
            if QMessageBox.warning(
                    self, "确认下发后固化 Flash",
                    "将先下发整套参数到 RAM, 随后调用 param_save 固化到 Flash。\n\n"
                    "固件要求关节处于 disable 态才会执行擦写 (enable 态返回 ERR 0x04)。\n"
                    "请确认已先在 [控制] 页 [失能]?",
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel) != QMessageBox.Ok:
                flash_save = False
                self.status.setText("已取消固化选项, 仅下发 RAM")
        self._log(f"[INFO] 调参[导入] {path}: 差异 {len(dlg.diffs)} 项,"
                  f" 固化={flash_save}")
        self._apply_full_snapshot(snap, flash_save=flash_save)

    def _apply_full_snapshot(self, snap: dict, flash_save: bool = False):
        if QMessageBox.warning(
                self, "确认批量下发",
                f"将按固件写口顺序逐条下发整套参数\n"
                f"  · 关节 {C.NUM_JOINTS} × {len(C.JOINT_PARAMS)} 项 (0x22/0x23/0x26)\n"
                f"  · 全局标量 + friction_model + ff_mask (0x28/0x27)\n\n"
                "下发生效为即时 RAM 修改 (刚度/限位/前馈), 请确认当前安全。",
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            self.status.setText("批量下发已取消")
            return
        mat = snap["joints"]
        ops = self._build_row_ops(set(JOINT_KEYS), mat)
        glob = snap["global"]
        cli = self._client

        def worker():
            rowres = _run_ops(cli, ops)
            grec = _send_global(cli, glob)
            g, leaf_ok, model_ok, mask_ok = grec
            save_ok = None
            if flash_save:
                try:
                    ok, _code = cli.param_save(timeout=6.0)
                    save_ok = bool(ok)
                except Exception:  # noqa: BLE001
                    save_ok = False
            return {"row": rowres, "glob": glob,
                    "leaf_ok": leaf_ok, "model_ok": model_ok, "mask_ok": mask_ok,
                    "save_ok": save_ok}

        self._start("批量下发", worker, self._sig_batch_done)

    def _on_batch_done(self, res):
        self._set_busy_ui(False)
        if res is None:
            return
        okc = res["row"]["ok"]
        failc = res["row"]["fail"]
        self._commit_row_success(okc)
        for (rk, j), code in failc.items():
            self._paint(JOINT_KEYS.index(rk), j, 3)
            txt = P.ERR_TEXT.get(code, f"code 0x{code:02X}") if code is not None else "超时"
            self._log(f"[ERR] 调参[批量] {rk} J{j + 1}: {txt}")
        g = res["glob"]
        leaf_ok, model_ok, mask_ok = res["leaf_ok"], res["model_ok"], res["mask_ok"]
        # 同步 global 基线: 成功叶取下发值, 失败叶保留旧
        old = self._synced_glob
        sg = {k: (list(v) if isinstance(v, list) else v)
              for k, v in (old if old is not None else g).items()}
        for gp in C.GLOBAL_PARAMS:
            if gp.key == "friction_model":
                if model_ok:
                    sg[gp.key] = g[gp.key]
                continue
            if leaf_ok.get(gp.key):
                sg[gp.key] = (list(g[gp.key]) if isinstance(g[gp.key], list)
                              else g[gp.key])
        if mask_ok:
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
        gfail = sum(1 for k, ok in leaf_ok.items() if not ok) \
            + (0 if model_ok else 1) + (0 if mask_ok else 1)
        msg = (f"批量下发完成: 关节成功 {len(okc)}/失败 {len(failc)}, "
               f"全局失败 {gfail}")
        if res["save_ok"] is True:
            msg += "; 已固化到 Flash"
        elif res["save_ok"] is False:
            msg += "; 固化失败 (enable 态会返回 0x04 须先失能)"
        self.status.setText(msg)
        self._log(f"[{'OK' if not failc and gfail == 0 else 'ERR'}] 调参[批量] {msg}")

    # ================= 导出 =================
    def _on_export(self):
        if not self._pre_op("导出"):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出当前参数", "litearm_params.yaml", "参数文件 (*.yaml)")
        if not path:
            return
        self._pending_export = os.path.abspath(path)
        # 复用刷新读回流程, 完成后由 _on_refreshed 写文件
        self._on_refresh()

    # ================= param_save (二次确认) =================
    def _on_save_flash(self):
        if not self._pre_op("固化"):
            return
        if QMessageBox.question(
                self, "固化到 Flash (1/2)",
                "将把当前 RAM 参数写入 Flash 持久化 (涉及扇区擦除)。\n\n"
                "固件要求关节处于 disable 态 (enable 态返回 ERR 0x04)。",
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            return
        if QMessageBox.warning(
                self, "再次确认固化 (2/2)",
                "Flash 参数在下电后仍生效, 固件会整体重钳一遍所有参数。\n\n"
                "确认现在固化?",
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            self.status.setText("固化已取消")
            return
        cli = self._client

        def worker():
            try:
                ok, code = cli.param_save(timeout=6.0)
                if ok:
                    return True, "固化成功 (已写 Flash)"
                txt = P.ERR_TEXT.get(code, f"code 0x{code:02X}") if code is not None else "超时"
                return False, f"固件拒绝: {txt}"
            except Exception as e:  # noqa: BLE001
                return False, f"异常: {e}"

        self._start("固化到 Flash", worker, self._sig_saved)

    def _on_saved(self, ok, text):
        self._set_busy_ui(False)
        self.status.setText(text)
        self._log(f"[{'OK' if ok else 'ERR'}] 调参[固化] {text}")


# ================= 纯执行辅助 =================
def _run_ops(cli, ops):
    """顺序执行、逐个等 ACK; 返回 {'ok': {(rk,j):val}, 'fail': {(rk,j):code}}"""
    okc, failc = {}, {}
    for op in ops:
        try:
            r = op["run"](cli)
            if isinstance(r, tuple):
                ok, code = bool(r[0]), r[1]
            else:
                ok, code = bool(r), None
        except Exception:  # noqa: BLE001
            ok, code = False, None
        for (rk, j, val) in op["cells"]:
            if ok:
                okc[(rk, j)] = val
            else:
                failc[(rk, j)] = code
    return {"ok": okc, "fail": failc}


def _send_global(cli, g):
    """按 0x28/0x27 顺序下发 global; 返回 (g, leaf_ok{key:bool}, model_ok, mask_ok)"""
    leaf_ok = {}
    model_ok = mask_ok = True
    for gp in C.GLOBAL_PARAMS:
        if gp.key == "friction_model":
            continue
        v = g[gp.key]
        if gp.is_array:
            good = all(_set_scalar(cli, gp.item, sub, float(v[k]))
                       for k, sub in enumerate(gp.subs))
        else:
            good = _set_scalar(cli, gp.item, gp.subs[0], float(v))
        leaf_ok[gp.key] = good
    model_ok = _set_scalar(cli, C.GLOBAL_BY_KEY["friction_model"].item, 0,
                           float(g["friction_model"]))
    try:
        mask_ok = bool(cli.set_ff_flags(int(g["ff_mask"]))[0]) \
            if isinstance(cli.set_ff_flags(int(g["ff_mask"])), tuple) \
            else bool(cli.set_ff_flags(int(g["ff_mask"])))
    except Exception:  # noqa: BLE001
        mask_ok = False
    return g, leaf_ok, model_ok, mask_ok


def _set_scalar(cli, item, sub, value) -> bool:
    try:
        r = cli.set_ff_scalar(item, sub, value)
        return bool(r[0]) if isinstance(r, tuple) else bool(r)
    except Exception:  # noqa: BLE001
        return False


def _dump_snapshot(snap, path):
    doc = {"joints": [{"name": f"J{i + 1}", **jd}
                      for i, jd in enumerate(snap["joints"])],
           "global": {k: (list(v) if isinstance(v, list) else v)
                      for k, v in snap["global"].items()}}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)


# ================= diff 预览对话框 =================
class ParamDiffDialog(QDialog):
    def __init__(self, parent, old_snap, new_snap):
        super().__init__(parent)
        self.setWindowTitle("参数导入 — 差异预览")
        self.resize(800, 480)
        self.new_snap = new_snap
        self.diffs = C.diff_snapshots(old_snap, new_snap)

        lay = QVBoxLayout(self)
        if old_snap is None:
            tip = QLabel("尚无设备基线 (未刷新过) — 下表为待导入全量参数, 请逐项核对。")
            tip.setWordWrap(True)
            lay.addWidget(tip)

        tb = QTableWidget(len(self.diffs), 4)
        tb.setHorizontalHeaderLabels(["参数", "旧值 (设备当前)", "新值 (导入)", "说明"])
        tb.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tb.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        tb.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        tb.verticalHeader().setVisible(False)
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for ri, (lab, old, new) in enumerate(self.diffs):
            row = [QTableWidgetItem(lab),
                   QTableWidgetItem(C.fmt_value(lab, old)),
                   QTableWidgetItem(C.fmt_value(lab, new)),
                   QTableWidgetItem("新增" if old is None else "修改")]
            for c, it in enumerate(row):
                if c == 2:
                    it.setBackground(QColor("#e3f6e3"))
                tb.setItem(ri, c, it)
        lay.addWidget(tb)

        bottom = QHBoxLayout()
        self.save_checkbox = QCheckBox("下发后固化到 Flash (param_save; 须先失能)")
        bottom.addWidget(self.save_checkbox)
        bottom.addStretch(1)
        b_ok = QPushButton("应用")
        b_ok.clicked.connect(self.accept)
        b_cancel = QPushButton("取消")
        b_cancel.clicked.connect(self.reject)
        bottom.addWidget(b_ok)
        bottom.addWidget(b_cancel)
        lay.addLayout(bottom)
