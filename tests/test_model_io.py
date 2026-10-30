"""`litetool/model_io.py` —— 模型读写薄封装 (在 `arm.model` 之上)。

替身纪律: `tests/fake_arm._FakeModel` **实现了真实语义** (9 刚体与关节数解耦 /
掩码校验回 0x07 / 失能门控回 0x04 / 惰性拷贝按位图分组), 否则"替身替 SDK 撒谎"
—— 本项目已被这类问题坑过两次。
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from litetool import hyy_config as H
from litetool import model_io as M
from litetool import param_catalog as C
from tests.fake_arm import FakeArm

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "data" / "DeviceConfig.yaml"


@pytest.fixture()
def fake_arm():
    """本项目既有惯例: 直接 `FakeArm(n=7)` (见 tests/test_params_io.py)。"""
    return FakeArm(n=7)


@pytest.fixture()
def baseline() -> dict:
    return yaml.safe_load((REPO / "presets" / "current_master_defaults.yaml").read_text("utf-8"))


@pytest.fixture()
def model() -> dict:
    cfg = H.parse_hyy_config(str(FIXTURE))
    bench = yaml.safe_load((REPO / "presets" / "current_master_defaults.yaml").read_text("utf-8"))
    _, m, _ = H.to_snapshot(cfg, bench)
    return m


# ---------------------------------------------------------------------------
# 常量与契约
# ---------------------------------------------------------------------------
def test_mask_and_shape_constants():
    assert M.MASK_WRITTEN == 0x2FE
    assert M.MASK_WRITTEN == C.MODEL_MASK_WRITTEN
    assert M.NBODY == C.MODEL_NBODY == 9
    assert M.BODY_PARAMS == 10
    assert M.JM_N == C.MODEL_JM_N == 7


def test_err_text_covers_0x07():
    """0x07 (掩码不符) 必须与 0x02 (数值非法) 分开 —— 产线最常见的是前者。"""
    assert "掩码" in M.err_text(0x07)
    assert "数值" in M.err_text(0x02)
    assert M.err_text(None) == "超时/无应答"


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------
def test_probe_true(fake_arm):
    assert M.probe(fake_arm) is True


def test_probe_false_on_old_firmware(fake_arm):
    fake_arm.model.supported = False
    assert M.probe(fake_arm) is False


# ---------------------------------------------------------------------------
# 下发 / 读回
# ---------------------------------------------------------------------------
def test_send_model_full_roundtrip(fake_arm, model):
    fake_arm.disable()
    res = M.send_model(fake_arm, model)
    assert res["aborted"] is None
    assert res["commit"][0] is True, res
    assert all(ok for ok, _ in res["frames"].values())

    diffs = M.readback_compare(fake_arm, model)
    assert diffs == [], f"读回应与下发逐项一致, 实得 {diffs[:5]}"


def _written(arm):
    """从调用记录里取本次发过的 (kind, idx)。"""
    out = []
    for name, arg in arm.calls:
        if name == "model.set_body":
            out.append(("body", arg[0]))
        elif name == "model.set_jm":
            out.append(("jm", 0))
    return out


def test_send_model_only_writes_body1_to_7_and_jm(fake_arm, model):
    """body0 (base, 不递推) 与 body8 (ee, payload 复合位) **不发** —— 保持设备原值。"""
    fake_arm.disable()
    M.send_model(fake_arm, model)
    w = _written(fake_arm)
    bodies = {i for k, i in w if k == "body"}
    assert bodies == set(range(1, 8)), f"应只写 body1..7, 实得 {sorted(bodies)}"
    assert ("jm", 0) in w, "应写 jm"


def test_send_model_aborts_without_commit_on_frame_failure(fake_arm, model):
    """任一帧失败 ⇒ **立即中止且不 commit** (staging 里的半套不影响生效模型)。"""
    import litearm as pa
    fake_arm.disable()
    orig = fake_arm.model.set_body

    def boom(idx, vals):
        if int(idx) == 3:
            raise pa.CommandRejectedError("拒绝", cmd=0x30, code=0x02)
        return orig(idx, vals)

    fake_arm.model.set_body = boom
    res = M.send_model(fake_arm, model)
    assert res["aborted"] is not None
    assert res["commit"][0] is False
    assert not any(n == "model.commit" for n, _ in fake_arm.calls), "失败后不应 commit"


def test_send_model_rejects_bad_body_arity(fake_arm, model):
    bad = copy.deepcopy(model)
    bad["body"][1] = bad["body"][1][:5]
    res = M.send_model(fake_arm, bad)
    assert res["aborted"] is not None


def test_read_model_returns_nine_bodies_regardless_of_joint_count(fake_arm):
    """模型恒 9 刚体 —— 判据不掺 `arm.n`。"""
    m = M.read_model(fake_arm)
    assert len(m["body"]) == 9
    assert len(m["jm"]) == 7
    assert m["status"].override == 0


# ---------------------------------------------------------------------------
# 前置校验
# ---------------------------------------------------------------------------
def test_validate_model_accepts_real_yaml_model(model):
    assert M.validate_model(model) == []


def test_validate_model_rejects_nan(model):
    bad = copy.deepcopy(model)
    bad["body"][2][0] = float("nan")
    errs = M.validate_model(bad)
    assert any("body2.m" in e for e in errs)


def test_validate_model_rejects_oversize(model):
    bad = copy.deepcopy(model)
    bad["body"][2][0] = 1e30
    assert any("body2.m" in e for e in M.validate_model(bad))


def test_validate_model_rejects_body8_mass(model):
    """body8 是 payload 复合位 —— 质量必须恒 0 (与固件写口同口径)。"""
    bad = copy.deepcopy(model)
    bad["body"][8][0] = 0.5
    assert any("body8" in e for e in M.validate_model(bad))


def test_validate_model_rejects_bad_jm_len(model):
    bad = copy.deepcopy(model)
    bad["jm"] = bad["jm"][:3]
    assert any("jm" in e for e in M.validate_model(bad))


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------
def test_model_diff_empty_for_same(model):
    assert M.model_diff(model, copy.deepcopy(model)) == []


def test_model_diff_finds_change(model):
    new = copy.deepcopy(model)
    new["body"][3][0] = 1.5
    new["jm"][2] = -0.5
    d = dict((lab, (o, n)) for lab, o, n in M.model_diff(model, new))
    assert "B3.m" in d
    assert "jm.J3" in d


def test_model_diff_without_baseline_lists_written_set(model):
    """无基线时列出**实际写入的集合** (body1..7 + jm = 70 + 7), 不含 body0/body8。

    body0 (base) 与 body8 (ee) 不写、设备保持原值 ⇒ 算进去会每次都报一条假"修改"。
    """
    d = M.model_diff(None, model)
    assert len(d) == 7 * 10 + 7
    labels = {lab for lab, _, _ in d}
    assert not any(lab.startswith("B0.") or lab.startswith("B8.") for lab in labels)


# ---------------------------------------------------------------------------
# 回退
# ---------------------------------------------------------------------------
def test_revert_model(fake_arm, model):
    fake_arm.disable()
    M.send_model(fake_arm, model)
    assert fake_arm.model.override is True
    ok, code = M.revert_model(fake_arm)
    assert ok, code
    assert fake_arm.model.override is False


def test_revert_requires_disabled(fake_arm, model):
    fake_arm.disable()
    M.send_model(fake_arm, model)
    fake_arm.enable()
    ok, code = M.revert_model(fake_arm)
    assert (ok, code) == (False, 0x04)


# ---------------------------------------------------------------------------
# get_gravity
# ---------------------------------------------------------------------------
def test_get_gravity(fake_arm):
    g = M.get_gravity(fake_arm, [0.0] * 7)
    assert len(g) == 7


# ---------------------------------------------------------------------------
# 与 yaml 的端到端 (下发→读回闸)
# ---------------------------------------------------------------------------
def test_end_to_end_yaml_to_readback(fake_arm, model):
    """产线的真实序列: 解析 yaml → send_model → readback_compare 全绿。"""
    fake_arm.disable()
    assert M.validate_model(model) == []
    res = M.send_model(fake_arm, model)
    assert res["commit"][0] is True
    assert M.readback_compare(fake_arm, model) == []
