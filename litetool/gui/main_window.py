"""主窗口 —— 顶栏(串口/连接/固件/急停) + 四页签 + 日志；命令经工作线程执行。

线程模型：
- 读线程: SerialLink → Session._on_frame → client.handle_frame → PlotModel.push
- 命令线程: _run() 每次起一个 daemon 线程调 client.xxx()，结果经 bridge.sig_done 回主线程
- 主线程: QTimer 20Hz 采样状态刷新 UI；曲线页独立 30Hz 重绘 PlotModel 快照

安全交互（意图层，权威仍在固件）：
- 急停走 client.emergency_now() 旁路通道，不排队不等待
- 运动页锁定/勾选解锁；move_j/move_mit 下发前 checks.plan_motion 判 Δq 弹确认
"""
import threading
import time

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMainWindow,
                             QMessageBox, QPushButton, QSplitter, QTabWidget,
                             QVBoxLayout, QWidget)

from litetool import checks
from litetool import protocol as P
from litetool.gui.bridge import GuiBridge
from litetool.gui.control_page import ControlPage
from litetool.gui.monitor_page import MonitorPage
from litetool.gui.motion_page import MotionPage
from litetool.gui.plot_page import PlotPage
from litetool.gui.session import Session
from litetool.gui.widgets import LogPanel
from litetool import transport

