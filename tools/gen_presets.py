#!/usr/bin/env python3
"""由固件真源重新生成 `presets/*.yaml`。

用法::

    python tools/gen_presets.py [--fw-dir /path/to/litearm-stm32] [--check]

`--check` 只比对不写盘 (非零退出码表示漂移), 适合挂 CI。
`templates/params_example.yaml` 与 `README.md` 含教学注释, 不由此脚本覆盖 ——
它们的数值由 `tests/test_preset_sync.py` 断言守护。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from litetool import firmware_defaults as FD  # noqa: E402

_JOINT_ORDER = ["kp", "kd", "tau_max", "q_min", "q_max", "friction", "ki", "i_max",
                "wall_stiff", "wall_damp", "wall_tau_max", "gravity_scale", "inertia_scale",
                "friction_v", "friction_fc0", "friction_fc1", "zg_kp", "zg_kd",
                "zg_damping", "kd_extra"]
#: 尾四个字段的注释 (与人工维护版保持一致)
_JOINT_COMMENT = {
    "zg_kp": "# [段②] 零重力虚拟弹簧刚度 Nm/rad",
    "zg_kd": "# [段②] 零重力 MIT 速度阻尼 (固件会抬到下限)",
    "zg_damping": "# [段②] 零重力附加速度阻尼 Nm·s/rad",
    "kd_extra": "# [段③] τ 域软件微分阻尼 (腕部必须 0)",
}
_GLOBAL_SCALARS = ["wall_margin", "fric_db", "fric_v2_eps"]
_GLOBAL_ZG = ["drag_gain", "drag_db", "drag_kd_margin", "zg_vel_thr",
              "zg_engage_sec", "zg_engage_kp", "zg_engage_kd", "wall_fw_kd"]
_GLOBAL_MISC = ["hold_kp_gain", "friction_slew", "payload_mass"]

_HEADER = """# ============================================================
# {title}
# 本文件由 `tools/gen_presets.py` 从固件真源生成 —— **不要手改**, 改固件后重跑生成器。
# 真源: litearm-stm32/User/litearm/params/{{defaults.c, joint_limit_macros.h}}
# 一致性由 tests/test_preset_sync.py 断言 (固件仓不在场时跳过)。
# ============================================================
"""


def _num(v) -> str:
    return repr(float(v))


def render(snap: dict, *, title: str, ff_mask: int) -> str:
    out = [_HEADER.format(title=title), "joints:\n"]
    for i, j in enumerate(snap["joints"], start=1):
        out.append(f"- name: J{i}\n")
        for k in _JOINT_ORDER:
            c = f"          {_JOINT_COMMENT[k]}" if k in _JOINT_COMMENT else ""
            out.append(f"  {k}: {_num(j[k])}{c}\n")
    g = snap["global"]
    out.append("global:\n")
    for k in _GLOBAL_SCALARS:
        out.append(f"  {k}: {_num(g[k])}\n")
    out.append("  # ---- [段② 零重力] ----\n")
    for k in _GLOBAL_ZG:
        out.append(f"  {k}: {_num(g[k])}\n")
    out.append("  # ---- [段③ §6.2] ----\n")
    for k in _GLOBAL_MISC:
        out.append(f"  {k}: {_num(g[k])}\n")
    for k in ("gravity", "payload_com"):
        out.append(f"  {k}:\n")
        for v in g[k]:
            out.append(f"  - {_num(v)}\n")
    out.append(f"  friction_model: {int(g['friction_model'])}\n")
    out.append(f"  ff_mask: {int(ff_mask)}\n")
    return "".join(out)


def sync_values(text: str, snap: dict) -> str:
    """把已有 YAML 里的数值**就地**换成固件真值, 保留全部注释/行序/内联列表写法。

    用于 `templates/params_example.yaml` 这类带教学注释、不宜整体重写的文件。

    **按 YAML 段落判定** (而不是只看 key 名): `joints:` 段内才按关节号替换
    `_JOINT_ORDER` 的键, `global:` 段内才替换全局键 —— 否则 global 段里出现的同名
    键会被写成 J1 的值。block 风格数组 (`gravity:` 后跟 `- v` 行) 也会被同步,
    否则 `--check` 会假绿。
    """
    g = snap["global"]
    out: list = []
    joint, section = 0, None
    pat = re.compile(r"^(\s*)(\w+):(\s*)(\[[^\]]*\]|[^\s#]+)(\s*#.*)?$")
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line, body = lines[i], lines[i].rstrip("\n")
        if re.match(r"^joints:\s*$", body):
            section, i = "joints", i + 1
            out.append(line)
            continue
        if re.match(r"^global:\s*$", body):
            section, i = "global", i + 1
            out.append(line)
            continue
        m = re.match(r"^\s*-\s*name:\s*J(\d+)\b", body)      # 容忍行尾注释
        if m:
            joint, i = int(m.group(1)) - 1, i + 1
            out.append(line)
            continue
        mb = re.match(r"^(\s*)(gravity|payload_com):\s*$", body)   # block 风格数组
        if mb and section == "global" and isinstance(g.get(mb.group(2)), list):
            indent, key = mb.group(1), mb.group(2)
            vals = g[key]
            out.append(line)
            i += 1
            k = 0
            while i < len(lines) and re.match(r"^\s*-\s", lines[i]):
                out.append(f"{indent}- {_num(vals[k])}\n" if k < len(vals) else lines[i])
                k += 1
                i += 1
            continue
        mm = pat.match(body)
        if mm:
            indent, key, sp, _val, tail = mm.groups()
            if section == "joints" and key in _JOINT_ORDER:
                out.append(f"{indent}{key}:{sp}{_num(snap['joints'][joint][key])}{tail or ''}\n")
                i += 1
                continue
            if section == "global" and key in g:
                v = g[key]
                newv = ("[" + ", ".join(_num(x) for x in v) + "]" if isinstance(v, list)
                        else str(int(v)) if key in ("ff_mask", "friction_model")
                        else _num(v))
                out.append(f"{indent}{key}:{sp}{newv}{tail or ''}\n")
                i += 1
                continue
        out.append(line)
        i += 1
    return "".join(out)


def targets(snap: dict) -> dict:
    """相对路径 -> 期望内容。"""
    tpl_path = REPO / "templates" / "params_example.yaml"
    return {
        "presets/current_master_defaults.yaml": render(
            snap, title="当前固件出厂默认 (generated from defaults.c)", ff_mask=snap["global"]["ff_mask"]),
        "presets/se1_friction.yaml": render(
            snap, title="SE1 摩擦 v2 隔离预设: ff_mask 仅 master+friction(0x11=17), 便于单独标定摩擦",
            ff_mask=FD.FF_BITS["FF_MASTER"] | FD.FF_BITS["FF_FRICTION"]),
        "templates/params_example.yaml": sync_values(tpl_path.read_text("utf-8"), snap),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fw-dir", default=None, help="litearm-stm32 固件仓路径")
    ap.add_argument("--check", action="store_true", help="只检查不写盘")
    args = ap.parse_args(argv)

    snap = FD.load_firmware_defaults(args.fw_dir)
    drift = []
    for rel, text in targets(snap).items():
        path = REPO / rel
        old = path.read_text("utf-8") if path.is_file() else None
        if old == text:
            print(f"ok      {rel}")
        elif args.check:
            drift.append(rel)
            print(f"DRIFT   {rel}")
        else:
            path.write_text(text, "utf-8")
            print(f"written {rel}")
    if drift:
        print("\n预设与固件真源不一致, 跑 `python tools/gen_presets.py` 重新生成。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
