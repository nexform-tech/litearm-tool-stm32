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

import sys

from PyQt5.QtCore import QLocale, QTimer, Qt
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
                             QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QPushButton, QScrollArea, QSplitter,
                             QStackedWidget, QVBoxLayout, QWidget)

import litearm as pa

from litetool import checks
from litetool import dfu
from litetool import i18n
from litetool import obs
from litetool import pose_math
from litetool.diagnostics import build_diag_package, save_diag_package
from litetool import ports as ports_mod
from litetool.gui import i18n_ui
from litetool.gui.bridge import GuiBridge
from litetool.gui.i18n_ui import TrButton, TrCheckBox, TrLabel, tr_tooltip
from litetool.gui.prefs import UiPreferences
from litetool.gui.pages.capture_page import CapturePage
from litetool.gui.pages.activation_page import ActivationPage
from litetool.gui.pages.cart_page import CartPage
from litetool.gui.pages.diag_page import DiagPage
from litetool.gui.pages.fault_page import FaultPage
from litetool.gui.pages.firmware_page import FirmwarePage
from litetool.gui.pages.guide_page import TuningGuidePage
from litetool.gui.pages.gripper_page import GripperPage
from litetool.gui.pages.installation_page import InstallationPage
from litetool.gui.pages.joint_page import JointPage
from litetool.gui.pages.log_page import LogPage
from litetool.gui.pages.machine_page import MachinePage
from litetool.gui.pages.overview_page import OverviewPage
from litetool.gui.pages.params_page import ParamsPage
from litetool.gui.pages.scene_page import ScenePage
from litetool.gui.pages.settings_page import SettingsPage
from litetool.gui.pages.zerog_page import ZeroGPage
from litetool.gui.widgets import LogPanel, NavList, StatusStrip
from litetool.sdk_worker import SdkWorker, exit_zero_g_and_hold

TICK_MS = 50          # 20Hz：状态条/表格刷新
PLOT_MS = 33          # 30Hz：曲线重绘