CTRL_CMDS = {
    "enable": ("使能", lambda c: c.enable()),
    "disable": ("失能", lambda c: c.disable()),
    "clear_faults": ("清故障", lambda c: c.clear_faults()),
    "home": ("回零", lambda c: c.home()),
}


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle("LiteArm STM32 上位机工具")
        self.resize(1080, 720)
        self._settings = settings
        self.session: Session | None = None
        self.bridge = GuiBridge()

        self._busy = False
        self._was_online = False
        self._safety_latched = False
        self._fault_logged = False
        self._last_seq = None
        self._last_seq_t = 0.0
        self._fps = 0.0
        self._ui_n = 0
        self._cmd_seq = 0               # 每条命令递增 token，防过期 sig_done 串台
        self._pending_token = None
        self._pending_done = None

        self._build_ui()
        self._wire()
        self._refresh_ports()

        # 20Hz UI 采样 + 30Hz 曲线重绘
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(50)
        self.ui_timer.timeout.connect(self._tick)
        self.ui_timer.start()
        self.plot_timer = QTimer(self)
        self.plot_timer.setInterval(33)
        self.plot_timer.timeout.connect(self._tick_plot)
        self.plot_timer.start()

        self._set_online_ui(False)
        self._lock_motion("初始锁定 — 连接并解锁后可用")

    # ================= UI =================
    def _build_ui(self):
        # 顶栏
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
        self.dot = QLabel("● 离线")
        bl.addWidget(self.dot)
        self.fw_lbl = QLabel("固件: —")
        bl.addWidget(self.fw_lbl)
        bl.addStretch(1)
        self.btn_estop = QPushButton("⛔ 急停")
        self.btn_estop.setFixedSize(96, 40)
        self.btn_estop.setStyleSheet(
            "QPushButton{background:#b33a3a;color:white;font-weight:bold;"
            "font-size:16px;border-radius:4px;}"
            "QPushButton:pressed{background:#8a2a2a;}")
        self.btn_estop.clicked.connect(self._emergency)
        bl.addWidget(self.btn_estop)
        btn_clear_log = QPushButton("清日志")
        btn_clear_log.clicked.connect(lambda: self.log_panel.clear_log())
        bl.addWidget(btn_clear_log)

        # 页面
        self.monitor = MonitorPage()
        self.monitor.set_temp_alert(self._settings.temp_alert_c)
        self.plot = PlotPage(window_s=self._settings.plot_window_s)
        self.control = ControlPage()
        self.motion = MotionPage(self._settings)
        tabs = QTabWidget()
        tabs.addTab(self.monitor, "监控")
        tabs.addTab(self.plot, "曲线")
        tabs.addTab(self.control, "控制")
        tabs.addTab(self.motion, "运动")

        # 日志面板（暗色，可折叠高度）
        self.log_panel = LogPanel()
        self.log_panel.setMaximumBlockCount(1000)
        split = QSplitter(Qt.Vertical)
        split.addWidget(tabs)
        split.addWidget(self.log_panel)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)
        lay.addWidget(split, 1)
        self.setCentralWidget(central)

    def _wire(self):
        self.bridge.sig_log.connect(self.log_panel.append_line)
        self.bridge.sig_done.connect(self._on_done)
        self.control.cmd.connect(self._on_ctrl_cmd)
        self.control.tcp_req.connect(self._on_get_tcp)
        self.control.set_speed.connect(self._on_set_speed)
        self.motion.move_j.connect(self._on_move_j)
        self.motion.move_mit.connect(self._on_move_mit)

    # ================= 串口 =================
    def _refresh_ports(self):
        self.combo.clear()
        for p in transport.find_ports():
            self.combo.addItem(f"{p['device']}  ({p['description']})", p["device"])
        if self.combo.count() == 0:
            self.combo.addItem("（未找到串口 — 需板载 CDC 或 dialout 权限）", None)

    def _current_device(self):
        return self.combo.currentData()

    # ================= 连接 =================
    def _toggle_connect(self):
        if self.session is not None:
            self._disconnect()
            return
        device = self._current_device()
        if not device:
            self._log_ui("[ERR] 未选择有效串口")
            return
        try:
            sess = Session(log=self.bridge.sig_log.emit)
            sess.connect(device)
        except Exception as e:  # noqa: BLE001
            self._log_ui(f"[ERR] 连接失败: {e}")
            return
        self.session = sess
        self._last_seq = None
        self._last_seq_t = 0.0
        self._fps = 0.0
        self._was_online = False
        self._fault_logged = False
        self._ui_n = 0
        self.plot.set_joints(0)
        self.motion.set_joints(0)
        self._log_ui(f"[INFO] 已连接 {device}")
        self._run("固件版本", sess.client.get_firmware,
                  require_online=False, on_done=self._on_firmware)

    def _disconnect(self):
        if self.session is not None:
            self.session.close()
            self.session = None
        self._was_online = False
        self._last_seq = None
        self._busy = False
        self._cmd_seq += 1              # 作废所有在途 sig_done token
        self._pending_token = None
        self._pending_done = None
        self._fault_logged = False
        self._ui_n = 0
        self.plot.set_joints(0)
        self.motion.set_joints(0)
        self._log_ui("[INFO] 已断开")
        self._set_online_ui(False)
        self._lock_motion("未连接")

    @staticmethod
    def _err_text(name: str, code) -> str:
        if code is None:
            return f"[ERR] {name}: 无应答/超时"
        txt = P.ERR_TEXT.get(code, f"未知错误码 0x{code:02X}")
        return f"[ERR] {name} 被固件拒绝: {txt} (code 0x{code:02X})"

    # ================= 命令执行 =================
    def _run(self, name, fn, require_online=True, on_done=None):
        if self._busy:
            self._log_ui(f"[WARN] 忙，忽略 {name}")
            return
        if self.session is None:
            self._log_ui(f"[WARN] 未连接，忽略 {name}")
            return
        if require_online and not self.session.online:
            self._log_ui(f"[WARN] 离线，忽略 {name}")
            return
        self._cmd_seq += 1
        tok = self._cmd_seq
        self._pending_token = tok
        self._pending_done = on_done
        self._busy = True
        self._apply_busy()

        def target():
            try:
                res = fn()
            except Exception as e:  # noqa: BLE001
                self.bridge.sig_log.emit(f"[ERR] {name} 异常: {e}")
                res = False
            self.bridge.sig_done.emit(tok, name, res)

        threading.Thread(target=target, name=f"cmd-{name}", daemon=True).start()

    def _on_done(self, tok, name, res):
        if tok != self._pending_token:      # 过期命令（断开/重连后迟到），忽略
            return
        self._busy = False
        handler = self._pending_done
        self._pending_token = None
        self._pending_done = None
        self._apply_busy()
        if handler is not None:
            handler(res)

    def _on_firmware(self, ver):
        self.fw_lbl.setText(f"固件: {ver if ver else '（未应答）'}")

    # ================= 控制页命令 =================
    def _on_ctrl_cmd(self, name):
        sess = self.session
        if sess is None or sess.client is None:
            return
        if name == "reset":
            self._confirm_reset()
            return
        if name == "enable":
            st = sess.status
            if st is not None and (st.mode == 6 or st.has_fault):
                self._log_ui("[ERR] 存在 FAULT/急停锁存 —— 先 [清故障] 或 [复位]，enable 未发送")
                return
        if name not in CTRL_CMDS:
            return
        label, fn = CTRL_CMDS[name]
        self._run(label, lambda: fn(sess.client), on_done=self._after_cmd)

    def _after_cmd(self, ok):
        pass  # 具体日志已由 client 内 log 输出；此处用于收尾刷新

    def _confirm_reset(self):
        ret = QMessageBox.question(
            self, "确认复位", "确认复位？\n将中断当前运动并重启控制栈。\n"
            "（急停锁存 EMERGENCY 需 reset 才能退出）",
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if ret == QMessageBox.Ok and self.session and self.session.client:
            self._run("复位", self.session.client.reset, on_done=self._after_cmd)
            self._lock_motion("已复位 — 请重新解锁")

    def _on_get_tcp(self):
        sess = self.session
        if sess is None:
            return
        self._run("读取末端位姿", sess.client.get_tcp, on_done=self._show_tcp)

    def _show_tcp(self, res):
        if res is None:
            self.control.set_tcp_text("未应答")
            return
        pos, rpy = res
        self.control.set_tcp_text(
            f"x={pos[0]:.3f} y={pos[1]:.3f} z={pos[2]:.3f} | "
            f"roll={rpy[0]:.3f} pitch={rpy[1]:.3f} yaw={rpy[2]:.3f}")

    def _on_set_speed(self, v):
        sess = self.session
        if sess is not None and sess.client is not None:
            self._run("速度倍率", lambda: sess.client.set_speed_percent(v))

    # ================= 急停 =================
    def _emergency(self):
        self._log_ui("[ERR] 急停按钮按下")
        sess = self.session
        if sess is not None and sess.client is not None:
            sess.client.emergency_now()
        self._lock_motion("急停已按下 — 需 [复位 reset] 解除 EMERGENCY 后重新解锁")

    # ================= 运动页下发（含 Δq 确认） =================
    def _on_move_j(self, qs, speed):
        sess = self.session
        st = sess.status if sess else None
        if st is None or st.n != len(qs):
            self._log_ui("[ERR] move_j: 尚无状态帧/关节数不符，未发送")
            return
        cur = [j.q for j in st.joints]
        plan = checks.plan_motion(cur, qs, self._settings.confirm_threshold)
        if plan.needs_confirm:
            if not self._confirm_move(plan):
                self._log_ui("[INFO] move_j 已取消")
                return

        def done(res):
            ok, code = res
            if ok:
                self._log_ui(f"[OK] move_j 已发送 sp={speed}")
            else:
                self._log_ui(self._err_text("move_j", code))

        self._run("move_j", lambda: sess.client.move_j(qs, speed), on_done=done)

    def _on_move_mit(self, idx, q, dq, kp, kd, tau):
        sess = self.session
        st = sess.status if sess else None
        if st is None or idx >= st.n:
            self._log_ui("[ERR] move_mit: 无状态帧或关节序号非法，未发送")
            return
        plan = checks.plan_motion([st.joints[idx].q], [q],
                                  self._settings.confirm_threshold)
        if plan.needs_confirm:
            if not self._confirm_move(plan, labels=[f"J{idx + 1}"]):
                self._log_ui("[INFO] move_mit 已取消")
                return

        def done(res):
            ok, code = res
            if ok:
                self._log_ui(f"[OK] move_mit J{idx + 1} 单帧已发送")
            else:
                self._log_ui(self._err_text("move_mit", code))

        self._run("move_mit",
                  lambda: sess.client.move_mit(idx, q, dq, kp, kd, tau),
                  on_done=done)

    def _confirm_move(self, plan, labels=None) -> bool:
        lines = checks.confirm_lines(plan, labels=labels)
        msg = "以下关节目标与当前位置差较大，确认继续？\n\n" + "\n".join(lines)
        ret = QMessageBox.warning(self, "运动确认", msg,
                                  QMessageBox.Ok | QMessageBox.Cancel,
                                  QMessageBox.Cancel)
        return ret == QMessageBox.Ok

    # ================= 采样刷新 =================
    def _tick(self):
        sess = self.session
        onl = bool(sess is not None and sess.online)
        if sess is None:
            if self._was_online:
                self._was_online = False
            self._set_online_ui(False)
            return
        st = sess.status

        if onl and not self._was_online:
            self._was_online = True
            self._log_ui("[INFO] 在线 — 状态帧 100Hz 接收中")
        elif not onl and self._was_online:
            self._was_online = False
            self._log_ui("[WARN] 离线 — 超过 500ms 未收到状态帧")
            self._lock_motion("离线")

        fault_now = st is not None and (st.mode == 6 or st.has_fault)
        if fault_now:
            if not self._safety_latched:
                self._safety_latched = True
                self._lock_motion("检测到 FAULT / EMERGENCY — 需 [清故障] 或 [复位]")
                self._fault_logged = False
            if not self._fault_logged and st is not None:
                self._fault_logged = True
                reason = "急停锁存 EMERGENCY（需 [复位 reset]）" if st.mode == 6 \
                    else "FAULT 标志置位（可先试 [清故障 clear_faults]，若反复出现用 [复位 reset]）"
                self._log_ui(f"[WARN] 检测到 {reason} —— 使能与运动已锁定")
        else:
            self._safety_latched = False

        if st is not None:
            # N 自适应
            if st.n != self._ui_n:
                self._ui_n = st.n
                self.plot.set_joints(st.n)
                self.motion.set_joints(st.n)
            # 帧率（GUI 抽稀估计，仅展示用；丢帧计数用读线程 sess.drops()）
            now = time.monotonic()
            if self._last_seq is not None:
                dseq = (st.seq - self._last_seq) & (P.SEQ_MOD - 1)
                dt = now - self._last_seq_t
                if dseq > 0 and dt > 0:
                    self._fps = dseq / dt
            self._last_seq = st.seq
            self._last_seq_t = now
            bad = sess.bad_frames()
            self.monitor.update_from(st, bad, self._fps, sess.drops())

        self._set_online_ui(onl)
        self.control.set_online(onl)
        self.control.set_busy(self._busy)
        self.motion.set_online(onl)
        self.motion.set_busy(self._busy)
        self.motion.set_fault_blocked(fault_now)
        if st is not None:
            self.control.refresh_fault_hint(st)

    def _tick_plot(self):
        sess = self.session
        if sess is not None and not self.plot.frozen:
            self.plot.refresh(sess.model)

    # ================= UI 状态 =================
    def _set_online_ui(self, onl: bool):
        self.dot.setText("● 在线" if onl else "● 离线")
        self.dot.setStyleSheet(
            "color:#6fdd8b;font-weight:bold;" if onl
            else "color:#ff6b6b;font-weight:bold;")
        self.btn_conn.setText("断开" if self.session is not None else "连接")
        self.control.set_online(onl)
        self.motion.set_online(onl)

    def _apply_busy(self):
        self.control.set_busy(self._busy)
        self.motion.set_busy(self._busy)

    def _lock_motion(self, reason: str):
        self.motion.lock(reason)

    def _log_ui(self, msg: str):
        self.bridge.sig_log.emit(msg)

    def closeEvent(self, event):
        if self.session is not None:
            try:
                self.session.close()
            except Exception:  # noqa: BLE001
                pass
        super().closeEvent(event)
