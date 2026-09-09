"""GUI 冒烟 —— offscreen 构造主窗口并跑几轮空转，防 import/布局回归。

需要 PyQt5/pyqtgraph；无显示环境时用 offscreen 平台插件。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")


def test_mainwindow_constructs_and_ticks_offscreen():
    from PyQt5.QtWidgets import QApplication
    from litetool import settings as settings_mod
    from litetool.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    st = settings_mod.Settings.load(None)
    w = MainWindow(st)
    w._tick()            # session=None 分支
    w._tick_plot()
    w._lock_motion("test")
    w._apply_busy()
    w.close()
    assert w.session is None


def test_mainwindow_has_params_tab():
    """[调参页] 已注册为 "参数" 页签, 表格规格齐备。"""
    from PyQt5.QtWidgets import QApplication
    from litetool import settings as settings_mod
    from litetool.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(settings_mod.Settings.load(None))
    assert w.params is not None
    assert w.params.table.columnCount() == 8          # 1 参数列 + J1..J7
    assert w.params.table.rowCount() >= 16
    w.close()


def test_tuning_guide_page_builds_offscreen():
    """[调参指南] 页可建: 详解块 33 项 (16 关节+8 全局+9 ff位), reveal 可用。"""
    from PyQt5.QtWidgets import QApplication
    from litetool.gui.tuning_guide_page import TuningGuidePage

    app = QApplication.instance() or QApplication([])
    g = TuningGuidePage()
    assert len(g._key_widget) >= 33
    assert "kp" in g._key_widget and "gravity" in g._key_widget
    assert "FRICTION" in g._key_widget
    g.reveal("kp")
    g.reveal("FRICTION")
    g.close()


def test_mainwindow_has_guide_tab_and_jump():
    """主窗口含"调参指南"页签; params.show_guide 切页并定位。"""
    from PyQt5.QtWidgets import QApplication
    from litetool import settings as settings_mod
    from litetool.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(settings_mod.Settings.load(None))
    assert w.tabs.count() >= 6
    w._on_guide_from_params("kp")          # 不连接也可用 (指南纯说明)
    assert w.tabs.currentWidget() is w.guide
    w.close()


def test_params_page_builds_and_edits_offscreen():
    """params_page 离线可构建; 无 session 时禁用; 有 client 时编辑越界红标、已改未发黄标。"""
    from PyQt5.QtWidgets import QApplication
    from litetool import param_catalog as C
    from litetool.gui.params_page import ParamsPage

    class _Fake:                      # 仅用于非 None 判定
        pass

    app = QApplication.instance() or QApplication([])
    pg = ParamsPage()
    pg.set_online(True)                # 无 client -> 仍禁用
    assert pg.btn_refresh.isEnabled() is False

    pg.set_client(_Fake())
    pg.set_online(True)
    ri = next(i for i, p in enumerate(C.JOINT_PARAMS) if p.key == "kp")
    pg._loading = True
    pg._set_table_val(ri, 0, 360.0)    # 程序化填入 (itemChanged 被 loading 屏蔽)
    pg._loading = False
    pg._synced.setdefault("kp", {})[0] = 360.0
    pg._refresh_cell_color(ri, 0)
    assert pg.table.item(ri, 1).background().color().name() == "#ffffff"
    it = pg.table.item(ri, 1)
    it.setText("380")                  # 模拟双击编辑 -> 自动 itemChanged
    assert it.background().color().name() == "#fff3bf"      # 已改未发(黄)
    it.setText("99999")                # 越界 -> 红
    assert it.background().color().name() == "#ffd9d9"
    pg.deleteLater()
