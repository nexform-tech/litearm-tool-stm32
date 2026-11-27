"""主窗口 —— 左侧分组导航 + 常驻状态条/急停 + 底部日志。

职责分工
--------
- **展示/取值**：各页面（`litetool.gui.pages.*`）只管界面，发信号上来。
- **命令收口**：本窗口是唯一往 `SdkWorker` 投任务的地方（`_submit`），于是
  运动解锁、Δq 确认、忙态互斥、急停后重新锁定这些**跨页面**约束只有一个实现点。
- **串口所有权**：全部 SDK 调用都在 `SdkWorker` 的所有者线程上跑；本窗口从不
  直接读写 `Arm`（只读几个缓存属性如 `n`、`online`、`zero_g_active`）。
"""
from __future__ import annotations

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
                             QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QPushButton, QScrollArea, QSplitter,
                             QStackedWidget, QVBoxLayout, QWidget)

import litearm as pa

from litetool import checks
from litetool.diagnostics import build_diag_package, save_diag_package
from litetool import ports as ports_mod
from litetool.gui.bridge import GuiBridge
from litetool.gui.pages.capture_page import CapturePage
from litetool.gui.pages.cart_page import CartPage
from litetool.gui.pages.diag_page import DiagPage
from litetool.gui.pages.fault_page import FaultPage
from litetool.gui.pages.guide_page import TuningGuidePage
from litetool.gui.pages.installation_page import InstallationPage
from litetool.gui.pages.joint_page import JointPage
from litetool.gui.pages.machine_page import MachinePage
from litetool.gui.pages.overview_page import OverviewPage
from litetool.gui.pages.params_page import ParamsPage
from litetool.gui.pages.zerog_page import ZeroGPage
from litetool.gui.widgets import LogPanel, NavList, StatusStrip
from litetool.sdk_worker import SdkWorker, exit_zero_g_and_hold

TICK_MS = 50          # 20Hz：状态条/表格刷新
PLOT_MS = 33          # 30Hz：曲线重绘
OFFLINE_TEXT = "● 离线"
ONLINE_TEXT = "● 在线"


