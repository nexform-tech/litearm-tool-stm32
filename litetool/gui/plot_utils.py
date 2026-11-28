"""pyqtgraph 共用设置 —— 图例固定在图内，不接受拖动。"""
from __future__ import annotations

import pyqtgraph as pg


class FixedLegend(pg.LegendItem):
    """位置由 ``offset`` 决定、不接受拖动的图例。

    pyqtgraph 0.14 的 ``LegendItem.mouseDragEvent`` 对左键拖动一律 ``accept()``
    并调用 ``autoAnchor(pos + dpos)`` —— 图例会跟着鼠标跑。图例只用来读颜色，
    不该成为可摆放的窗口，所以这里把拖动吃掉（也不让它落到下面的 ViewBox 里
    变成平移，避免拖图例时图反而动了）。
    """

    def mouseDragEvent(self, ev):  # noqa: N802 - Qt 命名
        ev.accept()


def add_fixed_legend(plot_item, offset=(10, 10), **kwargs) -> FixedLegend:
    """``PlotItem.addLegend`` 的固定版；重复调用返回同一个图例。

    ``PlotItem.clear()`` 不会删掉图例对象，``addLegend`` 也会复用已有的那个；
    这里保持同样的语义，清屏/重画后不会叠加出第二个图例。
    """
    legend = plot_item.legend
    if legend is None:
        legend = FixedLegend(offset=offset, **kwargs)
        legend.setParentItem(plot_item.vb)
        plot_item.legend = legend
    return legend
