"""授权页 —— 读设备授权记录 + 在线激活。

只读/写 SDK 的两条授权命令（`0x2F` / `0x3F`），**不碰运动**；与运动解锁无关。
两段式流程（照 studio 的纪律）：

1. 在 SDK 所有者线程上读设备 UID（**不出网之前先拿到可信 UID**）；
2. 网络 POST 在**页面自建的线程**上跑 —— 它不碰串口，不能占住所有者线程；
3. 回到所有者线程写凭据 + 回读，回读才是"落位"的证据。

错误文案尽量指向下一步动作（未激活 / 已使能 / 需要升级 / 网络不通）。
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

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

CONSENT_TEXT = (
    "我同意将下方填写的注册信息（联系人、电话、单位、邮箱、地区、可选微信/行业/用途）"
    "与设备 UID、上位机/SDK/固件版本号提交至激活服务，用于签发本设备的授权凭据。"
    f"（同意书版本 {activation.CONSENT_TEXT_VERSION}）"
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
        form.addRow("联系人*", self.edit_name)
        form.addRow("手机号*", self.edit_phone)
        form.addRow("单位*", self.edit_org)
        form.addRow("微信（可选）", self.edit_wechat)
        form.addRow("邮箱*", self.edit_email)
        form.addRow("地区*", self.edit_region)
        form.addRow("行业（可选）", self.edit_industry)
        form.addRow("用途（可选）", self.edit_purpose)
        self.consent_label = QLabel(CONSENT_TEXT)
        self.consent_label.setWordWrap(True)
        self.consent_label.setStyleSheet("color:#8a97a4;font-size:12px;")
        form.addRow(self.consent_label)
        self.consent_cb = QCheckBox("我已阅读并同意上述同意书")
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
        self._online = bool(onl)
        if not self._online:
            self.state_lbl.setText("未连接")
            self.form_box.setVisible(False)
        self._update_buttons()

    def update_from(self, st):
        self._enabled = bool(getattr(st, "enabled", False)) if st is not None else False
        self._update_buttons()

    # ------------------------------------------------------------------ 读取
    def refresh(self):
        if self._submit is None or not self._online:
            return
        self._set_busy(True)
        self.record_hint.setText("正在读取授权记录…")
        self._submit("读取授权记录", read_record, self._on_record)

    def _on_record(self, res):
        self._set_busy(False)
        if res is None:
            return
        if not res.ok:
            self.record_hint.setText(f"读取失败：{res.text}")
            self.form_box.setVisible(False)
            return
        self._apply_record(res.value)

    def _apply_record(self, record: Dict[str, Any]):
        self._record = record
        supported = record.get("supported")
        if supported is False:
            self.state_val.setText("—")
            self.record_hint.setText("这台固件没有授权命令（版本过旧）—— 请升级固件。")
            self.form_box.setVisible(False)
            self._update_buttons()
            return
        if supported is None:
            self.state_val.setText("—")
            self.record_hint.setText(
                "设备未应答（固件过旧或链路异常）—— 无法确认授权状态，也不会提交注册信息。")
            self.form_box.setVisible(False)
            self._update_buttons()
            return

        state = record.get("stateName", "")
        self.state_val.setText(STATE_TEXT.get(state, state or "—"))
        self.uid_lbl.setText(record.get("uid") or "—")
        self.ver_lbl.setText(str(record.get("ver", "—")))
        self.cust_lbl.setText(str(record.get("custId", 0)))
        issued = record.get("issued", 0)
        self.issued_lbl.setText(str(issued) if issued else "—")
        self.flags_lbl.setText(f"0x{int(record.get('flags', 0)):X}")
        activated = bool(record.get("activated"))
        self.form_box.setVisible(not activated)
        if activated:
            self.record_hint.setText("已激活 —— 使能可用；授权记录不可修改。")
        else:
            self.record_hint.setText(
                "未激活：`enable` 会被固件拒绝（0x10/0x08）。填写下方注册信息并提交即可激活。")
        self._update_buttons()

    # ------------------------------------------------------------------ 激活
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
        self._submit("激活前读取 UID", read_record, self._on_uid_fresh)

    def _on_uid_fresh(self, res):
        if res is None:
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
                "contact": {
                    "name": self.edit_name.text(),
                    "phone": self.edit_phone.text(),
                    "organization": self.edit_org.text(),
                    "wechatId": self.edit_wechat.text(),
                    "email": self.edit_email.text(),
                    "region": self.edit_region.text(),
                    "industry": self.edit_industry.text(),
                    "purpose": self.edit_purpose.toPlainText(),
                },
                "diagnostics": {
                    "tool": _tool_version(),
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

        def work():
            try:
                lic = request_fn(url, request, expected_uid=uid)
                self.net_done.emit(lic, None)
            except BaseException as e:  # noqa: BLE001 - 交给 GUI 线程处理
                self.net_done.emit(None, e)

        threading.Thread(target=work, name="activation-post", daemon=True).start()

    def _on_net_done(self, lic, err):
        if err is not None:
            self._set_busy(False)
            reason = getattr(err, "reason", None)
            self._show_hint(_reason_text(err) if isinstance(err, activation.ActivationError)
                            else f"激活失败：{err}")
            self._log(f"[ERR] 激活请求失败({reason or 'error'}): {err}")
            return
        # 第 3 段：写凭据 + 回读（所有者线程）。
        self._show_hint("凭据已领到，正在写入设备…")
        self._submit("写入授权凭据", lambda arm: write_license(arm, lic), self._on_written)

    def _on_written(self, res):
        self._set_busy(False)
        if res is None:
            return
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
        self._apply_record(res.value)
        self._show_hint("")
        self._log("[OK] 激活成功 —— 授权记录已回读确认")
        self.consent_cb.setChecked(False)

    # ------------------------------------------------------------------ 杂项
    def set_firmware(self, firmware: str):
        self._firmware = str(firmware or "")

    def _copy_uid(self):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self.uid_lbl.text())

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
        self.btn_activate.setEnabled(can_read)
        uid = self.uid_lbl.text()
        self.btn_copy_uid.setEnabled(bool(uid) and uid != "—")
        if not self._online:
            self.state_lbl.setText("未连接")


def _reason_text(err: activation.ActivationError) -> str:
    """把客户端的短码翻成下一步动作（与 studio 的 reason 判据同一组）。"""
    reason = getattr(err, "reason", "")
    table = {
        "consent_required": "请先阅读并勾选同意书。",
        "bad_uid": "设备 UID 形态不对 —— 请重新读取设备信息。",
        "uid_mismatch": "服务端返回的凭据不是这台机器的 —— 请联系供应商核对。",
        "unsupported_format": "服务端凭据格式比本上位机新 —— 请升级上位机。",
        "missing_contact": "注册信息不完整。",
        "contact_too_long": "注册信息有字段过长。",
        "bad_phone": "手机号格式不正确（需 11 位）。",
        "bad_email": "邮箱格式不正确。",
        "bad_name": "姓名格式不正确（只允许文字，不能含数字）。",
        "unconfigured": "未配置激活服务地址。",
        "unreachable": "连不上激活服务 —— 检查网络后重试。",
        "rate_limited": "提交过于频繁 —— 请稍后重试。",
        "maintenance": "激活服务维护中 —— 请稍后重试。",
        "server": "激活服务出错 —— 请稍后重试或联系供应商。",
        "bad_response": "激活服务返回的应答不可用 —— 请联系供应商。",
        "armed": "设备已使能 —— 请先失能，再提交激活。",
        "rejected": "固件拒绝了这次写入。",
    }
    return table.get(reason, str(err))


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
