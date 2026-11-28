"""图表图例必须固定 —— pyqtgraph 默认允许左键把图例拖走。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Drag:
    """``QGraphicsSceneMouseEvent`` 在 PyQt5 里不能实例化，喂一个够用的替身。"""

    def __init__(self, start, end):
        self._last = QPointF(*start)
        self._pos = QPointF(*end)
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def pos(self):
        return self._pos

    def lastPos(self):
        return self._last

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def _drag(legend, start=(20.0, 20.0), end=(80.0, 60.0)):
    ev = _Drag(start, end)
    legend.mouseDragEvent(ev)
    return ev


def test_a_plain_pyqtgraph_legend_would_move(app):
    """钉住上游行为 —— 这正是必须用 FixedLegend 的原因。"""
    import pyqtgraph as pg

    pi = pg.PlotItem()
    legend = pg.LegendItem(offset=(10, 10))
    legend.setParentItem(pi.vb)
    before = legend.pos()
    _drag(legend)
    assert legend.pos() != before


def test_a_fixed_legend_swallows_the_drag(app):
    from litetool.gui.plot_utils import FixedLegend, add_fixed_legend

    import pyqtgraph as pg

    pi = pg.PlotItem()
    legend = add_fixed_legend(pi)
    assert isinstance(legend, FixedLegend)
    assert add_fixed_legend(pi) is legend, "重复调用不能叠加第二个图例"
    pi.clear()
    assert add_fixed_legend(pi) is legend

    before = legend.pos()
    assert _drag(legend).accepted
    assert legend.pos() == before, "图例被拖动了"


def test_the_capture_page_pins_all_three_legends(app):
    from litetool.gui.pages.capture_page import CapturePage
    from litetool.gui.plot_utils import FixedLegend

    page = CapturePage()
    try:
        for pi in page.plots:
            assert isinstance(pi.legend, FixedLegend)
            before = pi.legend.pos()
            assert _drag(pi.legend).accepted
            assert pi.legend.pos() == before
    finally:
        page.close()


def test_the_overview_pane_pins_its_legends(app):
    from litetool.gui.pages.plot_pane import PlotPane
    from litetool.gui.plot_utils import FixedLegend

    pane = PlotPane()
    try:
        for pi in pane.plots:
            legend = pane._legends[id(pi)]
            assert isinstance(legend, FixedLegend)
            before = legend.pos()
            assert _drag(legend).accepted
            assert legend.pos() == before
    finally:
        pane.close()
