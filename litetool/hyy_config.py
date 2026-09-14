"""HYY/SE1 控制器辨识配置 (`DeviceConfig.yaml`) 的解析与映射。

## 用途

产线流程: 每台臂出厂前上 HYY 控制器做一次动力学辨识 → 得到一份 `DeviceConfig.yaml`
→ 本模块把它解析成 stm32 能接受的参数快照 → 经 SDK 写入固件 (**无需重新编译固件**)。

真源样例: `/home/llx/hanbin/SE1/robot_config/DeviceConfig.yaml`
          (`sha256[:16] = b423bf1ff35db041`)

## 映射范围 (四项 + 模型段)

| yaml 来源 | → 快照字段 | 规则 |
|---|---|---|
| `joint[i].dynamics_parameters.fv/.fc0/.fc1` | `joints[i].friction_v/.friction_fc0/.friction_fc1` | 按 catalog 范围校验 (**固件写口会静默钳幅**, 工具必须先拦) |
| `joint[i].axis.smin/smax` | `joints[i].q_min/.q_max` | 符号修正 (见 `S_SE1`) 后与 URDFv5 硬限位−1° **取交集** |
| `joint[i].axis.torque_max` | `joints[i].tau_max` | 原样 (安全类字段, UI 独立高亮) |
| `robot_group.robot[0].gravity` | `global.gravity` | 原样 (安全类字段) |
| `joint[i].dynamics_parameters.{m,cm*,ix*}` | `model.body[i+1]` | 逐关节 10 值, body 索引 = 关节号+1 |
| `joint[i].dynamics_parameters.jm` | `model.jm[i]` | 7 值 |

**不映射**: DH 几何 / `direction` / `encoder_ruler` / `gear_ratio` / `endlimit.*` / `tool.*`
等 —— 逐项列入 `unmapped` 并附原因, 不静默丢弃 (见 `UNMAPPED_REASONS`)。

## 两条容易踩的坑

1. **`expected_mask` 只写 body1..7 + jm** (0x2FE): body0=base 不参与递推、body8=ee 是
   payload 复合位, 都不该由导入改写 (固件也拒绝 body8 质量非 0)。
2. **软限位必须取交集**: J4 按 yaml 映射出的上界是 +0.64, 而 URDFv5 机械硬限位是 +0.035
   —— 直接下发等于把软限位放到机械限位之外 (越限锁存不受 `enabled` 门控、`reset` 清不掉)。
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from litetool import param_catalog as C

__all__ = ["HyyConfigError", "HyyConfig", "LimitNote", "parse_hyy_config", "to_snapshot",
           "map_limits", "symbol_fix", "S_SE1", "URDF_HARD_LIMITS", "LIMIT_SHRINK",
           "MODEL_BODY_KEYS", "UNMAPPED_REASONS", "unmapped_report"]


class HyyConfigError(ValueError):
    """yaml 结构/数值不合法 —— 文案面向操作员, 全部中文。"""


# ---------------------------------------------------------------------------
# 常量表 (镜像, 附出处; 由 tests/test_hyy_config.py 守着)
# ---------------------------------------------------------------------------

#: 关节符号真源 = `hyy_mapping.json` 的 `winner_id.s` (hyy_fk_align.py 的 MDH 对齐裁决产物)。
#: ⚠ **不是** yaml 里的 `axis.direction` —— 两者 Hamming 距离 = 1 (仅 J6 不同:
#: direction=[T,T,T,F,T,F,F] 翻转 {J4,J6,J7}, s 翻转 {J4,J7})。
#: 本份数据上两条规则结果恰好相同 (J6 的 smin/smax = ∓1.57 对称, 取负是恒等操作),
#: 但那是巧合: 只要将来 J6 限位不对称, 用 direction 就会算错 2·min(|smin|,|smax|)。
S_SE1: Tuple[int, ...] = (1, 1, 1, -1, 1, 1, -1)

#: URDFv5 机械硬限位 (rad)。真源 `litearm-stm32/assets/litearm/urdf/litearm.urdf` 的 <limit>。
#: 已实测: `litearm.urdf` 与 `litearm_id.urdf` 的限位值完全相同。
URDF_HARD_LIMITS: Tuple[Tuple[float, float], ...] = (
    (-2.827, 2.827), (-1.745, 1.745), (-2.827, 2.827), (-3.089, 0.035),
    (-2.827, 2.827), (-1.571, 1.571), (-1.571, 1.571),
)

#: 硬限位内缩 1° (= joint_limit_macros.h 的取整口径)
LIMIT_SHRINK = 0.0174532925

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
        raise HyyConfigError(f"{where} 缺字段 `{key}`")
    return d[key]


def _num(d: dict, key: str, where: str) -> float:
    v = _req(d, key, where)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise HyyConfigError(f"{where}.{key} 须为数值, 实际 {v!r}")
    f = float(v)
    if not math.isfinite(f):
        raise HyyConfigError(f"{where}.{key} 非有限 ({f})")
    return f


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
        raise HyyConfigError(f"读取/解析 yaml 失败: {e}") from e

    if not isinstance(raw, dict):
        raise HyyConfigError("yaml 顶层须为对象")

    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()[:16]

    ver = raw.get("version") or {}
    version = ".".join(str(ver.get(k, 0)) for k in ("major", "minor", "build")) \
        if isinstance(ver, dict) else str(ver)

    rob = _req(_req(raw, "robot_group", "顶层"), "robot", "robot_group")
    if not isinstance(rob, list) or not rob:
        raise HyyConfigError("robot_group.robot 须为非空数组")
    r0 = rob[0]

    joints = _req(r0, "joint", "robot[0]")
    if not isinstance(joints, list) or len(joints) != C.NUM_JOINTS:
        raise HyyConfigError(
            f"robot[0].joint 须为长度 {C.NUM_JOINTS} 的数组 (J1..J7, 顺序即关节号), "
            f"实际 {len(joints) if isinstance(joints, list) else type(joints).__name__}")

    for i, j in enumerate(joints):
        where = f"joint[{i}] (J{i + 1})"
        if not isinstance(j, dict):
            raise HyyConfigError(f"{where} 须为对象")
        ax = _req(j, "axis", where)
        # [关键] 数组顺序必须与 axis.id 一致 —— 否则 body[i+1] 会静默错位,
        # 而读回比对全绿 (写进去的和读回来的一致)。
        jid = ax.get("id")
        if jid is not None and int(jid) != i:
            raise HyyConfigError(
                f"{where}: axis.id={jid} 与数组下标 {i} 不一致 —— 顺序即关节号, 拒绝导入")
        d = _req(j, "dynamics_parameters", where)
        for k in MODEL_BODY_KEYS + ("fv", "fc0", "fc1", "jm"):
            _num(d, k, f"{where}.dynamics_parameters")
        lo = _num(ax, "smin", f"{where}.axis")
        hi = _num(ax, "smax", f"{where}.axis")
        if not lo < hi:
            raise HyyConfigError(f"{where}.axis: smin({lo}) 须 < smax({hi})")
        _num(ax, "torque_max", f"{where}.axis")
        _req(j, "kinematics_parameters", where)

    g = _req(r0, "gravity", "robot[0]")
    grav = tuple(_num(g, k, "robot[0].gravity") for k in ("x", "y", "z"))
    # [关键] gravity≈0 会让固件侧的 G 层零模型哨兵对**任何**模型失败
    # (哨兵比的是候选 G 与出厂 G 的比值)。固件已把评估重力钉死, 但 yaml 侧
    # 仍应拦住明显非法的 0 重力。
    if math.sqrt(sum(v * v for v in grav)) < 1.0:
        raise HyyConfigError(
            f"robot[0].gravity 模长 {math.sqrt(sum(v*v for v in grav)):.3f} < 1.0 m/s² —— 非法")

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
def symbol_fix(lo: float, hi: float, idx: int) -> Tuple[float, float]:
    """第 1 步: 符号修正。`x = s·q` (s 取 `S_SE1`) ⇒ `q = x/s`; s=-1 时上下界交换。"""
    s = S_SE1[idx] if idx < len(S_SE1) else 1
    a, b = lo / s, hi / s
    return (a, b) if a <= b else (b, a)


def map_limits(lo: float, hi: float, idx: int) -> Tuple[float, float]:
    """SE1 的 `smin/smax` -> 我方关节空间区间 (符号修正 + 与 URDFv5 硬限位−1° 取交集)。

    两步:
      1. 符号修正: 见 `symbol_fix`。
      2. 交集: 与 `URDF_HARD_LIMITS[idx] ∓ LIMIT_SHRINK` 取 `max(下界)` / `min(上界)`。
         **必须取** —— J4 的 yaml 上界 +0.64 超出机械硬限位 +0.035; 不取交集等于把软限位
         放到机械限位之外 (J4 越限锁存不受 `enabled` 门控、`reset` 也清不掉)。
    """
    mlo, mhi = symbol_fix(lo, hi, idx)
    hard_lo, hard_hi = URDF_HARD_LIMITS[idx]
    return max(mlo, hard_lo + LIMIT_SHRINK), min(mhi, hard_hi - LIMIT_SHRINK)


@dataclass(frozen=True)
class LimitNote:
    idx: int
    mapped: Tuple[float, float]
    clipped: Tuple[float, float]

    @property
    def conflict(self) -> bool:
        """映射值超出机械硬限位 => 交集已取 URDF 侧 (安全侧), 需显式告警。"""
        hl, hh = URDF_HARD_LIMITS[self.idx]
        return self.mapped[0] < hl - 1e-12 or self.mapped[1] > hh + 1e-12


def _check_range(key: str, v: float, where: str) -> None:
    """按 param_catalog 的范围校验 (关节项与全局项同源, 与固件钳幅一致)。

    ⚠ 这一步**必须**做: 固件对摩擦写口会**静默钳幅** (超范围不报错, 只改成边界值),
    于是"写进去的值"与"读回来的值"不一致 —— 读回闸会报差异, 而真因在钳幅。
    工具侧先拦, 让操作员看到准确的越界值。
    """
    p = C.JOINT_BY_KEY.get(key) or C.GLOBAL_BY_KEY.get(key)
    if p is None:
        raise HyyConfigError(f"{where}.{key} 不在参数目录中 (既非关节项也非全局项)")
    err = C.check_value(p.lo, p.hi, v, label=f"{where}.{key}")
    if err:
        raise HyyConfigError(err)


def to_snapshot(cfg: HyyConfig, baseline: Optional[dict],
                include_gravity: bool = True, include_limits: bool = True,
                include_tau_max: bool = True) -> Tuple[dict, dict, List[str]]:
    """把 yaml 映射成 `param_catalog.normalize_snapshot` 形状的**完整**快照。

    返回 `(snapshot, model, notes)`:
      - `snapshot`: `{joints: [...×7], global: {...}}` —— 所有键齐全 (未映射的从
        `baseline` 取), 可直接喂 `C.normalize_snapshot` / diff / 下发。
      - `model`: `{body: [[10 floats] × 9], jm: [7]}` —— 单独交付给 `model_io`。
      - `notes`: 面向操作员的中文提示 (J4 冲突等)。

    ⚠ `baseline is None` 时**拒绝** —— `normalize_snapshot` 强制要求 `global` 的
      15 个标量 + 2 个数组 + `friction_model` + `ff_mask` 全部存在, 缺一项即 raise;
      而没有设备基线就无从补齐。
    """
    if baseline is None:
        raise HyyConfigError("尚无设备基线 —— 请先点 [刷新当前] 再导入 (导入需要基线补齐未映射字段)")

    notes: List[str] = []
    joints: List[Dict[str, Any]] = []
    model_body: List[List[float]] = [[0.0] * len(MODEL_BODY_KEYS)
                                     for _ in range(C.NUM_JOINTS + 2)]
    model_jm: List[float] = [0.0] * C.NUM_JOINTS

    for i, j in enumerate(cfg.joints):
        where = f"J{i + 1}"
        d = j["dynamics_parameters"]
        ax = j["axis"]

        # 1) 摩擦三元组 (先按 catalog 范围校验 —— 固件写口会静默钳幅)
        fv, fc0, fc1 = _num(d, "fv", where), _num(d, "fc0", where), _num(d, "fc1", where)
        _check_range("friction_v", fv, where)
        _check_range("friction_fc0", fc0, where)
        _check_range("friction_fc1", fc1, where)

        # 2) 软限位 (符号修正 + 交集)
        smin, smax = _num(ax, "smin", where), _num(ax, "smax", where)
        q_lo, q_hi = map_limits(smin, smax, i)
        # mapped = 符号修正后、**取交集前**的值 (用于冲突判据); clipped = 交集后
        ln = LimitNote(idx=i, mapped=symbol_fix(smin, smax, i), clipped=(q_lo, q_hi))
        if include_limits:
            _check_range("q_min", q_lo, where)
            _check_range("q_max", q_hi, where)
            if not q_lo < q_hi:
                raise HyyConfigError(f"{where}: 限位交集为空 ([{q_lo}, {q_hi}])")
            if ln.conflict:
                notes.append(
                    f"⚠ J{i + 1}: yaml 映射限位 [{ln.mapped[0]:.4f}, {ln.mapped[1]:.4f}] 超出 "
                    f"URDFv5 机械硬限位 [{URDF_HARD_LIMITS[i][0]:.4f}, {URDF_HARD_LIMITS[i][1]:.4f}] "
                    f"—— 交集已取 URDF 侧 (安全侧); 放宽需先真机确认机械行程")

        # 3) tau_max (安全类字段)
        tmax = _num(ax, "torque_max", where)
        _check_range("tau_max", tmax, where)

        base = dict(baseline["joints"][i])
        if include_tau_max:
            base["tau_max"] = tmax
        if include_limits:
            base["q_min"], base["q_max"] = q_lo, q_hi
        base["friction_v"], base["friction_fc0"], base["friction_fc1"] = fv, fc0, fc1
        # 台架 1J 的 baseline 在 J2..J7 是 None (read_snapshot 的设计) ——
        # check_value 拒 None, 故上表四项必须把 None 列填满 (它们都有 yaml 来源)。
        for k, v in list(base.items()):
            # 只看参数键 (`name` 是助读字段, 不是参数)
            if v is None and k in C.JOINT_BY_KEY:
                raise HyyConfigError(
                    f"{where}.{k} 在设备基线上为空 —— 台架上 J2..J7 无读回值。"
                    f"导入需要整臂基线 (四项映射只能填 q_min/q_max/tau_max/摩擦)")
        joints.append(base)

        # 4) 模型段: body[i+1] = 该关节; body0 (base) 与 body8 (ee) 保持 0
        model_body[i + 1] = [float(d[k]) for k in MODEL_BODY_KEYS]
        model_jm[i] = float(d["jm"])

    glob = dict(baseline["global"])
    if include_gravity:
        grav = list(cfg.gravity)
        _check_range("gravity", grav[0], "global")
        _check_range("gravity", grav[1], "global")
        _check_range("gravity", grav[2], "global")
        glob["gravity"] = grav

    snap = {"joints": joints, "global": glob}
    C.normalize_snapshot(snap)          # 自检: 产物必须过固件同源的校验
    model = {"body": model_body, "jm": model_jm}
    return snap, model, notes


# ---------------------------------------------------------------------------
# 未映射清单 (由代码计算)
# ---------------------------------------------------------------------------
#: 已映射的键路径 (与 to_snapshot 的实现一一对应)。
MAPPED_KEYS = {
    "robot_group.robot[].joint[].dynamics_parameters.fv",
    "robot_group.robot[].joint[].dynamics_parameters.fc0",
    "robot_group.robot[].joint[].dynamics_parameters.fc1",
    "robot_group.robot[].joint[].axis.smin",
    "robot_group.robot[].joint[].axis.smax",
    "robot_group.robot[].joint[].axis.torque_max",
    "robot_group.robot[].gravity.x",
    "robot_group.robot[].gravity.y",
    "robot_group.robot[].gravity.z",
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


def unmapped_report(cfg: HyyConfig) -> List[Tuple[str, str]]:
    """`[(key_path, 原因)]` —— 由 yaml 的实际键集减去已映射集算出, 不手抄。"""
    out = []
    for k in cfg.raw_keys:
        if k in MAPPED_KEYS:
            continue
        out.append((k, UNMAPPED_REASONS.get(k, "未登记 —— 需裁决")))
    return out
