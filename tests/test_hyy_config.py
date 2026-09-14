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
# ★ A13/A14: 限位 —— 符号修正 + 与 URDFv5 硬限位−1° 取交集
# ---------------------------------------------------------------------------
def test_A14_symbol_table_and_hamming(cfg):
    """符号真源是 `hyy_mapping.json` 的 `s`, **不是** yaml 的 `direction`。

    两者 Hamming 距离 = 1, 位置在 J6。本份数据上两条规则结果恰好相同
    (J6 的 smin/smax = ∓1.57 对称), 但那是巧合 —— 所以锚点必须**正面断言 `s` 本身**,
    而不是断言"两条规则一致"(那条恒真, 对 `s` 抄错零分辨力)。
    """
    assert H.S_SE1 == (1, 1, 1, -1, 1, 1, -1)
    assert {i for i, s in enumerate(H.S_SE1) if s < 0} == {3, 6}     # J4 / J7
    direction = [bool(j["axis"]["direction"]) for j in cfg.joints]
    assert direction == [True, True, True, False, True, False, False]
    flipped_dir = {i for i, d in enumerate(direction) if not d}       # {3,5,6}
    hamming = {i for i in range(7) if (H.S_SE1[i] < 0) != (not direction[i])}
    assert hamming == {5}, "s 与 direction 的差异应仅在 J6 (0-based idx 5)"


def test_A13_limits_intersection(cfg, baseline):
    """交集后的 7 组限位逐位吻合 (取自分支 `hyy_limits.json` 的独立裁决结果)。"""
    snap, _, _ = H.to_snapshot(cfg, baseline)
    exp_min = [-2.79, -1.7275467075, -2.79, -3.05, -2.79, -1.5535467075, -1.5535467075]
    exp_max = [2.79, 1.7275467075, 2.79, 0.0175467075, 2.79, 1.5535467075, 1.5535467075]
    for i in range(7):
        assert snap["joints"][i]["q_min"] == pytest.approx(exp_min[i], abs=1e-9)
        assert snap["joints"][i]["q_max"] == pytest.approx(exp_max[i], abs=1e-9)


def test_A13_group1_symbol_fixed_before_intersection(cfg):
    """第一组断言: 符号修正后、**取交集前**的 lo/hi (只依赖 yaml + `S_SE1`)。

    与上一条拆开是为了定位 —— 实现错一半时能立刻看出是符号还是交集出问题。
    """
    exp_lo = [-2.79, -1.74, -2.79, -3.05, -2.79, -1.57, -1.57]
    exp_hi = [2.79, 1.74, 2.79, 0.64, 2.79, 1.57, 1.57]
    for i, j in enumerate(cfg.joints):
        ax = j["axis"]
        lo, hi = H.symbol_fix(ax["smin"], ax["smax"], i)
        assert lo == pytest.approx(exp_lo[i])
        assert hi == pytest.approx(exp_hi[i])


def test_j4_conflict_is_flagged(cfg, baseline):
    """J4 的 yaml 上界 +0.64 超出机械硬限位 +0.035 —— 必须显式告警, 不能静默截断。"""
    _, _, notes = H.to_snapshot(cfg, baseline)
    assert any("J4" in x and "硬限位" in x for x in notes), notes
    # 且交集确实取了 URDF 侧 (安全侧)
    lo, hi = H.map_limits(-0.64, 3.05, 3)
    assert hi == pytest.approx(0.0175467075, abs=1e-9)
    assert lo == pytest.approx(-3.05, abs=1e-9)


def test_limits_always_contain_current_zero(cfg):
    """7 个关节的最终限位都必须含 q=0 (home 位) —— 否则下发即越限。"""
    for i, j in enumerate(cfg.joints):
        lo, hi = H.map_limits(j["axis"]["smin"], j["axis"]["smax"], i)
        assert lo < 0.0 < hi, f"J{i + 1} 限位 [{lo}, {hi}] 不含 q=0"


# ---------------------------------------------------------------------------
# 其余三项映射
# ---------------------------------------------------------------------------
def test_tau_max_and_gravity(cfg, baseline):
    snap, _, _ = H.to_snapshot(cfg, baseline)
    assert [j["tau_max"] for j in snap["joints"]] == [20.0, 20.0, 28.0, 28.0, 10.0, 10.0, 10.0]
    assert snap["global"]["gravity"] == pytest.approx([0.0, 0.0, -9.802])


def test_tau_max_is_safety_flagged():
    """`tau_max` / `q_min` / `q_max` / `gravity` 必须标 safety —— yaml 的 torque_max
    (20,20,...) 与固件默认 (78,78,...) 相差极大, 而范围校验不会响。"""
    assert C.JOINT_BY_KEY["tau_max"].safety
    assert C.JOINT_BY_KEY["q_min"].safety
    assert C.JOINT_BY_KEY["q_max"].safety
    assert C.GLOBAL_BY_KEY["gravity"].safety
    assert not C.JOINT_BY_KEY["kp"].safety


# ---------------------------------------------------------------------------
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
    `ki`/`i_max`/`wall_*`/`gs`/`is`/`kd_extra`/`zg_*` **没有 yaml 来源** —— 台架上它们
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


# ---------------------------------------------------------------------------
# 软限位常量的出处
# ---------------------------------------------------------------------------
def test_urdf_hard_limits_shape():
    assert len(H.URDF_HARD_LIMITS) == 7
    for lo, hi in H.URDF_HARD_LIMITS:
        assert lo < hi
    assert H.URDF_HARD_LIMITS[3] == (-3.089, 0.035), "J4 硬限位非对称, 是交集告警的根源"
    assert H.LIMIT_SHRINK == pytest.approx(0.0174532925)
