"""CSV 导出 —— 列名单位、关节选择、1J/7J 轴数、文件名与两条数据源的差异。

离线测试；GUI 部分用 offscreen，文件对话框与消息框都被替换，不写真实用户目录。
"""
from __future__ import annotations

import csv
import datetime as dt
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from litetool import csv_export
from litetool.plot_model import PlotModel
from tests.fake_arm import make_state


def _read(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


def _model(states, times):
    seq = iter(times)

    def clock():
        try:
            return next(seq)
        except StopIteration:
            return float(times[-1]) + 0.01

    m = PlotModel(window_s=60.0, clock=clock)
    for st in states:
        m.push(st)
    return m


def _states(n=7, count=3):
    out = []
    for k in range(count):
        st = make_state(n=n, seq=k, q=[0.1 * i + k for i in range(n)])
        for i, j in enumerate(st.joints):
            j.t_mos = 30.0 + i
            j.t_coil = 40.0 + i
            j.err = 1 if i % 2 == 0 else 13
        st.joint_fault = 0x5
        out.append(st)
    return out


# ------------------------------------------------------------ 文件名
def test_timestamped_name_carries_firmware_and_time():
    name = csv_export.timestamped_name(
        "plot", "Litearm1.12.3-7J", when=dt.datetime(2026, 11, 27, 14, 5, 6))
    assert name == "litearm_plot_Litearm1.12.3-7J_20261127-140506.csv"


def test_timestamped_name_sanitises_unsafe_characters():
    name = csv_export.timestamped_name("plot/窗口", "bad fw:1", when=dt.datetime(2026, 1, 2, 3, 4, 5))
    assert "/" not in name and " " not in name and ":" not in name
    assert name.endswith(".csv")


# ------------------------------------------------------------ 曲线 CSV
def test_plot_csv_has_units_and_selected_joints_only(tmp_path):
    snap = _model(_states(), [0.0, 0.01, 0.02]).snapshot_full()
    path = tmp_path / "plot.csv"
    rows = csv_export.write_plot_csv(str(path), snap, joints=[0, 2], firmware="fw")

    assert rows == 3
    got = _read(path)
    header = got[0]
    assert header[0] == "t (s)"
    assert header[1] == "joint_fault (mask)"
    assert "J1 q (rad)" in header
    assert "J1 dq (rad/s)" in header
    assert "J1 tau (Nm)" in header
    assert "J1 T_mos (°C)" in header
    assert "J3 err" in header
    assert "J2 q (rad)" not in header, "没勾选的关节不得出现在 CSV 里"
    assert len(got) == 4
    # 时间列相对本次导出的第一行
    assert [r[0] for r in got[1:]] == ["0.000000", "0.010000", "0.020000"]
    # J1 的 q 依次是 0,1,2；J3 是 0.2,1.2,2.2
    assert got[1][2] == "0"
    assert got[2][2] == "1"
    assert got[1][8] == "0.2"
    # 断轴位图逐行保留
    assert {r[1] for r in got[1:]} == {"5"}


def test_plot_csv_uses_one_joint_for_a_1j_bench(tmp_path):
    snap = _model(_states(n=1, count=2), [0.0, 0.01]).snapshot_full()
    path = tmp_path / "one.csv"
    csv_export.write_plot_csv(str(path), snap)
    header = _read(path)[0]
    assert "J1 q (rad)" in header
    assert "J2 q (rad)" not in header, "1J 台架不能混入 J2 列"


def test_plot_csv_rejects_an_empty_window(tmp_path):
    with pytest.raises(ValueError, match="没有数据"):
        csv_export.write_plot_csv(str(tmp_path / "x.csv"), PlotModel().snapshot_full())


def test_plot_csv_rejects_a_bad_joint_index(tmp_path):
    snap = _model(_states(n=3, count=1), [0.0]).snapshot_full()
    with pytest.raises(ValueError, match="关节索引"):
        csv_export.write_plot_csv(str(tmp_path / "x.csv"), snap, joints=[5])


# ------------------------------------------------------------ 采集 CSV
def _sample(tick, n=3, base=0.0):
    return SimpleNamespace(tick=tick,
                           q_ref=tuple(base + i for i in range(n)),
                           dq=tuple(0.5 + i for i in range(n)),
                           tau=tuple(1.5 + i for i in range(n)))


def test_capture_csv_time_and_fields(tmp_path):
    path = tmp_path / "cap.csv"
    rows = csv_export.write_capture_csv(
        str(path), [_sample(100), _sample(130), _sample(160)], firmware="fw")

    assert rows == 3
    got = _read(path)
    assert got[0][:2] == ["tick", "t (s)"]
    assert "J1 q_ref (rad)" in got[0] and "J3 tau (Nm)" in got[0]
    # 300Hz：30 tick = 0.1 s
    assert [r[1] for r in got[1:]] == ["0.000000", "0.100000", "0.200000"]
    assert got[1][2] == "0"


def test_capture_csv_never_invents_temperature_or_error_columns(tmp_path):
    path = tmp_path / "cap.csv"
    csv_export.write_capture_csv(str(path), [_sample(1)], firmware="fw")
    header = _read(path)[0]
    assert not any("T_mos" in h or "err" in h for h in header), \
        "固件 300Hz 缓冲没有温度/错误码，CSV 里不能编造"


def test_capture_csv_1j_vs_7j(tmp_path):
    one = tmp_path / "one.csv"
    csv_export.write_capture_csv(str(one), [_sample(0, n=1)])
    assert "J2 q_ref (rad)" not in _read(one)[0]

    seven = tmp_path / "seven.csv"
    csv_export.write_capture_csv(str(seven), [_sample(0, n=7)])
    assert "J7 q_ref (rad)" in _read(seven)[0]


def test_capture_csv_rejects_empty_samples(tmp_path):
    with pytest.raises(ValueError, match="还没有读回"):
        csv_export.write_capture_csv(str(tmp_path / "x.csv"), [])


# ------------------------------------------------------------ GUI 接线
pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")


@pytest.fixture(scope="module")
def app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_capture_page_exports_the_last_read_back(tmp_path, monkeypatch, app):
    from PyQt5.QtWidgets import QFileDialog

    from litetool.gui.pages.capture_page import CapturePage
    from litetool.sdk_worker import TaskResult

    page = CapturePage()
    try:
        page.set_firmware("Litearm1.12.3-7J")
        assert not page.btn_csv.isEnabled(), "还没读回时导出按钮必须灰着"
        page._after_read(TaskResult("log.reader", True, value=[_sample(0), _sample(30)]))
        assert page.btn_csv.isEnabled()

        target = tmp_path / "cap.csv"
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (str(target), "")))
        page._on_csv()
        assert target.exists()
        assert len(_read(target)) == 3
        assert "已导出 2 行" in page.prog_lbl.text()
    finally:
        page.close()


