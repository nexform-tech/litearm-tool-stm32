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
