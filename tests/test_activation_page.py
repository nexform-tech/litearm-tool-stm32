"""授权页的离线测试 —— 假 arm + 假网络，不需要硬件也不出网。"""
from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("litearm")

import litearm as pa                                   # noqa: E402
from PyQt5.QtTest import QTest                         # noqa: E402
from PyQt5.QtWidgets import QApplication               # noqa: E402

from litetool import activation                        # noqa: E402
from litetool.gui.pages.activation_page import ActivationPage   # noqa: E402
from litetool.sdk_worker import TaskResult                       # noqa: E402

UID = bytes(range(0x10, 0x1C))
LIC = {"uid": UID.hex(), "cust_id": 1042, "issued": 20261126,
       "flags": 0, "mac": bytes(16)}


class FakeArm:
    """只实现授权页用到的两条 SDK 调用，形状与 `Arm` 一致。"""

    def __init__(self, *, activated=False, support=True):
        self.state = 1 if activated else 0
        self.support = support          # True / False / None(无应答)
        self.uid = UID
        self.cust_id = 1042 if activated else 0
        self.issued = 20261126 if activated else 0
        self.flags = 0
        self.calls = []
        self.fail = None                # (cmd, code)
        self.timeout_after_write = False   # 写后回读超时
        self.stay_inactive = False         # ACK 了但没落位
        self.factory_mode = False

    def license(self):
        if self.support is False:
            raise pa.UnsupportedByFirmwareError("no license cmd", cmd=0x2F, code=0x00)
        if self.support is None or (self.timeout_after_write and self.calls):
            raise pa.MotionTimeoutError("no answer")
        state = 2 if self.factory_mode else self.state
        flags = 1 if self.factory_mode else self.flags
        return pa.LicenseInfo(state=state, ver=1, uid=self.uid,
                              cust_id=self.cust_id, issued=self.issued, flags=flags)

    def activate(self, *, cust_id, issued, flags=0, mac):
        self.calls.append({"cust_id": cust_id, "issued": issued,
                           "flags": flags, "mac": mac})
        if self.fail is not None:
            raise pa.CommandRejectedError("rejected", cmd=self.fail[0], code=self.fail[1])
        if self.stay_inactive:
            return
        self.state = 2 if flags & 1 else 1
        self.cust_id, self.issued, self.flags = cust_id, issued, flags


class StubSubmit:
    """替身：同步跑任务并回调，相当于"所有者线程 + 桥"那两跳。"""

    def __init__(self, arm):
        self.arm = arm
        self.names = []

    def __call__(self, name, fn, on_done=None):
        self.names.append(name)
        try:
            res = TaskResult(name, True, value=fn(self.arm))
        except BaseException as e:  # noqa: BLE001
            res = TaskResult(name, False, error=e)
        if on_done is not None:
            on_done(res)


_APP = None


def _page(arm=None, *, request=None, logs=None):
    global _APP
    _APP = QApplication.instance() or QApplication([])
    page = ActivationPage()
    arm = arm or FakeArm()
    page.set_submit(StubSubmit(arm))
    page.set_log(logs.append if logs is not None else (lambda _m: None))
    page.set_online(True)               # 连上即自动读一次（与 studio 一致）
    if request is not None:
        page._request_fn = request
    return page, arm


def _fill(page):
    page.edit_name.setText("张三")
    page.edit_phone.setText("13800000000")
    page.edit_org.setText("测试单位")
    page.edit_email.setText("a@b.cn")
    page.edit_region.setText("杭州")
    page.consent_cb.setChecked(True)


def _activate(page, *, wait=200):
    page.refresh()
    _fill(page)
    page.update_from(None)              # 假臂的默认状态帧是"使能"，提交前清掉
    page._on_activate()
    QTest.qWait(wait)


# --------------------------------------------------------------------------- 记录
def test_connect_auto_reads_record():
    page, _ = _page()
    assert page.uid_lbl.text() == UID.hex()          # 没有手点 refresh
    assert page.state_val.text() == "未激活"
    page.close()


def test_unactivated_record_shows_uid_and_form():
    page, _ = _page()
    page.refresh()
    assert page.uid_lbl.text() == UID.hex()
    assert page.state_val.text() == "未激活"
    assert not page.form_box.isHidden()
    page.close()


def test_activated_record_hides_form_and_formats_issued():
    page, _ = _page(FakeArm(activated=True))
    page.refresh()
    assert page.state_val.text() == "已激活"
    assert page.issued_lbl.text() == "2026-11-26"
    assert page.cust_lbl.text() == "1042"
    assert page.flags_lbl.text() == "—"
    assert page.form_box.isHidden()
    page.close()