def test_plot_pane_exports_selected_joints_and_honours_freeze(tmp_path, monkeypatch, app):
    from PyQt5.QtWidgets import QFileDialog, QMessageBox

    from litetool.gui.pages.plot_pane import PlotPane

    model = _model(_states(count=2), [0.0, 0.01])
    pane = PlotPane(window_s=60.0)
    try:
        pane.set_joints(7)
        pane.set_context("Litearm1.12.3-7J")
        pane.refresh(model)
        assert pane.selected_joints() == [0, 1, 2], "默认勾选前三个关节"

        # 冻结后模型继续滚动，导出的仍应是冻结那一刻的两行
        pane._on_freeze(True)
        model.push(_states(count=1)[0])
        target = tmp_path / "plot.csv"
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (str(target), "")))
        seen = []
        monkeypatch.setattr(QMessageBox, "information",
                            staticmethod(lambda *a, **k: seen.append(a[2])))
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: seen.append(a[2])))
        pane._on_export()
        assert target.exists()
        got = _read(target)
        assert len(got) == 3, "冻结时只导出冻结那一刻的 2 行数据"
        assert "J3 q (rad)" in got[0] and "J4 q (rad)" not in got[0]
        assert "已写出 2 行" in seen[-1]
    finally:
        pane.close()
