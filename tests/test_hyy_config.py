"""`litetool/hyy_config.py` —— HYY/SE1 辨识配置的解析与映射。

**本文件的核心断言是 A12**: 从 `DeviceConfig.yaml` 解析出的摩擦三元组 21 个值,
在 **float32 下逐位等于固件出厂值**。这是「从这份 yaml 解析出来的就是固件现在用的
那套」的硬证据 —— 即产线重放同一份 yaml 不会改变现状, 导入别的臂的新 yaml 才产生 diff。

数据源纪律 (与 `test_preset_sync.py` 同款): `tests/data/DeviceConfig.yaml` 是**副本**,
用 sha256 断言它与真源一致; 真源不在场时 **skip 而非 pass**。
"""
from __future__ import annotations

import copy
import hashlib
import re
import struct
from pathlib import Path

import pytest
import yaml

from litetool import hyy_config as H
from litetool import param_catalog as C

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "data" / "DeviceConfig.yaml"
#: 真源 (产线机器上不一定在 —— 不在就只跑副本, 但 sha 断言会 skip)
REAL = Path("/home/llx/hanbin/SE1/robot_config/DeviceConfig.yaml")
EXPECT_SHA16 = "b423bf1ff35db041"


def _sha16(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _f32(v) -> float:
    """固定成 float32 —— 真源 yaml 是 float64, 固件是 float32。
    直接 `==` 会因 91 个值里那 1 个差 1 ULP 的项 (J4 的 ixy) 失败。"""
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


@pytest.fixture(scope="module")
def cfg() -> H.HyyConfig:
    return H.parse_hyy_config(str(FIXTURE))


@pytest.fixture()
def yaml_dict() -> dict:
    return yaml.safe_load(FIXTURE.read_text("utf-8"))


@pytest.fixture()
def baseline() -> dict:
    """设备基线 —— 用固件出厂预设冒充 (真实场景来自 [刷新当前] 的读回)。"""
    return yaml.safe_load((REPO / "presets" / "current_master_defaults.yaml").read_text("utf-8"))


# ---------------------------------------------------------------------------
# 副本↔真源一致性 (真源不在场则 skip, **不是** pass)
# ---------------------------------------------------------------------------
def test_fixture_matches_real_source():
    if not REAL.exists():
        pytest.skip(f"真源 {REAL} 不在场 —— 无法核对副本")
    assert _sha16(REAL) == _sha16(FIXTURE), "tests/data 副本与真源已漂移, 请重新拷贝"


def test_fixture_sha_is_the_verified_one():
    assert _sha16(FIXTURE) == EXPECT_SHA16, (
        "副本 sha 变了 —— 本文件里所有期望值都是针对 b423bf1ff35db041 标定的, 必须重新核对")


def test_fixture_is_checked_out_with_lf():
    """`.gitattributes` 必须锁住 LF；Windows checkout 的 CRLF 会改掉 fixture SHA。"""
    assert b"\r\n" not in FIXTURE.read_bytes()


def test_parse_basic_fields(cfg):
    assert cfg.sha256_16 == EXPECT_SHA16
    assert cfg.version == "13.0.0"
    assert len(cfg.joints) == C.NUM_JOINTS
    assert cfg.gravity == pytest.approx((0.0, 0.0, -9.802))


# ---------------------------------------------------------------------------
# ★ A12: 摩擦三元组 21 值 float32 逐位 == 固件出厂值
# ---------------------------------------------------------------------------
def test_A12_friction_bitwise_matches_firmware_defaults(cfg, baseline):
    """★ 本设计的核心证据: 「从这份 yaml 解析出来的就是固件现在用的那套」。"""
    snap, _, _ = H.to_snapshot(cfg, baseline)
    checked = 0
    for i in range(C.NUM_JOINTS):
        for key in ("friction_v", "friction_fc0", "friction_fc1"):
            a = _f32(snap["joints"][i][key])
            b = _f32(baseline["joints"][i][key])
            assert a == b, (
                f"J{i + 1}.{key}: yaml 解析出 {a!r} != 固件出厂 {b!r} "
                f"—— 解析链路或真源数据出问题了")
            checked += 1
    assert checked == 21


# ---------------------------------------------------------------------------
# ★ 只导辨识产物: 软限位 / tau_max / gravity 刻意**不**导
# ---------------------------------------------------------------------------
def test_control_config_fields_are_not_imported(cfg, baseline):
    """`axis.smin/smax` / `axis.torque_max` / `gravity` 是 HYY **控制器配置**,
    不是辨识产物 ⇒ 导入后必须**保持设备当前值不动**。

    两条实测理由 (写在这里是因为它们是真金白银踩出来的):
      · `torque_max` = `20,20,28,28,10,10,10`, 而本机 `tau_max` = `78,78,21,21,10,10,10`
        ⇒ 覆盖会把 J1/J2 的力矩天花板**砍到 1/4**, 而它是幅值的唯一兜底。
      · `smin/smax` 映射后 J4 上界 = `+0.64`, 超出 URDFv5 机械硬限位 `+0.035`
        ⇒ 下发等于把软限位放到机械限位之外。

    所以本用例是**反向断言**: 这三项在 snapshot 里必须逐项等于 baseline。
    """
    snap, _, _ = H.to_snapshot(cfg, baseline)
    for i in range(C.NUM_JOINTS):
        for k in ("q_min", "q_max", "tau_max"):
            assert snap["joints"][i][k] == baseline["joints"][i][k], (
                f"J{i + 1}.{k} 被导入改了 —— 该项属控制器配置, 不该导")
    assert snap["global"]["gravity"] == baseline["global"]["gravity"]


def test_control_config_fields_are_in_unmapped_list(cfg):
    """不导可以, 但**必须说出来** —— 逐项进未映射清单并附原因, 不静默丢弃。"""
    got = dict(H.unmapped_report(cfg))
    for k in ("robot_group.robot[].joint[].axis.smin",
              "robot_group.robot[].joint[].axis.smax",
              "robot_group.robot[].joint[].axis.torque_max",
              "robot_group.robot[].gravity.x",
              "robot_group.robot[].gravity.y",
              "robot_group.robot[].gravity.z"):
        assert k in got, f"{k} 既没导、也没进清单 = 静默丢弃"
        assert "HYY 控制器配置" in got[k], got[k]
    assert "robot_group.robot[].joint[].axis.smin" not in H.MAPPED_KEYS


def test_only_dynamics_parameters_are_mapped(cfg, baseline):
    """映射集合应**恰为** `dynamics_parameters` (摩擦三元组 + 模型段)。"""
    expected = {
        "robot_group.robot[].joint[].dynamics_parameters.fv",
        "robot_group.robot[].joint[].dynamics_parameters.fc0",
        "robot_group.robot[].joint[].dynamics_parameters.fc1",
        "robot_group.robot[].joint[].dynamics_parameters.jm",
    } | {f"robot_group.robot[].joint[].dynamics_parameters.{k}"
         for k in C.MODEL_BODY_KEYS}
    assert H.MAPPED_KEYS == expected
    # 且 snapshot 里除摩擦三元组外, 关节侧逐项 == baseline
    snap, _, _ = H.to_snapshot(cfg, baseline)
    for i in range(C.NUM_JOINTS):
        for k, v in snap["joints"][i].items():
            if k in ("friction_v", "friction_fc0", "friction_fc1") or k == "name":
                continue
            assert v == baseline["joints"][i][k], f"J{i + 1}.{k} 被意外改动"


# ---------------------------------------------------------------------------
# 模型段
# ---------------------------------------------------------------------------# ---------------------------------------------------------------------------
# 模型段
# ---------------------------------------------------------------------------
def test_model_section_maps_body_i_plus_1(cfg, baseline):
    """body[i+1] = 关节 i; body0 (base) 与 body8 (ee) 必须全 0。"""
    _, model, _ = H.to_snapshot(cfg, baseline)
    assert len(model["body"]) == C.MODEL_NBODY
    assert len(model["jm"]) == C.MODEL_JM_N
    assert all(v == 0.0 for v in model["body"][0]), "body0 (base) 必须全 0"
    assert all(v == 0.0 for v in model["body"][8]), "body8 (ee) 必须全 0"
    d = cfg.joints[0]["dynamics_parameters"]
    assert model["body"][1] == pytest.approx([d[k] for k in C.MODEL_BODY_KEYS])
    d1 = cfg.joints[1]["dynamics_parameters"]
    assert model["body"][2] == pytest.approx([d1[k] for k in C.MODEL_BODY_KEYS])


def test_jm_maps_and_is_negative(cfg, baseline):
    _, model, _ = H.to_snapshot(cfg, baseline)
    assert model["jm"][0] == 0.0 and model["jm"][1] == 0.0
    assert model["jm"][2] == pytest.approx(-0.0188174839)
    assert all(v <= 0.0 for v in model["jm"]), "辨识基 jm 全为非正值 (禁物理化修补)"


def test_snapshot_passes_normalize(cfg, baseline):
    """产物必须过 `C.normalize_snapshot` —— 否则导入流程在第一步就炸。"""
    snap, _, _ = H.to_snapshot(cfg, baseline)
    C.normalize_snapshot(snap)


def test_reject_bench_baseline(cfg, baseline):
    """台架 1J 的基线在 J2..J7 是 None ⇒ **拒绝导入**, 且报出第一个空字段。

    为什么不能"填满就行": yaml 只提供 4 项 (q_min/q_max/tau_max/摩擦), 而 `kp`/`kd`/
    `ki`/`i_max`/`wall_*`/`gs`/`is`/`kd_extra` **没有 yaml 来源** —— 台架上它们
    本来就是 None, 无从补齐。硬填会造出一份"看起来完整"的假快照并把它下发。
    """
    bench = copy.deepcopy(baseline)
    for i in range(1, C.NUM_JOINTS):
        for k in list(bench["joints"][i]):
            if k in C.JOINT_BY_KEY:
                bench["joints"][i][k] = None
    with pytest.raises(H.HyyConfigError, match="设备基线上为空"):
        H.to_snapshot(cfg, bench)


def test_to_snapshot_rejects_missing_baseline(cfg):
    with pytest.raises(H.HyyConfigError, match="基线"):
        H.to_snapshot(cfg, None)


# ---------------------------------------------------------------------------
# 结构校验 (全部中文报错)
# ---------------------------------------------------------------------------
def _write(tmp_path: Path, d: dict) -> str:
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), "utf-8")
    return str(p)