def test_factory_mode_is_labelled():
    arm = FakeArm(activated=True)
    arm.factory_mode = True
    page, _ = _page(arm)
    page.refresh()
    assert page.state_val.text() == "已激活（产线模式）"
    assert page.flags_lbl.text() == "产线码"
    page.close()


def test_old_firmware_states_are_distinguished():
    page, _ = _page(FakeArm(support=False))
    page.refresh()
    assert "没有授权命令" in page.record_hint.text()
    page.close()

    page, _ = _page(FakeArm(support=None))
    page.refresh()
    assert "未应答" in page.record_hint.text()
    assert page.form_box.isHidden()
    page.close()


def test_old_firmware_version_says_upgrade():
    page, _ = _page(FakeArm(support=None))
    page.set_firmware("Litearm1.5.3-7J")
    page.refresh()
    hint = page.record_hint.text()
    assert "升级固件" in hint and "1.8.0" in hint
    page.close()

    page, _ = _page(FakeArm(support=None))
    page.set_firmware("Litearm1.12.3-7J")
    page.refresh()
    assert "升级固件" not in page.record_hint.text()
    page.close()


def test_failed_reread_keeps_last_record_and_form():
    """与 studio 同一判据：失败重读不抹掉上一次的 UID/状态，只标成旧读数。"""
    page, arm = _page()
    page.refresh()
    before = dict(page._record)
    arm.support = None
    page.refresh()

    assert page.uid_lbl.text() == UID.hex()
    assert page.state_val.text() == "未激活"
    assert page.cust_lbl.text() == "—"
    assert page._record == before
    assert not page.form_box.isHidden()
    assert "上一次" in page.record_hint.text()
    page.close()


def test_disconnect_clears_previous_record():
    page, _ = _page()
    page.refresh()
    page.set_online(False)
    assert page.uid_lbl.text() == "—"
    assert page.state_val.text() == "—"
    assert page._record is None
    assert not page.btn_copy_uid.isEnabled()
    assert page.form_box.isHidden()
    assert page.record_hint.text().startswith("连接设备后")
    page.close()


def test_state_label_tracks_connection():
    page, _ = _page()
    assert page.state_lbl.text() == "已连接"
    page.set_online(False)
    assert page.state_lbl.text() == "未连接"
    page.close()


# --------------------------------------------------------------------------- 门禁
def test_activate_requires_consent():
    page, arm = _page(request=lambda *a, **k: LIC)
    page.refresh()
    _fill(page)
    page.consent_cb.setChecked(False)
    page._on_activate()
    assert "同意书" in page.form_hint.text()
    assert not arm.calls
    page.close()


def test_activate_blocked_when_enabled():
    page, arm = _page(request=lambda *a, **k: LIC)
    page.refresh()
    _fill(page)
    page.update_from(type("S", (), {"enabled": True})())
    page._on_activate()
    assert "失能" in page.form_hint.text()
    assert not arm.calls
    page.close()


def test_activate_requires_a_record():
    # 自动读也读不到（旧固件/无应答）：没有可信 UID，绝不提交。
    page, arm = _page(FakeArm(support=None), request=lambda *a, **k: LIC)
    _fill(page)
    page.update_from(None)
    page._on_activate()
    assert "可信的设备 UID" in page.form_hint.text()
    assert not arm.calls
    page.close()


# --------------------------------------------------------------------------- 提交
def test_activate_success_writes_and_reads_back():
    logs = []
    page, arm = _page(request=lambda *a, **k: LIC, logs=logs)
    _activate(page)
    assert arm.calls and arm.calls[0]["cust_id"] == 1042
    assert page.state_val.text() == "已激活"
    assert page.form_box.isHidden()
    assert any("[OK] 激活成功" in line for line in logs)
    page.close()


def test_activate_network_error_is_reported():
    def fail(*_a, **_k):
        raise activation.ActivationError("unreachable", "连不上")

    page, arm = _page(request=fail)
    _activate(page)
    assert "连不上" in page.form_hint.text()
    assert not arm.calls
    page.close()


def test_activate_sends_studio_diagnostics_keys():
    captured = {}

    def request(_url, body, **_kw):
        captured.update(body)
        return LIC

    page, _ = _page(request=request)
    _activate(page)
    # ⚠ 服务端契约：`studio` / `sdk` / `firmware`（多出来的键会被 zod 静默丢掉）。
    assert set(captured["diagnostics"]) == {"studio", "sdk", "firmware"}
    assert captured["diagnostics"]["studio"].startswith("litearm-tool")
    page.close()