class MainWindow(QMainWindow):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._armed = False
        self._fault_blocked = False
        self._n = 0
        self._connected = False
        self._log_tail: list = []       # 诊断包用：最近 200 行
        self._last_error = None         # 最近一次失败（SDK ErrorText）
        self._fault_snapshot: set = set()   # 已记录过的 (轴, 原因)，用于事件去重
        self._last_fault_bits = 0           # 上次查询时的 joint_fault 位图
        self._fault_query_inflight = False  # 防止同一故障重复查询
        self._fault_detail = None           # 最近一次 0x51 应答

        self.bridge = GuiBridge()
        self.worker = SdkWorker(
            log=lambda m: self.bridge.sig_log.emit(m),
            on_online=lambda ok, why: self.bridge.sig_online.emit(ok, why),
            on_task=lambda res: self.bridge.sig_task.emit(res, None),
            plot_window_s=settings.plot_window_s,
        )

        self._build_ui()
        self._wire()
        self._refresh_ports()
        self._apply_online(False, "未连接")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)
        self._ptimer = QTimer(self)
        self._ptimer.timeout.connect(self._tick_plot)
        self._ptimer.start(PLOT_MS)

        self._log("[INFO] LiteArm Tool STM32 —— 交互层经 litearm；"
                  "硬防护权威仍在固件")

    # ================= 界面 =================
    def _build_ui(self):
        self.setWindowTitle("LiteArm Tool STM32")

        # ---- 顶栏：串口 / 连接 / 解锁 / 急停 ----
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 4, 8, 4)
        bl.addWidget(QLabel("串口:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(300)
        bl.addWidget(self.combo)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_ports)
        bl.addWidget(btn_refresh)
        self.btn_conn = QPushButton("连接")
        self.btn_conn.clicked.connect(self._toggle_connect)
        bl.addWidget(self.btn_conn)
        self.dot = QLabel(OFFLINE_TEXT)
        self.dot.setStyleSheet("color:#b0b0b0;font-weight:bold;")
        bl.addWidget(self.dot)
        self.fw_lbl = QLabel("固件: —")
        bl.addWidget(self.fw_lbl)
        bl.addSpacing(12)
        self.unlock_cb = QCheckBox("我已确认机械臂周围无障碍、急停可及")
        self.unlock_cb.setToolTip(
            "运动类页面（整机的回零 / 关节 / 笛卡尔 / 零重力）在此勾选前一律锁定。\n"
            "断线、急停、FAULT、复位会自动重新锁定。")
        self.unlock_cb.toggled.connect(self._on_unlock)
        bl.addWidget(self.unlock_cb)
        bl.addStretch(1)
        self.btn_estop = QPushButton("⛔ 急停")
        self.btn_estop.setFixedSize(96, 40)
        self.btn_estop.setStyleSheet(
            "QPushButton{background:#b33a3a;color:white;font-weight:bold;"
            "font-size:16px;border-radius:4px;}"
            "QPushButton:pressed{background:#8a2a2a;}")
        self.btn_estop.clicked.connect(self._emergency)
        bl.addWidget(self.btn_estop)
        # 急停结果必须留在**显眼处**：日志会滚，现场用户只看显眼处
        self.estop_lbl = QLabel("")
        self.estop_lbl.setStyleSheet("color:#ff6b6b;font-weight:bold;")
        bl.addWidget(self.estop_lbl)

        # 最近一次失败的码 + 标题。点一下复制诊断包（白名单 JSON）。
        self.err_btn = QPushButton("")
        self.err_btn.setVisible(False)
        self.err_btn.setToolTip("点击复制诊断包")
        self.err_btn.setStyleSheet(
            "QPushButton{color:#ffb454;background:transparent;"
            "border:1px solid #ffb454;border-radius:4px;padding:4px 8px;}"
            "QPushButton:hover{background:#3a2f1a;}")
        self.err_btn.clicked.connect(self._copy_diagnostics)
        bl.addWidget(self.err_btn)

        # ---- 常驻状态条 ----
        self.strip = StatusStrip()

        # ---- 左侧导航 + 页面栈 ----
        self.nav = NavList()
        self.stack = QStackedWidget()
        self.pages = {}
        self.scrolls = {}
        self._add_page("overview", "总览", "状态表 + 100Hz 曲线",
                       OverviewPage(self._settings))
        self._add_page("capture", "采集", "固件 300Hz 控制拍采集与导出", CapturePage())
        self._add_page("machine", "整机", "使能/复位/清故障/回零/限速/park",
                       MachinePage())
        self._add_page("fault", "故障", "当前故障/原因/处置/事件历史/诊断包",
                       FaultPage())
        self._add_page("joint", "关节", "movej / move_js / move_mit",
                       JointPage(self._settings))
        self._add_page("cart", "笛卡尔", "get_tcp / ik / move_p",
                       CartPage(self._settings))
        self._add_page("zerog", "零重力", "拖动示教（保活由 SDK 维持）", ZeroGPage())
        self._add_page("params", "参数表", "关节/前馈参数读写与批量导入导出",
                       ParamsPage())
        self._add_page("guide", "调参指南", "公式 / 症状速查 / 逐参数详解",
                       TuningGuidePage())
        self._add_page("diag", "诊断", "KIN_BENCH / 启动原因 / 链路计数", DiagPage())
        self._add_page("install", "安装方向",
                       "gravity 向量 (0x28 item6) —— 正装/侧装/倒装",
                       InstallationPage())
        self.nav.select("overview")

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        body_lay.addWidget(self.nav)
        body_lay.addWidget(self.stack, 1)

        # ---- 日志（可折叠高度）----
        self.log_panel = LogPanel()
        split = QSplitter(Qt.Vertical)
        split.addWidget(body)
        split.addWidget(self.log_panel)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 1)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)
        lay.addWidget(self.strip)
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self.resize(1280, 820)

    def _add_page(self, key: str, title: str, tip: str, page):
        """按导航分组把页面挂上去。分组由 `_GROUPS` 决定，顺序即页面顺序。

        每页套一层 `QScrollArea`：`QStackedWidget` 的最小高度取**所有页的 max**，
        一页撑高就会把整个窗口顶上去（参数表/采集页在窄屏上本来就要滚动）。
        """
        group = self._group_for(key)
        self.nav.add_page(group, key, title, tip)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        self.pages[key] = page
        self.scrolls[key] = scroll
        self.stack.addWidget(scroll)

    def current_page(self):
        """当前显示页面（`stack.currentWidget()` 是外壳 QScrollArea）。"""
        return self.stack.currentWidget().widget()

    _GROUPS = {"监视": ("overview", "capture"),
               "操作": ("machine", "fault", "joint", "cart", "zerog"),
               # ⚠ 新页 key 必须登记在这里: `_group_for` 用的是无默认值的 next(),
               # 漏登记会在 __init__ 期间抛 StopIteration -> 崩启动。
               "参数": ("params", "install", "guide", "diag")}

    def _group_for(self, key: str):
        title = next(t for t, keys in self._GROUPS.items() if key in keys)
        for i in range(self.nav.topLevelItemCount()):
            it = self.nav.topLevelItem(i)
            if it.text(0) == title:
                return it
        return self.nav.add_group(title)

    def _wire(self):
        self.nav.navigated.connect(self._on_nav)
        self.bridge.sig_log.connect(self.log_panel.append_line)
        self.bridge.sig_task.connect(self._on_task)
        self.bridge.sig_online.connect(self._on_online)

        m, j, c, z = (self.pages["machine"], self.pages["joint"],
                      self.pages["cart"], self.pages["zerog"])
        m.cmd.connect(self._on_ctrl_cmd)
        m.home_req.connect(lambda: self._on_ctrl_cmd("home"))
        m.set_speed.connect(self._on_set_speed)
        m.park_req.connect(lambda: self._submit("park", lambda arm: arm.park(),
                                                self._after_simple))
        m.status_now.connect(self._on_status_now)
        self.pages["fault"].cmd.connect(self._on_ctrl_cmd)
        self.pages["fault"].diag_req.connect(self._copy_diagnostics)
        j.movej.connect(self._on_movej)
        j.move_js.connect(self._on_move_js)
        j.mit_one.connect(self._on_mit_one)
        j.mit_all.connect(self._on_mit_all)
        c.tcp_req.connect(self._on_get_tcp)
        c.ik_req.connect(self._on_ik)
        c.movep.connect(self._on_movep)
        z.zg.connect(self._on_zero_g)
        self.pages["diag"].bench_req.connect(self._on_bench)
        self.pages["params"].set_log(self._log)
        self.pages["params"].set_submit(self._submit)
        self.pages["params"].show_guide.connect(self._on_guide)
        self.pages["capture"].set_submit(self._submit)
        self.pages["install"].set_log(self._log)
        self.pages["install"].set_submit(self._submit)
        self.nav.navigated.connect(self._on_page_changed)

    def _on_nav(self, key: str):
        scroll = self.scrolls.get(key)
        if scroll is not None:
            self.stack.setCurrentWidget(scroll)

    def _on_page_changed(self, key: str):
        if key == "overview":
            self.pages["overview"].clear_plot()

    def _on_guide(self, key: str):
        self.nav.select("guide")
        self._on_nav("guide")
        self.pages["guide"].reveal(key)

    # ================= 日志 / 任务 =================
    def _log(self, msg: str):
        self._log_tail.append(str(msg))
        if len(self._log_tail) > 200:
            del self._log_tail[:-200]
        self.bridge.sig_log.emit(msg)

    def _submit(self, name: str, fn, on_done=None):
        """把 `fn(arm)` 投到 SDK 所有者线程；`on_done(TaskResult)` 回到 GUI 主线程。"""
        self.worker.submit(name, fn,
                           lambda res: self.bridge.sig_task.emit(res, on_done))

    def _on_task(self, res, cb):
        if res is None:
            return
        self._log(f"[{'OK' if res.ok else 'ERR'}] {res.text}")
        if not res.ok:
            try:
                self._last_error = pa.describe_exc(res.error)
                self.err_btn.setText(f"[{self._last_error.code}] {self._last_error.title}")
                self.err_btn.setVisible(True)
            except Exception:  # noqa: BLE001 - 老 SDK 无 describe_exc 时降级
                self._last_error = None
        if cb is not None:
            cb(res)
        self._apply_busy()

    def _copy_diagnostics(self):
        """复制诊断包到剪贴板，同时写 ~/litearm-diag-<时间>.json。"""
        try:
            pkg = build_diag_package(
                firmware=self.worker.firmware,
                n_joints=self.worker.n_joints,
                state=self.worker.state,
                error_text=self._last_error,
                drops=self.worker.drops,
                log_tail=self._log_tail,
            )
            path = save_diag_package(pkg)
            import json
            QApplication.clipboard().setText(
                json.dumps(pkg, ensure_ascii=False, indent=2))
            self._log(f"[OK] 诊断包已复制并保存: {path}")
        except Exception as e:  # noqa: BLE001 - 导出失败不能拖垮界面
            self._log(f"[ERR] 诊断包导出失败: {e}")

    def _after_simple(self, res):
        pass

    def _after_move(self, res):
        if res.ok:
            self._log("[OK] 已到位")

    # ================= 串口 =================
    def _refresh_ports(self):
        cur = self.combo.currentData()
        self.combo.clear()
        for r in ports_mod.find_ports():
            self.combo.addItem(r["description"], r["device"])
        if cur:
            i = self.combo.findData(cur)
            if i >= 0:
                self.combo.setCurrentIndex(i)

    def _current_device(self):
        return self.combo.currentData()

    def _toggle_connect(self):
        if self._connected:
            self._disconnect()
            return
        port = self._current_device()
        if not port:
            QMessageBox.warning(self, "无可选串口", "未发现串口设备，请检查 USB 连接。")
            return
        self.btn_conn.setEnabled(False)
        try:
            self.worker.open(port)
        except Exception as e:  # noqa: BLE001 - SDK 的连接期异常都在这提示
            self._log(f"[ERR] 连接失败: {e}")
            QMessageBox.critical(self, "连接失败", str(e))
            self._apply_online(False, str(e))
        finally:
            self.btn_conn.setEnabled(True)

    def _disconnect(self):
        self.worker.close()
        self._apply_online(False, "已断开")

    def _on_online(self, ok: bool, why: str):
        self._apply_online(ok, why)

    def _apply_online(self, onl: bool, why: str = ""):
        self._connected = onl
        self.btn_conn.setText("断开" if onl else "连接")
        self.dot.setText(ONLINE_TEXT if onl else OFFLINE_TEXT)
        self.dot.setStyleSheet(
            f"color:{'#6fdd8b' if onl else '#b0b0b0'};font-weight:bold;")
        self.fw_lbl.setText(f"固件: {self.worker.firmware}" if onl else "固件: —")
        if not onl:
            self.strip.reset()
            # 断线必须回到锁定态 —— 否则重连后第一下手就是未确认的运动
            self._relock("链路断开")
        for page in self.pages.values():
            if hasattr(page, "set_online"):
                page.set_online(onl)
        # 导出上下文跟着连接走；断线后保留最后已知的固件版本（已读回的数据仍可导出）。
        self.pages["overview"].set_context(self.worker.firmware)
        self.pages["capture"].set_firmware(self.worker.firmware)
        self._apply_busy()

    # ================= 运动解锁（全局一把） =================
    def _on_unlock(self, checked: bool):
        if checked and not self._connected:
            self._log("[WARN] 未连接，解锁无效")
            self.unlock_cb.setChecked(False)
            return
        self._set_armed(bool(checked))
        self._log("[WARN] 运动控制已解锁" if checked else "[INFO] 运动控制已锁定")

    def _set_armed(self, on: bool):
        self._armed = on
        for key in ("machine", "joint", "cart", "zerog"):
            page = self.pages[key]
            page.set_fault_blocked(self._fault_blocked)
            page.set_armed(on)

    def _relock(self, reason: str):
        was = self.unlock_cb.isChecked()
        if was:
            self.unlock_cb.blockSignals(True)
            self.unlock_cb.setChecked(False)
            self.unlock_cb.blockSignals(False)
        self._set_armed(False)
        if reason and was:          # 没解锁过就别报"已锁定"——启动那一下会误导
            self._log(f"[WARN] 运动控制已锁定 — {reason}")

    # ================= 运动闸门（唯一收口） =================
    def _motion_denied(self, op: str) -> bool:
        """能不能发这条运动命令；不能则记日志并返回 True。

        ⚠ 各页按钮的 `setEnabled(False)` **只是 UX，不是安全边界**。任何能到达
        处理函数的路径都必须在这里被挡住：代码里直接 emit、将来某页漏禁一个控件、
        快捷键、某个 `_refresh()` 分支写错。守卫只做在控件状态上，就等于没有守卫
        —— 本仓 2026-09-13 评审的"新增守卫是死代码"是同一类问题。
        """
        if not self._connected:
            self._log(f"[WARN] 拒绝 {op} — 未连接")
            return True
        if self._fault_blocked:
            self._log(f"[WARN] 拒绝 {op} — FAULT/急停锁存中，先 [清故障] 或 [复位]")
            return True
        if not self._armed:
            self._log(f"[WARN] 拒绝 {op} — 运动未解锁（先勾选顶栏的确认项）")
            return True
        return False

    # ================= 急停 =================
    def _emergency(self):
        """常驻急停：**插队**写帧，不排队、不等 ACK。

        只写不读，故不会被在途的长命令（如十几秒的 movej）挡住；也因此**不能**
        声称"已失能" —— 帧出去了不等于固件已执行。文案必须如实区分这两种情形。
        """
        try:
            ok, why = self.worker.emergency_now()
        except Exception as e:  # noqa: BLE001 - 连异常也必须走"未发出"分支
            ok, why = False, str(e)
        # 收掉零重力保活 + 丢弃排队任务 —— 急停的语义是"停下"，不是"先做完手上的"
        dropped = self.worker.drop_pending()
        zg_err = self.worker.stop_zero_g_now()
        self._relock("急停")
        if dropped:
            self._log(f"[WARN] 急停：已丢弃 {dropped} 条排队中的命令")
        if zg_err:
            self._log(f"[WARN] 急停：零重力会话未能正常收尾（{zg_err}）")
        if ok:
            self.estop_lbl.setText("急停帧已发出 — 请目视确认臂已停止")
            self.estop_lbl.setStyleSheet("color:#ffd166;font-weight:bold;")
            self._log("[WARN] 急停帧已发出 —— 请目视确认臂已停止（帧发出≠固件已执行）")
        else:
            self.estop_lbl.setText("⚠ 急停未发出 — 请立即用硬件急停/断电")
            self.estop_lbl.setStyleSheet("color:#ff6b6b;font-weight:bold;")
            self._log(f"[ERR] 急停未发出（{why}）—— 请立即用硬件急停/断电")

    # ================= 周期刷新 =================
    def _tick(self):
        st = self.worker.state
        if st is not None and st.n != self._n:
            self._n = st.n
            self.pages["overview"].set_joints(st.n)
            self.pages["joint"].set_joints(st.n)
            self._log(f"[INFO] 识别到 {st.n} 个关节")

        fps = self.worker.model.rate()
        drops = self.worker.drops
        self.strip.update_from(st, drops, fps)

        self.pages["overview"].update_from(st)
        self.pages["machine"].update_from(st)
        self.pages["machine"].set_metrics(drops, fps, self.worker.last_reset_reason)
        # 离线时也喂一次 None：让参数页/安装方向页丢掉 enable 态的旧快照
        # （安装方向页的"须先失能"硬拦依赖它 —— 旧快照会拿过期的 enabled 放行）
        self.pages["params"].update_from(st)
        self.pages["install"].update_from(st)
        if st is not None:
            self.pages["cart"].set_seed_q(st.q)
            self.pages["joint"].fill_from(st)
        self._sync_fault_detail(st)
        self.pages["fault"].update_from(st, self._fault_detail)
        # 事件历史：只记**新出现**的 (轴, 原因)；清故障后快照随之清空
        detail = self._fault_detail
        cur = set(getattr(detail, "fault_reasons", []) or []) if detail else \
            set(getattr(st, "fault_reasons", []) or []) if st is not None else set()
        for a, r in sorted(cur - self._fault_snapshot):
            try:
                title = pa.describe_fault(r).title
            except Exception:  # noqa: BLE001
                title = f"原因 {r}"
            self.pages["fault"].add_event(f"J{a + 1} {title}")
        self._fault_snapshot = cur
        self.pages["diag"].set_metrics(
            drops=drops, fps=fps,
            firmware=self.worker.firmware,
            n_joints=self.worker.n_joints,
            reset_reason=self.worker.last_reset_reason,
            fault=self._fault_summary(st) if st is not None else "—")

        # 故障/急停一旦出现就收回解锁（切页/等待都不该让旧解锁态残留）
        faulted = bool(st is not None and st.faulted)
        if faulted != self._fault_blocked:
            self._fault_blocked = faulted
            for key in ("joint", "cart", "zerog"):
                self.pages[key].set_fault_blocked(faulted)
            self._set_armed(self._armed)
            if faulted and self._armed:
                self._relock("检测到 FAULT/急停锁存")
            elif faulted:
                self._log(f"[WARN] 故障: {self._fault_summary(st) or st.fault_detail}")
            d = self._fault_detail
            pairs = list(getattr(d, "fault_reasons", []) or []) if d else \
                list(getattr(st, "fault_reasons", []) or [])
            if faulted and pairs:
                a, r = pairs[0]
                try:
                    t = pa.describe_fault(r)
                    self._last_error = t
                    self.err_btn.setText(f"[{t.code}] J{a + 1} {t.title}")
                    self.err_btn.setVisible(True)
                except Exception:  # noqa: BLE001 - 老 SDK 无 describe_fault
                    pass

        self._sync_zero_g(st)
        self._apply_busy()

    def _sync_zero_g(self, st):
        """零重力按钮以**实际**状态为准（固件可能因看门狗/急停自行退出）。"""
        arm = self.worker.arm
        if arm is None:
            # 断线 = 会话已随链路消失。不清的话页面会一直显示"拖动中"，
            # 与实际相反（同类问题：断线后回显陈旧遥测）。
            self.pages["zerog"].set_state(False, None)
            return
        active = bool(getattr(arm, "zero_g_active", False))
        err = getattr(arm, "zero_g_error", None)
        self.pages["zerog"].set_state(active, err)

    def _apply_busy(self):
        busy = self.worker.busy
        for key in ("machine", "joint", "cart", "zerog", "capture", "diag"):
            page = self.pages[key]
            if hasattr(page, "set_busy"):
                page.set_busy(busy)
        self.pages["params"].set_busy(busy)
        self.pages["install"].set_busy(busy)

    def _tick_plot(self):
        self.pages["overview"].refresh_plot(self.worker.model)

    # ================= 整机命令 =================
    def _on_ctrl_cmd(self, name: str):
        if name == "home":
            if self._motion_denied("回零 home"):
                return
            if not self._confirm_home():
                return
            self._submit("回零 home", lambda arm: arm.home(), self._after_move)
        elif name == "clear_faults":
            if not self._confirm_clear_faults():
                return
            self._submit("清故障 clear_faults",
                         lambda arm: arm.clear_faults(), self._after_simple)
        elif name == "reset":
            if not self._confirm_reset():
                return
            self._submit("复位 reset", lambda arm: arm.reset(), self._after_reset)
        elif name == "enable":
            self._submit("使能 enable", lambda arm: arm.enable(), self._after_simple)
        elif name == "disable":
            self._submit("失能 disable", lambda arm: arm.disable(), self._after_simple)

    def _after_reset(self, res):
        if res.ok:
            # 复位退出 EMERGENCY 后必须重新锁定：旧解锁态不该跨过急停继续有效
            self._relock("已复位")

    def _confirm_home(self) -> bool:
        cur = ""
        st = self.worker.state
        if st is not None and st.joints:
            cur = "\n\n当前各轴: " + "  ".join(f"{v:+.3f}" for v in st.q)
        return QMessageBox.question(
            self, "确认回零 home",
            "各臂轴将回到 URDF 零位（固件把速度写死为 0.10 的低速）。" + cur +
            "\n\n确认下发？",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel) == QMessageBox.Ok

    def _sync_fault_detail(self, st):
        """[1.12.3] 状态帧 bit11 -> 按需查询 `GET_FAULT 0x51`。

        只在 `joint_fault` 位图变化时查一次；正常运行时零往返。
        旧固件没有 bit11，直接保持"原因不可知"。
        """
        if st is None:
            return
        jf = int(getattr(st, "joint_fault", 0) or 0)
        if not getattr(st, "fault_detail_available", False):
            self._fault_detail = None
            self._last_fault_bits = jf
            return
        if jf == 0:
            self._fault_detail = None
            self._last_fault_bits = 0
            return
        if jf == self._last_fault_bits or self._fault_query_inflight:
            return
        self._last_fault_bits = jf
        self._fault_query_inflight = True
        self._submit("读故障详情", lambda arm: arm.get_fault_detail(),
                     self._on_fault_detail)

    def _on_fault_detail(self, res):
        self._fault_query_inflight = False
        if res.ok:
            self._fault_detail = res.value
            self.pages["fault"].update_from(self.worker.state, self._fault_detail)
        else:
            self._log(f"[WARN] 故障详情不可用: {res.text}")

    def _fault_summary(self, st=None) -> str:
        """故障轴 + 原因，例 `J4: CAN 反馈丢失`。

        优先用 0x51 查询结果；没有时回退到状态帧自带的 `fault_reason`
        （1.12.2）或只给轴号（更老固件）。
        """
        d = self._fault_detail
        pairs = list(getattr(d, "fault_reasons", []) or []) if d else []
        if not pairs:
            st = st if st is not None else self.worker.state
            pairs = list(getattr(st, "fault_reasons", []) or []) if st else []
        parts = []
        for a, r in pairs:
            try:
                parts.append(f"J{a + 1}: {pa.describe_fault(r).title}")
            except Exception:  # noqa: BLE001
                parts.append(f"J{a + 1}: 原因 {r}")
        return "；".join(parts)

    def _confirm_clear_faults(self) -> bool:
        st = self.worker.state
        axes = ""
        if st is not None and st.joint_fault:
            summary = self._fault_summary(st)
            axes = "\n\n将被恢复出力的轴: " + (summary.replace("；", "、")
                                               or "、".join(
                                                   f"J{a + 1}" for a in st.fault_axes))
        return QMessageBox.question(
            self, "确认清故障 clear_faults",
            "清除故障锁存。若臂处于使能态，被锁轴会重新出力。" + axes +
            "\n\n确认下发？",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel) == QMessageBox.Ok

    def _confirm_reset(self) -> bool:
        return QMessageBox.question(
            self, "确认复位 reset",
            "复位会清除故障并退出急停锁存 —— 之后固件不再阻止运动。\n\n确认下发？",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel) == QMessageBox.Ok

    def _on_set_speed(self, percent: int):
        self._submit(f"全局限速 {percent}%",
                     lambda arm: arm.set_speed(int(percent)), self._after_simple)

    def _on_status_now(self):
        def done(res):
            if res.ok:
                self.pages["machine"].set_status_text(
                    f"seq={res.value.seq} mode={res.value.mode_name} "
                    f"n={res.value.n}")
        # ⚠ 2.0 起 `get_status_now`/`get_tcp`/`kin_bench` 返回 `Msg` 信封 ——
        # `TaskResult.value` 记的是 fn 的**原样**返回值, 故解信封必须在 fn 里做,
        # 否则 `done` 拿到的会是信封 (下面 `.seq` 会 AttributeError)。
        self._submit("读状态", lambda arm: arm.get_status_now().value, done)

    # ================= 关节运动 =================
    def _delta_ok(self, op: str, cur, targets) -> bool:
        """幅度闸门：有基线才判 Δq，**没基线就拒绝**。

        原先的做法是"拿不到当前角就不判，直接发" —— 于是连上后第一帧状态还没到
        时下发的第一条 movej 完全绕过了幅度确认，而那正是输入框还是默认值、
        最容易手滑的时刻。宁可让用户等一帧。
        """
        if cur is None or len(cur) != len(targets):
            self._log(f"[WARN] 拒绝 {op} — 拿不到当前关节角作基线（等一帧状态再试）")
            return False
        plan = checks.plan_motion(cur, targets, self._settings.confirm_threshold)
        return (not plan.needs_confirm) or self._confirm_motion(plan)

    def _on_movej(self, qs, speed):
        if self._motion_denied("movej"):
            return
        st = self.worker.state
        if not self._delta_ok("movej", st.q if st is not None else None, qs):
            return
        self._submit(f"movej sp={speed:.2f}",
                     lambda arm: arm.movej(qs, speed), self._after_move)

    def _confirm_motion(self, plan) -> bool:
        return QMessageBox.warning(
            self, "确认运动幅度",
            f"以下关节与当前位置差异超过 {plan.threshold} rad：\n\n"
            + "\n".join(checks.confirm_lines(plan)) + "\n\n确认下发？",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel) == QMessageBox.Ok

    def _on_move_js(self, q, dq, tau_ff):
        if self._motion_denied("move_js"):
            return
        st = self.worker.state
        if not self._delta_ok("move_js", st.q if st is not None else None, q):
            return
        self._submit("move_js",
                     lambda arm: arm.move_js(q, dq, tau_ff), self._after_simple)

    def _on_mit_one(self, idx, q, dq, kp, kd, tau):
        if self._motion_denied("move_mit"):
            return
        st = self.worker.state
        cur = [st.q[idx]] if (st is not None and 0 <= idx < st.n) else None
        if not self._delta_ok("move_mit", cur, [q]):
            return
        self._submit(f"move_mit J{idx + 1}",
                     lambda arm: arm.send_mit(idx, q, dq, kp, kd, tau),
                     self._after_simple)

    def _on_mit_all(self, q, dq, kp, kd, tau):
        if self._motion_denied("move_mit_all"):
            return
        st = self.worker.state
        if not self._delta_ok("move_mit_all", st.q if st is not None else None, q):
            return
        self._submit("move_mit_all",
                     lambda arm: arm.send_mit_all(q, dq, kp, kd, tau),
                     self._after_simple)

    # ================= 笛卡尔 =================
    def _on_get_tcp(self):
        def done(res):
            self.pages["cart"].show_tcp(res.value if res.ok else None)
        self._submit("读 TCP", lambda arm: arm.get_tcp().value, done)

    def _on_ik(self, pose, seed):
        # SDK 的 IK 种子恒为**模型 7 轴**（与关节数解耦）。台架 1J 上实测角只有 N 个，
        # 直接喂进去会被 SDK 拒（"q_seed 需 7 个"）。给 None 让 SDK 自己按
        # BENCH_MODEL_AXIS 构造 7 轴种子 —— 这正是它存在的理由。
        if seed is not None and len(seed) != 7:
            seed = None

        def done(res):
            if res.ok:
                self.pages["cart"].show_ik(res.value)
                self._log("[OK] IK 求解成功: "
                          + " ".join(f"{v:+.3f}" for v in res.value))
            else:
                self.pages["cart"].show_ik_error(str(res.error))
        self._submit("ik", lambda arm: arm.ik(pose, seed), done)

    def _on_movep(self, pose, speed):
        if self._motion_denied("movep"):
            return
        cur = self.pages["cart"]._tcp
        if cur is None:
            # 没有基线就判不了幅度。与其放行，不如顺手读一次 TCP 再回来判 ——
            # 比让用户自己想起去点 [读取当前末端位姿] 更稳。
            self._log("[INFO] 尚无当前位姿基线，先读一次 TCP 再判幅度")
            self._submit("读 TCP（movep 前置）", lambda arm: arm.get_tcp().value,
                         lambda res: self._movep_after_tcp(res, pose, speed))
            return
        self._movep_confirm_and_send(pose, speed, cur)

    def _movep_after_tcp(self, res, pose, speed):
        if not res.ok or res.value is None:
            self._log(f"[WARN] 拒绝 movep — 读不到当前 TCP，无法判断幅度"
                      f"（{res.error if not res.ok else '固件无应答'}）")
            return
        self.pages["cart"].show_tcp(res.value)
        self._movep_confirm_and_send(pose, speed, res.value)

    def _movep_confirm_and_send(self, pose, speed, cur):
        plan = checks.plan_pose(cur, pose, self._settings.pose_confirm_pos,
                                self._settings.pose_confirm_rot)
        if plan.needs_confirm:
            if QMessageBox.warning(
                    self, "确认位姿幅度",
                    f"movep 目标与当前位姿：\n\n{plan.summary()}\n\n确认下发？",
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel) != QMessageBox.Ok:
                return
        self._submit(f"movep sp={speed:.2f}",
                     lambda arm: arm.move_p(pose, speed), self._after_move)

    # ================= 零重力 =================
    def _on_zero_g(self, on: bool):
        period = self.pages["zerog"].period_value()
        # 退出永远放行 —— 把用户锁在零重力里比放行更危险
        if on and self._motion_denied("零重力进入"):
            return
        if on:
            def done(res):
                if not res.ok:
                    self.pages["zerog"].set_state(False, None)
            self._submit(f"零重力进入 (保活 {period:.3f}s)",
                         lambda arm: arm.zero_g_start(period), done)
        else:
            # 退出后必须补一条零位移 movej 保持：只发 off 的话，0.1 s 后命令
            # 看门狗会进 fail-soft (tau=0, kp=0.6×)，臂按 G/(0.6·kp) 下沉。
            # 显式退出不是 PC 掉线；movej 到当前 q 会把模式留在 MOVE_J，
            # 固件在该模式每拍自动 kick 看门狗 + 持续重力前馈。
            self._submit("零重力退出 + 保持",
                         lambda arm: exit_zero_g_and_hold(arm), self._after_simple)

    # ================= 诊断 =================
    def _on_bench(self):
        def done(res):
            if res.ok:
                self.pages["diag"].set_bench(res.value)
                self._log("[OK] KIN_BENCH 完成")
            else:
                self.pages["diag"].set_bench_error(str(res.error))
        self._submit("KIN_BENCH", lambda arm: arm.diag.kin_bench().value, done)

    # ================= 窗口 =================
    def activate(self):
        """把已有窗口提到前台 —— 第二个实例启动时由单实例锁调用。"""
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # ================= 关闭 =================
    def closeEvent(self, ev):  # noqa: N802 - Qt 命名
        self._timer.stop()
        self._ptimer.stop()
        try:
            self.worker.close()
        except Exception:  # noqa: BLE001 - 退出不该被链路故障卡住
            pass
        super().closeEvent(ev)
