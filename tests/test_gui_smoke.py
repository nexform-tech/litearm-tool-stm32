"""GUI 冒烟 —— offscreen 构造主窗口/各页并跑几轮空转，防 import/布局回归。

需要 PyQt5/pyqtgraph；无显示环境时用 offscreen 平台插件。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")

from litetool import settings as settings_mod                 # noqa: E402
from tests.fake_arm import make_state                         # noqa: E402

PAGE_KEYS = ("overview", "capture", "log", "machine", "fault", "joint", "cart",
             "zerog", "params", "install", "guide", "diag")


def _win():
    from PyQt5.QtWidgets import QApplication
    from litetool.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    _ = app
    return MainWindow(settings_mod.Settings.load(None))


def test_mainwindow_constructs_and_ticks_offscreen():
    w = _win()
    w._tick()            # worker 无状态的空转分支
    w._tick_plot()
    w._apply_busy()
    w.close()


def test_nav_has_three_groups_and_all_pages_registered():
    w = _win()
    assert w.nav.topLevelItemCount() == 3, "监视/操作/参数 三个分组"
    assert w.stack.count() == len(PAGE_KEYS)
    for key in PAGE_KEYS:
        assert key in w.pages, f"缺页面 {key}"
    w.close()


def test_activate_raises_an_existing_window():
    """第二个实例启动时走这里：窗口已隐藏/最小化也要能重新显示。"""
    w = _win()
    w.show()
    w.hide()
    w.activate()
    assert w.isVisible()
    w.close()


def test_log_page_is_wired_to_main_window_logs():
    w = _win()
    assert w.pages["log"].table.rowCount() >= 1, "启动那行 INFO 应进入日志页"
    assert w.pages["log"].slog is w.slog
    w.close()


def test_tick_with_full_state_touches_every_page():
    """一帧真实形状的状态喂进去，各页都不该抛异常。"""
    w = _win()
    w.worker._state = make_state(n=7, q=[0.1 * i for i in range(7)])
    w._tick()
    assert w._n == 7
    assert w.pages["overview"].plot._n == 7
    assert w.pages["joint"].mj_row.n == 7
    assert w.pages["overview"].table.table.rowCount() == 7
    w.close()


def test_narrow_bench_1j_state_is_handled():
    """台架 1J：关节数变化要重建各页输入行，不能崩。"""
    w = _win()
    w.worker._state = make_state(n=1)
    w._tick()
    assert w._n == 1
    assert w.pages["joint"].mj_row.n == 1
    w.close()


def test_params_page_registered_with_full_table():
    w = _win()
    pg = w.pages["params"]
    assert pg.table.columnCount() == 8          # 1 参数列 + J1..J7
    assert pg.table.rowCount() >= 16
    w.close()


def test_tuning_guide_page_builds_and_reveals():
    from PyQt5.QtWidgets import QApplication
    from litetool.gui.pages.guide_page import TuningGuidePage
    app = QApplication.instance() or QApplication([])
    _ = app
    g = TuningGuidePage()
    assert len(g._key_widget) >= 33
    assert "kp" in g._key_widget and "gravity" in g._key_widget
    assert "FRICTION" in g._key_widget
    g.reveal("kp")
    g.reveal("FRICTION")
    g.close()


def test_guide_jump_from_params():
    """params.show_guide -> 切到指南页并定位。"""
    w = _win()
    w._on_guide("kp")
    assert w.current_page() is w.pages["guide"]
    w.close()


def test_window_min_height_is_usable():
    """`QStackedWidget` 的最小高度取所有页的 max —— 任何一页撑高都会废掉整个窗口。

    曾经关节页用竖排关节输入，页面 2500px 高，把窗口最小高度顶到 2500px。
    """
    w = _win()
    assert w.minimumSizeHint().height() < 900, (
        f"窗口最小高度 {w.minimumSizeHint().height()}px —— 某页太高了")
    w.close()


def test_overview_zoom_toggles_table():
    w = _win()
    ov = w.pages["overview"]
    # 用 isHidden()（显式隐藏态）而非 isVisible()：offscreen 下窗口未 show，
    # 子控件一律报 not visible，断言不出"被逻辑隐藏"这件事
    assert not ov.split.widget(0).isHidden()
    ov.btn_zoom.setChecked(True)
    assert ov.split.widget(0).isHidden()
    ov.btn_zoom.setChecked(False)
    assert not ov.split.widget(0).isHidden()
    w.close()


def test_motion_pages_start_locked():
    """所有会动臂的页面在解锁前一律禁用。"""
    w = _win()
    for key in ("machine", "joint", "cart", "zerog"):
        page = w.pages[key]
        for name in ("btn_home", "btn_mj", "btn_mp", "btn"):
            b = getattr(page, name, None)
            if b is not None:
                assert not b.isEnabled(), f"{key}.{name} 未解锁却可用"
    w.close()


def test_capture_and_diag_pages_idle_offline():
    w = _win()
    assert not w.pages["capture"].btn_start.isEnabled()
    assert not w.pages["diag"].btn_bench.isEnabled()
    w._apply_online(True, "test")
    assert w.pages["diag"].btn_bench.isEnabled()
    w.close()


def test_plot_legend_hidden_until_there_are_curves():
    """空图例会在黑画布上留个空框子 —— 没曲线时先藏着，有曲线了再亮出来。"""
    w = _win()
    ov = w.pages["overview"]
    assert not any(lg.isVisible() for lg in ov.plot._legends.values())
    ov.set_joints(1)
    assert not any(lg.isVisible() for lg in ov.plot._legends.values())
    w.worker.model.push(make_state(n=1))
    ov.refresh_plot(w.worker.model)
    assert any(lg.isVisible() for lg in ov.plot._legends.values())
    w.close()
