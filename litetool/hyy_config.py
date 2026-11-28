"""HYY/SE1 控制器辨识配置 (`DeviceConfig.yaml`) 的解析与映射。

## 用途

产线流程: 每台臂出厂前上 HYY 控制器做一次动力学辨识 → 得到一份 `DeviceConfig.yaml`
→ 本模块把它解析成 stm32 能接受的参数快照 → 经 SDK 写入固件 (**无需重新编译固件**)。

真源样例: `/home/llx/hanbin/SE1/robot_config/DeviceConfig.yaml`
          (`sha256[:16] = b423bf1ff35db041`)

## 映射范围 = **只有 `dynamics_parameters`**（= HYY 辨识的产物）

| yaml 来源 | → 快照字段 | 规则 |
|---|---|---|
| `joint[i].dynamics_parameters.fv/.fc0/.fc1` | `joints[i].friction_v/.friction_fc0/.friction_fc1` | 按 catalog 范围校验 (**固件写口会静默钳幅**, 工具必须先拦) |
| `joint[i].dynamics_parameters.{m,cm*,ix*}` | `model.body[i+1]` | 逐关节 10 值, body 索引 = 关节号+1 |
| `joint[i].dynamics_parameters.jm` | `model.jm[i]` | 7 值 |

**只导辨识产物, 不导控制器配置**（用户 2026-09-14 裁决）。以下三项**刻意不映射**：

| 字段 | 为什么**不**导 |
|---|---|
| `joint[i].axis.smin/smax` | HYY **控制器的关节限位配置**, 不是辨识结果; 且与本机 URDF 口径不同 —— J4 按它映射出的上界是 `+0.64`, 而 URDFv5 机械硬限位是 `+0.035`, 直接下发等于把软限位放到机械限位之外 |
| `joint[i].axis.torque_max` | HYY **控制器的力矩钳幅配置** (`20,20,28,28,10,10,10`), 不是辨识结果。本机 `tau_max` 是 `78,78,21,21,10,10,10` (电机硬件口径), 拿它覆盖会把 J1/J2 的力矩天花板**砍到 1/4** |
| `robot_group.robot[0].gravity` | 常量配置 (HYY 用本地 g `−9.802`, 本机 `−9.81`), 不是辨识结果 |

**不映射的还有**: DH 几何 / `direction` / `encoder_ruler` / `gear_ratio` / `endlimit.*` /
`tool.*` / `fv2`/`fv3` 等 —— 逐项列入 `unmapped` 并附原因, 不静默丢弃 (见 `UNMAPPED_REASONS`)。

## 两条容易踩的坑

1. **`expected_mask` 只写 body1..7 + jm** (0x2FE): body0=base 不参与递推、body8=ee 是
   payload 复合位, 都不该由导入改写 (固件也拒绝 body8 质量非 0)。
2. **`to_snapshot` 必须产出完整快照** —— 未映射字段从设备 `baseline` 逐项取回,
   不导的项原样保持设备当前值。
"""
from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from litetool import i18n
from litetool import param_catalog as C

__all__ = ["HyyConfigError", "HyyConfig", "parse_hyy_config", "to_snapshot",
           "MODEL_BODY_KEYS", "UNMAPPED_REASONS", "unmapped_report",
           "FrictionAsymmetry", "friction_asymmetry", "suspicious_joints",
           "asymmetry_message", "FC_ASYM_RATIO", "FC_ASYM_MIN_DELTA"]


class HyyConfigError(ValueError):
    """yaml 结构/数值不合法 —— 文案面向操作员, 全部中文。"""


# ---------------------------------------------------------------------------
# 常量表 (镜像, 附出处; 由 tests/test_hyy_config.py 守着)
# ---------------------------------------------------------------------------
# [2026-09-14 裁决] 本模块**不再映射软限位** —— `axis.smin/smax` 是 HYY 控制器的
# 关节限位配置, 不是辨识产物。故原先那套"符号修正 (S_SE1) + 与 URDF 硬限位取交集"
# 的代码已删除, 其知识保留在下方 UNMAPPED_REASONS 的注释里 (含 J4 冲突的实测值)。

