"""页面 → SDK 的端到端接线 —— 用真 `SdkWorker` 驱动假 `Arm`。

单元测试各自验形状，这一层验**接线**：用户点一下按钮，最终真的落到哪个 SDK 调用上。
"功能全覆盖"这句话只有在这里才被真正验证 —— 少接一根线，这里就会红。
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("numpy")

from PyQt5.QtWidgets import QApplication                     # noqa: E402

from litetool import settings as settings_mod                # noqa: E402
from litetool.gui.main_window import MainWindow              # noqa: E402
from tests.fake_arm import FakeArm                           # noqa: E402


def pump(app, pred, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if pred():
            return True
        time.sleep(0.005)
    app.processEvents()
    return pred()


@pytest.fixture
def win():
    app = QApplication.instance() or QApplication([])
    w = MainWindow(settings_mod.Settings.load(None))
    arm = FakeArm()
    w.worker._factory = lambda port: arm
    w.worker.open(None)
    w._apply_online(True, "test")
    assert pump(app, lambda: w._n == 7)
    # 本文件验的是「接线」不是「闸门」—— 先把运动解锁，否则每条运动命令都会被
    # MainWindow 的 _motion_denied 挡掉（闸门本身由 test_safety_ui 覆盖）
    w.unlock_cb.setChecked(True)
    assert w._armed
    yield w, arm, app
    w.close()


def calls_of(arm, name):
    return [c for c in arm.calls if c[0] == name]


# ---------------------------------------------------------------- 整机
def test_enable_and_disable_reach_sdk(win):
    w, arm, app = win
    w._on_ctrl_cmd("enable")
    assert pump(app, lambda: calls_of(arm, "enable"))
    w._on_ctrl_cmd("disable")
    assert pump(app, lambda: calls_of(arm, "disable"))


def test_home_confirmed_reaches_sdk(win, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    w, arm, app = win
    monkeypatch.setattr("litetool.gui.main_window.QMessageBox.question",
                        lambda *a, **k: QMessageBox.Ok)
    w._on_ctrl_cmd("home")
    assert pump(app, lambda: calls_of(arm, "home"))


def test_clear_faults_and_reset_reach_sdk(win, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    w, arm, app = win
    monkeypatch.setattr("litetool.gui.main_window.QMessageBox.question",
                        lambda *a, **k: QMessageBox.Ok)
    w._on_ctrl_cmd("clear_faults")
    assert pump(app, lambda: calls_of(arm, "clear_faults"))
    w._on_ctrl_cmd("reset")
    assert pump(app, lambda: calls_of(arm, "reset"))


def test_speed_and_park_reach_sdk(win):
    w, arm, app = win
    w._on_set_speed(35)
    assert pump(app, lambda: calls_of(arm, "set_speed"))
    assert calls_of(arm, "set_speed")[0][1] == 35
    w.pages["machine"].park_req.emit()
    assert pump(app, lambda: calls_of(arm, "park"))


def test_status_now_reports_metrics(win):
    w, arm, app = win
    w._on_status_now()
    assert pump(app, lambda: "seq=" in w.pages["machine"].status_lbl.text())


# ---------------------------------------------------------------- 关节
def test_movej_reaches_sdk(win, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    w, arm, app = win
    monkeypatch.setattr("litetool.gui.main_window.QMessageBox.warning",
                        lambda *a, **k: QMessageBox.Ok)
    w._on_movej([0.0] * 7, 0.25)
    assert pump(app, lambda: calls_of(arm, "movej"))
    assert calls_of(arm, "movej")[0][1] == ([0.0] * 7, 0.25)


def test_move_js_mit_one_mit_all_reach_sdk(win, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    w, arm, app = win
    monkeypatch.setattr("litetool.gui.main_window.QMessageBox.warning",
                        lambda *a, **k: QMessageBox.Ok)
    w._on_move_js([0.0] * 7, [0.0] * 7, None)
    assert pump(app, lambda: calls_of(arm, "move_js"))
    w._on_mit_one(2, 0.0, 0.0, 30.0, 2.0, 0.0)
    assert pump(app, lambda: calls_of(arm, "send_mit"))
    w._on_mit_all([0.0] * 7, [0.0] * 7, [30.0] * 7, [2.0] * 7, [0.0] * 7)
    assert pump(app, lambda: calls_of(arm, "send_mit_all"))


# ---------------------------------------------------------------- 笛卡尔
def test_get_tcp_and_ik_report_back(win, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    w, arm, app = win
    w._on_get_tcp()
    assert pump(app, lambda: w.pages["cart"]._tcp is not None)
    monkeypatch.setattr("litetool.gui.main_window.QMessageBox.warning",
                        lambda *a, **k: QMessageBox.Ok)
    w._on_ik([0.3, 0.0, 0.35, 3.14, 0.0, 0.0], None)
    assert pump(app, lambda: w.pages["cart"].ik_out.toPlainText())


def test_movep_reaches_sdk(win, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    w, arm, app = win
    monkeypatch.setattr("litetool.gui.main_window.QMessageBox.warning",
                        lambda *a, **k: QMessageBox.Ok)
    w._on_movep([0.30, 0.0, 0.35, 3.1416, 0.0, 0.0], 0.2)
    assert pump(app, lambda: calls_of(arm, "move_p"))


# ---------------------------------------------------------------- 零重力 / 采集 / 诊断
def test_zero_g_start_and_stop_reach_sdk(win):
    w, arm, app = win
    w._on_zero_g(True)
    assert pump(app, lambda: calls_of(arm, "zero_g_start"))
    assert pump(app, lambda: w.pages["zerog"].btn.isChecked())
    w._on_zero_g(False)
    assert pump(app, lambda: calls_of(arm, "zero_g_stop"))
    assert pump(app, lambda: not w.pages["zerog"].btn.isChecked())


def test_capture_start_read_dump_reach_sdk(win, tmp_path):
    """注意 pump 的条件要落在**界面已更新**上：worker 记下调用 ≠ GUI 已处理回调。"""
    w, arm, app = win
    page = w.pages["capture"]
    page.n_ticks.setValue(30)
    page.btn_start.click()
    assert pump(app, lambda: "已开始记录 30 拍" in page.prog_lbl.text())
    page.btn_prog.click()
    assert pump(app, lambda: "42 拍" in page.prog_lbl.text())
    page.btn_read.click()
    assert pump(app, lambda: "读回 3 拍" in page.prog_lbl.text())
    page.btn_capture.click()
    assert pump(app, lambda: calls_of(arm, "log.capture"))


def test_capture_dump_writes_file(win, tmp_path, monkeypatch):
    w, arm, app = win
    out = tmp_path / "cap.bin"
    monkeypatch.setattr("litetool.gui.pages.capture_page.QFileDialog.getSaveFileName",
                        lambda *a, **k: (str(out), ""))
    w.pages["capture"].btn_dump.click()
    assert pump(app, lambda: calls_of(arm, "log.dump"))
    assert out.exists()


def test_kin_bench_parsed_into_diag_page(win):
    w, arm, app = win
    w._on_bench()
    assert pump(app, lambda: calls_of(arm, "kin_bench"))
    assert pump(app, lambda: w.pages["diag"].vals["reply_dropped"].text() == "1")
    assert w.pages["diag"].vals["loop_overruns"].text() == "2"
    assert "LOOP14000" in w.pages["diag"].raw.toPlainText()


# ---------------------------------------------------------------- 参数页
def test_params_refresh_reads_through_sdk(win):
    """参数页 [刷新当前] 必须真的走 SDK 的 params/ff 读口。"""
    w, arm, app = win
    pg = w.pages["params"]
    pg._on_refresh()
    assert pump(app, lambda: pg._device_synced)
    assert len(calls_of(arm, "get_joint_param")) == 7
    assert calls_of(arm, "get_ff_scalar")
    assert pg.btn_apply_all.isEnabled()


# ---------------------------------------------------------------- 台架 1J
def test_ik_on_1j_bench_does_not_send_bad_seed():
    """台架 1J：实测角只有 1 个，不能当 IK 种子喂给 SDK（它要 7 个模型轴）。

    真 SDK 会抛 `q_seed 需 7 个`；替身原先不校验，把这条真缺陷藏住了 —— 现在会。
    """
    app = QApplication.instance() or QApplication([])
    w = MainWindow(settings_mod.Settings.load(None))
    arm = FakeArm(n=1)
    w.worker._factory = lambda port: arm
    w.worker.open(None)
    w._apply_online(True, "bench")
    try:
        assert pump(app, lambda: w._n == 1)
        assert w.pages["cart"]._seed_q and len(w.pages["cart"]._seed_q) == 1
        w._on_ik([0.3, 0.0, 0.35, 0.0, 0.0, 0.0], w.pages["cart"]._seed_q)
        assert pump(app, lambda: w.pages["cart"].ik_out.toPlainText())
        txt = w.pages["cart"].ik_out.toPlainText()
        assert "失败" not in txt, f"台架 IK 失败: {txt}"
        # 真正发给 SDK 的 seed 必须是 None（由 SDK 按模型轴构造）
        _, seed = calls_of(arm, "ik")[0][1]
        assert seed is None, f"喂了长度 {len(seed)} 的种子给 SDK"
    finally:
        w.close()
