"""授权页 —— 读设备授权记录 + 在线激活。

只读/写 SDK 的两条授权命令（`0x2F` / `0x3F`），**不碰运动**；与运动解锁无关。
两段式流程（照 studio 的纪律）：

1. 在 SDK 所有者线程上读设备 UID（**不出网之前先拿到可信 UID**）；
2. 网络 POST 在**页面自建的线程**上跑 —— 它不碰串口，不能占住所有者线程；
3. 回到所有者线程写凭据 + 回读，回读才是"落位"的证据。

与 studio 同一套行为判据：
* 读失败/断线不抹掉上一次的授权记录（UID 是这一段唯一的交付物），只把它标成旧读数；
* 只有回读确认 `supported && activated` 才算激活成功，ACK 不算；
* 404 `not_found` 等错误码给出下一步动作，不只显示服务端原文。

错误文案尽量指向下一步动作（未激活 / 已使能 / 需要升级 / 网络不通）。
"""
from __future__ import annotations

import re
import threading
from typing import Any, Callable, Dict, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QFormLayout, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                             QPushButton, QVBoxLayout, QWidget)

from litetool import activation
from litetool.license_io import read_record, uid_of, write_license

STATE_TEXT = {
    "not_activated": "未激活",
    "activated": "已激活",
    "activated_factory": "已激活（产线模式）",
}

#: 隐私政策在服务站点上（站点上线前这个地址是 404，文案本身待法务定稿）。
PRIVACY_URL = "https://act.nexform.tech/privacy"

#: 授权功能从固件 1.8.0 起（与 studio 的 `_LICENSE_MIN_FW` 同值）。
LICENSE_MIN_FW = (1, 8, 0)

#: 同意书 —— 与 studio 的 `draft-4` **同一份文案**（逐项列出内容与用途）。
#: ⚠ 改文案必须改 `activation.CONSENT_TEXT_VERSION`：服务端记的是"用户同意了哪一版"。
CONSENT_TEXT = (
    "<b>激活注册信息同意书</b><br>"
    "激活会把下面这些内容发送给激活服务（act.nexform.tech）。每一项后面写了为什么要它"
    "——没有别的用途，也没有别的字段。<br><br>"
    "<b>姓名、手机号、单位、邮箱、微信号</b> —— 用于签发授权凭据，并在需要时联系到你"
    "（现场排障电话更快）。<br>"
    "<b>所在地区、所属行业、用途说明</b> —— 用于登记这台设备用在哪里、做什么，"
    "作为服务与统计的依据。<br>"
    "<b>设备 UID（24 位十六进制）</b> —— 用来定位这台机器：凭据只对它有效，"
    "换一台要重新签发。<br>"
    "<b>上位机 / SDK / 固件版本</b> —— 排查问题时判断你用的是哪一套，省一轮来回。<br><br>"
    "以上内容只用于签发授权、售后联系与服务登记；需要更正或删除请联系供应商。详见 "
    f"<a href='{PRIVACY_URL}'>隐私政策</a>。"
    f"<br><span style='color:#6b7683'>同意书版本 {activation.CONSENT_TEXT_VERSION}</span>"
)