def test_reject_wrong_joint_count(yaml_dict, tmp_path):
    d = copy.deepcopy(yaml_dict)
    d["robot_group"]["robot"][0]["joint"] = d["robot_group"]["robot"][0]["joint"][:6]
    with pytest.raises(H.HyyConfigError, match="长度 7"):
        H.parse_hyy_config(_write(tmp_path, d))


def test_reject_axis_id_mismatch(yaml_dict, tmp_path):
    """数组顺序 != axis.id 时必须拒绝 —— 否则 body[i+1] 静默错位且读回全绿。"""
    d = copy.deepcopy(yaml_dict)
    d["robot_group"]["robot"][0]["joint"][2]["axis"]["id"] = 5
    with pytest.raises(H.HyyConfigError, match="axis.id"):
        H.parse_hyy_config(_write(tmp_path, d))


def test_reject_missing_dynamics_field(yaml_dict, tmp_path):
    d = copy.deepcopy(yaml_dict)
    del d["robot_group"]["robot"][0]["joint"][0]["dynamics_parameters"]["fv"]
    with pytest.raises(H.HyyConfigError, match="fv"):
        H.parse_hyy_config(_write(tmp_path, d))


def test_reject_nan(yaml_dict, tmp_path):
    d = copy.deepcopy(yaml_dict)
    d["robot_group"]["robot"][0]["joint"][0]["dynamics_parameters"]["fv"] = float("nan")
    with pytest.raises(H.HyyConfigError, match="非有限"):
        H.parse_hyy_config(_write(tmp_path, d))


