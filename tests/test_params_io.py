"""`params_io` —— 在 litearm_core 之上的参数读写形状层。

页面要的是「逐写口一个 (ok, code)」；SDK 是「失败即抛异常」。这一层就是那道缝，
所以既要验**成功路径**的数值正确，也要验**失败路径**的 code 没有被吃掉 ——
参数页靠 code 把失败标到具体格上。
"""
from pathlib import Path

import pytest
import yaml

import litearm_core as pa

from litetool import param_catalog as C
from litetool import params_io as PIO
from tests.fake_arm import FakeArm

REPO = Path(__file__).resolve().parents[1]


def load_snap():
    raw = yaml.safe_load((REPO / "templates" / "params_example.yaml").read_text("utf-8"))
    return C.normalize_snapshot(raw)


# ---------------------------------------------------------------- 读回
def test_read_snapshot_shape_and_values():
    arm = FakeArm()
    snap = PIO.read_snapshot(arm)
    assert len(snap["joints"]) == C.NUM_JOINTS
    j0 = snap["joints"][0]
    for key in ("kp", "kd", "tau_max", "q_min", "q_max"):
        assert key in j0
    assert j0["kp"] == arm.params.kp[0]
    for p in C.JOINT_PARAMS:
        if p.kind == "vec":
            assert j0[p.key] == arm.ff_vec[p.item][0]
    assert snap["global"]["ff_mask"] == 0x1BF
    assert "gravity" in snap["global"] and len(snap["global"]["gravity"]) == 3


def test_read_snapshot_raises_on_partial_failure():
    """半截快照比没有更危险 —— 它会被当成基线。"""
    arm = FakeArm()
    arm.raise_error = pa.MotionTimeoutError("无应答")
    with pytest.raises(OSError):
        PIO.read_snapshot(arm)


# ---------------------------------------------------------------- 单写口
def test_set_joint_param_ok_and_rejected():
    arm = FakeArm()
    assert PIO.set_joint_param(arm, 0, 111.0, 2.0, 30.0) == (True, None)
    assert arm.params.kp[0] == 111.0

    arm.reject(0x22, 0x02, "set_joint_param")
    ok, code = PIO.set_joint_param(arm, 0, 1.0, 1.0, 1.0)
    assert not ok and code == 0x02


def test_unsupported_by_firmware_maps_to_code_zero():
    """固件没实现该命令时回 ERR{cmd,0x00} —— code 必须原样透出（不是 None）。"""
    arm = FakeArm()
    arm.reject(0x36, 0x00, "reset_factory")
    ok, code = PIO.save_params(arm)
    assert not ok and code == 0x00


def test_timeout_maps_to_none_code():
    arm = FakeArm()
    arm.raise_error = pa.MotionTimeoutError("无应答")
    ok, code = PIO.set_ff_mask(arm, 0x1BF)
    assert not ok and code is None
    assert "超时" in PIO.err_text(code)


def test_err_text_known_and_unknown():
    assert "未使能" in PIO.err_text(0x03)
    assert "0x7F" in PIO.err_text(0x7F)
    assert "超时" in PIO.err_text(None)


# ---------------------------------------------------------------- 批量
def test_run_ops_marks_failures_per_cell():
    arm = FakeArm()
    ops = [
        {"cells": [("kp", 0, 5.0)], "run": lambda a: PIO.set_joint_param(a, 0, 5, 2, 30)},
        {"cells": [("kd", 1, 6.0)], "run": lambda a: (False, 0x02)},
    ]
    res = PIO.run_ops(arm, ops)
    assert res["ok"] == {("kp", 0): 5.0}
    assert res["fail"] == {("kd", 1): 0x02}


def test_run_ops_survives_exception():
    arm = FakeArm()
    ops = [{"cells": [("kp", 0, 1.0)],
            "run": lambda a: (_ for _ in ()).throw(RuntimeError("boom"))}]
    res = PIO.run_ops(arm, ops)
    assert res["ok"] == {} and res["fail"][("kp", 0)] is None


def test_send_global_sends_ff_mask_exactly_once():
    """0x27 只发一次（Important-3）—— 逐叶重复发会把 ff_mask 反复改写。"""
    arm = FakeArm()
    g = load_snap()["global"]
    g, leaf_ok, model_ok, mask_ok = PIO.send_global(arm, g)
    masks = [c for c in arm.calls if c[0] == "set_ff_mask"]
    scalars = [c for c in arm.calls if c[0] == "set_ff_scalar"]
    assert len(masks) == 1
    assert len(scalars) == 21          # 20 个循环叶 + friction_model
    assert all(leaf_ok.values()) and model_ok and mask_ok


def test_send_global_reports_partial_failure():
    arm = FakeArm()
    g = load_snap()["global"]
    arm.reject(0x28, 0x02, "set_ff_scalar")     # 第一个叶失败
    g, leaf_ok, model_ok, mask_ok = PIO.send_global(arm, g)
    assert not all(leaf_ok.values())
    assert not leaf_ok[C.GLOBAL_PARAMS[0].key]


# ---------------------------------------------------------------- 导出
def test_dump_snapshot_roundtrip(tmp_path):
    arm = FakeArm()
    snap = PIO.read_snapshot(arm)
    out = tmp_path / "p.yaml"
    PIO.dump_snapshot(snap, str(out))
    back = C.normalize_snapshot(yaml.safe_load(out.read_text("utf-8")))
    assert back["joints"][0]["kp"] == snap["joints"][0]["kp"]
    assert back["global"]["ff_mask"] == snap["global"]["ff_mask"]


def test_reset_factory_ok_and_rejected():
    arm = FakeArm()
    assert PIO.reset_factory(arm) == (True, None)
    assert any(c[0] == "reset_factory" for c in arm.calls)

    arm.reject(0x36, 0x04, "reset_factory")      # enable 态：固件要求先失能
    ok, code = PIO.reset_factory(arm)
    assert not ok and code == 0x04
    assert "disable" in PIO.err_text(code)


# ---------------------------------------------------------------- 台架 1J 降级
def test_read_snapshot_on_1j_bench_marks_missing_joints_none():
    """台架 1J：真 SDK 的 `_check_idx` 对 idx≥1 会抛，所以只能读 1 个关节。

    超出的列填 None，由页面显示"—"并封禁编辑 —— 而不是让整个 [刷新当前] 挂掉。
    """
    arm = FakeArm(n=1)
    snap = PIO.read_snapshot(arm)
    assert len(snap["joints"]) == C.NUM_JOINTS
    assert snap["joints"][0]["kp"] is not None
    assert all(v is None for v in snap["joints"][1].values())
    assert all(v is None for v in snap["joints"][6].values())
    # 全局段不受影响
    assert snap["global"]["ff_mask"] == 0x1BF


def test_read_snapshot_7j_has_no_none():
    arm = FakeArm(n=7)
    snap = PIO.read_snapshot(arm)
    for row in snap["joints"]:
        assert all(v is not None for v in row.values()), row


def test_n_readable_clamps_to_arm_and_table_width():
    assert PIO.n_readable(FakeArm(n=7)) == C.NUM_JOINTS
    assert PIO.n_readable(FakeArm(n=1)) == 1
    assert PIO.n_readable(FakeArm(n=0)) == 0
