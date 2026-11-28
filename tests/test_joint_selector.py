"""关节开关 —— 一处勾选控制三张联动的 q/dq/tau 图。"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")

from PyQt5.QtWidgets import QApplication

from litetool.gui.joint_selector import COLORS, JointSelector


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _samples(n_joints=7, ticks=5):
    out = []
    for i in range(ticks):
        vals = [0.1 * (j + 1) + i * 0.01 for j in range(n_joints)]
        out.append(SimpleNamespace(tick=i * 30, q_ref=list(vals),
                                   dq=[v * 2 for v in vals],
                                   tau=[v * 3 for v in vals]))
    return out


def test_selector_builds_colored_boxes_and_reports_selection(app):
    sel = JointSelector()
    seen = []
    sel.changed.connect(lambda: seen.append(1))
    try:
        assert sel.n == 0
        sel.set_joints(7)
        assert sel.n == 7
        assert sel.enabled() == [True] * 7
        assert sel.selected() == list(range(7))
        for j, cb in enumerate(sel._boxes):
            assert cb.text() == f"J{j + 1}"
            assert COLORS[j % len(COLORS)] in cb.styleSheet(), "勾选文字应与曲线同色"

        sel.set_enabled(4, False)
        assert seen == [1], "一次开关只发一个 changed"
        assert sel.selected() == [0, 1, 2, 3, 5, 6]

        sel.set_joints(7)                    # 关节数不变：保留用户勾选
        assert sel.selected() == [0, 1, 2, 3, 5, 6]
        seen.clear()
        sel.set_joints(3)                    # 重建：默认全部勾选
        assert sel.enabled() == [True] * 3
        assert seen == [], "重建时的 setChecked 不能被当成用户操作"

        sel.set_joints(7, default_first=3)   # 实时曲线默认前 3 个
        assert sel.selected() == [0, 1, 2]
    finally:
        sel.close()


def test_capture_page_toggles_one_joint_across_all_three_plots(app):
    from litetool.gui.pages.capture_page import CapturePage

    page = CapturePage()
    try:
        page._draw(_samples())
        assert page.joints.n == 7
        assert len(page.curves) == 3 * 7
        assert all(pi.legend is None for pi in page.plots), "图内不应再有图例"

        page.joints.set_enabled(4, False)    # J5
        for f in range(3):
            assert not page.curves[(f, 4)].isVisible()
            assert page.curves[(f, 0)].isVisible()

        page.joints.set_enabled(4, True)
        for f in range(3):
            assert page.curves[(f, 4)].isVisible()
    finally:
        page.close()


def test_capture_axis_labels_are_short_and_unitless(app):
    from litetool.gui.pages.capture_page import CapturePage, FIELD_TITLES

    page = CapturePage()
    try:
        assert FIELD_TITLES == ("参考位置", "执行速度", "实测力矩")
        for title, pi in zip(FIELD_TITLES, page.plots):
            assert pi.getAxis("left").labelText == title
    finally:
        page.close()


def test_overview_pane_uses_the_same_selector(app):
    from litetool.gui.pages.plot_pane import PlotPane

    pane = PlotPane()
    try:
        pane.set_joints(7)
        assert pane.joints.n == 7
        assert pane.selected_joints() == [0, 1, 2], "实时图默认仍只开前 3 个关节"
        assert all(pi.legend is None for pi in pane.plots)

        pane.joints.set_enabled(0, False)
        assert pane.selected_joints() == [1, 2]
        pane.set_joints(7)
        assert pane.selected_joints() == [1, 2], "同一关节数下重设不能丢勾选"
    finally:
        pane.close()
