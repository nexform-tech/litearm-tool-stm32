"""presets/ 与 templates/ 必须与固件 `defaults.c` **逐字段**一致。

背景: 这两份文件自称"当前固件出厂默认", 但 2026-09 实测漂移 32 处字段 —— preset 抄的是
09-07 的 `PARAM_STATE.md §A1` 台账, 而 `defaults.c` 在 09-12 换源重定过。旧测试只断言
"能 normalize", 不读 defaults.c, 所以漂移完全测不出来。本测试把真源接进来。

固件仓不在场时 skip (用 `LITEARM_FW_DIR` 指定)。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from litetool import firmware_defaults as FD

REPO = Path(__file__).resolve().parents[1]

#: 逐关节必须与固件一致的键 (写口能改的全部数值字段)
JOINT_KEYS = ["kp", "kd", "tau_max", "q_min", "q_max", "friction", "ki", "i_max",
              "wall_stiff", "wall_damp", "wall_tau_max", "gravity_scale", "inertia_scale",
              "friction_v", "friction_fc0", "friction_fc1",
              # [v10] zg_kp/zg_kd/zg_damping 已删除
              # [1.12.0] drag_gain 改为逐关节 (0x26 item16)
              "drag_gain",
              "kd_extra"]
#: 全局必须一致的键 (ff_mask 除外: se1 预设故意只开 master+friction)
GLOBAL_KEYS = ["wall_margin", "fric_db", "friction_slew", "payload_mass", "fric_v2_eps",
               # [v10] drag_kd_margin/zg_vel_thr/zg_engage_* 已删除
               # [1.12.0] drag_gain 改为逐关节, 不再在 global
               "drag_db", "wall_fw_kd", "hold_kp_gain",
               "gravity", "payload_com", "friction_model"]


@pytest.fixture(scope="module")
def fw_defaults():
    if FD.find_firmware_dir() is None:
        pytest.skip("未找到 litearm-stm32 固件仓 (设 LITEARM_FW_DIR 可指定)")
    return FD.load_firmware_defaults()


def _close(a, b) -> bool:
    return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(b)))


@pytest.mark.parametrize("rel", ["presets/current_master_defaults.yaml",
                                 "presets/se1_friction.yaml",
                                 "templates/params_example.yaml"])
def test_joints_match_firmware_defaults(fw_defaults, rel):
    snap = yaml.safe_load((REPO / rel).read_text("utf-8"))
    assert len(snap["joints"]) == len(fw_defaults["joints"]) == 7, rel
    bad = []
    for i, (got, exp) in enumerate(zip(snap["joints"], fw_defaults["joints"])):
        for k in JOINT_KEYS:
            if k not in got:
                bad.append(f"J{i + 1}.{k} 缺失")
            elif not _close(got[k], exp[k]):
                bad.append(f"J{i + 1}.{k}: {got[k]} != 固件 {exp[k]}")
    assert not bad, f"{rel} 与固件 defaults.c 不一致:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("rel", ["presets/current_master_defaults.yaml",
                                 "templates/params_example.yaml"])
def test_globals_match_firmware_defaults(fw_defaults, rel):
    snap = yaml.safe_load((REPO / rel).read_text("utf-8"))["global"]
    bad = []
    for k in GLOBAL_KEYS:
        if k not in snap:
            bad.append(f"{k} 缺失")
        elif isinstance(fw_defaults["global"][k], list):
            if len(snap[k]) != 3 or any(not _close(a, b) for a, b in zip(snap[k], fw_defaults["global"][k])):
                bad.append(f"{k}: {snap[k]} != 固件 {fw_defaults['global'][k]}")
        elif not _close(snap[k], fw_defaults["global"][k]):
            bad.append(f"{k}: {snap[k]} != 固件 {fw_defaults['global'][k]}")
    assert not bad, f"{rel} 全局段与固件不一致:\n  " + "\n  ".join(bad)


def test_master_preset_ff_mask_matches_firmware(fw_defaults):
    snap = yaml.safe_load((REPO / "presets/current_master_defaults.yaml").read_text("utf-8"))
    assert snap["global"]["ff_mask"] == fw_defaults["global"]["ff_mask"]


def test_readme_kp_list_matches_firmware(fw_defaults):
    """README 里写死的 kp 列表是最容易过期的副本 —— 必须与固件一致。"""
    kp = [int(round(j["kp"])) for j in fw_defaults["joints"]]
    expect = ",".join(str(v) for v in kp)
    readme = (REPO / "README.md").read_text("utf-8")
    assert f"kp=[{expect}]" in readme, (
        f"README 的 kp 列表应为 kp=[{expect}]")


def test_readme_ff_mask_matches_firmware(fw_defaults):
    """README/工具文案里的出厂 ff_mask 也要跟随固件 (曾写 0x3F, 实际 0x1BF)。"""
    mask = int(fw_defaults["global"]["ff_mask"])
    readme = (REPO / "README.md").read_text("utf-8").lower()
    assert f"0x{mask:x}" in readme, (
        f"README 未写对出厂 ff_mask (固件 {hex(mask)})")


def test_sync_values_is_section_aware(fw_defaults):
    """`sync_values` 只按 key 名匹配会改错行: global 段里的同名 key 会被写成 J1 的值。"""
    from tools.gen_presets import sync_values

    text = ("joints:\n- name: J1\n  kp: 111.0\n  kd: 1.0\n"
            "global:\n  kp: 999.0\n  wall_margin: 0.9\n")
    out = sync_values(text, fw_defaults)
    assert "kp: 999.0" in out, "global 段的 kp 被 joints 段的值覆盖了"
    assert "wall_margin: 0.02" in out, "global 段未同步"
    assert f"kp: {fw_defaults['joints'][0]['kp']}" in out, "joints 段未同步"


def test_sync_values_handles_block_style_arrays(fw_defaults):
    """block 风格数组 (gravity:\\n  - x) 必须同步, 否则 --check 会假绿。"""
    from tools.gen_presets import sync_values

    text = "global:\n  gravity:\n  - 9.0\n  - 9.0\n  - 9.0\n"
    out = sync_values(text, fw_defaults)
    vals = [float(re.match(r"\s*-\s*(-?[\d.eE+-]+)", x).group(1))
            for x in out.splitlines() if re.match(r"\s*-\s*-?[\d.]", x)]
    assert vals == [float(v) for v in fw_defaults["global"]["gravity"]], out
