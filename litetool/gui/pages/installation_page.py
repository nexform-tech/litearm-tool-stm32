"""安装方向页 —— 读写固件的 gravity 向量（正装 / 侧装 / 倒装 / 任意斜置）。

对应 SDK：`set_ff_scalar(6, sub, v)`（0x28 item6 sub0/1/2 写）
`get_ff_scalar(6, sub)`（0x2C item6 读回）`save_params`（0x25 固化）
`model.get_gravity(q)`（0x39，用于"写进去了没有"的前后自比）。

## 为什么要有这一页

固件**没有** `installation` / `base_rpy` 这类语义接口 —— 改安装方向就是改 base 系
**gravity 向量**这一个量。原先它埋在参数页的"全局参数"网格里，用户得自己知道
「侧装该填什么向量」，还得和另外 20 个全局叶一起批量下发。本页把它单拎出来：
选装向 → 自动算向量 → 在三道闸下写下去。

## 三道闸（顺序固定，任一不过则**一帧都不发**）

1. **基线闸**：未成功 [读当前] 过 → 禁下发（防 `QDoubleSpinBox` 的默认值被盲发）。
2. **失能闸（硬拦）**：`_st is None`（状态没到手 == 不知道，不等于安全）或 `_st.enabled`
   → 弹「须先失能」并直接 return。**比参数页的"确认框放行"更严**，因为改 gravity 会让
   重力前馈当拍阶跃（正装↔侧装 |Δg|=13.87 m/s²=1.41g，J2/J3 上几十 Nm），而
   `set_ff_scalar` 三条**非原子** —— 中途会经过模长 13.87、方向偏 45° 的中间态。
   ⚠ 固件 1.5.3 起 armed 态会回 `ERR{0x28,0x04}` 拒绝，但**更早的固件会默默写进去**，
   所以这道闸在工具侧，不能指望固件。
   **本页不代劳 `disable()`** —— 失能有物理后果（臂失去保持力矩），那是用户在
   [整机] 页的决策，不是本页的。
3. **模长闸**：|g| 偏离 9.81 超 1% → 二次确认（抓"只改了一个轴"这类看着合理的错）。

## 与参数页的关系

参数页的 gravity 编辑**保持原样**（确认框放行策略）。本页用硬拦策略 —— 两者策略不同，
不是重复实现，故不做抽象合并（避免动一个已测页面）。
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QLabel, QMessageBox, QPushButton, QVBoxLayout,
                             QWidget)

from litetool import i18n
from litetool import model_io as MIO
from litetool import param_catalog as C
from litetool import params_io as PIO
from litetool.gui.i18n_ui import TrButton, TrLabel, tr_tooltip
from litetool.gui.pages.common import group, hint, note, row, spin

GRAVITY_ITEM = 6            # 0x28/0x2C 的 item6
G0 = 9.81                   # 标准重力加速度 (m/s²)
MAG_TOL_REL = 0.01          # |g| 偏离 9.81 超 1% 就二次确认

#: 预设 (按钮名, 该装向对应的 base_rpy, 将写入的 gravity 向量)
#: 向量由 `gravity_from_rpy` 算出并**写死在这里**，测试会断言二者一致 ——
#: 免得哪天公式改了而预设表没跟上。
PRESETS: Tuple[Tuple[str, Tuple[float, float, float], Tuple[float, float, float]], ...] = (
    ("正装",   (0.0, 0.0, 0.0),                 (0.0, 0.0, -G0)),
    ("倒装",   (0.0, math.pi, 0.0),             (0.0, 0.0, G0)),
    ("侧装 +x", (0.0, math.pi / 2, 0.0),        (G0, 0.0, 0.0)),
    ("侧装 -x", (0.0, -math.pi / 2, 0.0),       (-G0, 0.0, 0.0)),
    ("侧装 +y", (-math.pi / 2, 0.0, 0.0),       (0.0, G0, 0.0)),
    ("侧装 -y", (math.pi / 2, 0.0, 0.0),        (0.0, -G0, 0.0)),
)


def gravity_from_rpy(rpy: Sequence[float]) -> Tuple[float, float, float]:
    """`g_base = R(rpy)ᵀ·(0,0,-9.81)`，`R = Rz(yaw)·Ry(pitch)·Rx(roll)`。

    与固件 `kin.c::kin_rpy_to_rot` / pylitearm `gravity_from_installation` 同式
    （URDF 约定）。纯 Python 3x3 —— 本页不需要 numpy。
    """
    r, p, y = float(rpy[0]), float(rpy[1]), float(rpy[2])
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    R = ((cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
         (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
         (-sp,     cp * sr,                cp * cr))
    G = (0.0, 0.0, -G0)
    # g = Rᵀ·G  ⇒  g[i] = Σ_k R[k][i]·G[k]
    return tuple(sum(R[k][i] * G[k] for k in range(3)) for i in range(3))


def _f32(v: float) -> float:
    """按 float32 打包再拆 —— 设备回读是 f32 往返，直接比会让末位 ULP 恒报差异。"""
    import struct
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def _mag(g: Sequence[float]) -> float:
    return math.sqrt(sum(float(v) * float(v) for v in g))


def _label_of(g: Sequence[float]) -> str:
    """把一个向量认成预设名；认不出返回 '(自定义)'。"""
    for name, _rpy, vec in PRESETS:
        if all(abs(float(g[i]) - vec[i]) < 1e-3 for i in range(3)):
            return name
    return "(自定义)"


class InstallationPage(QWidget):
    """安装方向（gravity 向量）读写。**只写参数，不动臂、不受运动解锁管辖。**"""

    sig_read_done = pyqtSignal(object)
    sig_apply_done = pyqtSignal(object)
    sig_save_done = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._submit = None
        self._log = lambda _m: None
        self._online = False
        self._busy = False
        self._ext_busy = False
        #: 构造期整体屏蔽联动。**这不是洁癖**: `setValue()` 会当场触发 `valueChanged`,
        #: 而槽里要碰的 `lbl_mag`/`btn_read` 那时还没建出来 -> AttributeError 落在 Qt 槽里
        #: -> PyQt5 调 qFatal **直接 abort 整个进程**（不是可捕获的 Python 异常, 连
        #: `pytest.raises` 都拦不住）。构造期一律关掉联动, 末尾再统一开。
        self._loading = True
        #: 未成功 [读当前] 前禁下发（防控件默认值盲发）—— 见模块头"三道闸"
        self._device_synced = False
        self._st = None                 # 主窗口周期喂的状态帧；失能闸要用
        self._baseline = None           # 设备当前 gravity（[读当前] 后填）
        self._custom = False            # 向量被手改过 → rpy 显示"(自定义)"
        self._loading = False           # 程序性回填中，别触发联动
        self._status_src = ("未连接 — 连接后可用", None)
        self._dev = None                # (向量, 预设名) —— 设备当前行

        gp = C.GLOBAL_BY_KEY["gravity"]
        self._gp = gp

        # ---- 状态行 ----
        self.status = QLabel(i18n.tr("未连接 — 连接后可用"))
        self.status.setStyleSheet("color:#61afef;")
        self.status.setWordWrap(True)

        # ---- 预设 ----
        self._preset_btns = {}
        btns = []
        for name, _rpy, vec in PRESETS:
            b = TrButton(name)
            b.setMinimumHeight(32)
            tr_tooltip(b, "写入 gravity = ({x:+.2f}, {y:+.2f}, {z:+.2f}) m/s²",
                       x=vec[0], y=vec[1], z=vec[2])
            b.clicked.connect(lambda _=False, v=vec, r=_rpy: self._apply_preset(v, r))
            self._preset_btns[name] = b
            btns.append(b)
        self.btn_custom = TrButton("自定义")
        self.btn_custom.setMinimumHeight(32)
        tr_tooltip(self.btn_custom, "不选预设，直接用下面的 base_rpy 或 gravity 向量")
        self.btn_custom.clicked.connect(self._on_custom)
        btns.append(self.btn_custom)
        g_preset = group("① 选择安装方向", row(*btns),
                         note("按钮上写的就是将下发的 base 系重力向量 —— 别去猜"
                              "「侧装 +y」是哪一边。不确定就用 base_rpy 推导，"
                              "或在 pylitearm 侧 set_installation/get_installation 取同一组值。"))

        # ---- base_rpy → gravity 联动 ----
        self._rpy_spins = [spin(-3.15, 3.15, 0.0, 0.01, 4) for _ in range(3)]
        for s in self._rpy_spins:
            s.valueChanged.connect(self._on_rpy_changed)
        self.lbl_rpy_state = QLabel("")
        self.lbl_rpy_state.setStyleSheet("color:#8a97a4;")

        # 初值随控件构造给出 —— 不要建完再 setValue（那会触发联动，见 `_loading` 注释）
        self._g_spins = [spin(gp.lo, gp.hi, v, 0.01, 4)
                         for v in (0.0, 0.0, -G0)]
        for s in self._g_spins:
            s.valueChanged.connect(self._on_g_changed)
        self.lbl_mag = QLabel("")
        self.lbl_mag.setMinimumWidth(190)

        g_vec = group(
            "② 安装姿态与向量（{unit}）",
            row(TrLabel("base_rpy  roll"), self._rpy_spins[0],
                TrLabel("pitch"), self._rpy_spins[1],
                TrLabel("yaw"), self._rpy_spins[2], self.lbl_rpy_state),
            row(TrLabel("gravity   x"), self._g_spins[0],
                TrLabel("y"), self._g_spins[1],
                TrLabel("z"), self._g_spins[2], self.lbl_mag),
            note("g = R(base_rpy)ᵀ·(0,0,-{g0})，与固件 kin.c 同式。改 rpy 会自动重算向量；"
                 "直接改向量则 rpy 标为「(自定义)」（反向不唯一，不做反解）。",
                 g0=G0),
            unit=gp.unit,
        )

        # ---- 设备当前 / 操作 ----
        self.btn_read = TrButton("读当前")
        self.btn_read.setMinimumHeight(34)
        tr_tooltip(self.btn_read,
                   "读 0x2C item6 三轴 —— 这是本页所有下发的前置（未读不许写）")
        self.btn_read.clicked.connect(self._on_read)

        self.btn_apply = TrButton("下发（须失能）")
        self.btn_apply.setMinimumHeight(34)
        tr_tooltip(
            self.btn_apply,
            "写 0x28 item6 sub0/1/2。须先失能：改 gravity 会让重力前馈当拍阶跃，\n"
            "且三条非原子（中途经过模长 13.87 的中间态）。本页不会替你失能。")
        self.btn_apply.clicked.connect(self._on_apply)

        self.btn_save = TrButton("固化到 Flash")
        self.btn_save.setMinimumHeight(34)
        tr_tooltip(self.btn_save, "写 0x25 保存当前 RAM 参数到 flash（同样须失能）")
        self.btn_save.clicked.connect(self._on_save)

        self.lbl_dev = QLabel(i18n.tr("设备当前：—"))
        self.lbl_dev.setStyleSheet("color:#c8c8c8;")

        g_ops = group("③ 读 / 下发 / 固化",
                      row(self.btn_read, self.btn_apply, self.btn_save),
                      row(self.lbl_dev))

        self.hint_lbl = hint("")
        self.hint_lbl.setVisible(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.status)
        lay.addWidget(self.hint_lbl)
        lay.addWidget(g_preset)
        lay.addWidget(g_vec)
        lay.addWidget(g_ops)
        lay.addStretch(1)

        self.sig_read_done.connect(self._on_read_done)
        self.sig_apply_done.connect(self._on_apply_done)
        self.sig_save_done.connect(self._on_save_done)
        self._loading = False          # 控件齐了, 开联动
        self._update_mag()
        self._refresh()

    # ================= 向量/rpy 联动 =================
    def _vector(self) -> Tuple[float, float, float]:
        return tuple(float(s.value()) for s in self._g_spins)

    def _rpy(self) -> Tuple[float, float, float]:
        return tuple(float(s.value()) for s in self._rpy_spins)

    def _set_rpy(self, rpy: Sequence[float]):
        self._loading = True
        for s, v in zip(self._rpy_spins, rpy):
            s.setValue(float(v))
        self._loading = False

    def _set_vector(self, g: Sequence[float]):
        self._loading = True
        for s, v in zip(self._g_spins, g):
            s.setValue(float(v))
        self._loading = False

    def _on_rpy_changed(self, _v):
        """改 rpy → 重算向量（用户此刻是在用 rpy 驱动）。"""
        if self._loading:
            return
        self._custom = False
        self._set_vector(gravity_from_rpy(self._rpy()))
        self._update_mag()

    def _on_g_changed(self, _v):
        """改向量 → 标记自定义（不做反解：R→rpy 不唯一）。"""
        if self._loading:
            return
        self._custom = True
        self._update_mag()

    def _apply_preset(self, vec, rpy):
        self._custom = False
        self._set_rpy(rpy)
        self._set_vector(vec)
        self._update_mag()

    def _on_custom(self):
        self._custom = True
        self._update_mag()

    def _update_mag(self):
        m = _mag(self._vector())
        off = abs(m - G0)
        ok = off <= G0 * MAG_TOL_REL
        self.lbl_mag.setText(
            i18n.tr("|g| = {mag:.4f}  ", mag=m)
            + ("✅" if ok else i18n.tr("⚠ 偏离 9.81 超 {pct:.0%}", pct=MAG_TOL_REL)))
        self.lbl_mag.setStyleSheet("color:#98c379;" if ok else "color:#ffd166;")
        self.lbl_rpy_state.setText(i18n.tr("(自定义)") if self._custom else "")
        self._refresh()

    # ================= 外部状态 =================
    def set_log(self, fn):
        self._log = fn

    def set_submit(self, fn):
        """主窗口注入 `fn(name, callable, on_done)` —— 在 SDK 所有者线程上执行。"""
        self._submit = fn
        # 换会话 = 设备参数未知 -> 禁下发，待 [读当前] 成功
        self._device_synced = False
        self._baseline = None
        # 换会话后旧会话在途任务的回调不会再到达本页 ⇒ 清忙态，否则页面一进来就是灰的
        self._busy = False
        self._refresh()

    def set_online(self, onl: bool):
        if onl != self._online:
            self._online = onl
            if not onl:
                # 断开/换板 → 旧基线是错的，一律作废（与参数页同一裁决）
                self._device_synced = False
                self._baseline = None
                self._busy = False
                self._dev = None
                self._render_dev()
                self._set_status("离线 — 断开或 500ms 无状态帧；重连后自动恢复")
            self._refresh()

    def set_busy(self, busy: bool):
        if busy != self._ext_busy:
            self._ext_busy = busy
            self._refresh()

    def update_from(self, st):
        """主窗口周期喂当前 RobotState —— **失能闸要用它**。

        ⚠ 离线时主窗口也会喂一次 `None`（照参数页的注释）：别让上一条连接的
        enable 态快照残留着，否则重连后闸门会拿旧状态放行。
        """
        self._st = st
        if st is not None and getattr(st, "enabled", False):
            self.hint_lbl.setText(i18n.tr(
                "⚠ 臂处于使能态 —— 下发需先到 [整机] 页失能（本页不会替你失能）"))
            self.hint_lbl.setVisible(True)
        else:
            self.hint_lbl.setVisible(False)
        self._refresh()

    def _can_run(self) -> bool:
        return bool(self._submit is not None and self._online
                    and not self._busy and not self._ext_busy)

    def _set_status(self, source: str, **fmt) -> None:
        self._status_src = (source, fmt or None)
        self.status.setText(i18n.tr(source, **fmt))

    def _render_dev(self) -> None:
        if self._dev is None:
            self.lbl_dev.setText(i18n.tr("设备当前：—"))
            return
        g, name = self._dev
        self.lbl_dev.setText(i18n.tr(
            "设备当前：({x:+.4f}, {y:+.4f}, {z:+.4f}) = {name}   |g|={mag:.4f}",
            x=g[0], y=g[1], z=g[2], name=i18n.tr(name), mag=_mag(g)))

    def retranslate(self) -> None:
        source, fmt = self._status_src
        self._set_status(source, **(fmt or {}))
        self._render_dev()
        self._update_mag()
        self._refresh()

    def _refresh(self):
        on = self._can_run()
        self.btn_read.setEnabled(on)
        ready = on and self._device_synced
        self.btn_apply.setEnabled(ready)
        self.btn_save.setEnabled(ready)
        for b in self._preset_btns.values():
            b.setEnabled(on)
        self.btn_custom.setEnabled(on)
        for s in self._rpy_spins + self._g_spins:
            s.setEnabled(on)
        if self._submit is not None and self._online and on and not self._device_synced:
            self._set_status("已连接 — 尚未读取设备当前装向，请先 [读当前]；在此之前禁下发")

    def _pre_op(self, what: str) -> bool:
        if self._submit is None:
            self._set_status("未连接")
            return False
        if not self._online:
            self._set_status("离线，忽略操作")
            return False
        if self._busy:
            self._set_status("忙：前一条操作仍在执行，已忽略 {what}", what=what)
            return False
        if self._ext_busy:
            self._set_status("忙：运动/控制命令在途（MainWindow），已忽略本页操作")
            return False
        return True

    def _require_device_sync(self, what: str) -> bool:
        if self._device_synced:
            return True
        QMessageBox.warning(self, i18n.tr("请先读取设备参数"),
                            i18n.tr("{what}\n\n尚未成功 [读当前]，"
                                    "此时下发等于把控件里的默认值盲写进设备。\n"
                                    "请先点 [读当前]。", what=what))
        self._set_status("已拒绝 — 请先 [读当前]")
        return False

    def _confirm_disabled(self, what: str) -> bool:
        """**硬拦**：armed 或状态未知时不发任何帧。与参数页的确认框放行策略不同。"""
        st = self._st
        if st is not None and not getattr(st, "enabled", True):
            return True
        reason = (i18n.tr("臂处于使能态") if st is not None
                  else i18n.tr("状态未知（尚未收到状态帧）—— 状态没到手不等于安全"))
        QMessageBox.warning(
            self, i18n.tr("须先失能"),
            i18n.tr("{what}\n\n{reason}。\n\n"
                    "改 gravity 会让重力前馈当拍阶跃（正装↔侧装 |Δg|=13.87 m/s²，"
                    "J2/J3 上几十 Nm），且三条分量下发非原子（中途模长 13.87、方向偏 45°）。\n"
                    "请先到 [整机] 页失能 —— 本页不会替你失能（那会让你失去保持力矩）。",
                    what=what, reason=reason))
        self._set_status("已拒绝 — 须先失能")
        return False

    def _confirm_magnitude(self, g: Sequence[float]) -> bool:
        m = _mag(g)
        if abs(m - G0) <= G0 * MAG_TOL_REL:
            return True
        return QMessageBox.warning(
            self, i18n.tr("|g| 偏离 9.81"),
            i18n.tr("当前 |g| = {mag:.4f} m/s²，偏离 9.81 超过 {pct:.0%}。\n\n"
                    "常见成因：只改了一个分量（例如正装→侧装时 z 没清零 → "
                    "({x:+.2f},{y:+.2f},{z:+.2f}) 模长 13.87 = 1.41×g）。\n"
                    "确认这是有意为之？",
                    mag=m, pct=MAG_TOL_REL, x=g[0], y=g[1], z=g[2]),
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Ok

    def _start(self, what: str, worker, sig):
        if not self._pre_op(what):
            return
        self._busy = True
        self._set_status("执行中：{what} …", what=what)
        self._refresh()
        self._submit(i18n.tr("安装方向[{what}]", what=what), worker,
                     lambda res: self._unpack(res, what, sig))

    def _unpack(self, res, what, sig):
        self._busy = False
        if res is None or not res.ok:
            err = res.error if res is not None else "未执行"
            self._log(i18n.tr("[ERR] 安装方向[{what}] 失败：{err}", what=what, err=err))
            self._set_status("失败：{err}", err=err)
            sig.emit(None)
            return
        sig.emit(res.value)

    # ================= 读当前 =================
    def _on_read(self):
        self._start(i18n.tr("读当前"), _worker_read, self.sig_read_done)

    def _on_read_done(self, val):
        if val is None:
            self._refresh()
            return
        g = val["gravity"]
        if any(v is None for v in g):
            self._set_status("读回失败 — 固件不支持 0x2C item6？（需 ≥1.5.x）")
            self._refresh()
            return
        self._baseline = list(g)
        self._device_synced = True
        self._set_vector(g)
        name = _label_of(g)
        if name != "(自定义)":
            self._custom = False
            for pname, rpy, vec in PRESETS:
                if pname == name:
                    self._set_rpy(rpy)
                    break
        else:
            self._custom = True
        self._update_mag()
        self._dev = (list(g), name)
        self._render_dev()
        self._set_status("已读取设备当前装向（{name}）", name=i18n.tr(name))
        self._refresh()

    # ================= 下发 =================
    def _on_apply(self):
        if not self._pre_op(i18n.tr("下发安装方向")):
            return
        if not self._require_device_sync(i18n.tr("下发安装方向")):
            return
        if not self._confirm_disabled(i18n.tr("下发安装方向")):
            self._refresh()
            return
        g = self._vector()
        if not self._confirm_magnitude(g):
            self._set_status("已取消 — |g| 偏离未确认")
            self._refresh()
            return
        self._start(i18n.tr("下发安装方向"), _make_apply_worker(g),
                    self.sig_apply_done)

    def _on_apply_done(self, val):
        if val is None:
            self._refresh()
            return
        fails = val["fails"]
        if fails:
            for sub, code in fails:
                self._log(i18n.tr("[ERR] gravity[{sub}] 被拒：{err}",
                                  sub=sub, err=PIO.err_text(code)))
            self._set_status("下发失败：{detail}", detail=i18n.tr("；").join(
                i18n.tr("分量{sub}({err})", sub=sub, err=PIO.err_text(code))
                for sub, code in fails))
            self._refresh()
            return
        back = val["back"]
        if any(v is None for v in back):
            self._set_status("下发后回读失败 —— 不能确认已生效")
            self._refresh()
            return
        wrote = val["wrote"]
        dmax = max(abs(_f32(back[i]) - _f32(wrote[i])) for i in range(3))
        ok_rb = dmax < 1e-4
        mag = _mag(back)
        ok_mag = abs(mag - G0) <= G0 * MAG_TOL_REL
        # G(q) 前后自比：写同值时**不该变**，写不同值时必须变（证明真的进了模型）
        gb, ga = val["gq_before"], val["gq_after"]
        if gb is None or ga is None:
            gq_txt = i18n.tr("G(q)：未取到当前姿态，跳过")
            ok_gq = True
        else:
            changed = max(abs(ga[i] - gb[i]) for i in range(7)) > 1e-6
            expect_change = dmax >= 1e-4 or max(
                abs(_f32(back[i]) - (_f32(self._baseline[i]) if self._baseline else back[i]))
                for i in range(3)) > 1e-4
            ok_gq = (changed == expect_change)
            gq_txt = i18n.tr(
                "G(q)：{changed}（{verdict}）",
                changed=i18n.tr("变了") if changed else i18n.tr("未变"),
                verdict=i18n.tr("符合预期") if ok_gq else i18n.tr("⚠ 与预期不符"))
        self._baseline = list(back)
        self._dev = (list(back), _label_of(back))
        self._render_dev()
        self._set_status("读回差异 {dmax:.2e} {ok_rb}；|g|={mag:.4f} {ok_mag}；{gq}",
                         dmax=dmax,
                         ok_rb="✅" if ok_rb else i18n.tr("❌ 与写入不一致"),
                         mag=mag, ok_mag="✅" if ok_mag else "⚠", gq=gq_txt)
        for line in (ok_rb, ok_mag, ok_gq):
            if not line:
                self._log(i18n.tr("[ERR] 下发后自检未过：{status}",
                                  status=self.status.text()))
                break
        self._refresh()

    # ================= 固化 =================
    def _on_save(self):
        if not self._pre_op(i18n.tr("固化到 Flash")):
            return
        if not self._require_device_sync(i18n.tr("固化到 Flash")):
            return
        if not self._confirm_disabled(i18n.tr("固化到 Flash（0x25）")):
            self._refresh()
            return
        self._start(i18n.tr("固化到 Flash"), lambda arm: PIO.save_params(arm)[0],
                    self.sig_save_done)

    def _on_save_done(self, val):
        if val is None:
            self._refresh()
            return
        if val is True:
            self._set_status("已固化到 Flash（掉电保持）")
        else:
            self._set_status("固化失败：固件拒绝（须失能；0x04=需先 disable）")
            self._log(i18n.tr("[ERR] 0x25 PARAM_SAVE 被拒"))
        self._refresh()


# ================= 后台 worker（在 SDK 所有者线程执行） =================
def _worker_read(arm):
    vals = []
    for sub in (0, 1, 2):
        # ⚠ 2.0 起返回 `Msg` 信封, 取原值走 `.value` (信封本身恒非 None, 故下面那句
        # "取不到帧 -> None" 的判据必须落在 `.value` 上)。
        v = arm.get_ff_scalar(GRAVITY_ITEM, sub).value
        vals.append(None if v is None else float(v))
    return {"gravity": vals}


def _make_apply_worker(g: Sequence[float]):
    """写三条分量 + 回读 + 固件 G(q) 前后自比。返回结构化 dict 给 `_on_apply_done`。"""

    def worker(arm):
        out = {"wrote": [_f32(v) for v in g], "fails": [],
               "back": [None, None, None], "gq_before": None, "gq_after": None}
        q = None
        st = getattr(arm, "state", None)
        if st is not None:
            try:
                q = list(st.q)
            except Exception:      # noqa: BLE001 - 取不到就不做前后自比, 不阻断下发
                q = None
        if q is not None:
            out["gq_before"] = MIO.get_gravity(arm, q)
        for sub in (0, 1, 2):
            ok, code = PIO.set_ff_scalar(arm, GRAVITY_ITEM, sub, float(g[sub]))
            if not ok:
                out["fails"].append((sub, code))
        back = []
        for sub in (0, 1, 2):
            v = arm.get_ff_scalar(GRAVITY_ITEM, sub).value
            back.append(None if v is None else float(v))
        out["back"] = back
        if q is not None:
            out["gq_after"] = MIO.get_gravity(arm, q)
        return out

    return worker
