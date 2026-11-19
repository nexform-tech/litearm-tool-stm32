"""param_catalog 测试 —— 目录范围镜像表 + schema 规范化 + ff_mask + diff。

范围值以固件为准: User/litearm/params/params.c (params_set_joint_ctrl /
params_ff_vec / params_ff_scalar) 与 flash_store.c apply_loaded 同源钳制。
"""
import io
from pathlib import Path

import pytest
import yaml

from litetool import param_catalog as C

REPO = Path(__file__).resolve().parents[1]


def _load_example():
    raw = yaml.safe_load((REPO / "templates" / "params_example.yaml").read_text("utf-8"))
    return C.normalize_snapshot(raw)


# ---------------- 目录结构与范围 (镜像固件) ----------------
def test_joint_catalog_order_and_kind():
    assert [p.key for p in C.JOINT_PARAMS] == [
        "kp", "kd", "tau_max", "q_min", "q_max",
        "friction", "ki", "i_max", "wall_stiff", "wall_damp", "wall_tau_max",
        "gravity_scale", "inertia_scale", "friction_v", "friction_fc0", "friction_fc1",
        "kd_extra", "drag_gain"]
    kinds = {p.kind for p in C.JOINT_PARAMS}
    assert kinds == {"ctrl", "limits", "vec"}


def test_joint_ranges_match_firmware_clamp():
    """钳幅核对固件 params.c / flash_store.c apply_loaded。"""
    spec = {
        "kp": (0.0, 500.0), "kd": (0.0, 5.0), "tau_max": (0.1, 120.0),
        "q_min": (-15.0, 15.0), "q_max": (-15.0, 15.0),
        "friction": (0.0, 50.0), "ki": (0.0, 1000.0), "i_max": (0.0, 100.0),
        "wall_stiff": (0.0, 2000.0), "wall_damp": (0.0, 50.0),
        "wall_tau_max": (0.0, 50.0), "gravity_scale": (0.0, 20.0),
        "inertia_scale": (0.0, 20.0), "friction_v": (0.0, 20.0),
        "friction_fc0": (0.0, 50.0), "friction_fc1": (-50.0, 0.0),
        "drag_gain": (0.0, 5.0),
        "kd_extra": (0.0, 50.0),
    }
    assert {p.key: (p.lo, p.hi) for p in C.JOINT_PARAMS} == spec


def test_vec_item_numbers_match_write_protocol():
    """0x26 item 号: 1..11 与固件 params_ff_vec 一致。"""
    got = {p.key: p.item for p in C.JOINT_PARAMS if p.kind == "vec"}
    assert got == {"friction": 1, "ki": 2, "i_max": 3, "wall_stiff": 4,
                   "wall_damp": 5, "wall_tau_max": 6, "gravity_scale": 7,
                   "inertia_scale": 8, "friction_v": 9, "friction_fc0": 10,
                   "friction_fc1": 11,
                   "kd_extra": 15, "drag_gain": 16}


def test_global_ranges_match_firmware():
    spec = {"fric_db": (1e-4, 0.5), "wall_margin": (0.0, 0.5),
            "friction_slew": (0.0, 500.0), "payload_mass": (0.0, 20.0),
            "payload_com": (-1.0, 1.0), "gravity": (-50.0, 50.0),
            "fric_v2_eps": (1e-3, 0.5),
            # [段② 零重力] drag_db 0 合法 (= 硬 sign, 厂商 MITDragDemo 同款);
            # [1.12.0] drag_gain 已移到 JOINT_PARAMS (0x26 item16)
            "drag_db": (0.0, 0.5),
            "wall_fw_kd": (0.0, 5.0),
            # [段③ §6.2]
            "hold_kp_gain": (0.0, 5.0)}
    for gp in C.GLOBAL_PARAMS:
        if gp.key == "friction_model":
            assert gp.model is True
            continue
        lo, hi = spec[gp.key]
        assert (gp.lo, gp.hi) == (lo, hi), gp.key


def test_friction_model_accepts_0_1_2():
    """[段②] 2 = drag 版 (拖动用), 与固件 params_ff_scalar case 7 一致。"""
    assert C.check_value(0, 2, 0, model=True) is None
    assert C.check_value(0, 2, 1, model=True) is None
    assert C.check_value(0, 2, 2, model=True) is None
    assert C.check_value(0, 2, 3, model=True) is not None
    assert C.check_value(0, 2, 0.5, model=True) is not None


