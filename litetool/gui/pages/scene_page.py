"""3D 数字孪生页 —— 主窗口内的只读视图，不是独立窗口/进程。

数据流只有一条：`SdkWorker.state`（已有快照）→ `JointSmoother`（100Hz→60Hz
平滑）→ `SceneWidget.set_pose()`。页面不调用任何 SDK 方法，也不碰串口。

PyQt/OpenGL 相关模块在第一次显示时才 import：没打开 3D 的用户不为 PyOpenGL
付启动时间。没有资产/1J 台架/离线时都保留明确的空状态，不显示假姿态。
"""
from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from litetool import i18n
from litetool.gui.i18n_ui import TrButton, TrCheckBox, TrLabel
from litetool.gui.widgets import Banner
from litetool.scene.controller import JointSmoother

RENDER_MS = 16          # 60 Hz 上限
SMOOTH_TAU_S = 0.05


class ScenePage(QWidget):
    def __init__(self, worker, settings, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.settings = settings
        self._online = False
        self._faulted = False
        self._has_state = False
        self._n = 0
        self._seq = None
        self._last_q = None
        self._model = None
        self._view = None
        self._smoother = None
        self._loading = False
        self._placeholder_src = ("连接机械臂后显示 3D 模型", None)
        self._banner_src = None
        self._timer = QTimer(self)
        self._timer.setInterval(RENDER_MS)
        self._timer.timeout.connect(self._render)
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.title = TrLabel("3D 数字孪生")
        self.title.setStyleSheet("font-weight:bold;font-size:14px;")
        self.status = QLabel(i18n.tr("只读 · 等待连接"))
        self.status.setStyleSheet("color:#8a97a4;font-size:12px;")

        self.btn_iso = TrButton("等轴")
        self.btn_front = TrButton("正视")
        self.btn_side = TrButton("侧视")
        self.btn_tool = TrButton("工具")
        self.btn_reset = TrButton("重置")
        for b in (self.btn_iso, self.btn_front, self.btn_side,
                  self.btn_tool, self.btn_reset):
            b.setFixedHeight(26)
        self.btn_iso.clicked.connect(lambda: self._camera("iso"))
        self.btn_front.clicked.connect(lambda: self._camera("front"))
        self.btn_side.clicked.connect(lambda: self._camera("side"))
        self.btn_tool.clicked.connect(lambda: self._camera("tool"))
        self.btn_reset.clicked.connect(self._reset_camera)

        self.cb_grid = TrCheckBox("网格")
        self.cb_axes = TrCheckBox("坐标轴")
        self.cb_grid.setChecked(True)
        self.cb_axes.setChecked(True)
        self.cb_grid.toggled.connect(lambda on: self._toggle_grid(on))
        self.cb_axes.toggled.connect(lambda on: self._toggle_axes(on))

        head = QHBoxLayout()
        head.addWidget(self.title)
        head.addWidget(self.status)
        head.addStretch(1)
        for b in (self.btn_iso, self.btn_front, self.btn_side,
                  self.btn_tool, self.btn_reset):
            head.addWidget(b)
        head.addSpacing(8)
        head.addWidget(self.cb_grid)
        head.addWidget(self.cb_axes)

        self.banner = Banner()
        self.banner.setVisible(False)

        self.placeholder = QLabel(i18n.tr("连接机械臂后显示 3D 模型"))
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setStyleSheet("color:#8a97a4;font-size:13px;")
        self.view_host = QWidget()
        self.view_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._view_lay = QVBoxLayout(self.view_host)
        self._view_lay.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.view_host)
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stack.setMinimumHeight(380)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(head)
        lay.addWidget(self.banner)
        lay.addWidget(self.stack, 1)
        self._set_buttons(False)

    # ------------------------------------------------------------------ 生命周期
    def showEvent(self, ev):  # noqa: N802 - Qt 命名
        super().showEvent(ev)
        self._ensure_scene()
        if self._online:
            self._start()

    def hideEvent(self, ev):  # noqa: N802 - Qt 命名
        self._timer.stop()
        super().hideEvent(ev)

    def closeEvent(self, ev):  # noqa: N802 - Qt 命名
        self._timer.stop()
        if self._view is not None:
            self._view.shutdown()
        super().closeEvent(ev)

    def set_online(self, onl: bool):
        self._online = bool(onl)
        if not self._online:
            self._timer.stop()
            if self._has_state and self._view is not None:
                self._set_banner("未连接 — 3D 画面冻结在最后一帧")
            elif self._n != 1:
                self._clear_banner()
                self._show_placeholder("未连接 — 连接机械臂后显示实时姿态")
            self.status.setText(i18n.tr("只读 · 离线"))
            return
        if self._view is None and self.worker.state is None:
            self._set_info("已连接 — 等待状态帧")
        elif not self._faulted:
            self._clear_banner()
        self.status.setText(self._status_text())
        if self.isVisible():
            self._ensure_scene()
            self._start()

    def update_from(self, st):
        """MainWindow 的 20Hz 轮询调用；只更新空状态/横幅，不做渲染。"""
        if st is None:
            if self._has_state and self._view is not None:
                self._set_banner("未连接 — 3D 画面冻结在最后一帧")
            elif self._online:
                self._set_info("已连接 — 等待状态帧")
            elif self._n != 1:
                self._clear_banner()
                self._show_placeholder("未连接 — 连接机械臂后显示实时姿态")
            return
        self._has_state = True
        n = int(getattr(st, "n", 0) or 0)
        if n != self._n:
            self._n = n
            if n == 1:
                self._timer.stop()
                self._show_placeholder(
                    "台架 1J — 没有 7 轴 URDF 模型，3D 视图不适用。\n"
                    "请使用总览/关节页查看 1 轴状态。")
                self.status.setText(i18n.tr("只读 · 台架 1J"))
            elif n == 7:
                if self._view is not None:
                    self.stack.setCurrentWidget(self.view_host)
                    self._set_buttons(True)
                    if self.isVisible() and self._online:
                        self._start()
                elif self.isVisible() and self._online:
                    self._ensure_scene()
        faulted = bool(getattr(st, "faulted", False)) or \
            (getattr(st, "mode_name", "") == "EMERGENCY")
        self._faulted = faulted
        if faulted:
            self._set_banner("FAULT / 急停锁存 — 画面冻结在最后一帧")
        elif self._online:
            self._clear_banner()

    # ------------------------------------------------------------------ 渲染
    def _render(self):
        if self._view is None or not self._online or self._smoother is None:
            return
        st = self.worker.state
        if st is None:
            return
        q = getattr(st, "q", None)
        if q is None or len(q) != self._smoother.n:
            return
        qv = np.asarray(q, dtype=float)
        changed = (self._last_q is None or
                   float(np.max(np.abs(qv - self._last_q))) > 1e-5)
        if changed:
            self._last_q = qv.copy()
            self._seq = getattr(st, "seq", None)
            self._smoother.set_target(qv)
        # 静止且已收敛：不重绘。相机拖动时也暂停姿态刷新 —— 让鼠标事件
        # 独占事件循环，软件渲染下拖动才跟手。
        if (not changed and self._smoother.settled) or self._view._interacting:
            return
        out = self._smoother.sample()
        if out is not None:
            self._view.set_pose(out)

    def _start(self):
        if self._view is not None and self._online and not self._timer.isActive():
            self._timer.start()
            self._render()

    # ------------------------------------------------------------------ 构建
    def _ensure_scene(self):
        if self._view is not None or self._loading or self._n == 1:
            return
        if not self._online:
            self._show_placeholder("未连接 — 连接机械臂后显示实时姿态")
            return
        self._loading = True
        self._show_placeholder("正在加载 3D 模型…")
        QTimer.singleShot(0, self._build_scene)

    def _build_scene(self):
        if self._view is not None:
            self._loading = False
            return
        if self._n == 1:
            self._loading = False
            self._show_placeholder(
                "台架 1J — 没有 7 轴 URDF 模型，3D 视图不适用。\n"
                "请使用总览/关节页查看 1 轴状态。")
            return
        try:
            from litetool.scene.urdf_model import load_default_model
            model = load_default_model(lod=bool(getattr(self.settings, "scene_lod", True)))
        except Exception as e:  # noqa: BLE001 - 资产坏了显示空状态，不能拖垮主窗口
            self._loading = False
            self._show_placeholder("3D 模型加载失败：{err}",
                                   err=i18n.safe_detail(e))
            return
        if model is None:
            self._loading = False
            self._show_placeholder(
                "未找到 3D 模型资产（assets/description）。\n"
                "源码运行请确认仓库包含该目录；冻结包请重新打包。")
            return
        try:
            from litetool.scene.view import SceneWidget
            view = SceneWidget(model)
        except Exception as e:  # noqa: BLE001 - 无 OpenGL/驱动异常时给可读提示
            self._loading = False
            self._show_placeholder("3D 视图初始化失败（OpenGL）：{err}",
                                   err=i18n.safe_detail(e))
            return

        self._model = model
        self._view = view
        self._smoother = JointSmoother(model.n_joints, tau_s=SMOOTH_TAU_S)
        self._view_lay.addWidget(view)
        self.stack.setCurrentWidget(self.view_host)
        self._set_buttons(True)
        view.set_grid_visible(self.cb_grid.isChecked())
        view.set_axes_visible(self.cb_axes.isChecked())
        self.status.setText(self._status_text())
        self._loading = False
        st = self.worker.state
        if st is not None and getattr(st, "q", None) is not None \
                and len(st.q) == model.n_joints:
            self._smoother.reset(st.q)
            view.set_pose(st.q)
        if self._online:
            self._start()

    def _show_placeholder(self, source: str, **fmt):
        self._placeholder_src = (source, fmt or None)
        self.placeholder.setText(i18n.tr(source, **fmt))
        self.stack.setCurrentWidget(self.placeholder)
        self._set_buttons(False)

    # ------------------------------------------------------------------ 控件
    def _set_buttons(self, on: bool):
        for b in (self.btn_iso, self.btn_front, self.btn_side,
                  self.btn_tool, self.btn_reset, self.cb_grid, self.cb_axes):
            b.setEnabled(bool(on))

    def _camera(self, name: str):
        if self._view is not None:
            self._view.camera_preset(name)

    def _reset_camera(self):
        if self._view is not None:
            st = self.worker.state
            self._view.frame_model(st.q if st is not None else None)

    def _toggle_grid(self, on: bool):
        if self._view is not None:
            self._view.set_grid_visible(on)

    def _toggle_axes(self, on: bool):
        if self._view is not None:
            self._view.set_axes_visible(on)

    def _set_banner(self, source: str):
        self._banner_src = ("warn", source)
        self.banner.set_warn(i18n.tr(source))
        self.banner.setVisible(True)

    def _set_info(self, source: str):
        self._banner_src = ("ok", source)
        self.banner.set_ok(i18n.tr(source))
        self.banner.setVisible(True)

    def _status_text(self) -> str:
        if self._view is not None:
            return i18n.tr("只读 · {n}J · {k}k 三角形",
                           n=self._view.model.n_joints,
                           k=self._view.triangle_count // 1000)
        return (i18n.tr("只读 · 在线，准备加载模型") if self._online
                else i18n.tr("只读 · 离线"))

    def _clear_banner(self):
        self._banner_src = None
        self.banner.setText("")
        self.banner.setVisible(False)

    def retranslate(self):
        self.status.setText(self._status_text())
        source, fmt = self._placeholder_src
        self.placeholder.setText(i18n.tr(source, **(fmt or {})))
        if self._banner_src is not None:
            kind, text = self._banner_src
            (self.banner.set_warn if kind == "warn" else self.banner.set_ok)(i18n.tr(text))
