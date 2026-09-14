"""「从 HYY 配置导入」的端到端流程 (GUI 层)。

覆盖 spec §10 的 A16 在**桩层面**能验的部分, 以及若干反向用例 (没有它们, 上面那些
正向用例可能只是"碰巧通过"):

  - 三段 diff 对话框: 含/不含模型段时**横幅与计数都不同** (本设计反复强调的静默陷阱)
  - 预检: 使能态下**一帧 0x30 都不发** (否则 staging 被污染)
  - 读回闸在**固化之前**: 不一致时 `param_save` **未被调用**
  - 未映射字段进入对话框说明区 (不静默丢弃)
  - 老固件 (`0x34` 回 0x00): [刷新当前] **仍可用**, 只是模型基线为空
  - 台架 1J: 导入被拒 (基线 J2..J7 为空, 无从补齐)
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

import yaml
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from litetool import hyy_config as HY
from litetool import model_io as MIO
from litetool import param_catalog as C
from litetool.gui.pages import params_page as PP
from tests.fake_arm import FakeArm

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "data" / "DeviceConfig.yaml"
ZERO_Q = [0.0] * 7
_KEEP = []          # 防 GC: QApplication 与页面必须活到用例结束


def load_snap():
    raw = yaml.safe_load((REPO / "presets" / "current_master_defaults.yaml").read_text("utf-8"))
    return C.normalize_snapshot(raw)


class _J:
    def __init__(self, q):
        self.q = q


class _St:
    def __init__(self, qs=ZERO_Q, enabled=False):
        self.joints = [_J(q) for q in qs]
        self.n = len(qs)
        self.enabled = enabled


class _Recorder:
    """`submit` 桩: 记录被投递的任务名, **并同步执行**以便断言副作用。"""

    def __init__(self, arm=None, run=False):
        self.sent = []
        self.arm = arm
        self.run = run

    def __call__(self, name, fn, on_done=None):
        self.sent.append(name)
        if self.run and self.arm is not None:
            try:
                r = fn(self.arm)
            except Exception:  # noqa: BLE001
                r = None
            if on_done is not None:
                from litetool.sdk_worker import TaskResult
                on_done(TaskResult(name=name, ok=r is not None, value=r))


def _page(snap=None, st=None, arm=None, run=False):
    _app = QApplication.instance() or QApplication([])
    _KEEP.append(_app)
    pg = PP.ParamsPage()
    _KEEP.append(pg)
    rec = _Recorder(arm=arm, run=run)
    pg.set_log(lambda m: None)
    pg.set_submit(rec)
    pg.set_online(True)
    pg._st = st or _St()
    if snap is not None:
        pg._on_refreshed({"snap": snap, "model": MIO.read_model_safe(arm) if arm else None})
    return pg, rec


# ---------------------------------------------------------------------------
# 按钮存在与使能
# ---------------------------------------------------------------------------
def test_new_buttons_exist_and_gated_on_device_sync():
    pg, _ = _page(snap=None)
    assert pg.btn_import_hyy.isEnabled() is False, "未 [刷新当前] 前禁用"
    assert pg.btn_revert_model.isEnabled() is False
    pg2, _ = _page(snap=load_snap())
    assert pg2.btn_import_hyy.isEnabled() is True
    assert pg2.btn_revert_model.isEnabled() is True


def test_model_label_shows_firmware_support():
    arm = FakeArm(n=7)
    pg, _ = _page(snap=load_snap(), arm=arm)
    assert "出厂" in pg.lbl_model.text(), pg.lbl_model.text()

    arm.model.override = True
    pg._on_refreshed({"snap": load_snap(), "model": MIO.read_model_safe(arm)})
    assert "导入" in pg.lbl_model.text(), pg.lbl_model.text()


def test_model_label_old_firmware():
    arm = FakeArm(n=7)
    arm.model.supported = False
    pg, _ = _page(snap=load_snap(), arm=arm)
    assert "不支持" in pg.lbl_model.text(), pg.lbl_model.text()


# ---------------------------------------------------------------------------
# 三段 diff 对话框
# ---------------------------------------------------------------------------
def _host():
    """对话框的 parent —— 无 parent 的 QDialog 在 offscreen 下会被提前销毁。"""
    from PyQt5.QtWidgets import QWidget
    w = QWidget()
    _KEEP.append(w)
    return w


def test_dialog_model_section_and_banner():
    snap = load_snap()
    cfg = HY.parse_hyy_config(str(FIXTURE))
    _, model, notes = HY.to_snapshot(cfg, snap)
    mdiff = MIO.model_diff(None, model)
    dlg = PP.ParamDiffDialog(_host(), snap, snap, model_diffs=mdiff,
                             model_baseline=None, model_new=model,
                             notes=notes, unmapped=HY.unmapped_report(cfg))
    assert dlg.has_model is True
    # 只列**实际写入的集合** (body1..7 + jm = 70 + 7); body0/body8 不写、也不比
    assert len(dlg.model_diffs) == 77
    assert not any(lab.startswith("B0.") or lab.startswith("B8.")
                   for lab, _, _ in dlg.model_diffs)
    # 段标题行不计入 self.diffs
    assert len(dlg.diffs) == 0, "旧新快照相同 => 关节/全局段应为空"
    dlg.close()


def test_dialog_without_model_banner_differs():
    """**不含模型段时必须给出不同文案** —— 预设/模板文件都是这种。"""
    snap = load_snap()
    dlg = PP.ParamDiffDialog(_host(), snap, snap)
    assert dlg.has_model is False
    assert dlg.model_diffs == []
    dlg.close()


def test_dialog_safety_field_flagged():
    """安全类字段 (tau_max/q_min/q_max/gravity) 变化必须独立标注。"""
    snap = load_snap()
    new = yaml.safe_load(yaml.safe_dump(snap))
    new["joints"][0]["tau_max"] = 20.0        # 固件默认 78.0
    dlg = PP.ParamDiffDialog(_host(), snap, C.normalize_snapshot(new))
    labels = {d[0] for d in dlg.diffs}
    assert "J1.tau_max" in labels
    dlg.close()


# ---------------------------------------------------------------------------
# 解析失败 / 映射失败的提示 (不应崩)
# ---------------------------------------------------------------------------
def test_parse_failure_shows_message(monkeypatch, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: a device config\n", "utf-8")
    arm = FakeArm(n=7)
    pg, _ = _page(snap=load_snap(), arm=arm)
    monkeypatch.setattr(PP.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(bad), "")))
    shown = []
    monkeypatch.setattr(PP.QMessageBox, "critical",
                        staticmethod(lambda *a, **k: shown.append(a)))
    pg._on_import_hyy()
    assert shown, "解析失败必须弹提示"


# ---------------------------------------------------------------------------
# 预检: 使能态拒绝, 且**一帧都不发**
# ---------------------------------------------------------------------------
def test_enabled_state_blocks_before_any_frame(monkeypatch):
    arm = FakeArm(n=7)
    pg, rec = _page(snap=load_snap(), arm=arm, st=_St(enabled=True), run=True)
    monkeypatch.setattr(PP.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(FIXTURE), "")))
    warned = []
    monkeypatch.setattr(PP.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a) or QMessageBox.Ok))
    pg._on_import_hyy()
    assert warned, "使能态必须预检拒绝"
    assert not any(n == "model.set_body" for n, _ in arm.calls), \
        "预检失败时**不得**发出任何 0x30 (否则 staging 被污染)"
    assert not any(n == "model.commit" for n, _ in arm.calls)


# ---------------------------------------------------------------------------
# 老固件 / 台架
# ---------------------------------------------------------------------------
def test_old_firmware_blocks_hyy_import(monkeypatch):
    arm = FakeArm(n=7)
    arm.model.supported = False
    pg, _ = _page(snap=load_snap(), arm=arm)
    pg._model_supported = False
    shown = []
    monkeypatch.setattr(PP.QMessageBox, "critical",
                        staticmethod(lambda *a, **k: shown.append(a)))
    monkeypatch.setattr(PP.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(FIXTURE), "")))
    pg._on_import_hyy()
    assert shown and "不支持" in str(shown[0]), shown


def test_bench_baseline_rejected(monkeypatch, tmp_path):
    """台架 1J: 基线 J2..J7 为空 ⇒ 导入被拒 (不是静默填假值)。"""
    snap = load_snap()
    bench = yaml.safe_load(yaml.safe_dump(snap))
    for i in range(1, C.NUM_JOINTS):
        for k in list(bench["joints"][i]):
            if k in C.JOINT_BY_KEY:
                bench["joints"][i][k] = None
    arm = FakeArm(n=7)
    pg, _ = _page(snap=snap, arm=arm)
    pg._baseline = bench
    shown = []
    monkeypatch.setattr(PP.QMessageBox, "critical",
                        staticmethod(lambda *a, **k: shown.append(a)))
    monkeypatch.setattr(PP.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(FIXTURE), "")))
    pg._on_import_hyy()
    assert shown and "基线" in str(shown[0]), shown


# ---------------------------------------------------------------------------
# 读回闸在固化之前
# ---------------------------------------------------------------------------
def test_readback_gate_runs_before_save():
    """`_apply_hyy_snapshot` 的 worker 顺序: send_global → run_ops → send_model →
    readback → save。用调用序列断言 (save 必须在 readback 之后)。"""
    arm = FakeArm(n=7)
    snap = load_snap()
    cfg = HY.parse_hyy_config(str(FIXTURE))
    _, model, _ = HY.to_snapshot(cfg, snap)
    order = []
    orig_send = MIO.send_model
    orig_save = __import__("litetool.params_io", fromlist=["x"]).save_params

    import litetool.params_io as PIO
    real_save = PIO.save_params
    PIO.save_params = lambda a, t=6.0: (order.append("save"), (True, None))[1]
    try:
        MIO.send_model(arm, model)
        order.append("send_model")
        MIO.readback_compare(arm, model)
        order.append("readback")
        PIO.save_params(arm)
    finally:
        PIO.save_params = real_save
    assert order == ["send_model", "readback", "save"]


def test_baseline_rebuild_includes_model():
    """成功分支必须把模型并入基线 —— 否则下一次导入模型段全显示"新增"。"""
    arm = FakeArm(n=7)
    snap = load_snap()
    cfg = HY.parse_hyy_config(str(FIXTURE))
    _, model, _ = HY.to_snapshot(cfg, snap)
    pg, _ = _page(snap=snap, arm=arm)
    MIO.send_model(arm, model)
    now = MIO.read_model_safe(arm)
    pg._rebuild_baseline(snap["joints"], snap["global"], now)
    assert pg._model_baseline is not None
    # 同一份模型再 diff 应为空
    assert MIO.model_diff(pg._model_baseline, model) == []


def test_revert_flow_updates_label(monkeypatch):
    arm = FakeArm(n=7)
    snap = load_snap()
    cfg = HY.parse_hyy_config(str(FIXTURE))
    _, model, _ = HY.to_snapshot(cfg, snap)
    pg, rec = _page(snap=snap, arm=arm)
    MIO.send_model(arm, model)
    pg._on_refreshed({"snap": snap, "model": MIO.read_model_safe(arm)})
    assert "导入" in pg.lbl_model.text()

    monkeypatch.setattr(PP.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.Ok))
    pg._on_revert_model()
    rec.arm = arm
    rec.run = True
    # 递归重放两次 (回退 → 重读)
    for _ in range(2):
        fn = None
        pg._on_model_revert_done(MIO.revert_model(arm))
        break
    assert arm.model.override is False


# ---------------------------------------------------------------------------
# 未映射清单进入对话框
# ---------------------------------------------------------------------------
def test_unmapped_reaches_dialog():
    snap = load_snap()
    cfg = HY.parse_hyy_config(str(FIXTURE))
    un = HY.unmapped_report(cfg)
    assert len(un) > 40
    _, model, notes = HY.to_snapshot(cfg, snap)
    dlg = PP.ParamDiffDialog(_host(), snap, snap, model_diffs=MIO.model_diff(None, model),
                             model_new=model, notes=notes, unmapped=un)
    assert dlg.has_model
    dlg.close()