class ActivationPage(QWidget):
    """授权页。`set_submit` / `set_log` 由主窗口注入，与参数页同一套。"""

    #: 网络段结束 → GUI 线程（跨线程 emit 是 Qt 的安全用法）。
    net_done = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._submit: Optional[Callable[..., Any]] = None
        self._log: Callable[[str], None] = lambda _m: None
        self._online = False
        self._enabled = False
        self._busy = False
        self._record: Optional[Dict[str, Any]] = None
        self._stale = False
        self._firmware = ""
        #: 链路代次：断线/重连/换板后，上一代链路上的异步结果一律作废。
        self._epoch = 0
        self._read_epoch = 0
        self._flow_epoch = 0
        self._net_epoch = 0
        self._write_epoch = 0
        self._request_fn = activation.request_license
        self._url = activation.activation_url()
        self._build_ui()
        self.net_done.connect(self._on_net_done)

    # ------------------------------------------------------------------ 注入
    def set_submit(self, fn: Callable[..., Any]) -> None:
        self._submit = fn

    def set_log(self, fn: Callable[[str], None]) -> None:
        self._log = fn

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.title = QLabel("授权")
        self.title.setStyleSheet("font-weight:bold;font-size:14px;")
        self.state_lbl = QLabel("未连接")
        self.state_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")
        self.url_lbl = QLabel(f"激活服务: {self._url}")
        self.url_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")
        self.btn_refresh = QPushButton("读取授权记录")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_copy_uid = QPushButton("复制 UID")
        self.btn_copy_uid.clicked.connect(self._copy_uid)
        self.btn_copy_uid.setEnabled(False)

        head = QHBoxLayout()
        head.addWidget(self.title)
        head.addWidget(self.state_lbl)
        head.addStretch(1)
        head.addWidget(self.btn_refresh)
        head.addWidget(self.btn_copy_uid)

        # ---- 记录 ----
        self.uid_lbl = QLabel("—")
        self.uid_lbl.setStyleSheet("font-family:'DejaVu Sans Mono';color:#61afef;")
        self.uid_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.state_val = QLabel("—")
        self.cust_lbl = QLabel("—")
        self.issued_lbl = QLabel("—")
        self.flags_lbl = QLabel("—")
        self.ver_lbl = QLabel("—")
        rec_grid = QGridLayout()
        rec_grid.addWidget(QLabel("UID"), 0, 0)
        rec_grid.addWidget(self.uid_lbl, 0, 1, 1, 3)
        rec_grid.addWidget(QLabel("状态"), 1, 0)
        rec_grid.addWidget(self.state_val, 1, 1)
        rec_grid.addWidget(QLabel("记录版本"), 1, 2)
        rec_grid.addWidget(self.ver_lbl, 1, 3)
        rec_grid.addWidget(QLabel("客户号"), 2, 0)
        rec_grid.addWidget(self.cust_lbl, 2, 1)
        rec_grid.addWidget(QLabel("签发日"), 2, 2)
        rec_grid.addWidget(self.issued_lbl, 2, 3)
        rec_grid.addWidget(QLabel("flags"), 3, 0)
        rec_grid.addWidget(self.flags_lbl, 3, 1)
        rec_box = QGroupBox("设备授权记录")
        rec_lay = QVBoxLayout(rec_box)
        rec_lay.addLayout(rec_grid)
        self.record_hint = QLabel("连接设备后点「读取授权记录」。")
        self.record_hint.setWordWrap(True)
        self.record_hint.setStyleSheet("color:#8a97a4;font-size:12px;")
        rec_lay.addWidget(self.record_hint)

        # ---- 注册表单 ----
        self.form_box = QGroupBox("在线激活（未激活设备）")
        form = QFormLayout(self.form_box)
        self.edit_name = QLineEdit()
        self.edit_phone = QLineEdit()
        self.edit_org = QLineEdit()
        self.edit_wechat = QLineEdit()
        self.edit_email = QLineEdit()
        self.edit_region = QLineEdit()
        self.edit_industry = QLineEdit()
        self.edit_purpose = QPlainTextEdit()
        self.edit_purpose.setMaximumHeight(64)
        # 输入框上限与 studio / 激活网站的表单同值（真正的门禁仍在 `build_request`）。
        self.edit_name.setMaxLength(32)
        self.edit_phone.setMaxLength(11)
        self.edit_org.setMaxLength(128)
        self.edit_wechat.setMaxLength(64)
        self.edit_email.setMaxLength(128)
        self.edit_region.setMaxLength(64)
        self.edit_industry.setMaxLength(64)
        self.edit_purpose.textChanged.connect(self._trim_purpose)
        for edit in (self.edit_name, self.edit_phone, self.edit_org, self.edit_wechat,
                     self.edit_email, self.edit_region, self.edit_industry):
            edit.textChanged.connect(lambda _text: self._update_buttons())
        # QPlainTextEdit.textChanged() 没有参数（QLineEdit 那把带 str）。
        self.edit_purpose.textChanged.connect(self._update_buttons)
        form.addRow("联系人*", self.edit_name)
        form.addRow("手机号*", self.edit_phone)
        form.addRow("单位*", self.edit_org)
        form.addRow("微信（可选）", self.edit_wechat)
        form.addRow("邮箱*", self.edit_email)
        form.addRow("地区*", self.edit_region)
        form.addRow("行业（可选）", self.edit_industry)
        form.addRow("用途（可选）", self.edit_purpose)
        self.consent_label = QLabel(CONSENT_TEXT)
        self.consent_label.setTextFormat(Qt.RichText)
        self.consent_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.consent_label.setOpenExternalLinks(True)
        self.consent_label.setWordWrap(True)
        self.consent_label.setStyleSheet("color:#8a97a4;font-size:12px;")
        # 与 studio 的"弹窗里逐项阅读"等价：默认收起，按钮展开；勾选框始终可见。
        self.btn_consent = QPushButton("查看《激活注册信息同意书》")
        self.btn_consent.setCheckable(True)
        self.btn_consent.toggled.connect(self._toggle_consent)
        form.addRow(self.btn_consent)
        form.addRow(self.consent_label)
        self.consent_label.setVisible(False)
        self.consent_cb = QCheckBox("我已阅读并同意《激活注册信息同意书》")
        self.consent_cb.toggled.connect(lambda _checked: self._update_buttons())
        form.addRow(self.consent_cb)
        self.btn_activate = QPushButton("提交并激活")
        self.btn_activate.clicked.connect(self._on_activate)
        self.form_hint = QLabel("")
        self.form_hint.setWordWrap(True)
        self.form_hint.setStyleSheet("color:#ffd166;font-size:12px;")
        foot = QHBoxLayout()
        foot.addWidget(self.btn_activate)
        foot.addStretch(1)
        form.addRow(foot)
        form.addRow(self.form_hint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(head)
        lay.addWidget(self.url_lbl)
        lay.addWidget(rec_box)
        lay.addWidget(self.form_box)
        lay.addStretch(1)
        self.form_box.setVisible(False)
        self._update_buttons()

    # ------------------------------------------------------------------ 主窗口回调
    def set_online(self, onl: bool):
        onl = bool(onl)
        if onl == self._online:
            # 重复通知不能打断进行中的读取/提交。
            self._update_buttons()
            return
        self._online = onl
        # 链路变了：上一代链路上的异步结果（读/网络/写）一律作废。
        self._epoch += 1
        if not onl:
            self._stale = False
            self._record = None
            self._clear_record_display()
            self.state_lbl.setText("未连接")
            self.state_lbl.setStyleSheet("color:#8a97a4;font-size:12px;")
            self.record_hint.setText("连接设备后点「读取授权记录」。")
            self.form_box.setVisible(False)
            self._show_hint("")
            self._set_busy(False)
            return

        self.state_lbl.setText("已连接")
        self.state_lbl.setStyleSheet("color:#61afef;font-size:12px;")
        self._update_buttons()
        if self._submit is not None:
            # 与 studio 一致：连上就自动读一次，不让操作员先点一下才知道 UID。
            self.refresh()

    def update_from(self, st):
        self._enabled = bool(getattr(st, "enabled", False)) if st is not None else False
        self._update_buttons()

    # ------------------------------------------------------------------ 读取
    def refresh(self):
        if self._submit is None or not self._online:
            return
        self._set_busy(True)
        self._read_epoch = self._epoch
        self.record_hint.setText("正在读取授权记录…")
        self._submit("读取授权记录", read_record, self._on_record)

    def _on_record(self, res):
        self._set_busy(False)
        if res is None:
            return
        if self._read_epoch != self._epoch:
            return                          # 读的过程中断线/换机：结果作废
        if not res.ok:
            self._show_read_error(res.text)
            return
        self._apply_record(res.value)

    def _show_read_error(self, text: str):
        """链路层失败也要保留上一次的记录 —— 与 `supported: null` 同一处理。"""
        self._stale = self._record is not None
        if self._record is not None:
            self.record_hint.setText(
                f"读取失败：{text} —— 下面是上一次读数（提交前会重新核对 UID）。")
            self.form_box.setVisible(not bool(self._record.get("activated")))
        else:
            self.record_hint.setText(f"读取失败：{text}")
            self.form_box.setVisible(False)
        self._update_buttons()

    def _apply_record(self, record: Dict[str, Any]):
        supported = record.get("supported")
        if supported is True:
            self._record = record
            self._stale = False
            state = record.get("stateName", "")
            self.state_val.setText(STATE_TEXT.get(state, state or "—"))
            self.uid_lbl.setText(record.get("uid") or "—")
            self.ver_lbl.setText(str(record.get("ver", "—")))
            cust = int(record.get("custId", 0))
            self.cust_lbl.setText(str(cust) if cust else "—")
            self.issued_lbl.setText(_format_issued(record.get("issued", 0)))
            flags = int(record.get("flags", 0))
            if record.get("factoryMode"):
                self.flags_lbl.setText("产线码")
            elif flags:
                self.flags_lbl.setText(f"0x{flags:X}")
            else:
                self.flags_lbl.setText("—")
            activated = bool(record.get("activated"))
            self.form_box.setVisible(not activated)
            if activated:
                self.record_hint.setText("已激活 —— 使能可用；授权记录不可修改。")
            else:
                self.record_hint.setText(
                    "未激活：`enable` 会被固件拒绝（0x10/0x08）。"
                    "填写下方注册信息并提交即可激活。")
            self._update_buttons()
            return

        # 这一次没读到 / 固件没有这条命令：上一次的记录如果还在，就保留它并标明是旧读数。
        # ⚠ UID 是这一段唯一的交付物，一次链路抖动不该把它从屏幕上抹掉
        #   （studio `docs/ACTIVATION.md` §7）。
        why = ("这台固件没有授权命令（版本过旧）—— 请升级固件"
               if supported is False else _unreadable_reason(self._firmware))
        self._stale = self._record is not None
        if self._record is not None:
            self.record_hint.setText(
                f"{why}。下面是上一次读数（提交前会重新核对 UID）。")
            self.form_box.setVisible(not bool(self._record.get("activated")))
        else:
            self._clear_record_display()
            self.record_hint.setText(f"{why}。无法确认授权状态，也不会提交注册信息。")
            self.form_box.setVisible(False)
        self._update_buttons()

    # ------------------------------------------------------------------ 激活
    def _contact_payload(self) -> Dict[str, str]:
        return {
            "name": self.edit_name.text(),
            "phone": self.edit_phone.text(),
            "organization": self.edit_org.text(),
            "wechatId": self.edit_wechat.text(),
            "email": self.edit_email.text(),
            "region": self.edit_region.text(),
            "industry": self.edit_industry.text(),
            "purpose": self.edit_purpose.toPlainText(),
        }

    def _form_problem(self) -> Optional[activation.ActivationError]:
        """按 `build_request` 的同一套判据看表单；返回第一个问题或 None。"""
        uid = uid_of(self._record)
        if uid is None:
            return activation.ActivationError("bad_uid", "还没有可信的设备 UID")
        try:
            activation.build_request({
                "uid": uid,
                "consent": {"granted": True},
                "contact": self._contact_payload(),
            })
        except activation.ActivationError as e:
            return e
        return None

    def _can_submit(self) -> bool:
        """与 studio 的 `canSubmitActivation` 同一组门禁（点击时还会再判一次）。"""
        if not self._online or self._busy or self._enabled:
            return False
        if self._record is None or self._record.get("activated"):
            return False
        if not self.consent_cb.isChecked():
            return False
        return self._form_problem() is None

    def _submit_tooltip(self) -> str:
        """按钮为什么不能按 —— 没有行内错误提示时，tooltip 是最近的说明。"""
        if self._busy:
            return "正在处理…"
        if not self._online:
            return "未连接设备"
        if self._record is None:
            return "请先读取授权记录"
        if self._record.get("activated"):
            return "这台设备已激活"
        if self._enabled:
            return "设备已使能 —— 请先在「整机」页失能"
        if not self.consent_cb.isChecked():
            return "请先阅读并勾选同意书"
        problem = self._form_problem()
        return _reason_text(problem) if problem is not None else ""

    def _on_activate(self):
        if self._submit is None:
            return
        if not self._online:
            self._show_hint("未连接设备。")
            return
        if self._busy:
            return
        if not self.consent_cb.isChecked():
            self._show_hint("请先阅读并勾选同意书。")
            return
        record = self._record
        uid = uid_of(record)
        if uid is None:
            self._show_hint("还没有可信的设备 UID —— 请先点「读取授权记录」。")
            return
        if self._enabled:
            # 固件要求失能才写 flash（ERR{0x3F,0x04}）；在这里先拦一道，省一次往返。
            self._show_hint("设备已使能 —— 请先在「整机」页失能，再提交激活。")
            return
        self._show_hint("")
        self._set_busy(True)

        # 第 1 段：所有者线程上重读 UID（记录可能是几分钟前的）。
        self._flow_epoch = self._epoch
        self._submit("激活前读取 UID", read_record, self._on_uid_fresh)

    def _on_uid_fresh(self, res):
        if res is None:
            self._set_busy(False)
            return
        if self._flow_epoch != self._epoch:
            self._set_busy(False)
            self._show_hint("连接已变化 —— 请重新读取设备信息后再提交。")
            return
        if not res.ok:
            self._set_busy(False)
            self._show_hint(f"读取设备 UID 失败：{res.text}")
            return

        record = res.value
        uid = uid_of(record)
        if uid is None:
            self._set_busy(False)
            self._apply_record(record)
            self._show_hint("读不到可信 UID —— 不会提交注册信息。")
            return
        if self._record and uid_of(self._record) and uid != uid_of(self._record):
            self._set_busy(False)
            self._apply_record(record)
            self._show_hint("设备 UID 与刚才读取的不一致 —— 请核对后重试。")
            return
        self._record = record
        try:
            payload = {
                "uid": uid,
                "consent": {"granted": True},
                "contact": self._contact_payload(),
                "diagnostics": {
                    # ⚠ 键名是服务端契约（`studio` / `sdk` / `firmware`）。值带上
                    #   `litearm-tool` 前缀，后台的 "Studio" 一栏才能看出是哪一套上位机。
                    "studio": _tool_identification(),
                    "sdk": _sdk_version(),
                    "firmware": str(getattr(self, "_firmware", "") or ""),
                },
            }
            request = activation.build_request(payload)
        except activation.ActivationError as e:
            self._set_busy(False)
            self._show_hint(_reason_text(e))
            return

        # 第 2 段：网络 —— 不在所有者线程上跑。
        url = self._url
        request_fn = self._request_fn
        self._net_epoch = self._epoch

        def work():
            try:
                lic = request_fn(url, request, expected_uid=uid)
                self.net_done.emit(lic, None)
            except BaseException as e:  # noqa: BLE001 - 交给 GUI 线程处理
                self.net_done.emit(None, e)

        threading.Thread(target=work, name="activation-post", daemon=True).start()

    def _on_net_done(self, lic, err):
        if self._net_epoch != self._epoch:
            self._set_busy(False)
            self._log("[WARN] 连接已变化 —— 丢弃这次激活结果")
            return
        if err is not None:
            self._set_busy(False)
            reason = getattr(err, "reason", None)
            self._show_hint(_reason_text(err) if isinstance(err, activation.ActivationError)
                            else f"激活失败：{err}")
            self._log(f"[ERR] 激活请求失败({reason or 'error'}): {err}")
            return
        # 第 3 段：写凭据 + 回读（所有者线程）。
        self._show_hint("凭据已领到，正在写入设备…")
        self._write_epoch = self._epoch
        self._submit("写入授权凭据", lambda arm: write_license(arm, lic), self._on_written)

    def _on_written(self, res):
        if res is None:
            self._set_busy(False)
            return
        if self._write_epoch != self._epoch:
            self._set_busy(False)
            self._log("[WARN] 连接已变化 —— 丢弃这次写入结果")
            return
        self._set_busy(False)
        if not res.ok:
            err = res.error
            if isinstance(err, activation.ActivationError):
                # ⚠ 显示我们映射过的文案, 不要用 `res.text`: 它沿 `__context__` 找到
                # 原始的固件 ERR, 会把"已使能请先失能"说回成 `[3F-04] 当前模式不允许`。
                self._show_hint(_reason_text(err))
                self._log(f"[ERR] 写入授权失败: {err}")
            else:
                self._show_hint(f"写入授权失败：{res.text}")
                self._log(f"[ERR] 写入授权失败: {res.text}")
            self.refresh()
            return

        record = res.value or {}
        self._apply_record(record)
        # ⚠ 只有**回读确认**才算成功（ACK 只说明固件答应了）—— 与 studio 的
        #   `useActivation.submit` 同一判据：`supported === true && activated`。
        if record.get("supported") is True and record.get("activated") is True:
            self._show_hint("")
            self._log("[OK] 激活成功 —— 授权记录已回读确认")
            self.consent_cb.setChecked(False)
        else:
            state = record.get("stateName") or "未知"
            self._show_hint("写入已受理，但回读未确认激活 —— 请点「读取授权记录」再确认。")
            self._log(f"[WARN] 授权写入已受理，但回读未确认激活（设备状态 {state}）")

    # ------------------------------------------------------------------ 杂项
    def set_firmware(self, firmware: str):
        self._firmware = str(firmware or "")

    def _copy_uid(self):
        from PyQt5.QtWidgets import QApplication
        uid = self.uid_lbl.text()
        if not uid or uid == "—":
            return
        try:
            QApplication.clipboard().setText(uid)
        except Exception as e:  # noqa: BLE001 - 复制失败不能拖垮界面
            self._log(f"[WARN] 复制 UID 失败: {e}")
            return
        self._log("[OK] 设备 UID 已复制到剪贴板")

    def _toggle_consent(self, shown: bool):
        self.consent_label.setVisible(bool(shown))
        self.btn_consent.setText(
            "收起《激活注册信息同意书》" if shown else "查看《激活注册信息同意书》")

    def _trim_purpose(self):
        """用途输入框与 studio 的 500 字上限同值（超长只可能来自粘贴）。"""
        text = self.edit_purpose.toPlainText()
        if len(text) <= 500:
            return
        cursor = self.edit_purpose.textCursor()
        pos = cursor.position()
        self.edit_purpose.blockSignals(True)
        self.edit_purpose.setPlainText(text[:500])
        self.edit_purpose.blockSignals(False)
        cursor = self.edit_purpose.textCursor()
        cursor.setPosition(min(pos, 500))
        self.edit_purpose.setTextCursor(cursor)

    def _show_hint(self, text: str):
        self.form_hint.setText(text)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self._update_buttons()
        if busy:
            self.btn_activate.setText("处理中…")
        else:
            self.btn_activate.setText("提交并激活")

    def _update_buttons(self):
        can_read = self._online and not self._busy and self._submit is not None
        self.btn_refresh.setEnabled(can_read)
        self.btn_activate.setEnabled(can_read and self._can_submit())
        self.btn_activate.setToolTip(self._submit_tooltip())
        uid = self.uid_lbl.text()
        self.btn_copy_uid.setEnabled(bool(uid) and uid != "—")

    def _clear_record_display(self):
        self.uid_lbl.setText("—")
        self.state_val.setText("—")
        self.cust_lbl.setText("—")
        self.issued_lbl.setText("—")
        self.flags_lbl.setText("—")
        self.ver_lbl.setText("—")
        self.btn_copy_uid.setEnabled(False)


def _format_issued(issued: Any) -> str:
    """`20261126` → `2026-11-26`；不是这个形状就原样回（不猜日期）。"""
    text = str(int(issued or 0))
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text if issued else "—"


def _firmware_version(text: str) -> Optional[Tuple[int, int, int]]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.groups())   # type: ignore[return-value]


