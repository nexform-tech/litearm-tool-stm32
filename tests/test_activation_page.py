"""授权页的离线测试 —— 假 arm + 假网络，不需要硬件也不出网。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("litearm")

import litearm as pa                                   # noqa: E402
from PyQt5.QtTest import QTest                         # noqa: E402
from PyQt5.QtWidgets import QApplication               # noqa: E402

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

    def license(self):
        if self.support is False:
            raise pa.UnsupportedByFirmwareError("no license cmd", cmd=0x2F, code=0x00)
        if self.support is None:
            raise pa.MotionTimeoutError("no answer")
        return pa.LicenseInfo(state=self.state, ver=1, uid=self.uid,
                              cust_id=self.cust_id, issued=self.issued,
                              flags=self.flags)

    def activate(self, *, cust_id, issued, flags=0, mac):
        self.calls.append({"cust_id": cust_id, "issued": issued,
                           "flags": flags, "mac": mac})
        if self.fail is not None:
            raise pa.CommandRejectedError("rejected", cmd=self.fail[0], code=self.fail[1])
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


def _page(arm=None, *, request=None):
    global _APP
    _APP = QApplication.instance() or QApplication([])
    page = ActivationPage()
    arm = arm or FakeArm()
    page.set_submit(StubSubmit(arm))
    page.set_log(lambda _m: None)
    page.set_online(True)
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


def test_unactivated_record_shows_uid_and_form():
    page, _ = _page()
    page.refresh()
    assert page.uid_lbl.text() == UID.hex()
    assert page.state_val.text() == "未激活"
    assert not page.form_box.isHidden()
    page.close()


def test_activated_record_hides_form():
    page, _ = _page(FakeArm(activated=True))
    page.refresh()
    assert page.state_val.text() == "已激活"
    assert page.form_box.isHidden()
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


def test_activate_success_writes_and_reads_back():
    page, arm = _page(request=lambda *a, **k: LIC)
    page.refresh()
    _fill(page)
    page._on_activate()
    QTest.qWait(200)                    # 网络段在自建线程上，等信号回来
    assert arm.calls and arm.calls[0]["cust_id"] == 1042
    assert page.state_val.text() == "已激活"
    assert page.form_box.isHidden()
    page.close()


def test_activate_network_error_is_reported():
    def fail(*_a, **_k):
        raise page_mod_error()
    from litetool.activation import ActivationError

    def page_mod_error():
        return ActivationError("unreachable", "连不上")

    page, arm = _page(request=fail)
    page.refresh()
    _fill(page)
    page._on_activate()
    QTest.qWait(200)
    assert "连不上" in page.form_hint.text()
    assert not arm.calls
    page.close()


def test_aggregated_0x02_counts_as_success_when_record_is_activated():
    """`ERR{0x3F,0x02}` 包含"已经激活过" —— 回读已激活就算成功。"""
    arm = FakeArm(activated=False)
    arm.state = 1                       # 回读会看到已激活
    arm.fail = (0x3F, 0x02)
    page, _ = _page(arm, request=lambda *a, **k: LIC)
    page.refresh()
    _fill(page)
    page._on_activate()
    QTest.qWait(200)
    assert page.form_box.isHidden()
    page.close()


def test_armed_rejection_maps_to_actionable_text():
    arm = FakeArm(activated=False)
    arm.fail = (0x3F, 0x04)
    page, _ = _page(arm, request=lambda *a, **k: LIC)
    page.refresh()
    _fill(page)
    page._on_activate()
    QTest.qWait(200)
    assert "失能" in page.form_hint.text()
    page.close()