#: 模型段每刚体的 10 个字段 (顺序 **必须**与固件 `DYN_MODEL_BODY_PARAMS` 一致:
#: `dyn.h` 注释 + `dyn_model_data.h` 的 DYN_INERTIA 排列 = ixx ixy ixz iyy iyz izz)。
MODEL_BODY_KEYS = ("m", "cmx", "cmy", "cmz", "ixx", "ixy", "ixz", "iyy", "iyz", "izz")

#: 辨识基参数的上界 —— 只做有限性/量级校验, **不做物理范围钳制**。
#: 理由 (用户口径): 辨识基参数单个无物理意义 (m 全是归一化占位值 1.0、I 含负值、
#: M 非正定), 物理钳制会把**正确**模型判成非法。与固件写口 `|v| <= 1e6` 同口径。
MODEL_ABS_MAX = 1e6


# ---------------------------------------------------------------------------
# 未映射字段的原因枚举 (清单由代码计算, 不手抄 —— 漏一项就红)
# ---------------------------------------------------------------------------
NO_PORT = "无 CDC 写口 (编译期常量)"
KINEMATIC = "连杆几何, 同型号恒定, 本设计不改"
NON_RUNTIME = "非运行时参数"
AXIS_FIXED = "轴配置 (方向/编码器/减速比), 编译期常量"
#: [2026-09-14] `axis.smin/smax` / `axis.torque_max` / `gravity` 归入此类 —— 它们是
#: **HYY 控制器的配置**, 不是辨识产物, 用户裁决不导 (见模块 docstring 的对照表)。
HYY_CTRL_CFG = "HYY 控制器配置, 非辨识产物 (本机用自身口径) "


@dataclass(frozen=True)
class HyyConfig:
    """解析后的 DeviceConfig.yaml。"""

    path: str
    sha256_16: str
    version: str
    serial: str
    description: str
    joints: List[dict]          # 7 个 dict, 每项含 kinematics/dynamics/axis
    gravity: Tuple[float, float, float]
    raw_keys: Tuple[str, ...]   # 展开后的全部 yaml 键路径 (供 unmapped 计算)


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------
def _req(d: dict, key: str, where: str):
    if not isinstance(d, dict) or key not in d:
        raise HyyConfigError(i18n.tr("{where} 缺字段 `{key}`", where=where, key=key))
    return d[key]


def _num(d: dict, key: str, where: str) -> float:
    v = _req(d, key, where)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise HyyConfigError(i18n.tr("{where}.{key} 须为数值, 实际 {value}",
                                      where=where, key=key, value=repr(v)))
    f = float(v)
    if not math.isfinite(f):
        raise HyyConfigError(i18n.tr("{where}.{key} 非有限 ({value})",
                                      where=where, key=key, value=f))
    return f


