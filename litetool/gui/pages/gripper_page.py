"""夹爪页 —— LiteGrip 连接、使能、开合/抓取/释放、遥测、标定与设置。

仅 Linux（SocketCAN）。页面自己持有 `GripperWorker`；夹爪的 CAN 链路与机械臂
串口互不相干，所以本页不参与顶栏的运动解锁，也不占用 `SdkWorker` 的队列。
急停/释放是**旁路**零力矩帧，不排队等长 `grasp` 走完。

平台不支持（Windows）或未安装 `litegrip-python` 时，页面保留但连接按钮禁用，
并在页头写明原因 —— 不做成"点下去没反应"。
"""
from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (QComboBox, QFileDialog, QLabel, QLineEdit,
                             QMessageBox, QPlainTextEdit, QPushButton,
                             QVBoxLayout, QWidget)

from litetool import i18n
from litetool.gripper import GripperWorker, list_channels
from litetool.gui.i18n_ui import (TrButton, TrLabel, tr_items, tr_placeholder,
                                  tr_tooltip)
from litetool.gui.pages.common import group, hint, note, row, spin
from litetool.gui.widgets import mono_label

TICK_MS = 100


class GripperPage(QWidget):
    def __init__(self, settings, worker=None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._log_fn = None
        self._busy = False
        self._online = False
        self._worker = worker or GripperWorker(log=self._log)
        self._avail, self._why = self._worker.available()
        self._calib = None

        # ---------------- 连接 / 身份 ----------------
        # 通道默认从内核枚举（/sys/class/net/type == 280）；枚举不到时仍保留 can0，
        # 也允许手动输入（vcan0、驱动改了名字的 can3 等）。
        self.channel = QComboBox()
        self.channel.setEditable(True)
        self.channel.setInsertPolicy(QComboBox.NoInsert)
        self.channel.setFixedWidth(110)
        tr_tooltip(self.channel,
                   "内核枚举到的 CAN 接口；也可以手动输入未列出的名字")
        self.btn_channels = TrButton("刷新")
        tr_tooltip(self.btn_channels, "重新枚举 /sys/class/net 里的 CAN 接口")
        self.btn_channels.clicked.connect(self._refresh_channels)
        self.can_id = spin(1, 127, 8, 1, decimals=0)
        self.mst_id = spin(0, 127, 0, 1, decimals=0)
        tr_tooltip(self.mst_id, "0 = 自动探测；非 0 时作为状态帧的 master ID")
        self.mount = QComboBox()
        tr_items(self.mount, [("出厂（正装）", None), ("正装模板", "normal"),
                              ("反装模板", "reverse")])
        self.calib_path = QLineEdit()
        tr_placeholder(self.calib_path,
                       "可选：标定 JSON（留空则用上面的模板/出厂标定）")
        self.btn_browse = TrButton("浏览…")
        self.btn_browse.clicked.connect(self._pick_calibration)
        self.btn_conn = TrButton("连接")
        self.btn_conn.clicked.connect(self._toggle_connect)
        self.conn_lbl = QLabel("—")
        self.conn_lbl.setStyleSheet("color:#a0a0a0;")

        g_conn = group(
            "连接与身份（更改通道 / CAN ID / MST ID 后需断开重连）",
            row(TrLabel("通道"), self.channel, self.btn_channels,
                TrLabel("CAN ID"), self.can_id,
                TrLabel("MST ID"), self.mst_id,
                TrLabel("安装"), self.mount,
                self.btn_conn),
            row(TrLabel("标定文件"), self.calib_path, self.btn_browse),
            self.conn_lbl,
        )

        # ---------------- 动作 ----------------
        self.btn_enable = TrButton("使能")
        self.btn_enable.clicked.connect(self._toggle_enable)
        self.btn_open = TrButton("张开")
        self.btn_open.clicked.connect(lambda: self._act("张开", self._worker.open_jaws))
        self.btn_close = TrButton("闭合")
        self.btn_close.clicked.connect(lambda: self._act("闭合", self._worker.close_jaws))
        self.force = spin(0.0, 60.0, 20.0, 1.0)
        self.hold = spin(0.5, 60.0, 3.0, 0.5)
        self.btn_grasp = TrButton("抓取")
        self.btn_grasp.clicked.connect(self._on_grasp)
        self.btn_stop = TrButton("停止 / 释放")
        tr_tooltip(
            self.btn_stop,
            "旁路发零力矩帧；若有动作在途，再失能电机以中止它（否则保力循环下一帧\n"
            "就会把力矩写回来），并丢弃排队中的动作。不代替机械臂急停。")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_refresh = TrButton("刷新状态")
        self.btn_refresh.clicked.connect(lambda: self._act("刷新", self._worker.refresh))

        g_act = group(
            "动作",
            row(self.btn_enable, self.btn_open, self.btn_close),
            row(TrLabel("抓取力 (N)"), self.force,
                TrLabel("保持 (s)"), self.hold,
                self.btn_grasp, self.btn_stop),
            row(self.btn_refresh),
            hint("⚠ 夹爪与机械臂共用现场空间：抓取前确认手指路径上没有人。"
                 "「停止 / 释放」会发零力矩帧并中止在途动作，但不是机械臂急停。"),
        )

        # ---------------- 遥测 ----------------
        self.pos_lbl = mono_label(90)
        self.force_lbl = mono_label(90)
        self.tau_lbl = mono_label(90)
        self.temp_lbl = mono_label(130)
        self.err_lbl = mono_label(90)
        self.fresh_lbl = mono_label(150)
        g_tel = group(
            "遥测（10Hz 轮询）",
            row(TrLabel("位置 (mm)"), self.pos_lbl,
                TrLabel("夹持力 (N)"), self.force_lbl,
                TrLabel("力矩 (Nm)"), self.tau_lbl),
            row(TrLabel("温度 mos/coil (°C)"), self.temp_lbl,
                TrLabel("错误码"), self.err_lbl),
            row(TrLabel("新鲜度"), self.fresh_lbl),
        )

        # ---------------- 标定 ----------------
        self.calib_lbl = QLabel("—")
        self.calib_lbl.setStyleSheet("font-family:'DejaVu Sans Mono';")
        self.btn_calib = TrButton("读取标定")
        self.btn_calib.clicked.connect(self._act_calibration)
        self.btn_load = TrButton("加载标定…")
        self.btn_load.clicked.connect(self._load_calibration)
        self.btn_save = TrButton("保存标定…")
        self.btn_save.clicked.connect(self._save_calibration)
        self.btn_zero = TrButton("写零（不可逆）")
        tr_tooltip(self.btn_zero,
                   "把当前编码器角写为电机零位，写入电机 Flash。不可逆。")
        self.btn_zero.clicked.connect(self._on_write_zero)
        g_cal = group(
            "标定",
            self.calib_lbl,
            row(self.btn_calib, self.btn_load, self.btn_save, self.btn_zero),
            note("标定决定行程与开合方向；未标定时 SDK 拒绝一切运动。"
                 "写零会改写电机 Flash，臂/手指需支撑好。"),
        )

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(90)
        self.log_view.setStyleSheet(
            "QPlainTextEdit{background:#1e1e1e;color:#c8c8c8;"
            "font-family:'DejaVu Sans Mono';font-size:11px;}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(g_conn)
        lay.addWidget(g_act)
        lay.addWidget(g_tel)
        lay.addWidget(g_cal)
        lay.addWidget(self.log_view)
        lay.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)
        self._refresh_channels()
        self._refresh()

    # ---------------- 外部 ----------------
    def set_log(self, fn):
        self._log_fn = fn

    def shutdown(self):
        self._timer.stop()
        try:
            self._worker.close()
        except Exception:  # noqa: BLE001 - 退出不该被夹爪卡住
            pass

    def _log(self, msg: str):
        self.log_view.appendPlainText(str(msg))
        if self._log_fn is not None:
            self._log_fn(str(msg))

    # ---------------- 连接 ----------------
    def _refresh_channels(self):
        """重新枚举 CAN 接口；保留用户已经选/手填的通道。

        枚举为空时保留 can0 作为可见的兜底 —— 机器没起 CAN 时，操作员至少能看到
        默认值，而不是一个空下拉框。
        """
        cur = self.channel.currentText().strip()
        found = list_channels()
        self.channel.blockSignals(True)
        self.channel.clear()
        for name in found:
            self.channel.addItem(name)
        if cur and cur not in found:
            self.channel.addItem(cur)
        if self.channel.count() == 0:
            self.channel.addItem("can0")
        idx = self.channel.findText(cur) if cur else 0
        self.channel.setCurrentIndex(idx if idx >= 0 else 0)
        self.channel.blockSignals(False)

    def _toggle_connect(self):
        if self._worker.online:
            self._worker.close()
            self._refresh()
            return
        top = self.channel.currentText().strip() or "can0"
        try:
            self._worker.open(
                channel=top,
                can_id=int(self.can_id.value()),
                mst_id=int(self.mst_id.value()) or None,
                mount=self.mount.currentData(),
                calibration_path=self.calib_path.text().strip() or None,
            )
        except Exception as e:  # noqa: BLE001 - 用户要看到原因
            self._log(i18n.tr("[ERR] 夹爪连接失败: {err}", err=e))
            QMessageBox.critical(self, i18n.tr("夹爪连接失败"),
                                 i18n.safe_detail(e) or i18n.tr("未知错误"))
        self._refresh()

    # ---------------- 动作 ----------------
    def _toggle_enable(self):
        if not self._worker.online:
            return
        enabled = bool(getattr(self._worker.state, "is_enabled", False))
        self._busy = True
        self._refresh()
        if enabled:
            self._worker.disable(cb=self._on_task)
        else:
            self._worker.enable(cb=self._on_task)

    def _act(self, label: str, fn):
        if not self._worker.online:
            self._log(i18n.tr("[WARN] 夹爪未连接"))
            return
        self._busy = True
        self._refresh()
        fn(cb=self._on_task)

    def _act_calibration(self):
        self._act("读取标定", self._worker.calibration)

    def _on_grasp(self):
        force = float(self.force.value())
        hold = float(self.hold.value())
        self._busy = True
        self._refresh()
        self._worker.grasp(force, hold, cb=self._on_task)

    def _on_stop(self):
        ok, why = self._worker.stop_now()
        self._log((i18n.tr("[WARN] 夹爪停止: ") if ok
                   else i18n.tr("[ERR] 夹爪停止未完整生效: ")) + why)

    def _on_write_zero(self):
        if not self._worker.online:
            return
        if QMessageBox.warning(
                self, i18n.tr("确认写零"),
                i18n.tr("写零会把当前编码器角写为电机零位并写入电机 Flash，不可逆。\n"
                        "标定行程保持不变。确认继续？"),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Ok:
            return
        self._busy = True
        self._refresh()
        self._worker.write_zero(cb=self._on_task)

    def _pick_calibration(self):
        path, _ = QFileDialog.getOpenFileName(self, i18n.tr("选择标定文件"), "",
                                              i18n.tr("JSON (*.json);;全部 (*)"))
        if path:
            self.calib_path.setText(path)

    def _load_calibration(self):
        if not self._worker.online:
            return
        path, _ = QFileDialog.getOpenFileName(self, i18n.tr("加载标定文件"), "",
                                              i18n.tr("JSON (*.json);;全部 (*)"))
        if not path:
            return
        self._busy = True
        self._refresh()
        self._worker.load_calibration(path=path, cb=self._on_task)

    def _save_calibration(self):
        if not self._worker.online:
            return
        path, _ = QFileDialog.getSaveFileName(self, i18n.tr("保存标定文件"),
                                              "litegrip_calibration.json",
                                              i18n.tr("JSON (*.json);;全部 (*)"))
        if not path:
            return
        self._busy = True
        self._refresh()
        self._worker.save_calibration(path, cb=self._on_task)

    def _on_task(self, res):
        self._busy = False
        self._log(("[OK] " if res.ok else "[ERR] ") + res.text)
        if res.ok and res.value and isinstance(res.value, dict):
            self._calib = res.value
            self._render_calib()
        self._refresh()

    # ---------------- 轮询 ----------------
    def _render_conn(self, online: bool) -> None:
        self.conn_lbl.setText(i18n.tr("● 已连接") if online
                              else i18n.tr("● 未连接"))
        self.conn_lbl.setStyleSheet(
            "color:#6fdd8b;" if online else "color:#a0a0a0;")
        if not self._avail:
            self.conn_lbl.setText(i18n.tr("● 不可用 — {why}",
                                          why=i18n.tr(self._why)))
            self.conn_lbl.setStyleSheet("color:#d8a13a;")

    def _render_calib(self) -> None:
        v = self._calib
        if v is None:
            self.calib_lbl.setText("—")
            return
        self.calib_lbl.setText(i18n.tr(
            "通道 {channel} · CAN 0x{can_id:02X} · MST {mst} · 方向 {mount} · "
            "行程 {travel:.1f} mm · {state}",
            channel=v['channel'], can_id=int(v['can_id']), mst=v['mst_id'],
            mount=i18n.tr(v['mount'] or "未标定"),
            travel=v['travel_mm'],
            state=i18n.tr("已标定") if v['calibrated'] else i18n.tr("未标定")))

    def retranslate(self) -> None:
        self._render_conn(bool(self._worker.online))
        self._render_calib()
        self._tick()

    def _tick(self):
        online = bool(self._worker.online)
        if online != self._online:
            self._online = online
            self._render_conn(online)
            if not online:
                for lb in (self.pos_lbl, self.force_lbl, self.tau_lbl,
                           self.temp_lbl, self.err_lbl, self.fresh_lbl):
                    lb.setText("—")
        st = self._worker.state
        if st is not None:
            self.pos_lbl.setText(f"{st.position_mm:+.2f}")
            self.force_lbl.setText(f"{st.force_n:+.2f}")
            self.tau_lbl.setText(f"{st.torque_nm:+.3f}")
            self.temp_lbl.setText(f"{st.temperature_mos}/{st.temperature_coil}")
            self.err_lbl.setText(str(st.error_code))
            age = "—" if st.data_age_s is None else f"{st.data_age_s * 1000:.0f} ms"
            self.fresh_lbl.setText(
                i18n.tr("{state} · {age}",
                        state=i18n.tr("新帧") if st.fresh else i18n.tr("缓存"),
                        age=age))
        self._refresh()

    def _refresh(self):
        online = bool(self._worker.online)
        enabled = bool(getattr(self._worker.state, "is_enabled", False)) if online else False
        can = online and not self._busy
        self.btn_conn.setEnabled(self._avail)
        self.btn_conn.setText(i18n.tr("断开") if online else i18n.tr("连接"))
        self.btn_enable.setEnabled(can)
        self.btn_enable.setText(i18n.tr("失能") if enabled else i18n.tr("使能"))
        for b in (self.btn_open, self.btn_close, self.btn_grasp,
                  self.btn_refresh, self.btn_calib, self.btn_load,
                  self.btn_save, self.btn_zero):
            b.setEnabled(can)
        self.btn_stop.setEnabled(online)      # 停止永远比其它动作可达
        self.force.setEnabled(True)
        self.hold.setEnabled(True)
        for w in (self.channel, self.btn_channels, self.can_id, self.mst_id,
                  self.mount, self.calib_path, self.btn_browse):
            w.setEnabled(not online)          # 身份改动要求重新连接
        if not self._avail:
            self.conn_lbl.setText(i18n.tr("● 不可用 — {why}",
                                          why=i18n.tr(self._why)))
            self.conn_lbl.setStyleSheet("color:#d8a13a;")