def test_reject_smin_ge_smax(yaml_dict, tmp_path):
    d = copy.deepcopy(yaml_dict)
    ax = d["robot_group"]["robot"][0]["joint"][1]["axis"]
    ax["smin"], ax["smax"] = ax["smax"], ax["smin"]
    with pytest.raises(H.HyyConfigError, match="smin"):
        H.parse_hyy_config(_write(tmp_path, d))


def test_reject_zero_gravity(yaml_dict, tmp_path):
    """gravity≈0 会让固件 G 层哨兵对任何模型失败 (虽已把评估重力钉死, yaml 侧仍须拦)。"""
    d = copy.deepcopy(yaml_dict)
    d["robot_group"]["robot"][0]["gravity"] = {"x": 0.0, "y": 0.0, "z": 0.0}
    with pytest.raises(H.HyyConfigError, match="gravity"):
        H.parse_hyy_config(_write(tmp_path, d))


def test_reject_non_numeric(yaml_dict, tmp_path):
    d = copy.deepcopy(yaml_dict)
    d["robot_group"]["robot"][0]["joint"][0]["dynamics_parameters"]["fv"] = "abc"
    with pytest.raises(H.HyyConfigError, match="须为数值"):
        H.parse_hyy_config(_write(tmp_path, d))


def test_friction_out_of_catalog_range_rejected(yaml_dict, tmp_path, baseline):
    """固件对摩擦写口会**静默钳幅** (超范围不报错, 只改成边界值) ⇒ 工具必须先拦。"""
    d = copy.deepcopy(yaml_dict)
    d["robot_group"]["robot"][0]["joint"][0]["dynamics_parameters"]["fv"] = 25.0   # 上限 20
    cfg2 = H.parse_hyy_config(_write(tmp_path, d))
    with pytest.raises(H.HyyConfigError, match="超出范围"):
        H.to_snapshot(cfg2, baseline)