def _unreadable_reason(firmware: str) -> str:
    """读不到授权记录时的原因 —— 用固件版本把"该升级"从"查链路"里分出来。

    与 studio 的 `_uid_unavailable` 同一判据：旧固件回 `ERR{0x2F,0x00}`，当前 SDK 把
    它等成超时；只看现象会把"升级固件"误导成"检查 USB 线"。
    """
    version = _firmware_version(firmware)
    if version is not None and version < LICENSE_MIN_FW:
        return (f"这台固件没有授权功能（需要 "
                f"{LICENSE_MIN_FW[0]}.{LICENSE_MIN_FW[1]}.{LICENSE_MIN_FW[2]} 及以上）"
                "—— 请升级固件")
    return "设备未应答（固件过旧或链路异常）"


def _reason_text(err: activation.ActivationError) -> str:
    """把客户端的短码翻成下一步动作（与 studio 的 reason 判据同一组）。"""
    reason = getattr(err, "reason", "")
    table = {
        "consent_required": "请先勾选同意发送注册信息。",
        "bad_uid": "设备 UID 形态不对 —— 请重新读取设备信息。",
        "invalid_uid": "设备 UID 不是合法的 24 位十六进制 —— 请重新连接机械臂后重试。",
        "uid_mismatch": "服务端返回的凭据不是这台机器的 —— 请联系供应商核对。",
        "unsupported_format": "服务端凭据格式比本上位机新 —— 请升级上位机。",
        "missing_contact": "注册信息没填完 —— 带 * 的字段都要填。",
        "contact_too_long": "注册信息有一项过长 —— 请核对姓名、手机号、单位、邮箱、"
                            "微信号、地区、行业与用途说明的长度。",
        "bad_phone": "手机号不符合要求 —— 需为 11 位手机号。",
        "bad_email": "邮箱不符合要求 —— 格式不正确。",
        "bad_name": "姓名不符合要求 —— 只能是文字，2–32 个字，不能含数字。",
        "unconfigured": "本地程序没有配置激活服务地址 —— 请用 --activation-url 启动。",
        "unreachable": "连不上激活服务 —— 请检查这台机器的网络。",
        "not_found": "激活服务上没有这台机器的凭据 —— "
                     "请把设备 UID 发给供应商核对补录，然后重新提交。",
        "rate_limited": "激活服务暂时拒绝了本次请求（请求过于频繁）—— 请过一会儿再试。",
        "maintenance": "激活服务正在维护 —— 请稍后重试。",
        "code_required": "激活服务要求提供订单号 / 激活码 —— 请升级上位机，或联系供应商。",
        "invalid_request": "激活服务拒绝了这份注册信息 —— 请核对带 * 的字段后重新提交"
                           "（若反复出现，说明网站的字段规则已更新）。",
        "server": "激活服务出错了 —— 请稍后重试；一直失败请联系供应商。",
        "bad_response": "激活服务的应答不可用 —— 请稍后重试。",
        "device_uid_unavailable": "读不到设备的授权记录 —— 请检查 USB 链路后重试。",
        "firmware_unsupported": "这台固件没有授权功能（需要 1.8.0 及以上）—— 请升级固件。",
        "armed": "固件只在失能状态下接受写入授权记录 —— 请先按「失能」，再重新提交。",
        "rejected": "固件拒绝了这次写入（已激活过 / 凭据与本机不符 / 写入失败共用一个"
                    "错误码）—— 请点「读取授权记录」看授权状态；仍未激活就核对 UID 后"
                    "重新申请凭据。",
    }
    return table.get(reason, str(err))


def _tool_identification() -> str:
    """后台 `Studio` 一栏里的值：带上产品名，避免和 studio 的版本混淆。"""
    version = _tool_version()
    return f"litearm-tool {version}".strip()


def _tool_version() -> str:
    """安装后的包版本；源码运行（未安装）时为空串 —— 诊断字段允许缺省。"""
    try:
        from importlib.metadata import version
        return str(version("litearm-tool-stm32"))
    except Exception:  # noqa: BLE001
        return ""


def _sdk_version() -> str:
    try:
        import litearm
        return str(getattr(litearm, "__version__", ""))
    except Exception:  # noqa: BLE001
        return ""