class MainWindow(QMainWindow):
    def __init__(self, settings, parent=None, *, log_dir=None,
                 arm_factory=None, fake: bool = False, prefs=None,
                 language: str | None = None):
        super().__init__(parent)
        self._settings = settings
        self._fake = bool(fake)
        self._prefs = prefs or UiPreferences()
        #: `--lang` 只覆盖本次运行；设置页里改语言会落盘并解除这个覆盖。
        self._language_override = language
        ui_languages = QLocale.system().uiLanguages()
        self._system_language = i18n.detect_language(ui_languages=ui_languages,
                                                     platform=sys.platform)
        #: `auto` 真正落到的语言：config.yaml > 系统检测。
        self._default_language = (i18n.normalize_language(settings.language)
                                  or self._system_language)
        self._target_language = i18n.resolve_language(
            self._prefs.language() or settings.language,
            override=language, ui_languages=ui_languages, platform=sys.platform)
        self._armed = False
        self._fault_blocked = False
        self._n = 0
        self._connected = False
        self._upgrading = False          # 固件升级中：连接/解锁一律禁用
        self._last_port: str | None = None
        self._log_tail: list = []       # 诊断包用：最近 200 行
        self._last_error = None         # 最近一次失败（SDK ErrorText）
        self._last_exc = None           # 产生 _last_error 的原始异常（切语言时重译）
        self._last_fault_axis = None    # 最近一次写进顶栏红框的 (轴, 原因码)
        self._estop_state = None        # (ok, why) —— 切语言时重写急停提示
        self._fault_snapshot: set = set()   # 已记录过的 (轴, 原因)，用于事件去重
        self._last_fault_bits = 0           # 上次查询时的 joint_fault 位图
        self._fault_query_inflight = False  # 防止同一故障重复查询
        self._fault_detail = None           # 最近一次 0x51 应答
        # 结构化日志先于 worker：连接期日志也要落盘（worker 的回调会走到 _log）。
        self.slog = obs.StructuredLogger(log_dir)

        self.bridge = GuiBridge()
        self.worker = SdkWorker(
            arm_factory=arm_factory,
            log=self._log_from_worker,
            on_online=lambda ok, why: self.bridge.sig_online.emit(ok, why),
            on_task=lambda res: self.bridge.sig_task.emit(res, None),
            on_reconnect=lambda n, why: self.bridge.sig_reconnect.emit(n, why),
            plot_window_s=settings.plot_window_s,
        )

        # 静态文案以中文源串构造，随后统一切到目标语言（见 gui/i18n_ui.py）。
        with i18n.source_language():
            self._build_ui()
        i18n.set_language(self._target_language)
        i18n_ui.retranslate_all()
        self.nav.retranslate()
        # 静态控件已由登记表重写；动态/目录类文案由各页按状态重写一遍
        # （参数行标题、调参指南 HTML、授权同意书…）。
        for page in self.pages.values():
            hook = getattr(page, "retranslate", None)
            if callable(hook):
                hook()
        self._wire()
        self._refresh_ports()
        self._apply_online(False, i18n.tr("未连接"))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)
        self._ptimer = QTimer(self)
        self._ptimer.timeout.connect(self._tick_plot)
        self._ptimer.start(PLOT_MS)

        self._log(i18n.tr("[INFO] LiteArm Tool STM32 —— 交互层经 litearm；"
                          "硬防护权威仍在固件"))
        if self._fake:
            self.setWindowTitle("LiteArm Tool STM32 — FAKE")
            self._log(i18n.tr("[INFO] --fake 模式：SDK 假传输，不连接真实串口"))
            QTimer.singleShot(0, self.connect_fake)

    # ================= 界面 =================
    def _build_ui(self):
        self.setWindowTitle("LiteArm Tool STM32")

        # ---- 顶栏：串口 / 连接 / 解锁 / 急停 ----
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 4, 8, 4)
        bl.addWidget(TrLabel("串口:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(300)
        bl.addWidget(self.combo)
        btn_refresh = TrButton("刷新")
        btn_refresh.clicked.connect(self._refresh_ports)
        bl.addWidget(btn_refresh)
        self.btn_conn = TrButton("连接")
        self.btn_conn.clicked.connect(self._toggle_connect)
        bl.addWidget(self.btn_conn)
        self.dot = QLabel(i18n.tr("● 离线"))
        self.dot.setStyleSheet("color:#b0b0b0;font-weight:bold;")
        bl.addWidget(self.dot)
        self.fw_lbl = QLabel(i18n.tr("固件: —"))
        bl.addWidget(self.fw_lbl)
        bl.addSpacing(12)
        self.unlock_cb = TrCheckBox("我已确认机械臂周围无障碍、急停可及")
        tr_tooltip(
            self.unlock_cb,
            "运动类页面（整机的回零 / 关节 / 笛卡尔 / 零重力）在此勾选前一律锁定。\n"
            "断线、急停、FAULT、复位会自动重新锁定。")
        self.unlock_cb.toggled.connect(self._on_unlock)
        bl.addWidget(self.unlock_cb)
        bl.addStretch(1)
        self.btn_estop = TrButton("⛔ 急停")
        self.btn_estop.setFixedSize(108, 40)
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
        tr_tooltip(self.err_btn, "点击复制诊断包")
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
        self._add_page("scene", "3D", "数字孪生（只读，不碰串口）",
                       ScenePage(self.worker, self._settings))
        self._add_page("capture", "采集", "固件 300Hz 控制拍采集与导出", CapturePage())
        self._add_page("log", "日志", "结构化 JSONL：实时/筛选/历史回读/导出",
                       LogPage(self.slog))
        self._add_page("machine", "整机", "使能/复位/清故障/回零/限速/park",
                       MachinePage())
        self._add_page("fault", "故障", "当前故障/原因/处置/事件历史/诊断包",
                       FaultPage())
        self._add_page("joint", "关节", "movej / move_js / move_mit",
                       JointPage(self._settings))
        self._add_page("cart", "笛卡尔", "get_tcp / ik / move_p",
                       CartPage(self._settings))
        self._add_page("zerog", "零重力", "拖动示教（保活由 SDK 维持）", ZeroGPage())
        self._add_page("gripper", "夹爪",
                       "LiteGrip（仅 Linux）：连接/使能/开合/抓取/标定",
                       GripperPage(self._settings))
        self._add_page("params", "参数表", "关节/前馈参数读写与批量导入导出",
                       ParamsPage())
        self._add_page("guide", "调参指南", "公式 / 症状速查 / 逐参数详解",
                       TuningGuidePage())
        self._add_page("diag", "诊断", "KIN_BENCH / 启动原因 / 链路计数", DiagPage())
        self._add_page("install", "安装方向",
                       "gravity 向量 (0x28 item6) —— 正装/侧装/倒装",
                       InstallationPage())
        self._add_page("activation", "授权",
                       "读取 UID / 在线激活（0x2F / 0x3F）",
                       ActivationPage())
        self._add_page("firmware", "固件升级",
                       "USB DFU (0483:DF11) —— 选镜像 / 烧录 / 回读校验",
                       FirmwarePage())
        # `--lang` 是本次运行的覆盖：设置页把它显示成当前选项，但不动已保存选择；
        # 操作员真在页里改一次才会落盘（并解除覆盖）。
        settings_pref = self._prefs.language() or \
            (i18n.normalize_language(self._language_override) or "")
        self._add_page("settings", "设置", "界面语言与运行偏好",
                       SettingsPage(settings_pref, self._default_language))
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

    _GROUPS = {"监视": ("overview", "scene", "capture", "log"),
               "操作": ("machine", "fault", "joint", "cart", "zerog", "gripper"),
               # ⚠ 新页 key 必须登记在这里: `_group_for` 用的是无默认值的 next(),
               # 漏登记会在 __init__ 期间抛 StopIteration -> 崩启动。
               "参数": ("params", "install", "activation", "firmware", "guide",
                        "diag", "settings")}

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
        self.bridge.sig_log_record.connect(self.pages["log"].append)
        self.bridge.sig_task.connect(self._on_task)
        self.bridge.sig_online.connect(self._on_online)
        self.bridge.sig_reconnect.connect(self._on_reconnect)

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
        j.movej_takeover.connect(
            lambda qs, sp: self._on_movej(qs, sp, supersede=True))
        j.move_js.connect(self._on_move_js)
        j.mit_one.connect(self._on_mit_one)
        j.mit_all.connect(self._on_mit_all)
        c.tcp_req.connect(self._on_get_tcp)
        c.ik_req.connect(self._on_ik)
        c.movep.connect(self._on_movep)
        c.movel.connect(self._on_movel)
        c.jog_step.connect(self._on_jog_step)
        c.stop_req.connect(self._on_stop_jog)
        z.zg.connect(self._on_zero_g)
        self.pages["diag"].bench_req.connect(self._on_bench)
        self.pages["params"].set_log(
            lambda m: self._log(m, category="parameter"))
        self.pages["params"].set_submit(self._submit)
        self.pages["params"].show_guide.connect(self._on_guide)
        self.pages["capture"].set_submit(self._submit)
        self.pages["install"].set_log(
            lambda m: self._log(m, category="installation"))
        self.pages["install"].set_submit(self._submit)
        self.pages["gripper"].set_log(self._log)
        self.pages["activation"].set_log(self._log)
        self.pages["activation"].set_submit(self._submit)
        fw = self.pages["firmware"]
        fw.set_log(self._log)
        fw.set_worker(self.worker)
        fw.set_upgrading_cb(self._set_upgrading)
        fw.reconnect_requested.connect(self._reconnect_after_upgrade)
        self.nav.navigated.connect(self._on_page_changed)
        self.pages["settings"].language_changed.connect(self._on_language_changed)

    def _on_nav(self, key: str):
        scroll = self.scrolls.get(key)
        if scroll is not None:
            self.stack.setCurrentWidget(scroll)

    def _on_page_changed(self, key: str):
        if key == "overview":
            self.pages["overview"].clear_plot()
        elif key == "firmware":
            # 进页面时顺手重探一次 DFU（板子可能在别处插上/复位了）。
            self.pages["firmware"].refresh_status()

    def _on_guide(self, key: str):
        self.nav.select("guide")
        self._on_nav("guide")
        self.pages["guide"].reveal(key)

    # ================= 界面语言 =================
    def _on_language_changed(self, preference: str):
        """设置页的选择：落盘 + 立即切换（不重启）。"""
        self._prefs.set_language(preference)
        self._language_override = None
        target = i18n.resolve_language(
            preference or self._settings.language,
            ui_languages=QLocale.system().uiLanguages(), platform=sys.platform)
        self._target_language = target
        i18n.set_language(target)
        self.retranslate()

    def retranslate(self):
        """切换语言后重写静态文案，再让各页按当前状态重写动态文案。

        顺序不能反：`i18n_ui` 会先把每个静态控件恢复成**构造时的源文案**翻成的
        新语言，页面钩子随后覆盖状态相关的那些（连接中/使能/故障…）。
        """
        i18n_ui.retranslate_all()
        self.nav.retranslate()
        for page in self.pages.values():
            hook = getattr(page, "retranslate", None)
            if callable(hook):
                hook()
        self.log_panel.retranslate()
        self._apply_online(self._connected,
                           "" if self._connected else i18n.tr("未连接"))
        self._render_estop()
        self._render_last_error()
        self._tick()

    # ================= 日志 / 任务 =================
    _LEVEL_PREFIX = (("[TRACE]", "TRACE"), ("[DEBUG]", "DEBUG"),
                     ("[INFO]", "INFO"), ("[OK]", "INFO"),
                     ("[WARN]", "WARN"), ("[ERR]", "ERROR"), ("[FATAL]", "FATAL"))

    def _log(self, msg: str, *, category: str = "app", event=None, fields=None):
        """一行日志同时进：底部面板、结构化 JSONL、日志页实时视图。"""
        text = str(msg)
        sev = "INFO"
        for prefix, level in self._LEVEL_PREFIX:
            if text.startswith(prefix):
                sev = level
                break
        rec = self.slog.record(sev, text, category=category, event=event,
                               fields=fields)
        self._log_tail.append(text)
        if len(self._log_tail) > 200:
            del self._log_tail[:-200]
        self.bridge.sig_log_record.emit(rec)
        self.bridge.sig_log.emit(text)

    def _log_from_worker(self, msg: str):
        """SDK 所有者线程的日志 —— 只做分类，不碰任何控件。"""
        text = str(msg)
        low = text.lower()
        if text.startswith("[OK]") and ("已连接" in text or "connected" in low):
            event = "session.connect.succeeded"
        elif (text.startswith("[ERR]") and ("离线" in text or "offline" in low)) or \
                (text.startswith("[WARN]") and
                 ("链路" in text or "link" in low)):
            event = "session.link.lost"
        else:
            event = "session.log"
        self._log(text, category="session", event=event)

    def _submit(self, name: str, fn, on_done=None):
        """把 `fn(arm)` 投到 SDK 所有者线程；`on_done(TaskResult)` 回到 GUI 主线程。"""
        self.worker.submit(name, fn,
                           lambda res: self.bridge.sig_task.emit(res, on_done))

    def _on_task(self, res, cb):
        if res is None:
            return
        superseded = isinstance(getattr(res, "error", None),
                                getattr(pa, "MotionSupersededError", ()))
        err = None
        if not res.ok and not superseded:
            self._last_exc = res.error
            self._last_fault_axis = None
            self._render_last_error()
        if res.ok:
            event, text = "command.ok", i18n.tr("[OK] {text}", text=res.text)
        elif superseded:
            # 被新的运动接管不是故障：规划按预期作废，别把红框留给用户。
            event, text = "command.superseded", i18n.tr(
                "[WARN] {text}（已被新的运动接管）", text=res.text)
        else:
            event, text = "command.failed", i18n.tr("[ERR] {text}", text=res.text)
        self._log(text, category="command", event=event,
                  fields={"name": res.name, "ok": bool(res.ok),
                          "code": getattr(err, "code", None),
                          "title": getattr(err, "title", None)})
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
                log_path=str(self.slog.path),
            )
            path = save_diag_package(pkg)
            import json
            QApplication.clipboard().setText(
                json.dumps(pkg, ensure_ascii=False, indent=2))
            self._log(i18n.tr("[OK] 诊断包已复制并保存: {path}", path=path),
                      category="diagnostics", event="diagnostics.saved")
        except Exception as e:  # noqa: BLE001 - 导出失败不能拖垮界面
            self._log(i18n.tr("[ERR] 诊断包导出失败: {err}", err=e),
                      category="diagnostics", event="diagnostics.failed")

    def _after_simple(self, res):
        pass

    def _after_move(self, res):
        if res.ok:
            self._log(i18n.tr("[OK] 已到位"))

    # ================= 串口 =================
    def _refresh_ports(self):
        if self._fake:
            self.combo.clear()
            self.combo.addItem(i18n.tr("假设备 (--fake)"), "fake")
            return
        cur = self.combo.currentData()
        self.combo.clear()
        for r in ports_mod.find_ports():
            self.combo.addItem(r["description"], r["device"])
        if cur:
            i = self.combo.findData(cur)
            if i >= 0:
                self.combo.setCurrentIndex(i)

    def connect_fake(self):
        """`--fake` 启动后自动接上假设备（等主窗口事件循环起来再连）。"""
        i = self.combo.findData("fake")
        if i >= 0:
            self.combo.setCurrentIndex(i)
        if not self._connected:
            self._toggle_connect()

    def _current_device(self):
        return self.combo.currentData()

    def _toggle_connect(self):
        if self._connected:
            self._disconnect()
            return
        port = self._current_device()
        if not port:
            QMessageBox.warning(self, i18n.tr("无可选串口"),
                                i18n.tr("未发现串口设备，请检查 USB 连接。"))
            return
        self.btn_conn.setEnabled(False)
        self._last_port = port
        try:
            self.worker.open(port)
        except Exception as e:  # noqa: BLE001 - SDK 的连接期异常都在这提示
            self._log(i18n.tr("[ERR] 连接失败: {err}", err=e),
                      category="session",
                      event="session.connect.failed", fields={"reason": str(e)})
            hint = ""
            try:
                # 板子停在 ROM bootloader 里时没有应用态 CDC —— "连接"永远失败。
                # 这句话是 issue #152 的落点：不说清，操作员会去换线、换口、重装驱动，
                # 而它只想被烧一次。
                if dfu.engine.available() and dfu.engine.find_device() is not None:
                    hint = i18n.tr(
                        "\n\n检测到一块停在 bootloader (DFU) 里的控制器：它没有"
                        "应用态可连，「连接」不会成功。请到「参数 → 固件升级」"
                        "直接烧录，或断电重新上电。")
            except Exception:  # noqa: BLE001 - 连接失败提示不该再炸一次
                hint = ""
            QMessageBox.critical(self, i18n.tr("连接失败"), f"{e}{hint}")
            self._apply_online(False, str(e))
        finally:
            self.btn_conn.setEnabled(not self._upgrading)

    def _disconnect(self):
        self.worker.close()
        self._apply_online(False, i18n.tr("已断开"))
        self._log(i18n.tr("[INFO] 已断开（用户操作）"), category="session",
                  event="session.disconnected", fields={"reason": "用户断开"})

    def _on_online(self, ok: bool, why: str):
        # 升级期间我们自己会 close 掉 worker（设备交出 CDC）。那条离线信号如果
        # 比重连成功后的在线信号**晚**到，会把界面从"已接回"拉回离线 —— 所以要丢掉
        # 这种过期的 False（判据是 worker 此刻确实在线）。
        if self._upgrading and not ok and self.worker.online:
            return
        self._apply_online(ok, why)

    def _on_reconnect(self, attempt: int, why: str):
        """自动重连的每次尝试 —— 顶栏必须说"正在重连"，不能只留一个"离线"。"""
        self.dot.setText(i18n.tr("● 重连中({n})", n=attempt))
        self.dot.setStyleSheet("color:#ffd166;font-weight:bold;")
        self.fw_lbl.setText(i18n.tr("固件: —"))
        self._log(f"[WARN] {why}")

    def _apply_online(self, onl: bool, why: str = ""):
        self._connected = onl
        self.btn_conn.setText(i18n.tr("断开") if onl else i18n.tr("连接"))
        if self._upgrading:
            self.btn_conn.setText(i18n.tr("连接"))
            self.btn_conn.setEnabled(False)
            self.unlock_cb.setEnabled(False)
            self.dot.setText(i18n.tr("● 升级中"))
            self.dot.setStyleSheet("color:#ffd166;font-weight:bold;")
            self.fw_lbl.setText(i18n.tr("固件: 升级中"))
        else:
            self.btn_conn.setEnabled(True)
            self.unlock_cb.setEnabled(True)
            self.dot.setText(i18n.tr("● 在线") if onl else i18n.tr("● 离线"))
            self.dot.setStyleSheet(
                f"color:{'#6fdd8b' if onl else '#b0b0b0'};font-weight:bold;")
            self.fw_lbl.setText(i18n.tr("固件: {version}", version=self.worker.firmware)
                                if onl else i18n.tr("固件: —"))
        if not onl:
            self.strip.reset()
            # 断线必须回到锁定态 —— 否则重连后第一下手就是未确认的运动
            self._relock(i18n.tr("链路断开"))
        # 授权页连上即自动读一次 —— 先把固件版本喂进去，旧固件才能直接提示"升级固件"。
        self.pages["activation"].set_firmware(self.worker.firmware)
        self.pages["firmware"].set_link_info(self._last_port or "", self.worker.firmware)
        for page in self.pages.values():
            if hasattr(page, "set_online"):
                page.set_online(onl)
        # 导出上下文跟着连接走；断线后保留最后已知的固件版本（已读回的数据仍可导出）。
        self.pages["overview"].set_context(self.worker.firmware)
        self.pages["capture"].set_firmware(self.worker.firmware)
        # 笛卡尔规划的固件能力（connect 时探测）：点动/movel 的按钮门控。
        self.pages["cart"].set_cart_supported(
            self.worker.cart_supported if onl else None,
            self.worker.cart_probe_silent if onl else False)
        self._apply_busy()

    # ================= 固件升级（USB DFU） =================
    def _set_upgrading(self, active: bool):
        """升级期间锁死连接/解锁入口 —— 设备在 bootloader 里，普通命令一律不可达。"""
        active = bool(active)
        self._upgrading = active
        if active:
            self.btn_conn.setEnabled(False)
            self.unlock_cb.setEnabled(False)
            self._relock(i18n.tr("固件升级"))
            self.btn_conn.setText(i18n.tr("连接"))
            self.dot.setText(i18n.tr("● 升级中"))
            self.dot.setStyleSheet("color:#ffd166;font-weight:bold;")
            self.fw_lbl.setText(i18n.tr("固件: 升级中"))
            self._log(i18n.tr("[INFO] 固件升级期间：连接/解锁已禁用，升级结束后自动恢复"))
        else:
            self.unlock_cb.setEnabled(True)
            self._apply_online(self.worker.online, i18n.tr("升级结束"))

    def _upgrade_candidates(self, hint: str | None) -> list:
        """升级后重连候选：上次的端口 → 板载 CDC。端口名重枚举后会变，所以必须发现。"""
        out: list = []
        if hint:
            out.append(hint)
        try:
            for row in ports_mod.find_ports():
                if row.get("_ours") and row["device"] not in out:
                    out.append(row["device"])
        except Exception:  # noqa: BLE001 - 枚举失败不该让重连直接放弃
            pass
        return out

    def _reconnect_after_upgrade(self, hint: str):
        """由升级线程通过信号请求，在 GUI 线程上真正重连 —— 保证 online 信号有顺序。"""
        fw = self.pages["firmware"]
        try:
            self.worker.close()
        except Exception as e:  # noqa: BLE001
            self._log(i18n.tr("[WARN] 升级重连前关闭串口失败: {err}", err=e))
        last = ""
        for port in self._upgrade_candidates(hint or self._last_port):
            try:
                self._last_port = port
                self.worker.open(port)
            except Exception as e:  # noqa: BLE001 - 设备还没回来是预期结局
                last = f"{port}: {type(e).__name__}: {e}"
                self._log(i18n.tr("[WARN] 升级后重连失败 {detail}", detail=last))
                continue
            self._refresh_ports()
            fw.reconnect_finished(True, port, self.worker.firmware, "")
            self._log(i18n.tr("[OK] 升级后已重新连接: {port} · {fw}",
                              port=port, fw=self.worker.firmware))
            return
        missing = i18n.tr("没有发现 STM32 CDC 设备")
        fw.reconnect_finished(False, "", "", last or missing)
        self._log(i18n.tr("[ERR] 升级后重连失败: {detail}", detail=last or missing))

    # ================= 运动解锁（全局一把） =================
    def _on_unlock(self, checked: bool):
        if checked and not self._connected:
            self._log(i18n.tr("[WARN] 未连接，解锁无效"))
            self.unlock_cb.setChecked(False)
            return
        self._set_armed(bool(checked))
        self._log(i18n.tr("[WARN] 运动控制已解锁") if checked
                  else i18n.tr("[INFO] 运动控制已锁定"))

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
            self._log(i18n.tr("[WARN] 运动控制已锁定 — {reason}", reason=reason))

    # ================= 运动闸门（唯一收口） =================
    def _motion_denied(self, op: str) -> bool:
        """能不能发这条运动命令；不能则记日志并返回 True。

        ⚠ 各页按钮的 `setEnabled(False)` **只是 UX，不是安全边界**。任何能到达
        处理函数的路径都必须在这里被挡住：代码里直接 emit、将来某页漏禁一个控件、
        快捷键、某个 `_refresh()` 分支写错。守卫只做在控件状态上，就等于没有守卫
        —— 本仓 2026-09-13 评审的"新增守卫是死代码"是同一类问题。
        """
        if not self._connected:
            self._log(i18n.tr("[WARN] 拒绝 {op} — 未连接", op=op))
            return True
        if self._fault_blocked:
            self._log(i18n.tr("[WARN] 拒绝 {op} — FAULT/急停锁存中，先 [清故障] 或 [复位]",
                              op=op))
            return True
        if not self._armed:
            self._log(i18n.tr("[WARN] 拒绝 {op} — 运动未解锁（先勾选顶栏的确认项）",
                              op=op))
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
        self._relock(i18n.tr("急停"))
        if dropped:
            self._log(i18n.tr("[WARN] 急停：已丢弃 {n} 条排队中的命令", n=dropped),
                      category="command", event="command.emergency_stop",
                      fields={"sent": bool(ok), "dropped": int(dropped)})
        if zg_err:
            self._log(i18n.tr("[WARN] 急停：零重力会话未能正常收尾（{err}）",
                              err=zg_err),
                      category="command", event="command.emergency_stop",
                      fields={"sent": bool(ok), "zero_g_error": str(zg_err)})
        self._estop_state = (bool(ok), str(why))
        self._render_estop()
        if ok:
            self._log(i18n.tr(
                "[WARN] 急停帧已发出 —— 请目视确认臂已停止（帧发出≠固件已执行）"),
                category="command", event="command.emergency_stop",
                fields={"sent": True, "dropped": int(dropped)})
        else:
            self._log(i18n.tr("[ERR] 急停未发出（{why}）—— 请立即用硬件急停/断电",
                              why=why),
                      category="command", event="command.emergency_stop",
                      fields={"sent": False, "dropped": int(dropped), "reason": str(why)})

    def _render_estop(self):
        """顶栏急停结果 —— 切语言时也要按同样的事实重写。"""
        if self._estop_state is None:
            self.estop_lbl.setText("")
            return
        ok, _why = self._estop_state
        if ok:
            self.estop_lbl.setText(i18n.tr("急停帧已发出 — 请目视确认臂已停止"))
            self.estop_lbl.setStyleSheet("color:#ffd166;font-weight:bold;")
        else:
            self.estop_lbl.setText(i18n.tr("⚠ 急停未发出 — 请立即用硬件急停/断电"))
            self.estop_lbl.setStyleSheet("color:#ff6b6b;font-weight:bold;")

    def _render_last_error(self):
        """顶栏错误红框 —— 故障原因走 ``describe_fault``，本地异常走 ``describe_exc``。"""
        err = None
        prefix = ""
        if self._last_fault_axis is not None:
            axis, reason = self._last_fault_axis
            try:
                err = pa.describe_fault(reason, locale=i18n.sdk_locale())
                prefix = f"J{axis + 1} "
            except Exception:  # noqa: BLE001
                err = None
        elif self._last_exc is not None:
            try:
                err = pa.describe_exc(self._last_exc, locale=i18n.sdk_locale())
            except Exception:  # noqa: BLE001 - 老 SDK 无 describe_exc 时降级
                err = None
        if err is None:
            self.err_btn.setVisible(False)
            self._last_error = None
            return
        self._last_error = err
        self.err_btn.setText(f"[{err.code}] {prefix}{err.title}")
        self.err_btn.setVisible(True)

    # ================= 周期刷新 =================
    def _tick(self):
        st = self.worker.state
        if st is not None and st.n != self._n:
            self._n = st.n
            self.pages["overview"].set_joints(st.n)
            self.pages["joint"].set_joints(st.n)
            self._log(i18n.tr("[INFO] 识别到 {n} 个关节", n=st.n))

        fps = self.worker.model.rate()
        drops = self.worker.drops
        self.strip.update_from(st, drops, fps)

        self.pages["overview"].update_from(st)
        self.pages["scene"].update_from(st)
        self.pages["machine"].update_from(st)
        self.pages["machine"].set_metrics(drops, fps, self.worker.last_reset_reason)
        # 离线时也喂一次 None：让参数页/安装方向页丢掉 enable 态的旧快照
        # （安装方向页的"须先失能"硬拦依赖它 —— 旧快照会拿过期的 enabled 放行）
        self.pages["params"].update_from(st)
        self.pages["install"].update_from(st)
        self.pages["activation"].update_from(st)
        self.pages["activation"].set_firmware(self.worker.firmware)
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
                title = pa.describe_fault(r, locale=i18n.sdk_locale()).title
            except Exception:  # noqa: BLE001
                title = i18n.tr("原因 {reason}", reason=r)
            self.pages["fault"].add_event(int(a), int(r))
            self._log(i18n.tr("[WARN] 故障 J{axis} {title}",
                              axis=a + 1, title=title), category="fault",
                      event="fault.detected",
                      fields={"joint": int(a) + 1, "reason": int(r)})
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
                self._relock(i18n.tr("检测到 FAULT/急停锁存"))
            elif faulted:
                self._log(i18n.tr("[WARN] 故障: {detail}",
                                  detail=self._fault_summary(st) or st.fault_detail))
            d = self._fault_detail
            pairs = list(getattr(d, "fault_reasons", []) or []) if d else \
                list(getattr(st, "fault_reasons", []) or [])
            if faulted and pairs:
                a, r = pairs[0]
                self._last_fault_axis = (int(a), int(r))
                self._last_exc = None
                self._render_last_error()

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
            if self._motion_denied(i18n.tr("回零 home")):
                return
            if not self._confirm_home():
                return
            self._submit(i18n.tr("回零 home"), lambda arm: arm.home(), self._after_move)
        elif name == "clear_faults":
            if not self._confirm_clear_faults():
                return
            self._submit(i18n.tr("清故障 clear_faults"),
                         lambda arm: arm.clear_faults(), self._after_simple)
        elif name == "reset":
            if not self._confirm_reset():
                return
            self._submit(i18n.tr("复位 reset"), lambda arm: arm.reset(), self._after_reset)
        elif name == "enable":
            self._submit(i18n.tr("使能 enable"), lambda arm: arm.enable(),
                         self._after_simple)
        elif name == "disable":
            self._submit(i18n.tr("失能 disable"), lambda arm: arm.disable(),
                         self._after_simple)

    def _after_reset(self, res):
        if res.ok:
            # 复位退出 EMERGENCY 后必须重新锁定：旧解锁态不该跨过急停继续有效
            self._relock(i18n.tr("已复位"))

    def _confirm_home(self) -> bool:
        cur = ""
        st = self.worker.state
        if st is not None and st.joints:
            cur = i18n.tr("\n\n当前各轴: {q}",
                          q="  ".join(f"{v:+.3f}" for v in st.q))
        return QMessageBox.question(
            self, i18n.tr("确认回零 home"),
            i18n.tr("各臂轴将回到 URDF 零位（固件把速度写死为 0.10 的低速）。{q}"
                    "\n\n确认下发？", q=cur),
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
        self._submit(i18n.tr("读故障详情"), lambda arm: arm.get_fault_detail(),
                     self._on_fault_detail)

    def _on_fault_detail(self, res):
        self._fault_query_inflight = False
        if res.ok:
            self._fault_detail = res.value
            self.pages["fault"].update_from(self.worker.state, self._fault_detail)
        else:
            self._log(i18n.tr("[WARN] 故障详情不可用: {text}", text=res.text))

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
                parts.append(i18n.tr("J{axis}: {title}", axis=a + 1,
                                     title=pa.describe_fault(
                                         r, locale=i18n.sdk_locale()).title))
            except Exception:  # noqa: BLE001
                parts.append(i18n.tr("J{axis}: 原因 {reason}", axis=a + 1, reason=r))
        return i18n.tr("；").join(parts)

    def _confirm_clear_faults(self) -> bool:
        st = self.worker.state
        axes = ""
        if st is not None and st.joint_fault:
            summary = self._fault_summary(st)
            axes = i18n.tr("\n\n将被恢复出力的轴: {axes}",
                           axes=summary.replace(i18n.tr("；"), i18n.tr("、"))
                           or i18n.tr("、").join(f"J{a + 1}" for a in st.fault_axes))
        return QMessageBox.question(
            self, i18n.tr("确认清故障 clear_faults"),
            i18n.tr("清除故障锁存。若臂处于使能态，被锁轴会重新出力。{axes}"
                    "\n\n确认下发？", axes=axes),
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel) == QMessageBox.Ok

    def _confirm_reset(self) -> bool:
        return QMessageBox.question(
            self, i18n.tr("确认复位 reset"),
            i18n.tr("复位会清除故障并退出急停锁存 —— 之后固件不再阻止运动。"
                    "\n\n确认下发？"),
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel) == QMessageBox.Ok

    def _on_set_speed(self, percent: int):
        self._submit(i18n.tr("全局限速 {percent}%", percent=percent),
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
        self._submit(i18n.tr("读状态"),
                     lambda arm: arm.get_status_now().value, done)

    # ================= 关节运动 =================
    def _delta_ok(self, op: str, cur, targets) -> bool:
        """幅度闸门：有基线才判 Δq，**没基线就拒绝**。

        原先的做法是"拿不到当前角就不判，直接发" —— 于是连上后第一帧状态还没到
        时下发的第一条 movej 完全绕过了幅度确认，而那正是输入框还是默认值、
        最容易手滑的时刻。宁可让用户等一帧。
        """
        if cur is None or len(cur) != len(targets):
            self._log(i18n.tr(
                "[WARN] 拒绝 {op} — 拿不到当前关节角作基线（等一帧状态再试）", op=op))
            return False
        plan = checks.plan_motion(cur, targets, self._settings.confirm_threshold)
        return (not plan.needs_confirm) or self._confirm_motion(plan)

    def _on_movej(self, qs, speed, supersede: bool = False):
        if self._motion_denied("movej"):
            return
        st = self.worker.state
        if not self._delta_ok("movej", st.q if st is not None else None, qs):
            return
        if supersede and self.worker.busy:
            # 旁路写帧：在途的 move_l(wait=True) 会把所有者线程占住，排队等于等它走完。
            ok, why = self.worker.takeover_movej(qs, speed)
            if ok:
                self._log(i18n.tr("[WARN] 接管 movej 已发出（sp={speed:.2f}）—— "
                                  "固件会作废在途点动/直线规划", speed=speed))
            else:
                self._log(i18n.tr("[ERR] 接管 movej 未发出: {why}", why=why))
            return
        if supersede:
            self._log(i18n.tr("[INFO] 当前没有在途运动，按普通 movej 下发"))
        self._submit(i18n.tr("movej sp={speed:.2f}", speed=speed),
                     lambda arm: arm.movej(qs, speed), self._after_move)

    def _confirm_motion(self, plan) -> bool:
        return QMessageBox.warning(
            self, i18n.tr("确认运动幅度"),
            i18n.tr("以下关节与当前位置差异超过 {threshold} rad：\n\n{lines}"
                    "\n\n确认下发？",
                    threshold=plan.threshold,
                    lines="\n".join(checks.confirm_lines(plan))),
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
        self._submit(i18n.tr("读 TCP"), lambda arm: arm.get_tcp().value, done)

    def _on_ik(self, pose, seed):
        # SDK 的 IK 种子恒为**模型 7 轴**（与关节数解耦）。台架 1J 上实测角只有 N 个，
        # 直接喂进去会被 SDK 拒（"q_seed 需 7 个"）。给 None 让 SDK 自己按
        # BENCH_MODEL_AXIS 构造 7 轴种子 —— 这正是它存在的理由。
        if seed is not None and len(seed) != 7:
            seed = None

        def done(res):
            if res.ok:
                self.pages["cart"].show_ik(res.value)
                self._log(i18n.tr("[OK] IK 求解成功: {q}",
                                  q=" ".join(f"{v:+.3f}" for v in res.value)))
            else:
                self.pages["cart"].show_ik_error(str(res.error))
        self._submit(i18n.tr("ik"), lambda arm: arm.ik(pose, seed), done)

    def _on_movep(self, pose, speed):
        if self._motion_denied("movep"):
            return
        cur = self.pages["cart"]._tcp
        if cur is None:
            # 没有基线就判不了幅度。与其放行，不如顺手读一次 TCP 再回来判 ——
            # 比让用户自己想起去点 [读取当前末端位姿] 更稳。
            self._log(i18n.tr("[INFO] 尚无当前位姿基线，先读一次 TCP 再判幅度"))
            self._submit(i18n.tr("读 TCP（movep 前置）"), lambda arm: arm.get_tcp().value,
                         lambda res: self._movep_after_tcp(res, pose, speed))
            return
        self._movep_confirm_and_send(pose, speed, cur)

    def _movep_after_tcp(self, res, pose, speed):
        if not res.ok or res.value is None:
            self._log(i18n.tr(
                "[WARN] 拒绝 movep — 读不到当前 TCP，无法判断幅度（{why}）",
                why=res.error if not res.ok else i18n.tr("固件无应答")))
            return
        self.pages["cart"].show_tcp(res.value)
        self._movep_confirm_and_send(pose, speed, res.value)

    def _movep_confirm_and_send(self, pose, speed, cur):
        plan = checks.plan_pose(cur, pose, self._settings.pose_confirm_pos,
                                self._settings.pose_confirm_rot)
        if plan.needs_confirm:
            if QMessageBox.warning(
                    self, i18n.tr("确认位姿幅度"),
                    i18n.tr("movep 目标与当前位姿：\n\n{summary}\n\n确认下发？",
                            summary=plan.summary()),
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel) != QMessageBox.Ok:
                return
        self._submit(i18n.tr("movep sp={speed:.2f}", speed=speed),
                     lambda arm: arm.move_p(pose, speed), self._after_move)

    # ================= 笛卡尔直线 / 点动 =================
    def _on_movel(self, pose, speed):
        if self._motion_denied("movel"):
            return
        cur = self.pages["cart"]._tcp
        if cur is None:
            self._log(i18n.tr("[INFO] 尚无当前位姿基线，先读一次 TCP 再判幅度"))
            self._submit(i18n.tr("读 TCP（movel 前置）"), lambda arm: arm.get_tcp().value,
                         lambda res: self._movel_after_tcp(res, pose, speed))
            return
        self._movel_confirm_and_send(pose, speed, cur)

    def _movel_after_tcp(self, res, pose, speed):
        if not res.ok or res.value is None:
            self._log(i18n.tr(
                "[WARN] 拒绝 movel — 读不到当前 TCP，无法判断幅度（{why}）",
                why=res.error if not res.ok else i18n.tr("固件无应答")))
            return
        self.pages["cart"].show_tcp(res.value)
        self._movel_confirm_and_send(pose, speed, res.value)

    def _movel_confirm_and_send(self, pose, speed, cur):
        plan = checks.plan_pose(cur, pose, self._settings.pose_confirm_pos,
                                self._settings.pose_confirm_rot)
        if plan.needs_confirm:
            if QMessageBox.warning(
                    self, i18n.tr("确认位姿幅度"),
                    i18n.tr("movel 目标与当前位姿：\n\n{summary}\n\n确认下发？",
                            summary=plan.summary()),
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel) != QMessageBox.Ok:
                return
        self._submit(i18n.tr("movel sp={speed:.2f}", speed=speed),
                     lambda arm: arm.move_l(pose, speed), self._after_movel)

    def _after_movel(self, res):
        if not res.ok:
            return
        plan = res.value
        settled = bool(getattr(plan, "settled", True))
        err = float(getattr(plan, "settle_err_rad", 0.0) or 0.0)
        if settled:
            self._log(i18n.tr("[OK] movel 到位"))
        else:
            self._log(i18n.tr("[WARN] movel 规划完成但未停在目标"
                              "（settled=False，settle_err={err:.3f} rad）", err=err))
        # 运动结束后把真实落点读回来 —— 别让页面停在"计划目标"上。
        self._submit(i18n.tr("读 TCP（movel 后）"), lambda arm: arm.get_tcp().value,
                     lambda r: self.pages["cart"].show_tcp(r.value if r.ok else None))

    def _on_jog_step(self, axis: str, kind: str, amount: float, frame: str,
                     speed: float, gen: int):
        """点动的一步：读实测 TCP → 算一小步 → move_l。"""
        if self._motion_denied(i18n.tr("点动 {axis}", axis=axis)):
            self.pages["cart"].jog_result(gen, None)
            return

        def fn(arm):
            tcp = arm.get_tcp().value
            if tcp is None:
                raise pa.InvalidCommandError(i18n.tr("读不到当前 TCP，点动中止"))
            target = pose_math.jog_pose(tcp, axis, kind, amount, frame)
            return tcp, target, arm.move_l(target, speed)

        self._submit(i18n.tr("点动 {axis}", axis=axis), fn,
                     lambda res: self.pages["cart"].jog_result(gen, res))

    def _on_stop_jog(self):
        """受控停止：旁路写 movej 到当前实测关节角。

        停止**不经过运动闸门**（和急停一样是降风险方向）；但链路断开时 worker
        会拒绝并给出原因。
        """
        ok, why = self.worker.stop_jog_now()
        if ok:
            self._log(i18n.tr("[WARN] 受控停止帧已发出 —— 在途点动/直线规划将被固件作废"))
        else:
            self._log(i18n.tr("[ERR] 受控停止未发出: {why}", why=why))

    # ================= 零重力 =================
    def _on_zero_g(self, on: bool):
        period = self.pages["zerog"].period_value()
        # 退出永远放行 —— 把用户锁在零重力里比放行更危险
        if on and self._motion_denied(i18n.tr("零重力进入")):
            return
        if on:
            def done(res):
                if not res.ok:
                    self.pages["zerog"].set_state(False, None)
            self._submit(i18n.tr("零重力进入 (保活 {period:.3f}s)", period=period),
                         lambda arm: arm.zero_g_start(period), done)
        else:
            # 退出后必须补一条零位移 movej 保持：只发 off 的话，0.1 s 后命令
            # 看门狗会进 fail-soft (tau=0, kp=0.6×)，臂按 G/(0.6·kp) 下沉。
            # 显式退出不是 PC 掉线；movej 到当前 q 会把模式留在 MOVE_J，
            # 固件在该模式每拍自动 kick 看门狗 + 持续重力前馈。
            self._submit(i18n.tr("零重力退出 + 保持"),
                         lambda arm: exit_zero_g_and_hold(arm), self._after_simple)

    # ================= 诊断 =================
    def _on_bench(self):
        def done(res):
            if res.ok:
                self.pages["diag"].set_bench(res.value)
                self._log(i18n.tr("[OK] KIN_BENCH 完成"))
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
        # 升级烧到一半时退出，板子可能停在 bootloader —— 必须让人看见再决定。
        fw = self.pages.get("firmware")
        if fw is not None and fw.is_running():
            reply = QMessageBox.warning(
                self, i18n.tr("固件升级进行中"),
                i18n.tr("固件正在烧录/升级。现在退出会中断升级，可能让板子停在 "
                        "bootloader 或导致变砖。\n\n确定要退出吗？"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                ev.ignore()
                return
        self._timer.stop()
        self._ptimer.stop()
        try:
            self.pages["gripper"].shutdown()
        except Exception:  # noqa: BLE001 - 退出不该被夹爪卡住
            pass
        try:
            self.worker.close()
        except Exception:  # noqa: BLE001 - 退出不该被链路故障卡住
            pass
        self.slog.close()
        super().closeEvent(ev)