# ---------------------------------------------------------------------------
# 未映射清单 (由代码计算, 断言恰等于手写白名单)
# ---------------------------------------------------------------------------
def test_unmapped_report_equals_whitelist(cfg):
    """清单必须**恰等于**白名单 —— 真源新增字段时会红, 迫使显式裁决, 而不是静默丢弃。"""
    rep = H.unmapped_report(cfg)
    got = {k for k, _ in rep}
    assert got == set(H.UNMAPPED_REASONS), (
        f"清单与白名单不符:\n  多出 {sorted(got - set(H.UNMAPPED_REASONS))}\n"
        f"  缺少 {sorted(set(H.UNMAPPED_REASONS) - got)}")
    assert all(reason for _, reason in rep), "每一项都必须有原因"


def test_unmapped_covers_the_known_traps(cfg):
    """rev2 曾漏列的项必须在清单里。"""
    got = {k for k, _ in H.unmapped_report(cfg)}
    for k in ("robot_group.robot[].joint[].dynamics_parameters.fv2",
              "robot_group.robot[].joint[].dynamics_parameters.fv3",
              "robot_group.robot[].joint[].axis.direction2",
              "robot_group.robot[].joint[].axis.encoder_ruler2",
              "robot_group.robot[].endlimit.tran_velocity_max",
              "robot_group.robot[].tool.x",
              "robot_group.robot[].use_feedforward",
              "robot_group.robot[].encoder_mode"):
        assert k in got, f"未映射清单漏了 {k}"


def test_mapped_keys_are_not_in_unmapped(cfg):
    got = {k for k, _ in H.unmapped_report(cfg)}
    assert not (got & H.MAPPED_KEYS)




def test_snapshot_values_are_float32_representable(cfg, baseline):
    """快照里的数值必须是 **float32 可精确表示** 的。

    回归守卫: 设备存的是 float32; 若快照留着 yaml 的 float64, `diff_snapshots` 的
    精确比较会把"同一个 float32 的两种写法"判成不同 ⇒ 每次导入刷出 21 行假"修改"。
    （2026-09-14 真机验出来的: yaml `0.7516675845629472` vs 设备 `0.7516675591468811`。）
    """
    import struct
    def f32(v): return struct.unpack("<f", struct.pack("<f", float(v)))[0]

    snap, model, _ = H.to_snapshot(cfg, baseline)
    for i in range(C.NUM_JOINTS):
        for k in ("friction_v", "friction_fc0", "friction_fc1"):
            v = snap["joints"][i][k]
            assert f32(v) == v, f"J{i + 1}.{k}={v!r} 不是 float32 可表示值 -> diff 会假报修改"
    for b in model["body"]:
        for v in b:
            assert f32(v) == v
    for v in model["jm"]:
        assert f32(v) == v