def _f32(v) -> float:
    """把 yaml 的 float64 固定成 **float32** —— 固件存的就是 float32。

    [2026-09-14 真机验出的 bug] 不 cast 的后果: yaml 侧的 `0.7516675845629472` 与
    设备读回的 `0.7516675591468811`（同一 float32 的两种 float64 写法）在
    `diff_snapshots` 的精确比较下**判为不同** ⇒ 每次导入都刷出 21 行假"修改"。
    让操作员学会无视红字, 比报错更危险。
    （`model_io.model_diff` 一开始就做了 cast, 所以模型段没这个毛病。）
    """
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def _walk_keys(obj, prefix: str, out: List[str]) -> None:
    """展开 yaml 全部键路径 (数组下标用 `[]`), 供未映射清单计算。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk_keys(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, list):
        # 数组: 只展开第 0 项并记成 `[]` —— 逐项展开会让清单爆炸且无信息量
        if obj:
            _walk_keys(obj[0], f"{prefix}[]", out)
        else:
            out.append(f"{prefix}[]")
    else:
        out.append(prefix)


def parse_hyy_config(path: str) -> HyyConfig:
    """解析并校验 DeviceConfig.yaml。结构/数值错误抛 `HyyConfigError` (中文)。"""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except HyyConfigError:
        raise
    except Exception as e:                       # noqa: BLE001 - 统一转中文
        raise HyyConfigError(i18n.tr("读取/解析 yaml 失败: {err}", err=e)) from e

    if not isinstance(raw, dict):
        raise HyyConfigError(i18n.tr("yaml 顶层须为对象"))

    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()[:16]

    ver = raw.get("version") or {}
    version = ".".join(str(ver.get(k, 0)) for k in ("major", "minor", "build")) \
        if isinstance(ver, dict) else str(ver)

    rob = _req(_req(raw, "robot_group", "顶层"), "robot", "robot_group")
    if not isinstance(rob, list) or not rob:
        raise HyyConfigError(i18n.tr("robot_group.robot 须为非空数组"))
    r0 = rob[0]

    joints = _req(r0, "joint", "robot[0]")
    if not isinstance(joints, list) or len(joints) != C.NUM_JOINTS:
        raise HyyConfigError(i18n.tr(
            "robot[0].joint 须为长度 {n} 的数组 (J1..J7, 顺序即关节号), 实际 {got}",
            n=C.NUM_JOINTS,
            got=len(joints) if isinstance(joints, list) else type(joints).__name__))

    for i, j in enumerate(joints):
        where = f"joint[{i}] (J{i + 1})"
        if not isinstance(j, dict):
            raise HyyConfigError(i18n.tr("{where} 须为对象", where=where))
        ax = _req(j, "axis", where)
        # [关键] 数组顺序必须与 axis.id 一致 —— 否则 body[i+1] 会静默错位,
        # 而读回比对全绿 (写进去的和读回来的一致)。
        jid = ax.get("id")
        if jid is not None and int(jid) != i:
            raise HyyConfigError(i18n.tr(
                "{where}: axis.id={jid} 与数组下标 {i} 不一致 —— "
                "顺序即关节号, 拒绝导入", where=where, jid=jid, i=i))
        d = _req(j, "dynamics_parameters", where)
        for k in MODEL_BODY_KEYS + ("fv", "fc0", "fc1", "jm"):
            _num(d, k, f"{where}.dynamics_parameters")
        lo = _num(ax, "smin", f"{where}.axis")
        hi = _num(ax, "smax", f"{where}.axis")
        if not lo < hi:
            raise HyyConfigError(i18n.tr(
                "{where}.axis: smin({lo}) 须 < smax({hi})",
                where=where, lo=lo, hi=hi))
        _num(ax, "torque_max", f"{where}.axis")
        _req(j, "kinematics_parameters", where)

    g = _req(r0, "gravity", "robot[0]")
    grav = tuple(_num(g, k, "robot[0].gravity") for k in ("x", "y", "z"))
    # [关键] gravity≈0 会让固件侧的 G 层零模型哨兵对**任何**模型失败
    # (哨兵比的是候选 G 与出厂 G 的比值)。固件已把评估重力钉死, 但 yaml 侧
    # 仍应拦住明显非法的 0 重力。
    if math.sqrt(sum(v * v for v in grav)) < 1.0:
        raise HyyConfigError(i18n.tr(
            "robot[0].gravity 模长 {mag:.3f} < 1.0 m/s² —— 非法",
            mag=math.sqrt(sum(v * v for v in grav))))

    keys: List[str] = []
    _walk_keys(raw, "", keys)

    return HyyConfig(path=path, sha256_16=sha, version=version,
                     serial=str(raw.get("serial", "")),
                     description=str(raw.get("description", "")),
                     joints=list(joints), gravity=grav,   # type: ignore[arg-type]
                     raw_keys=tuple(sorted(set(keys))))


# ---------------------------------------------------------------------------
# 映射
# ---------------------------------------------------------------------------
def _check_range(key: str, v: float, where: str) -> None:
    """按 param_catalog 的范围校验 (关节项与全局项同源, 与固件钳幅一致)。

    ⚠ 这一步**必须**做: 固件对摩擦写口会**静默钳幅** (超范围不报错, 只改成边界值),
    于是"写进去的值"与"读回来的值"不一致 —— 读回闸会报差异, 而真因在钳幅。
    工具侧先拦, 让操作员看到准确的越界值。
    """
    p = C.JOINT_BY_KEY.get(key) or C.GLOBAL_BY_KEY.get(key)
    if p is None:
        raise HyyConfigError(i18n.tr(
            "{where}.{key} 不在参数目录中 (既非关节项也非全局项)",
            where=where, key=key))
    err = C.check_value(p.lo, p.hi, v, label=f"{where}.{key}")
    if err:
        raise HyyConfigError(err)


def to_snapshot(cfg: HyyConfig, baseline: Optional[dict]) -> Tuple[dict, dict, List[str]]:
    """把 yaml 映射成 `param_catalog.normalize_snapshot` 形状的**完整**快照。

    返回 `(snapshot, model, notes)`:
      - `snapshot`: `{joints: [...×7], global: {...}}` —— 所有键齐全。
        **只有摩擦三元组来自 yaml**; 其余一律从 `baseline` 原样取回 (不动设备当前值)。
      - `model`: `{body: [[10 floats] × 9], jm: [7]}` —— 单独交付给 `model_io`。
      - `notes`: 面向操作员的中文提示。

    ⚠ `baseline is None` 时**拒绝** —— `normalize_snapshot` 强制要求 `global` 的
      15 个标量 + 2 个数组 + `friction_model` + `ff_mask` 全部存在, 缺一项即 raise;
      而没有设备基线就无从补齐未映射字段。

    **只导辨识产物**: `dynamics_parameters` 的摩擦三元组 + 模型段。`axis.smin/smax` /
    `axis.torque_max` / `gravity` 刻意不导 (见模块 docstring 的说明)。
    """
    if baseline is None:
        raise HyyConfigError(i18n.tr(
            "尚无设备基线 —— 请先点 [刷新当前] 再导入 (导入需要基线补齐未映射字段)"))

    notes: List[str] = []
    joints: List[Dict[str, Any]] = []
    model_body: List[List[float]] = [[0.0] * len(MODEL_BODY_KEYS)
                                     for _ in range(C.NUM_JOINTS + 2)]
    model_jm: List[float] = [0.0] * C.NUM_JOINTS

    for i, j in enumerate(cfg.joints):
        where = f"J{i + 1}"
        d = j["dynamics_parameters"]

        # 唯一的关节级映射: 摩擦三元组。
        # 先按 catalog 范围校验 —— 固件对摩擦写口会**静默钳幅** (超范围不报错,
        # 只改成边界值), 那样"写进去的"与"读回来的"不一致, 读回闸会报差异而真因在钳幅。
        fv, fc0, fc1 = _num(d, "fv", where), _num(d, "fc0", where), _num(d, "fc1", where)
        _check_range("friction_v", fv, where)
        _check_range("friction_fc0", fc0, where)
        _check_range("friction_fc1", fc1, where)

        base = dict(baseline["joints"][i])
        for k, v in list(base.items()):
            # 只看参数键 (`name` 是助读字段, 不是参数)
            if v is None and k in C.JOINT_BY_KEY:
                raise HyyConfigError(i18n.tr(
                    "{where}.{key} 在设备基线上为空 —— 台架上 J2..J7 无读回值。"
                    "导入需要整臂基线", where=where, key=k))
        # **cast 成 float32** —— 见 `_f32` 的说明: 设备存的是 float32, 不 cast 会让
        # diff 每次都报这 21 项假"修改"。
        base["friction_v"], base["friction_fc0"], base["friction_fc1"] = \
            _f32(fv), _f32(fc0), _f32(fc1)
        # q_min/q_max/tau_max/kp/kd/... 全部保持设备当前值 (原样从 baseline 取回)
        joints.append(base)

        # 模型段: body[i+1] = 该关节; body0 (base) 与 body8 (ee) 保持 0
        model_body[i + 1] = [_f32(d[k]) for k in MODEL_BODY_KEYS]
        model_jm[i] = _f32(d["jm"])

    glob = {k: (list(v) if isinstance(v, list) else v) for k, v in baseline["global"].items()}

    snap = {"joints": joints, "global": glob}
    C.normalize_snapshot(snap)          # 自检: 产物必须过固件同源的校验
    model = {"body": model_body, "jm": model_jm}
    return snap, model, notes


# ---------------------------------------------------------------------------
# 摩擦对称性检查 —— 机械健康哨兵
# ---------------------------------------------------------------------------
# 固件的摩擦模型 (`law.c` / `tuning_guide.py:20`):
#     τ_fric v2 = fv·q̇ + fc0·max(tanh(q̇/ε),0) + fc1·max(−tanh(q̇/ε),0)
# 即 **fc0 = 正向库仑 (≥0)、fc1 = 负向库仑 (≤0)**。所以 `|fc0|` 与 `|fc1|` 就是
# 同一关节**正、反两个方向的摩擦力幅值**。
#
# 健康关节两向摩擦应大致对称; 相差悬殊通常指向**机械问题** (轴承发卡 / 减速器磨损 /
# 异物 / 预紧异常), 或辨识时该关节被外力干扰 —— 两种情况都值得让人先看一眼再导入。
#
# 阈值锚点来自 SE1 实测 (一台**已知正常**的臂, `|fc0|`/`|fc1|` 比值):
#     J1 1.03 · J2 1.42 · J3 1.06 · J4 1.19 · J5 1.05 · J6 1.36 · J7 1.02
# 健康臂最大值 1.42 ⇒ 取 2.0, 留约 40% 余量。
# (取 1.5 只剩 6% 余量, 每台好臂都会弹窗, 很快会被操作员学会条件反射点掉 ——
#  那比不报警更糟, 与 [[hyy-model-import]] 里"让操作员学会无视红字比报错更危险"
#  是同一条教训。)
FC_ASYM_RATIO = 2.0

#: **纯比值会在摩擦趋近 0 的关节上误报**: `fc0=0.001 / fc1=−0.003` 比值 3.0 而差值
#: 仅 0.002 Nm, 毫无物理意义。故比值之外**必须**再加绝对差值下限。
#: 实测数据里最小的有效 |fc| 是 J7 的 0.077, 取下限 0.05 不会误伤。
FC_ASYM_MIN_DELTA = 0.05


@dataclass(frozen=True)
class FrictionAsymmetry:
    """单个关节正/反库仑摩擦的对称性。"""

    joint: int                  # 1-based
    fc0: float                  # 正向库仑 (≥0)
    fc1: float                  # 负向库仑 (≤0)

    @property
    def a(self) -> float:
        return abs(self.fc0)

    @property
    def b(self) -> float:
        return abs(self.fc1)

    @property
    def delta(self) -> float:
        return abs(self.a - self.b)

    @property
    def ratio(self) -> float:
        """`max/min`。一侧恰好为 0 时是 ∞ —— 单侧有摩擦本身就是强信号。"""
        lo, hi = sorted((self.a, self.b))
        return math.inf if lo <= 0.0 else hi / lo

    @property
    def suspicious(self) -> bool:
        """比值超标 **且** 差值有物理量级 —— 两个条件缺一不可。"""
        return self.ratio > FC_ASYM_RATIO and self.delta >= FC_ASYM_MIN_DELTA


def friction_asymmetry(cfg: HyyConfig) -> List[FrictionAsymmetry]:
    """逐关节算正/反库仑摩擦对称性 (**全部**关节, 不过滤)。

    数值校验 (`_num`) 与 `to_snapshot` 同源 —— 本函数可独立调用。
    """
    out: List[FrictionAsymmetry] = []
    for i, j in enumerate(cfg.joints):
        where = f"J{i + 1}"
        d = j["dynamics_parameters"]
        out.append(FrictionAsymmetry(joint=i + 1,
                                     fc0=_num(d, "fc0", where),
                                     fc1=_num(d, "fc1", where)))
    return out


def suspicious_joints(cfg: HyyConfig) -> List[FrictionAsymmetry]:
    """只返回**可疑**的关节 (空 = 全对称, 正常路径)。"""
    return [x for x in friction_asymmetry(cfg) if x.suspicious]


def asymmetry_message(items: List[FrictionAsymmetry]) -> Tuple[str, str]:
    """`(一句话结论, 逐关节明细)` —— **富文本 (HTML 子集)**, 供 `QMessageBox` 直接渲染。

    ⚠ 换行与加粗必须写 `<br>` / `<b>`, **不能**用 Markdown 的 `**` 和 `\\n`:

      - `QMessageBox` 不认 Markdown, `**` 会**原样打出来** (离屏渲染实测);
      - 文本一旦含 HTML 标签, Qt 就切到**富文本模式**, 此时 `\\n` 不再换行。

    两件事是连在一起的 —— 只把 `**` 换成 `<b>` 而留着 `\\n`, 版面会从"分行"塌成
    "挤成一坨"。所以本函数整体按富文本写。
    """
    n = len(items)
    head = i18n.tr(
        "检测到 <b>{n}</b> 个关节的<b>正、反方向库仑摩擦严重不对称</b>"
        "<br>判据: 比值 &gt; {ratio:g} 且差值 ≥ {delta:g} Nm",
        n=n, ratio=FC_ASYM_RATIO, delta=FC_ASYM_MIN_DELTA)

    rows: List[str] = []
    for x in items:
        r = "∞" if math.isinf(x.ratio) else f"{x.ratio:.2f}"
        # 每个关节固定两行 —— 单行版在窄窗口下会**折在数字中间** (离屏渲染实测),
        # 显式换行不依赖窗口宽度, 也就不会有那种难看的断点。
        rows.append(i18n.tr(
            "&nbsp;&nbsp;J{joint}:&nbsp; |fc0| = <b>{a:.3f}</b> Nm , "
            "|fc1| = <b>{b:.3f}</b> Nm"
            "<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "比值 <b>{ratio}</b> , 差值 {delta:.3f} Nm",
            joint=x.joint, a=x.a, b=x.b, ratio=r, delta=x.delta))
    return head, "<br>".join(rows)


# ---------------------------------------------------------------------------
# 未映射清单 (由代码计算)
# ---------------------------------------------------------------------------
#: 已映射的键路径 (与 to_snapshot 的实现一一对应)。
MAPPED_KEYS = {
    "robot_group.robot[].joint[].dynamics_parameters.fv",
    "robot_group.robot[].joint[].dynamics_parameters.fc0",
    "robot_group.robot[].joint[].dynamics_parameters.fc1",
} | {f"robot_group.robot[].joint[].dynamics_parameters.{k}" for k in MODEL_BODY_KEYS} \
  | {"robot_group.robot[].joint[].dynamics_parameters.jm"}

#: 未映射键 -> 原因 (手写白名单; 测试断言 `unmapped_report` 的输出**恰等于**本表)。
#: 由 `tests/test_hyy_config.py` 守着 —— 真源 yaml 新增字段时会红, 迫使显式裁决。
UNMAPPED_REASONS: Dict[str, str] = {
    "version.major": NON_RUNTIME, "version.minor": NON_RUNTIME, "version.build": NON_RUNTIME,
    "serial": NON_RUNTIME, "description": NON_RUNTIME,
    "robot_group.robot[].model_solve": NON_RUNTIME,
    "robot_group.robot[].use_feedforward": NON_RUNTIME,
    "robot_group.robot[].use_jointsensor": NON_RUNTIME,
    "robot_group.robot[].encoder_mode": NON_RUNTIME,
    "robot_group.robot[].tool.x": KINEMATIC, "robot_group.robot[].tool.y": KINEMATIC,
    "robot_group.robot[].tool.z": KINEMATIC,
    "robot_group.robot[].tool.k": KINEMATIC, "robot_group.robot[].tool.p": KINEMATIC,
    "robot_group.robot[].tool.s": KINEMATIC,
    "robot_group.robot[].base.x": NON_RUNTIME, "robot_group.robot[].base.y": NON_RUNTIME,
    "robot_group.robot[].base.z": NON_RUNTIME,
    "robot_group.robot[].base.k": NON_RUNTIME, "robot_group.robot[].base.p": NON_RUNTIME,
    "robot_group.robot[].base.s": NON_RUNTIME,
    "robot_group.robot[].endlimit.tran_velocity_max": NON_RUNTIME,
    "robot_group.robot[].endlimit.tran_acceleration_max": NON_RUNTIME,
    "robot_group.robot[].endlimit.tran_jerk_max": NON_RUNTIME,
    "robot_group.robot[].endlimit.rot_velocity_max": NON_RUNTIME,
    "robot_group.robot[].endlimit.rot_acceleration_max": NON_RUNTIME,
    "robot_group.robot[].endlimit.rot_jerk_max": NON_RUNTIME,
}
for _k in ("theta", "d", "a", "alpha", "offset", "mdh", "flip"):
    UNMAPPED_REASONS[f"robot_group.robot[].joint[].kinematics_parameters.{_k}"] = KINEMATIC
for _k in ("id", "initial_offset", "initial_offset2", "sensor_offset", "sensor_offset2",
           "sigma", "direction", "direction2", "vmin", "vmax", "amin", "amax",
           "jmin", "jmax", "current_coeff", "torque_coeff", "sensor_coeff",
           "sensor_coeff2", "encoder_ruler", "encoder_ruler2", "gear_ratio"):
    UNMAPPED_REASONS[f"robot_group.robot[].joint[].axis.{_k}"] = AXIS_FIXED
for _k in ("fv2", "fv3"):
    UNMAPPED_REASONS[f"robot_group.robot[].joint[].dynamics_parameters.{_k}"] = NO_PORT

# [2026-09-14 裁决] 只导辨识产物; 这三项是 HYY 控制器配置, 刻意不导。
# 实测差异 (本机 vs yaml):
#   smin/smax  : 本机 = URDF 硬限位−1° (J1 ±2.809547 / J4 [-3.071547, +0.017547]);
#                yaml 映射后 J4 上界 +0.64 —— 超出机械硬限位 +0.035, 直接下发不安全
#   torque_max : 本机 78,78,21,21,10,10,10 (电机硬件口径);
#                yaml 20,20,28,28,10,10,10 —— 覆盖会把 J1/J2 的力矩天花板砍到 1/4
#   gravity    : 本机 (0,0,-9.81); yaml (0,0,-9.802) (HYY 用本地 g)
UNMAPPED_REASONS["robot_group.robot[].joint[].axis.smin"] = HYY_CTRL_CFG
UNMAPPED_REASONS["robot_group.robot[].joint[].axis.smax"] = HYY_CTRL_CFG
UNMAPPED_REASONS["robot_group.robot[].joint[].axis.torque_max"] = HYY_CTRL_CFG
UNMAPPED_REASONS["robot_group.robot[].gravity.x"] = HYY_CTRL_CFG
UNMAPPED_REASONS["robot_group.robot[].gravity.y"] = HYY_CTRL_CFG
UNMAPPED_REASONS["robot_group.robot[].gravity.z"] = HYY_CTRL_CFG


def unmapped_report(cfg: HyyConfig) -> List[Tuple[str, str]]:
    """`[(key_path, 原因)]` —— 由 yaml 的实际键集减去已映射集算出, 不手抄。"""
    out = []
    for k in cfg.raw_keys:
        if k in MAPPED_KEYS:
            continue
        out.append((k, i18n.tr(UNMAPPED_REASONS.get(k, "未登记 —— 需裁决"))))
    return out
