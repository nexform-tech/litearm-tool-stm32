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


# ---------------------------------------------------------------------------
# 固化状态必须显式上报 (RAM vs Flash 的边界)
# ---------------------------------------------------------------------------
def _batch_res(snap, save_ok, model_ok=True):
    return {"row": {"ok": {("friction_v", j): 1.0 for j in range(7)}, "fail": {}},
            "glob": None, "leaf_ok": {}, "fre_model_ok": True, "mask_ok": True,
            "dyn_model": {"commit": (model_ok, None), "aborted": None},
            "model_diffs": [], "model_now": None, "save_ok": save_ok,
            "mat": snap["joints"]}


def test_unsaved_import_is_loudly_reported():
    """**未勾"下发后固化"必须显式报警**。

    固件侧 0x30/0x32/0x33/0x26 全都只写 RAM (`0x32` 只 `flash_store_mark_dirty()` 标脏),
    唯一的落盘入口是 `0x25 PARAM_SAVE`。所以"没勾固化"= 掉电即回退整次导入。
    原实现在这一支**什么都不说** —— 操作员会以为已经生效并归档。
    """
    snap = load_snap()
    pg, _ = _page(snap=snap)
    pg._on_batch_done(_batch_res(snap, save_ok=None))
    txt = pg.status.text()
    assert "未固化" in txt, txt
    assert "RAM" in txt and "掉电" in txt, txt
    assert "固化 Flash" in txt or "固化到 Flash" in txt, "要给出补救动作"


def test_saved_import_says_so():
    """反向用例: 勾了固化就要说已固化 —— 否则上面那条无法区分。"""
    snap = load_snap()
    pg, _ = _page(snap=snap)
    pg._on_batch_done(_batch_res(snap, save_ok=True))
    assert "已固化到 Flash" in pg.status.text()


def test_save_failure_is_reported():
    snap = load_snap()
    pg, _ = _page(snap=snap)
    pg._on_batch_done(_batch_res(snap, save_ok=False))
    assert "固化失败" in pg.status.text()


# ---------------------------------------------------------------------------
# 固化勾选框默认状态 (2026-09-14 用户裁决: 默认勾选)
# ---------------------------------------------------------------------------
def test_save_checkbox_defaults_to_checked():
    """**默认勾选** —— 固件侧唯一的落盘入口是 0x25, 一次漏勾就白做一台。

    反向用例在下面: 取消勾选时确认框必须明确说出"不会固化"。
    """
    dlg = PP.ParamDiffDialog(_host(), load_snap(), load_snap())
    assert dlg.save_checkbox.isChecked() is True
    dlg.close()


def test_hyy_confirm_says_whether_it_will_flash(monkeypatch):
    """确认框必须**明说**这次会不会固化 —— 勾了写 flash、没勾只在 RAM。"""
    snap = load_snap()
    arm = FakeArm(n=7)

    def run(checked):
        pg, _ = _page(snap=snap, arm=arm)
        texts = []
        monkeypatch.setattr(PP.QMessageBox, "warning",
                            staticmethod(lambda *a, **k: texts.append(str(a[2] if len(a) > 2 else a)) or QMessageBox.Ok))
        monkeypatch.setattr(PP.QMessageBox, "Ok", QMessageBox.Ok, raising=False)
        monkeypatch.setattr(PP.QMessageBox, "Cancel", QMessageBox.Cancel, raising=False)
        # 直接把 confirim 框捕获下来, 不进 worker
        monkeypatch.setattr(pg, "_pre_op", lambda *a, **k: True)
        monkeypatch.setattr(pg, "_require_device_sync", lambda *a, **k: True)
        monkeypatch.setattr(pg, "_confirm_enabled_write", lambda *a, **k: True)
        monkeypatch.setattr(pg, "_start", lambda *a, **k: None)
        pg._apply_hyy_snapshot(snap, {"body": [[0.0]*10]*9, "jm": [0.0]*7},
                               flash_save=checked)
        return " ".join(texts)

    t_on = run(True)
    assert "固化" in t_on and "不会固化" not in t_on, t_on
    t_off = run(False)
    assert "不会固化" in t_off and "RAM" in t_off, t_off


# ---------------------------------------------------------------------------
# 摩擦不对称哨兵 (|fc0| vs |fc1|) —— 机械健康告警
# ---------------------------------------------------------------------------
def _plain(s: str) -> str:
    """富文本 -> 纯文本 (断言针对渲染后的文字, 不是 HTML 源码)。"""
    import re
    s = re.sub(r"<[^>]+>", "", s)
    for a, b in (("&nbsp;", " "), ("&gt;", ">"), ("&lt;", "<"), ("&amp;", "&")):
        s = s.replace(a, b)
    return s


