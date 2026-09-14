"""解析固件 litearm-stm32 的**出厂默认**真源 (`params/defaults.c` + `joint_limit_macros.h`)。

为什么要它: `presets/` 与 `templates/` 是"出厂默认"的副本, 必须由固件真源生成, 不能手抄 ——
2026-09 曾因手抄漂移 **32 处字段** (preset 抄的是 09-07 的 `PARAM_STATE.md §A1` 台账,
而 `defaults.c` 在 09-12 换源重定过: kp J1-J4、wall_*、gs J2/J3/J4、全局 wall_margin/fric_v2_eps)。
本模块同时被 `tools/gen_presets.py` 与 `tests/test_preset_sync.py` 使用, 保证"生成"与"断言"同源。

固件目录解析顺序: 参数 > 环境变量 `LITEARM_FW_DIR` > 仓库同级 `../litearm-stm32`。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

#: ff_mask 位名 -> 值 (与固件 litearm.h 一致)
FF_BITS = {
    "FF_MASTER": 0x0001, "FF_G": 0x0002, "FF_INERTIA": 0x0004,
    "FF_CORIOLIS": 0x0008, "FF_FRICTION": 0x0010, "FF_INTEGRAL": 0x0020,
    "FF_WALL": 0x0040, "FF_QUANT": 0x0080, "FF_VELREF": 0x0100,
}

#: 逐关节数值字段 (preset 键 -> defaults.c 里的 `.字段=` 名)
_JOINT_FIELDS = {
    "kp": "mit_kp", "kd": "mit_kd", "tau_max": "tau_max",
    "friction": "friction", "ki": "ki", "i_max": "i_max",
    "wall_stiff": "wall_stiff", "wall_damp": "wall_damp", "wall_tau_max": "wall_tau_max",
    "friction_v": "friction_v", "friction_fc0": "friction_fc0", "friction_fc1": "friction_fc1",
    "kd_extra": "kd_extra",
}

#: 全局标量字段 (preset 键 -> defaults.c 的 `.字段=`)
_GLOBAL_FIELDS = {
    "wall_margin": "wall_margin", "fric_db": "fric_db", "friction_slew": "friction_slew",
    "payload_mass": "payload_mass", "fric_v2_eps": "fric_v2_eps",
    "drag_gain": "drag_gain", "drag_db": "drag_db", "drag_kd_margin": "drag_kd_margin",
    "zg_vel_thr": "zg_vel_thr", "zg_engage_sec": "zg_engage_sec",
    "zg_engage_kp": "zg_engage_kp", "zg_engage_kd": "zg_engage_kd",
    "wall_fw_kd": "wall_fw_kd", "hold_kp_gain": "hold_kp_gain",
}

#: 全局逐关节数组 (preset 关节键 -> dyn 块数组名)
_GLOBAL_ARRAYS = {
    "gravity_scale": "gravity_scale", "inertia_scale": "inertia_scale",
    "zg_kp": "zg_kp", "zg_kd": "zg_kd", "zg_damping": "zg_damping",
}

_NUM = r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"


def _f(s: str) -> float:
    return float(s.rstrip("fF"))


def _find_num(text: str, field: str) -> Optional[float]:
    m = re.search(rf"\.{field}\s*=\s*({_NUM})f?", text)
    return _f(m.group(1)) if m else None


def _find_array(text: str, name: str) -> Optional[list]:
    m = re.search(rf"\.{name}\s*=\s*\{{([^}}]*)\}}", text)
    if not m:
        return None
    return [_f(x.strip()) for x in m.group(1).split(",") if x.strip()]


def parse_limit_macros(text: str) -> dict:
    """`#define JL_QMIN_J1 (-2.809547f)` -> {'JL_QMIN_J1': -2.809547}"""
    out = {}
    for m in re.finditer(rf"#define\s+(JL_Q\w+)\s+\(?\s*({_NUM})f?\s*\)?", text):
        out[m.group(1)] = _f(m.group(2))
    return out


def parse_defaults_c(text: str, macros: Optional[dict] = None) -> dict:
    """解析 defaults.c 全文 -> {'joints': [ {…}×7 ], 'global': {…}} (键名同 preset)。"""
    macros = macros or {}

    # --- 7J 关节表: 以 `JL_QMIN_J<n>` 出现的行作为每个关节的起点 (1J 台架表不用宏) ---
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.search(r"JL_QMIN_J\d", ln)]
    if len(starts) != 7:
        raise ValueError(f"未找到 7 个关节 (找到 {len(starts)}): defaults.c 结构变了?")
    joints = []
    for k, i0 in enumerate(starts):
        i1 = starts[k + 1] if k + 1 < len(starts) else len(lines)
        blk = "\n".join(lines[i0:i1])
        j = {}
        for key, field in _JOINT_FIELDS.items():
            v = _find_num(blk, field)
            if v is not None:
                j[key] = v
        for axis, mac in (("q_min", "QMIN"), ("q_max", "QMAX")):
            m = re.search(rf"\.{axis}\s*=\s*(JL_Q\w+)", blk)
            if not m:
                raise ValueError(f"J{k + 1} 的 {axis} 未用 JL_ 宏, 解析需扩展")
            if m.group(1) not in macros:
                raise ValueError(f"缺宏 {m.group(1)} (未提供 joint_limit_macros.h?)")
            j[axis] = macros[m.group(1)]
        joints.append(j)

    # --- 7J dyn 块 = **最后一个** `.dyn = { … }` (1J 台架块在最前, gs 全 0) ---
    dyn_hits = [m for m in re.finditer(r"\.dyn\s*=\s*\{", text)]
    if not dyn_hits:
        raise ValueError("未找到 .dyn 块")
    tail = text[dyn_hits[-1].start():]
    glob = {}
    for key, field in _GLOBAL_FIELDS.items():
        v = _find_num(tail, field)
        if v is not None:
            glob[key] = v
    for jkey, arr in _GLOBAL_ARRAYS.items():
        vals = _find_array(tail, arr)
        if vals is None:
            raise ValueError(f"dyn 块缺数组 {arr}")
        if len(vals) != len(joints):
            raise ValueError(f"{arr} 长度 {len(vals)} != 关节数 {len(joints)}")
        for i, v in enumerate(vals):
            joints[i][jkey] = v
    for key, arr in (("gravity", "gravity"), ("payload_com", "payload_com")):
        vals = _find_array(tail, arr)
        glob[key] = vals if vals else [0.0, 0.0, 0.0]
    m = re.search(r"\.friction_model\s*=\s*(\d+)u?", tail)
    glob["friction_model"] = int(m.group(1)) if m else 0
    m = re.search(r"\.ff_mask\s*=\s*\(([^)]*)\)", tail)
    if not m:
        raise ValueError("dyn 块缺 ff_mask 表达式")
    mask = 0
    for part in m.group(1).split("|"):
        name = part.strip()
        if name not in FF_BITS:
            raise ValueError(f"未知 ff_mask 位 {name}")
        mask |= FF_BITS[name]
    glob["ff_mask"] = mask
    return {"joints": joints, "global": glob}


def find_firmware_dir(explicit: Optional[str] = None) -> Optional[Path]:
    """定位固件仓 (`litearm-stm32`)。找不到返回 None (调用方决定 skip 或报错)。"""
    cands = []
    if explicit:
        cands.append(Path(explicit))
    env = os.environ.get("LITEARM_FW_DIR")
    if env:
        cands.append(Path(env))
    cands.append(Path(__file__).resolve().parents[2] / "litearm-stm32")
    cands.append(Path(__file__).resolve().parents[1] / "litearm-stm32")
    for c in cands:
        if (c / "User" / "litearm" / "params" / "defaults.c").is_file():
            return c
    return None


def load_firmware_defaults(fw_dir=None) -> dict:
    """读取并解析固件真源; 定位失败抛 FileNotFoundError。"""
    root = find_firmware_dir(fw_dir)
    if root is None:
        raise FileNotFoundError(
            "未找到 litearm-stm32 固件仓 (用 LITEARM_FW_DIR 指定, 或置于同级目录)")
    pdir = root / "User" / "litearm" / "params"
    macros = parse_limit_macros((pdir / "joint_limit_macros.h").read_text("utf-8", errors="replace"))
    return parse_defaults_c((pdir / "defaults.c").read_text("utf-8", errors="replace"), macros)
