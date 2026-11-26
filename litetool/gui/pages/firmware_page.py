"""固件升级页 —— USB DFU（0483:DF11），复用 studio 的 DfuSe 引擎。

三步：**选镜像 → 看摘要并确认 → 开始**。两条合法起点：

* 连着应用态（常规升级）：先失能、再发 `CMD_ENTER_DFU (0x15)`；
* **板子已经停在 ROM bootloader 里**（救援）：没有应用态会话，跳过失能/进 DFU，
  直接从"等 DFU 设备"起跑。这条路是 issue #152 的落点：连不上正是因为它停在
  bootloader 里，而"先连接才能烧"会把唯一能救它的动作锁在外面。

⚠ 烧录相位内取消不生效（擦一半比烧完更糟）；其他相位之间可以取消。升级期间
界面连不上控制器是**正常的** —— 设备在 bootloader 里，不在应用态。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                             QPushButton, QVBoxLayout, QWidget)

from litetool import dfu
from litetool.dfu import controller as dfu_controller
from litetool.dfu import job
from litetool.gui.pages.common import group, row

PHASE_TEXT = {
    job.PHASE_VALIDATE: "校验镜像",
    job.PHASE_DISARM: "失能机械臂",
    job.PHASE_ENTER_DFU: "进入 bootloader",
    job.PHASE_WAIT_DFU: "等待 DFU 设备",
    job.PHASE_FLASH: "擦写并读回校验",
    job.PHASE_DETACH: "复位回应用",
    job.PHASE_RECONNECT: "重新连接控制器",
    job.PHASE_DONE: "完成",
}

#: 镜像大小上限（字节）。1MB Flash 的镜像远小于它；再加一道内存闸。
MAX_IMAGE_BYTES = 4 * 1024 * 1024

_REASON_TEXT = {
    "image_unreadable": "读不出这份镜像：它既不是合法的 Intel HEX，也不是 .bin。"
                        "请向供应商索取官方的 .hex",
    "image_not_at_app_base": "镜像的起始地址不是 0x08000000：应用只能烧到那里。"
                             "请确认选的是固件而不是别的固件段",
    "image_too_large": "镜像超出控制器 1 MB 的 Flash：请确认选对了文件",
    "image_covers_protected": "镜像覆盖了许可证与出厂标定所在的扇区（擦掉不可恢复）："
                              "这份镜像不能用，请向供应商索取正确的固件",
    "arm_enabled": "机械臂没有失能，已中止：带着使能进 bootloader 会让电机松开、臂下垂",
    "dfu_not_entered": "控制器没有接受进入 bootloader 的请求（登记被撤销或未执行）："
                       "机械臂原样可用，确认已失能后重试",
    "dfu_device_absent": "进入 bootloader 后没有找到 DFU 设备（0483:DF11）："
                         "请检查 USB 线；Windows 上需要 ST 的 WinUSB 驱动",
    "dfu_permission_denied": "打不开 DFU 设备（权限不足）：板子已经在 bootloader 里，"
                             "但当前用户没有权限访问它。Linux 上需要一条 udev 规则："
                             'SUBSYSTEM=="usb", ATTR{idVendor}=="0483", '
                             'ATTR{idProduct}=="df11", MODE="0666"',
    "engine_unavailable": "这台机器上没有可用的 USB 烧录引擎",
    "flash_failed": "烧录失败",
    "reconnect_failed": "固件已经写入并通过读回校验，但没能重新连上控制器",
    "cancelled": "升级已取消（若已进入烧录相位，取消不再生效）",
    "not_connected": "机械臂未连接：请先在顶栏连接设备",
}


def _reason_text(reason: Optional[str], message: str = "") -> str:
    """短码 → 面向操作员的一句话；短码不认识时如实回服务端/引擎的消息。"""
    key = reason or ""
    base = _REASON_TEXT.get(key)
    if key in ("dfu_device_absent", "dfu_permission_denied"):
        # 这两条的 message 本身就是可执行的说明（缺什么 / 怎么修），不要覆盖它。
        return message or base or key
    if key == "engine_unavailable":
        detail = message or "未找到 libusb 后端"
        return (f"这台机器上没有可用的 USB 烧录引擎：{detail}"
                "（需要 pyusb 与 libusb；Windows 上还要装 ST 的 WinUSB 驱动）")
    if key == "flash_failed":
        tail = ("设备已被尽量擦回空白，可以直接重试；若反复失败需要 SWD 探针救机"
                if message else "请重试")
        return f"烧录失败：{message}。{tail}" if message else (base or "烧录失败")
    if key == "reconnect_failed":
        return message or (base or key)
    if key == "arm_enabled" and message:
        return f"{base}（{message}）" if base else message
    if key == "dfu_not_entered" and message:
        return f"{base}（{message}）" if base else message
    return base or message or key or "升级失败"


class FirmwarePage(QWidget):
    """固件升级页。升级线程 → 页面信号 → GUI 线程更新。"""

    #: 升级线程发出（Qt 自动排队到 GUI 线程）。
    sig_progress = pyqtSignal(object)
    sig_result = pyqtSignal(object)
    sig_upgrading = pyqtSignal(bool)
    sig_log = pyqtSignal(str)
    #: 升级线程请求界面线程去重连（阻塞 RPC 的请求半边）。
    reconnect_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._online = False
        self._engine = dfu.engine
        self._engine_ready = False
        self._engine_checked = False
        self._engine_label = ""
        self._worker: Any = None
        self._summary: Any = None
        self._blob: Optional[bytes] = None
        self._result: Any = None
        self._running = False
        self._controller: Optional[dfu_controller.UpgradeController] = None
        self._dfu_present = False
        self._dfu_location = ""
        self._port = ""
        self._firmware = ""
        self._last_phase: Optional[str] = None
        self._log_cb: Callable[[str], None] = lambda _m: None
        self._upgrading_cb: Callable[[bool], None] = lambda _b: None
        self._confirm_cb: Callable[[bool], bool] = self._confirm_dialog
        self._reconnect_override: Optional[Callable[[str], tuple]] = None
        self._reconnect_event = threading.Event()
        self._reconnect_result: Optional[tuple] = None
        self._poll_pending = False
        self._build_ui()
        self.sig_progress.connect(self._on_progress)
        self.sig_result.connect(self._on_result)
        self.sig_upgrading.connect(self._on_upgrading)
        self.sig_log.connect(self._on_log)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(10_000)          # 板子可能在我们看不见的时候插上
        QTimer.singleShot(0, self._poll)

    # ------------------------------------------------------------------ 注入
    def set_worker(self, worker: Any) -> None:
        self._worker = worker

    def set_log(self, fn: Callable[[str], None]) -> None:
        self._log_cb = fn

    def set_upgrading_cb(self, fn: Callable[[bool], None]) -> None:
        """升级开始/结束 → 主窗口锁/解锁顶栏与运动入口。"""
        self._upgrading_cb = fn

    def set_engine(self, engine_module: Any) -> None:
        """测试注入 `litetool.dfu.fake.FakeEngine`；生产用默认的真引擎。"""
        self._engine = engine_module
        self._poll()

    def set_confirm(self, fn: Callable[[bool], bool]) -> None:
        """测试替换确认框；参数是 `from_dfu`。"""
        self._confirm_cb = fn

    def set_reconnect_override(self, fn: Optional[Callable[[str], tuple]]) -> None:
        """测试替换"界面线程重连"那段；生产走 `reconnect_requested` 信号。"""
        self._reconnect_override = fn

    def set_link_info(self, port: str, firmware: str) -> None:
        self._port = str(port or "")
        self._firmware = str(firmware or "")
        self._update_status()

    # ------------------------------------------------------------------ 主窗口回调
    def set_online(self, onl: bool):
        self._online = bool(onl)
        if onl:
            self._dfu_present = False
            self._dfu_location = ""
        else:
            self._schedule_poll()
        self._update_status()
        self._refresh_buttons()

    def is_running(self) -> bool:
        return bool(self._running or (self._controller is not None
                                     and self._controller.is_running()))

    def refresh_status(self) -> None:
        """进页面/连接失败后重探一次 DFU（不阻塞：排到事件循环下一拍）。"""
        if not self._running:
            self._schedule_poll()

    # ------------------------------------------------------------------ RPC
    def reconnect_finished(self, ok: bool, port: str, firmware: str, error: str) -> None:
        """由主窗口在 GUI 线程调用 —— 唤醒升级线程里的重连等待。"""
        self._reconnect_result = (bool(ok), str(port or ""), str(firmware or ""),
                                  str(error or ""))
        self._reconnect_event.set()

    def _reconnect_rpc(self, hint: str) -> tuple:
        if self._reconnect_override is not None:
            return self._reconnect_override(hint)
        self._reconnect_event.clear()
        self._reconnect_result = None
        self.reconnect_requested.emit(str(hint or ""))
        if not self._reconnect_event.wait(dfu_controller.RECONNECT_RPC_TIMEOUT_S):
            return (False, "", "", "界面没有响应重连请求")
        return self._reconnect_result or (False, "", "", "没有重连结果")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.title = QLabel("固件升级（USB DFU）")
        self.title.setStyleSheet("font-weight:bold;font-size:14px;")
        self.state_lbl = QLabel("未连接")
        self.state_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")
        head = QHBoxLayout()
        head.addWidget(self.title)
        head.addWidget(self.state_lbl)
        head.addStretch(1)

        self.engine_lbl = QLabel("")
        self.engine_lbl.setWordWrap(True)
        self.engine_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")
        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")

        # ---- 选镜像 ----
        self.btn_pick = QPushButton("选择固件文件")
        self.btn_pick.clicked.connect(self._on_pick)
        self.file_lbl = QLabel("")
        self.file_lbl.setStyleSheet("font-family:'DejaVu Sans Mono';font-size:12px;")
        self.file_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.error_lbl = QLabel("")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setStyleSheet("color:#b33a3a;font-size:12px;")
        self.error_lbl.setVisible(False)
        pick_row = row(self.btn_pick, self.file_lbl)
        pick_box = group("镜像文件", pick_row, self.error_lbl)

        # ---- 摘要 ----
        self.ver_lbl = QLabel("—")
        self.size_lbl = QLabel("—")
        self.range_lbl = QLabel("—")
        self.format_lbl = QLabel("—")
        self.holes_lbl = QLabel("—")
        self.sha_lbl = QLabel("—")
        for lb in (self.ver_lbl, self.size_lbl, self.range_lbl, self.format_lbl,
                   self.holes_lbl):
            lb.setStyleSheet("font-family:'DejaVu Sans Mono';font-size:12px;")
        self.sha_lbl.setStyleSheet("font-family:'DejaVu Sans Mono';font-size:12px;")
        self.sha_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.sha_lbl.setWordWrap(True)
        self.version_note_lbl = QLabel("")
        self.version_note_lbl.setWordWrap(True)
        self.version_note_lbl.setStyleSheet("color:#9a6400;font-size:12px;")
        self.version_note_lbl.setVisible(False)
        grid = QGridLayout()
        grid.addWidget(QLabel("版本"), 0, 0)
        grid.addWidget(self.ver_lbl, 0, 1)
        grid.addWidget(QLabel("大小"), 0, 2)
        grid.addWidget(self.size_lbl, 0, 3)
        grid.addWidget(QLabel("地址范围"), 1, 0)
        grid.addWidget(self.range_lbl, 1, 1, 1, 3)
        grid.addWidget(QLabel("格式"), 2, 0)
        grid.addWidget(self.format_lbl, 2, 1)
        grid.addWidget(QLabel("空洞"), 2, 2)
        grid.addWidget(self.holes_lbl, 2, 3)
        grid.addWidget(QLabel("sha256"), 3, 0)
        grid.addWidget(self.sha_lbl, 3, 1, 1, 3)
        self.summary_box = QGroupBox("镜像摘要")
        sl = QVBoxLayout(self.summary_box)
        sl.addLayout(grid)
        sl.addWidget(self.version_note_lbl)
        self.summary_box.setVisible(False)

        # ---- 安全确认 ----
        self.safety_lbl = QLabel("")
        self.safety_lbl.setWordWrap(True)
        self.safety_lbl.setStyleSheet("color:#9a6400;font-size:12px;")
        self.safety_cb = QCheckBox("我确定机械臂在安全状态下，且升级期间不再控制它")
        self.safety_cb.toggled.connect(lambda _on: self._refresh_buttons())
        safety_box = group("开始之前必须确认", self.safety_lbl, self.safety_cb)

        # ---- 动作 ----
        self.btn_start = QPushButton("开始升级")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel = QPushButton("取消升级")
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_reset = QPushButton("重置")
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_cancel.setVisible(False)
        self.btn_reset.setEnabled(False)
        action_row = row(self.btn_start, self.btn_cancel, self.btn_reset)

        # ---- 进度 ----
        self.phase_lbl = QLabel("")
        self.phase_lbl.setStyleSheet("font-weight:bold;font-size:12px;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.detail_lbl = QLabel("")
        self.detail_lbl.setWordWrap(True)
        self.detail_lbl.setStyleSheet("font-family:'DejaVu Sans Mono';font-size:12px;"
                                      "color:#8a97a4;")
        self.progress_box = group("升级进度", self.phase_lbl, self.bar, self.detail_lbl)
        self.progress_box.setVisible(False)

        # ---- 终局 ----
        self.result_lbl = QLabel("")
        self.result_lbl.setWordWrap(True)
        self.warning_lbl = QLabel("")
        self.warning_lbl.setWordWrap(True)
        self.warning_lbl.setStyleSheet("color:#9a6400;font-size:12px;")
        self.warning_lbl.setVisible(False)
        self.result_box = group("结果", self.result_lbl, self.warning_lbl)
        self.result_box.setVisible(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addLayout(head)
        lay.addWidget(self.engine_lbl)
        lay.addWidget(self.status_lbl)
        lay.addWidget(pick_box)
        lay.addWidget(self.summary_box)
        lay.addWidget(safety_box)
        lay.addLayout(action_row)
        lay.addWidget(self.progress_box)
        lay.addWidget(self.result_box)
        lay.addStretch(1)
        self._update_status()
        self._refresh_buttons()

    # ------------------------------------------------------------------ 文件/摘要
    def _on_pick(self):
        path, _selected = QFileDialog.getOpenFileName(
            self, "选择固件镜像", "",
            "固件镜像 (*.hex *.bin);;所有文件 (*)")
        if path:
            self.load_image(path)

    def load_image(self, path: str) -> None:
        try:
            size = os.path.getsize(path)
        except OSError as e:
            self._reject_image(f"读不出文件: {e}")
            return
        if size > MAX_IMAGE_BYTES:
            self._reject_image(
                _reason_text("image_too_large",
                             f"文件 {size} B 超过 {MAX_IMAGE_BYTES} B 上限"))
            return
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            self._reject_image(f"读不出文件: {e}")
            return
        self.inspect_bytes(Path(path).name, data)

    def _reject_image(self, text: str) -> None:
        """换镜像失败时**必须把旧摘要清掉** —— 留着旧摘要 + 新错误最危险。"""
        self._summary = None
        self._blob = None
        self.summary_box.setVisible(False)
        self._result = None
        self.result_box.setVisible(False)
        self._show_image_error(text)
        self._refresh_buttons()

    def inspect_bytes(self, name: str, data: bytes) -> None:
        """离线校验一份镜像。测试直接调这里（不经过文件对话框）。"""
        try:
            blob, summary = dfu.inspect(name, data)
        except dfu.ImageError as e:
            self._reject_image(_reason_text(e.reason, str(e)))
            return
        self._summary = summary
        self._blob = blob
        self._show_image_error("")
        self._show_summary(summary)
        self._result = None
        self.result_box.setVisible(False)
        self.progress_box.setVisible(False)
        self._log(f"[INFO] 镜像已校验: {summary.name} · {summary.size} B · "
                  f"版本 {summary.version or '未识别'} · sha256 {summary.sha256[:12]}")
        self._refresh_buttons()

    def _show_image_error(self, text: str) -> None:
        self.error_lbl.setText(text)
        self.error_lbl.setVisible(bool(text))
        self.file_lbl.setText("" if text else self.file_lbl.text())

    def _show_summary(self, summary) -> None:
        self.summary_box.setVisible(True)
        self.file_lbl.setText(summary.name)
        self.ver_lbl.setText(summary.version or
                             f"未识别（{summary.version_note or '—'}）")
        self.size_lbl.setText(f"{summary.size} B")
        end = summary.base + summary.size - 1
        self.range_lbl.setText(f"0x{summary.base:08X}..0x{end:08X}")
        self.format_lbl.setText(summary.format)
        self.holes_lbl.setText(f"{summary.holes} 段（按 0xFF 填充）")
        self.sha_lbl.setText(summary.sha256)
        self.version_note_lbl.setText(summary.version_note or "")
        self.version_note_lbl.setVisible(bool(summary.version_note))

    # ------------------------------------------------------------------ 状态
    def _schedule_poll(self) -> None:
        if self._poll_pending:
            return
        self._poll_pending = True
        QTimer.singleShot(0, self._poll)

    def _poll(self) -> None:
        self._poll_pending = False
        if self._running:
            return
        try:
            self._engine_ready = bool(self._engine.available())
            label = str(self._engine.backend_status())
        except Exception:                                        # noqa: BLE001
            self._engine_ready = False
            label = "引擎状态读取失败"
        self._engine_checked = True
        self._engine_label = label
        dev = None
        if not self._online and self._engine_ready:
            try:
                dev = self._engine.find_device()
            except Exception as e:                               # noqa: BLE001
                self._dfu_present = False
                self._dfu_location = ""
                self._log(f"[WARN] 枚举 USB 设备失败: {type(e).__name__}: {e}")
            else:
                self._dfu_present = dev is not None
                self._dfu_location = dfu.device_location(dev) if dev is not None else ""
        else:
            self._dfu_present = False
            self._dfu_location = ""
        self._update_status()
        self._refresh_buttons()

    def _from_dfu(self) -> bool:
        return (not self._online) and self._dfu_present

    def _update_status(self) -> None:
        if self._running:
            state, color = "升级中", "#9a6400"
        elif self._online:
            state, color = "已连接", "#1f6fb2"
        elif self._dfu_present:
            state, color = "DFU", "#9a6400"
        else:
            state, color = "未连接", "#8a97a4"
        self.state_lbl.setText(state)
        self.state_lbl.setStyleSheet(f"color:{color};font-size:12px;")

        if not self._engine_checked:
            self.engine_lbl.setText("烧录引擎：检查中…")
            self.engine_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")
        elif self._engine_ready:
            self.engine_lbl.setText(f"烧录引擎可用：{self._engine_label}")
            self.engine_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")
        else:
            self.engine_lbl.setText(
                f"烧录引擎不可用：{self._engine_label}"
                "（需要 pyusb 与 libusb；Windows 上还要装 ST 的 WinUSB 驱动）")
            self.engine_lbl.setStyleSheet("color:#b33a3a;font-size:12px;")

        if self._running:
            self.status_lbl.setText(
                "升级进行中 —— 控制器在 bootloader 里，升级结束前界面连不上它，"
                "这是正常的。")
        elif self._from_dfu():
            text = ("检测到控制器停在 bootloader（DFU）里：它不在应用态，所以顶栏"
                    "连不上它 —— 这不是没插线。点下面的「烧录并复位回应用」把它写回来。")
            if self._dfu_location:
                text += f"\n找到的控制器位于 USB {self._dfu_location}，请确认这就是你要烧录的控制器。"
            self.status_lbl.setText(text)
        elif self._online:
            self.status_lbl.setText(
                f"当前固件：{self._firmware or '—'} · 端口：{self._port or '—'}")
        else:
            self.status_lbl.setText(
                "未连接控制器 —— 连上之后才能升级。若板子停在 DFU 里，这里会单独提示。")

        if self._from_dfu():
            disarm = ("这次不会再失能一次 —— 应用早已停下，电机保持松开；"
                      "烧录完成后板子会复位回应用态")
        else:
            disarm = "升级会先让机械臂失能 —— 中途电机会松开，有重力负载就会下垂"
        self.safety_lbl.setText(
            f"• {disarm}\n"
            "• 升级期间无法急停 —— 设备在 bootloader 里，应用已停摆\n"
            "• 许可证与出厂标定所在的扇区不会被触碰；镜像若覆盖该区会被直接拒绝")

    def _refresh_buttons(self) -> None:
        running = self._running
        self.btn_pick.setEnabled(not running)
        self.btn_reset.setEnabled(not running and (self._summary is not None
                                                   or self._result is not None))
        self.btn_cancel.setVisible(running)
        self.btn_cancel.setEnabled(running)
        if not running:
            self.btn_cancel.setText("取消升级")
        from_dfu = self._from_dfu()
        can_start = (not running and self._worker is not None
                     and self._summary is not None
                     and self._engine_ready and (self._online or from_dfu)
                     and self.safety_cb.isChecked())
        self.btn_start.setEnabled(can_start)
        self.btn_start.setText("烧录并复位回应用" if from_dfu else "开始升级")
        self.btn_start.setToolTip(self._start_tooltip(from_dfu))

    def _start_tooltip(self, from_dfu: bool) -> str:
        if self._running:
            return "升级进行中"
        if self._worker is None:
            return "内部错误：SDK 未接入"
        if not self._engine_ready:
            return "烧录引擎不可用 —— 需要 pyusb 与 libusb；Windows 上还要装 ST 的 WinUSB 驱动"
        if self._summary is None:
            return "请先选择并校验一份固件镜像"
        if not (self._online or from_dfu):
            return "请先连接控制器；若板子停在 bootloader 里，等它被检测到后可直接烧录"
        if not self.safety_cb.isChecked():
            return "请先确认机械臂处于安全状态"
        return ""

    # ------------------------------------------------------------------ 开始/取消
    def _on_start(self):
        if self._running or self._summary is None or self._blob is None:
            return
        from_dfu = self._from_dfu()
        if not (self._online or from_dfu):
            self._show_result_text("请先连接控制器，或把板子置于 DFU 状态。", error=True)
            return
        if not self.safety_cb.isChecked():
            self._show_result_text("请先勾选安全确认。", error=True)
            return
        if not self._confirm_cb(from_dfu):
            return
        self._start_now(from_dfu)

    def _start_now(self, from_dfu: bool):
        if self._blob is None or self._summary is None or self._worker is None:
            return
        self._result = None
        self.result_box.setVisible(False)
        self.progress_box.setVisible(True)
        self.phase_lbl.setText("准备…")
        self.bar.setRange(0, 0)
        self.detail_lbl.setText("")
        self._last_phase = None
        self._running = True
        self._refresh_buttons()
        self._log(f"[INFO] 固件升级开始: {self._summary.name} "
                  f"({self._summary.size} B) · "
                  f"{'从 bootloader 起跑' if from_dfu else '从应用态起跑'}")
        self._controller = dfu_controller.UpgradeController(
            sdk=self._worker, engine_module=self._engine,
            reconnect=self._reconnect_rpc,
            on_progress=self.sig_progress.emit,
            on_result=self.sig_result.emit,
            on_log=self.sig_log.emit,
            on_upgrading=self.sig_upgrading.emit)
        self._controller.start(self._blob, self._summary.base, self._summary,
                               from_dfu=from_dfu)

    def _on_cancel(self):
        if self._controller is not None and self._running:
            self._controller.cancel()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("正在取消…")
            self._log("[WARN] 已请求取消升级（烧录相位内不生效）")

    def _on_reset(self):
        if self._running:
            return
        self._summary = None
        self._blob = None
        self._result = None
        self.summary_box.setVisible(False)
        self.progress_box.setVisible(False)
        self.result_box.setVisible(False)
        self.error_lbl.setVisible(False)
        self.error_lbl.setText("")
        self.file_lbl.setText("")
        self.phase_lbl.setText("")
        self.detail_lbl.setText("")
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self._last_phase = None
        self._refresh_buttons()

    # ------------------------------------------------------------------ 信号槽
    def _on_progress(self, progress):
        if not isinstance(progress, job.Progress):
            return
        phase = PHASE_TEXT.get(progress.phase, progress.phase)
        self.phase_lbl.setText(f"升级进行中 · {phase}")
        if progress.phase == job.PHASE_FLASH and progress.total > 0:
            self.bar.setRange(0, progress.total)
            self.bar.setValue(min(progress.done, progress.total))
        elif progress.phase == job.PHASE_DONE:
            self.bar.setRange(0, 1)
            self.bar.setValue(1)
        else:
            self.bar.setRange(0, 0)          # 忙碌指示
        if progress.total > 0:
            self.detail_lbl.setText(f"{progress.detail}  [{progress.done}/"
                                    f"{progress.total} B]")
        else:
            self.detail_lbl.setText(progress.detail)
        if progress.phase != self._last_phase:
            self._last_phase = progress.phase
            self._log(f"[DFU] {phase} — {progress.detail}")
        elif any(word in progress.detail for word in ("校验", "擦除", "manifest")):
            self._log(f"[DFU] {progress.detail}")

    def _on_result(self, result):
        if not isinstance(result, job.Result):
            return
        self._running = False
        self._result = result
        self.progress_box.setVisible(False)
        self.result_box.setVisible(True)
        if result.ok:
            text = "升级完成，设备已回到应用态并通过读回校验。"
            if result.version:
                text += f" 设备现在报告的版本：{result.version}"
            self.result_lbl.setText(text)
            self.result_lbl.setStyleSheet("color:#2e7d32;font-size:13px;")
            self._log(f"[OK] 固件升级完成 · 设备版本 {result.version or '未知'}")
        else:
            self._show_result_text(
                f"升级失败：{_reason_text(result.reason, result.message)}",
                error=True)
            self._log(f"[ERR] 固件升级失败({result.reason}): {result.message}")
        self.warning_lbl.setText(result.warning or "")
        self.warning_lbl.setVisible(bool(result.warning))
        self._refresh_buttons()
        QTimer.singleShot(0, self._poll)         # 结果出来后刷新 DFU 是否存在

    def _show_result_text(self, text: str, *, error: bool) -> None:
        self.result_box.setVisible(True)
        self.result_lbl.setText(text)
        self.result_lbl.setStyleSheet(
            "color:#b33a3a;font-size:13px;" if error else "color:#2e7d32;font-size:13px;")
        if error:
            self.warning_lbl.setVisible(False)

    def _on_upgrading(self, active: bool):
        self._running = bool(active)
        self._upgrading_cb(bool(active))
        self._update_status()
        self._refresh_buttons()

    def _on_log(self, msg: str):
        self._log_cb(msg)

    def _log(self, msg: str) -> None:
        self._log_cb(str(msg))

    # ------------------------------------------------------------------ 确认框
    def _confirm_dialog(self, from_dfu: bool) -> bool:
        if from_dfu:
            body = ("板子停在 bootloader 里：应用没有在跑，机械臂此刻没有力矩。\n\n"
                    "升级期间无法控制机械臂，也无法软件急停。烧录完成后会自动复位回应用态。\n\n"
                    "继续吗？")
        else:
            body = ("升级会先让机械臂失能 —— 电机会松开，有重力负载的机械臂会下垂。\n\n"
                    "升级期间无法控制机械臂，也无法软件急停。请确认手臂已放稳或有支撑。\n\n"
                    "继续吗？")
        return QMessageBox.question(
            self, "开始固件升级", body,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