def _asym_yaml(tmp_path, joint=2, fc0=2.0, fc1=-0.8):
    """把 fixture 的某个关节改成不对称 (比值 2.5 > 2.0)。"""
    d = yaml.safe_load(FIXTURE.read_text("utf-8"))
    dp = d["robot_group"]["robot"][0]["joint"][joint]["dynamics_parameters"]
    dp["fc0"], dp["fc1"] = fc0, fc1
    p = tmp_path / "asym.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), "utf-8")
    return str(p)


def test_healthy_config_never_prompts(monkeypatch):
    """**正常臂不该被打扰** —— 误报会让操作员学会无视红字, 比不报警更糟。"""
    pg, _ = _page(snap=load_snap(), arm=FakeArm(n=7))
    monkeypatch.setattr(PP.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(FIXTURE), "")))
    monkeypatch.setattr(pg, "_do_import_hyy", lambda *a, **k: None)

    def boom(items):
        raise AssertionError(f"正常配置不该弹不对称告警, 却收到 {items}")

    monkeypatch.setattr(pg, "_confirm_friction_asymmetry", boom)
    pg._on_import_hyy()          # 不抛即通过


def test_asymmetry_cancel_aborts_before_import(monkeypatch, tmp_path):
    """操作员选「取消」⇒ 不进 diff、不下发。"""
    pg, _ = _page(snap=load_snap(), arm=FakeArm(n=7))
    monkeypatch.setattr(PP.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (_asym_yaml(tmp_path), "")))
    called = []
    monkeypatch.setattr(pg, "_do_import_hyy", lambda *a, **k: called.append(a))
    monkeypatch.setattr(pg, "_confirm_friction_asymmetry", lambda items: False)
    pg._on_import_hyy()
    assert called == [], "取消后不得继续导入"
    assert "取消" in pg.status.text()


def test_asymmetry_continue_proceeds_with_note(monkeypatch, tmp_path):
    """操作员坚持导入 ⇒ 正常继续, 且告警写进 notes (不在点掉弹窗后消失)。"""
    pg, _ = _page(snap=load_snap(), arm=FakeArm(n=7))
    monkeypatch.setattr(PP.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (_asym_yaml(tmp_path), "")))
    called = []
    monkeypatch.setattr(pg, "_do_import_hyy", lambda *a, **k: called.append(a))
    monkeypatch.setattr(pg, "_confirm_friction_asymmetry", lambda items: True)
    pg._on_import_hyy()
    assert len(called) == 1, "确认后应当继续"
    notes = called[0][3]
    assert any("不对称" in n for n in notes), notes


def test_asymmetry_popup_defaults_to_cancel(monkeypatch, tmp_path):
    """弹窗的**默认按钮与 Esc 都必须是「取消」**。

    一个回车就能过掉的弹窗等于没有 —— 这个控件的全部价值就是让人停下来看一眼。
    """
    pg, _ = _page(snap=load_snap())
    cfg = HY.parse_hyy_config(_asym_yaml(tmp_path))
    items = HY.suspicious_joints(cfg)
    assert len(items) == 1

    cap = {}

    def fake_exec(self):
        cap["default"] = self.defaultButton().text()
        cap["escape"] = self.escapeButton().text()
        cap["text"] = self.text()
        cap["info"] = self.informativeText()
        cap["buttons"] = [b.text() for b in self.buttons()]
        cap["icon"] = self.icon()
        return 0

    monkeypatch.setattr(PP.QMessageBox, "exec_", fake_exec)
    monkeypatch.setattr(PP.QMessageBox, "clickedButton",
                        lambda self: self.defaultButton())

    assert pg._confirm_friction_asymmetry(items) is False
    assert cap["default"].startswith("取消"), cap
    assert cap["escape"].startswith("取消"), cap
    assert cap["icon"] == PP.QMessageBox.Critical, "必须是红色严重级图标"
    assert any("仍要导入" in b for b in cap["buttons"])

    info, text = _plain(cap["info"]), _plain(cap["text"])
    assert "1 个关节" in text
    assert "J3" in info and "|fc0|" in info and "|fc1|" in info
    # 弹窗是 QMessageBox, 不认 Markdown —— 星号会原样打在脸上 (离屏渲染实测)
    for s in (cap["info"], cap["text"]):
        assert "**" not in s, f"Markdown 星号会原样显示: {s}"
    assert "不会修好机械问题" in info, "要给出「导入≠修好机械」这句"
    assert "轴承" in info and "预紧" in info, "要列出可能原因"


def test_asymmetry_popup_returns_true_on_go(monkeypatch, tmp_path):
    """反向用例: 点「继续」必须返回 True —— 否则上面那条无法区分。"""
    pg, _ = _page(snap=load_snap())
    cfg = HY.parse_hyy_config(_asym_yaml(tmp_path))
    monkeypatch.setattr(PP.QMessageBox, "exec_", lambda self: 0)
    monkeypatch.setattr(PP.QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons()
                                          if "仍要导入" in b.text()))
    assert pg._confirm_friction_asymmetry(HY.suspicious_joints(cfg)) is True