def test_aggregated_0x02_counts_as_success_when_record_is_activated():
    """`ERR{0x3F,0x02}` 包含"已经激活过" —— 回读已激活就算成功。"""
    logs = []
    arm = FakeArm(activated=False)
    arm.state = 1                       # 回读会看到已激活
    arm.fail = (0x3F, 0x02)
    page, _ = _page(arm, request=lambda *a, **k: LIC, logs=logs)
    _activate(page)
    assert page.form_box.isHidden()
    assert any("[OK] 激活成功" in line for line in logs)
    page.close()


def test_armed_rejection_maps_to_actionable_text():
    arm = FakeArm(activated=False)
    arm.fail = (0x3F, 0x04)
    page, _ = _page(arm, request=lambda *a, **k: LIC)
    _activate(page)
    assert "失能" in page.form_hint.text()
    page.close()


def test_unconfirmed_readback_is_a_warning_not_success():
    """写后回读超时：ACK 不算成功，日志和界面都必须说"未确认"。"""
    logs = []
    arm = FakeArm()
    arm.timeout_after_write = True
    page, _ = _page(arm, request=lambda *a, **k: LIC, logs=logs)
    _activate(page)

    assert any("[WARN]" in line and "未确认" in line for line in logs)
    assert not any("[OK] 激活成功" in line for line in logs)
    assert page.state_val.text() == "未激活"          # 保留上一次读数
    assert not page.form_box.isHidden()               # 未激活 → 表单还在
    assert "未确认" in page.form_hint.text()
    page.close()


def test_write_accepted_but_still_inactive_is_a_warning():
    logs = []
    arm = FakeArm()
    arm.stay_inactive = True
    page, _ = _page(arm, request=lambda *a, **k: LIC, logs=logs)
    _activate(page)

    assert any("[WARN]" in line and "未确认" in line for line in logs)
    assert not any("[OK] 激活成功" in line for line in logs)
    assert page.state_val.text() == "未激活"
    assert not page.form_box.isHidden()
    page.close()


def test_not_found_maps_to_next_action():
    def fail(*_a, **_k):
        raise activation.ActivationError("not_found", "没有这台机器的凭据")

    page, _ = _page(request=fail)
    _activate(page)
    hint = page.form_hint.text()
    assert "供应商" in hint and "补录" in hint
    page.close()


def test_session_change_discards_pending_network_result():
    """网络段在飞的时候断线/换机：结果作废，绝不写到新链路上。"""
    logs = []
    gate = threading.Event()

    def request(*_a, **_k):
        gate.wait(2.0)
        return LIC

    page, arm = _page(request=request, logs=logs)
    page.refresh()
    _fill(page)
    page.update_from(None)
    page._on_activate()                 # 预读同步返回，网络线程卡在 gate
    page.set_online(False)              # 链路变化 → epoch+1
    gate.set()
    QTest.qWait(300)

    assert not arm.calls
    assert any("连接已变化" in line for line in logs)
    page.close()


# --------------------------------------------------------------------------- 文案/输入
def test_consent_document_matches_studio_draft():
    page, _ = _page()
    text = page.consent_label.text()
    for item in ("姓名、手机号、单位、邮箱、微信号",
                 "所在地区、所属行业、用途说明",
                 "设备 UID（24 位十六进制）",
                 "上位机 / SDK / 固件版本",
                 "隐私政策"):
        assert item in text
    assert activation.CONSENT_TEXT_VERSION in text
    assert page.consent_cb.text() == "我已阅读并同意《激活注册信息同意书》"
    page.close()


def test_consent_can_be_expanded_and_collapsed():
    page, _ = _page()
    assert page.consent_label.isHidden()
    page.btn_consent.setChecked(True)
    assert not page.consent_label.isHidden()
    assert "收起" in page.btn_consent.text()
    page.btn_consent.setChecked(False)
    assert page.consent_label.isHidden()
    assert "查看" in page.btn_consent.text()
    page.close()


def test_input_limits_match_the_website_form():
    page, _ = _page()
    assert page.edit_name.maxLength() == 32
    assert page.edit_phone.maxLength() == 11
    assert page.edit_org.maxLength() == 128
    assert page.edit_wechat.maxLength() == 64
    assert page.edit_email.maxLength() == 128
    assert page.edit_region.maxLength() == 64
    assert page.edit_industry.maxLength() == 64
    page.edit_purpose.setPlainText("x" * 600)
    assert len(page.edit_purpose.toPlainText()) == 500
    page.close()