def test_check_joint_out_of_range_and_q_relation():
    kp = C.JOINT_BY_KEY["kp"]
    assert C.check_joint(kp, -1.0) is not None
    assert C.check_joint(kp, 501.0) is not None
    assert C.check_joint(kp, 42.0) is None
    assert C.check_joint_limits_relation({"q_min": 1.0, "q_max": 0.5}) is not None
    assert C.check_joint_limits_relation({"q_min": -1.0, "q_max": 1.0}) is None


def test_friction_v2_sign_contract_inside_range():
    # fc1 上界 0 / 下界 -50 => 正号被拒
    fc1 = C.JOINT_BY_KEY["friction_fc1"]
    assert C.check_joint(fc1, 5.0) is not None
    assert C.check_joint(fc1, -5.0) is None


# ---------------- ff_mask ----------------
def test_ff_mask_bit_table_matches_firmware():
    names = [b for (_i, b, _l) in C.FF_BITS]
    assert names == ["MASTER", "G", "INERTIA", "CORIOLIS", "FRICTION",
                     "INTEGRAL", "WALL", "QUANT", "VELREF"]
    vals = {C.FF_BITS[i][1]: (1 << i) for i in range(len(C.FF_BITS))}
    assert vals == {"MASTER": 0x01, "G": 0x02, "INERTIA": 0x04, "CORIOLIS": 0x08,
                    "FRICTION": 0x10, "INTEGRAL": 0x20, "WALL": 0x40,
                    "QUANT": 0x80, "VELREF": 0x100}
    assert C.FF_ALL_MASK == 0x1FF


def test_ff_mask_to_bits_roundtrip():
    for mask in (0x0, 0x1FF, 447, 0x11, 0x100):
        bits = C.mask_to_bits(mask)
        assert len(bits) == len(C.FF_BITS)
        assert C.bits_to_mask(bits) == mask
    assert C.mask_to_bits(447) == [True, True, True, True, True, True,
                                   False, True, True]


def test_bits_to_mask_ignores_unknown_high_bits():
    assert C.bits_to_mask([True] * 9) == 0x1FF
    assert C.bits_to_mask([]) == 0



def _preset_j1_kp():
    """J1.kp 取 master 预设真值 (勿硬编码: 固件换源会变, 见 tests/test_preset_sync.py)。"""
    raw = yaml.safe_load((REPO / "presets" / "current_master_defaults.yaml").read_text("utf-8"))
    return raw["joints"][0]["kp"]

# ---------------- schema normalize ----------------
def test_normalize_example_valid():
    s = _load_example()
    assert len(s["joints"]) == 7
    assert set(s["joints"][0]) == set(p.key for p in C.JOINT_PARAMS)
    assert s["joints"][0]["kp"] == pytest.approx(_preset_j1_kp())
    assert s["global"]["ff_mask"] == 447
    assert s["global"]["friction_model"] == 1


def test_normalize_rejects_bad_structure():
    good = _load_example()
    bad = {"joints": good["joints"][:6], "global": good["global"]}
    with pytest.raises(ValueError):
        C.normalize_snapshot(bad)
    # 缺字段 / 缺 ff_mask **合法** —— 导出的文件只含本板支持的项, 回导时其余项
    # 必然缺键 (见 normalize_snapshot 的注释)。缺项 = 不下发, 不是文件损坏。
    s = C.normalize_snapshot({"joints": [{} for _ in range(7)],
                              "global": good["global"]})
    assert all(v is None for v in s["joints"][0].values())
    g = dict(good["global"])
    del g["ff_mask"]
    s = C.normalize_snapshot({"joints": good["joints"], "global": g})
    assert "ff_mask" not in s["global"]


def test_normalize_rejects_bad_value():
    good = _load_example()
    s = good["joints"][0].copy()
    s["kp"] = 5000.0
    with pytest.raises(ValueError):
        C.normalize_snapshot({"joints": [s] + good["joints"][1:],
                              "global": good["global"]})
    s = good["joints"][0].copy()
    s["q_min"], s["q_max"] = 1.0, -1.0      # q_min >= q_max
    with pytest.raises(ValueError):
        C.normalize_snapshot({"joints": [s] + good["joints"][1:],
                              "global": good["global"]})
    g = dict(good["global"])
    g["friction_model"] = 3                  # 仅 0/1/2
    with pytest.raises(ValueError):
        C.normalize_snapshot({"joints": good["joints"], "global": g})
    g = dict(good["global"])
    g["ff_mask"] = True                      # bool 拒绝
    with pytest.raises(ValueError):
        C.normalize_snapshot({"joints": good["joints"], "global": g})