def test_diff_is_empty_when_device_already_matches_yaml(cfg, baseline):
    """端到端: 把基线模拟成"设备读回"(float32), 导入同一份 yaml ⇒ diff 必须为空。

    这是产线最重要的那条性质 —— **重放同一份 yaml 不该改变现状**, 界面上也不该
    出现任何一行"修改"。
    """
    import struct
    def f32(v): return struct.unpack("<f", struct.pack("<f", float(v)))[0]

    dev = {"joints": [{k: (f32(v) if isinstance(v, float) else v) for k, v in j.items()}
                      for j in baseline["joints"]],
           "global": baseline["global"]}
    snap, model, _ = H.to_snapshot(cfg, dev)
    changed = sorted({d[0] for d in C.diff_snapshots(dev, snap)})
    assert changed == [], f"重放同一份 yaml 却报出改动: {changed}"
    assert H.MAPPED_KEYS  # 保留: 上面为空是因为值相同, 不是因为没映射


# ---------------------------------------------------------------------------
# 摩擦对称性哨兵 (|fc0| vs |fc1|)
# ---------------------------------------------------------------------------
def _plain(s: str) -> str:
    """富文本 -> 纯文本。

    断言必须针对**渲染后**的文字, 否则给数字加个 `<b>` 就会把
    `"1 个关节" in head` 变成假 —— 测的成了 HTML 源码, 不是操作员看到的东西。
    """
    s = re.sub(r"<[^>]+>", "", s)
    for a, b in (("&nbsp;", " "), ("&gt;", ">"), ("&lt;", "<"), ("&amp;", "&")):
        s = s.replace(a, b)
    return s


def _set_fc(tmp_path, yaml_dict, joint_idx, fc0, fc1):
    """改一份 yaml 里某个关节的 fc0/fc1, 写出并解析。"""
    d = copy.deepcopy(yaml_dict)
    dp = d["robot_group"]["robot"][0]["joint"][joint_idx]["dynamics_parameters"]
    dp["fc0"], dp["fc1"] = fc0, fc1
    return H.parse_hyy_config(_write(tmp_path, d))


def test_healthy_arm_is_clean(cfg):
    """**最重要的一条**: 已知正常的 SE1 臂必须一个都不报。

    阈值定错的代价不对称 —— 漏报只是少一层保护, 误报会让操作员学会无视红字,
    那比不报警更糟。
    """
    assert H.suspicious_joints(cfg) == []


def test_healthy_anchor_max_ratio_is_1_42(cfg):
    """把阈值的**数据锚点**钉住: 健康臂最不对称的是 J2, 比值 1.42。

    锚点动了 (换了台臂 / fixture 被改) 就该重新审阈值, 而不是让用例静默跟着漂。
    """
    rows = H.friction_asymmetry(cfg)
    assert [x.joint for x in rows] == list(range(1, 8))
    worst = max(rows, key=lambda x: x.ratio)
    assert worst.joint == 2
    assert worst.ratio == pytest.approx(1.42, abs=0.01)
    assert H.FC_ASYM_RATIO == 2.0, "阈值改动须同步本锚点与 README"


def test_asymmetry_math(cfg):
    j2 = H.friction_asymmetry(cfg)[1]
    assert j2.a == pytest.approx(2.2810, abs=1e-4)
    assert j2.b == pytest.approx(1.6099, abs=1e-4)
    assert j2.delta == pytest.approx(0.6712, abs=1e-4)
    assert j2.ratio == pytest.approx(1.4169, abs=1e-3)
    assert j2.suspicious is False


def test_ratio_over_two_is_flagged(tmp_path, yaml_dict):
    c = _set_fc(tmp_path, yaml_dict, 2, fc0=2.0, fc1=-0.8)      # ratio 2.5
    bad = H.suspicious_joints(c)
    assert [x.joint for x in bad] == [3]
    assert bad[0].ratio == pytest.approx(2.5)


def test_boundary_exactly_two_is_not_flagged(tmp_path, yaml_dict):
    """判据是**严格大于** —— 恰好 2.0 不报。边界不钉死, 阈值就没意义。"""
    c = _set_fc(tmp_path, yaml_dict, 0, fc0=1.0, fc1=-2.0)
    assert H.suspicious_joints(c) == []


def test_just_over_boundary_is_flagged(tmp_path, yaml_dict):
    c = _set_fc(tmp_path, yaml_dict, 0, fc0=1.0, fc1=-2.01)
    assert [x.joint for x in H.suspicious_joints(c)] == [1]


