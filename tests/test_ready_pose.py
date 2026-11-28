"""就绪姿态 —— 按轴数裁剪/补 0，走普通 movej 闸门。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication                    # noqa: E402

from litetool import settings as settings_mod               # noqa: E402
from litetool.gui.pages.joint_page import READY_POSE, JointPage  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _page(n):
    page = JointPage(settings_mod.Settings.load(None))
    page.set_joints(n)
    page.set_online(True)
    page.set_armed(True)
    return page


def test_7j_sends_the_full_ready_pose(app):
    page = _page(7)
    try:
        got = []
        page.movej.connect(lambda q, s: got.append((q, s)))
        page.btn_ready.click()
        assert got and got[0][0] == list(READY_POSE)
        assert got[0][1] == pytest.approx(settings_mod.Settings.load(None).default_speed)
        assert page.mj_row.value() == list(READY_POSE), "目标框要同步显示"
    finally:
        page.close()


def test_1j_and_3j_are_trimmed(app):
    for n, expected in ((1, [0.0]), (3, [0.0, 0.5, 0.0])):
        page = _page(n)
        try:
            got = []
            page.movej.connect(lambda q, s: got.append(q))
            page.btn_ready.click()
            assert got == [expected]
        finally:
            page.close()


def test_ready_pose_needs_the_motion_unlock(app):
    page = _page(7)
    try:
        page.set_armed(False)
        assert not page.btn_ready.isEnabled()
        page.set_armed(True)
        assert page.btn_ready.isEnabled()
    finally:
        page.close()


def test_cart_page_exposes_the_ready_pose(app):
    """issue #42：笛卡尔页也要能一键回就绪姿态，且同样受运动闸门约束。"""
    from litetool.gui.pages.cart_page import CartPage

    page = CartPage(settings_mod.Settings.load(None))
    try:
        page.set_online(True)
        page.set_armed(True)
        assert not page.btn_ready.isEnabled(), "未识别到关节数前不能裁剪目标"
        page.set_joints(7)
        assert page.btn_ready.isEnabled()

        got = []
        page.ready_req.connect(got.append)
        page.btn_ready.click()
        assert got == [pytest.approx(page.speed.value())]

        page.set_armed(False)
        assert not page.btn_ready.isEnabled()
    finally:
        page.close()