def test_normalize_rejects_name_mismatch():
    good = _load_example()
    j = dict(good["joints"][0], name="J2")
    with pytest.raises(ValueError):
        C.normalize_snapshot({"joints": [j] + good["joints"][1:],
                              "global": good["global"]})


# ---------------- diff / 打平 / roundtrip ----------------
def test_snapshot_flat_covers_all_leaves():
    s = _load_example()
    flat = C.snapshot_flat(s)
    assert flat["J1.kp"] == pytest.approx(_preset_j1_kp())
    # [1.12.0] drag_gain 移到关节 (7×18); 全局叶 = 8 标量 + friction_model
    #           + payload_com[3] + gravity[3] + ff_mask = 16
    assert len(flat) == 7 * len(C.JOINT_PARAMS) + 16
    assert "global.gravity[2]" in flat
    assert flat["global.ff_mask"] == 447


def test_diff_empty_for_identical():
    s = _load_example()
    assert C.diff_snapshots(s, s) == []
    s2 = yaml.safe_load(io.StringIO(yaml.safe_dump(
        {"joints": [{"name": f"J{i + 1}", **jd} for i, jd in enumerate(s["joints"])],
         "global": s["global"]}, allow_unicode=True, sort_keys=False)))
    assert C.diff_snapshots(s, C.normalize_snapshot(s2)) == []


def test_diff_detects_changes():
    old = _load_example()
    new = yaml.safe_load(io.StringIO(yaml.safe_dump(
        {"joints": [{"name": f"J{i + 1}", **jd} for i, jd in enumerate(old["joints"])],
         "global": old["global"]}, allow_unicode=True, sort_keys=False)))
    new["joints"][2]["kp"] = 400.0
    new["global"]["ff_mask"] = 17
    diffs = C.diff_snapshots(old, C.normalize_snapshot(new))
    labs = {lab for lab, _o, _n in diffs}
    assert "J3.kp" in labs and "global.ff_mask" in labs


def test_diff_with_no_baseline_lists_everything():
    s = _load_example()
    assert len(C.diff_snapshots(None, s)) == len(C.snapshot_flat(s))


def test_fmt_value_shows_mask_hex_and_decimals():
    assert "0x1BF" in C.fmt_value("global.ff_mask", 447)
    assert C.fmt_value("J1.kp", 360.0) == "360.0"


def test_all_params_have_role_hint_detail():
    """[调参指南] catalog 元数据完整 (tooltip/指南页同源)。"""
    for p in C.JOINT_PARAMS:
        assert p.role and p.hint and p.detail, p.key
    for p in C.GLOBAL_PARAMS:
        assert p.role and p.hint and p.detail, p.key
    assert len(C.FF_BIT_DETAIL) == len(C.FF_BITS) == 9
    assert all(C.FF_BIT_DETAIL)
    assert set(C.FF_DETAIL_BY_NAME) == {name for _b, name, _l in C.FF_BITS}


def test_firmware_defaults_presets_loadable():
    """templates/presets 全部能规范化 (真机台账值)。"""
    for path in (REPO / "templates" / "params_example.yaml",
                 REPO / "presets" / "current_master_defaults.yaml",
                 REPO / "presets" / "se1_friction.yaml"):
        raw = yaml.safe_load(path.read_text("utf-8"))
        s = C.normalize_snapshot(raw)
        assert len(s["joints"]) == 7
    s1 = yaml.safe_load((REPO / "presets" / "current_master_defaults.yaml").read_text("utf-8"))
    s2 = yaml.safe_load((REPO / "presets" / "se1_friction.yaml").read_text("utf-8"))
    assert C.normalize_snapshot(s1)["global"]["ff_mask"] == 447
    assert C.normalize_snapshot(s2)["global"]["ff_mask"] == 0x11
    assert C.normalize_snapshot(s2)["global"]["friction_model"] == 1