def test_tiny_values_with_big_ratio_are_not_flagged(tmp_path, yaml_dict):
    """**绝对差值下限的作用**: 0.001 vs −0.004 比值 4.0, 但差值只有 0.003 Nm。

    纯比值判据会在摩擦趋近 0 的关节上疯狂误报 —— 这是必须有下限的原因。
    """
    c = _set_fc(tmp_path, yaml_dict, 4, fc0=0.001, fc1=-0.004)
    x = H.friction_asymmetry(c)[4]
    assert x.ratio == 4.0, "比值确实超标"
    assert x.suspicious is False, "但差值无物理量级 ⇒ 不报"


def test_delta_floor_gates_the_decision(tmp_path, yaml_dict):
    """比值同样超标 (4.0 / 3.0) 时, 全看差值够不够量级。

    ⚠ 刻意**不**测 "差值恰好 0.05" 那个刀锋: 0.06−0.01 在 IEEE754 下是
    0.049999999999999996, 比 0.05 略小 —— 测它会变成测浮点舍入而不是测判据。
    真要卡死 >= / > 的语义, 见 `test_boundary_exactly_two_is_not_flagged`
    (那一处用的是精确可表示的 2.0)。
    """
    over = _set_fc(tmp_path, yaml_dict, 0, fc0=0.20, fc1=-0.05)   # ratio 4.0, Δ 0.15
    assert [x.joint for x in H.suspicious_joints(over)] == [1]

    under = _set_fc(tmp_path, yaml_dict, 0, fc0=0.06, fc1=-0.02)  # ratio 3.0, Δ 0.04
    assert H.suspicious_joints(under) == []


def test_one_sided_friction_is_flagged(tmp_path, yaml_dict):
    """一侧恰好为 0 ⇒ 比值 ∞ —— 单侧有摩擦本身就是强信号, 必须报。"""
    c = _set_fc(tmp_path, yaml_dict, 5, fc0=0.5, fc1=0.0)
    x = H.friction_asymmetry(c)[5]
    assert x.ratio == float("inf")
    assert x.suspicious is True
    assert [y.joint for y in H.suspicious_joints(c)] == [6]


def test_both_zero_is_not_flagged(tmp_path, yaml_dict):
    """两侧都是 0: 比值 ∞ 但差值 0 —— 不该报 (下限把它挡住了)。"""
    c = _set_fc(tmp_path, yaml_dict, 6, fc0=0.0, fc1=0.0)
    assert H.friction_asymmetry(c)[6].ratio == float("inf")
    assert H.suspicious_joints(c) == []


def test_message_names_the_joints(tmp_path, yaml_dict):
    c = _set_fc(tmp_path, yaml_dict, 2, fc0=3.0, fc1=-0.5)
    head, detail = H.asymmetry_message(H.suspicious_joints(c))
    hp, dp = _plain(head), _plain(detail)
    assert "1 个关节" in hp
    assert f"{H.FC_ASYM_RATIO:g}" in hp and f"{H.FC_ASYM_MIN_DELTA:g}" in hp
    assert "J3" in dp
    assert "3.000" in dp and "0.500" in dp
    assert "2.500" in dp, "差值也要给出来"


def test_message_needs_no_hardware(cfg):
    """正常臂也要能生成空列表的文案 (调用方不必先判空)。"""
    head, detail = H.asymmetry_message([])
    assert "0 个关节" in _plain(head)
    assert detail == ""


def test_message_is_richtext_not_markdown(tmp_path, yaml_dict):
    """**回归**: 弹窗是 `QMessageBox`, 它不认 Markdown —— `**` 会原样打在脸上。

    这个缺陷只靠断言子串是抓不到的 (文字内容全都在), 是**离屏渲染**时才肉眼看见的。
    所以这里钉死两条互锁的约束:

      - 不得出现 `**` (Markdown 会原样显示);
      - 不得出现 `\\n` (文本一旦含 HTML 标签, Qt 切富文本模式, `\\n` 就不再换行)。

    第二条最容易漏: 单独把 `**` 换成 `<b>` 而留着 `\\n`, 版面会从"分行"塌成"一坨"。
    """
    c = _set_fc(tmp_path, yaml_dict, 2, fc0=2.0, fc1=-0.8)
    head, detail = H.asymmetry_message(H.suspicious_joints(c))
    for s in (head, detail):
        assert "**" not in s, f"Markdown 星号会原样显示: {s}"
        assert "\n" not in s, f"富文本模式 \\n 不换行, 须用 <br>: {s}"
    assert "<b>" in head and "<br>" in head
    assert "<b>" in detail and "<br>" in detail
