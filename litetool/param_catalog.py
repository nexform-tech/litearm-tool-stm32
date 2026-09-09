"""参数目录镜像表 —— 逐关节 + 全局运行时参数 的范围/单位/写口/读口映射。

数据源头 = 固件 (改时须核对, 不在这里漂移):
  - 钳幅与符号契约:  User/litearm/params/params.c   (params_set_joint_ctrl / params_ff_vec / params_ff_scalar)
                       User/litearm/params/flash_store.c (apply_loaded, 与 params.c 同源钳制)
  - 参数字段布局:      User/litearm/litearm.h   (joint_param_t / dyn_runtime_t, FF_* 位)
  - 写/读口:           User/litearm/hal/usb_cmd.h  (CMD 0x22..0x28; 读回 0x2B/0x2C 按协议稿)
  - 出厂默认(7J):      User/litearm/params/defaults.c

纯 Python 无 Qt —— GUI 与 测试/yaml 导入导出 共用本表, 保证 UI 范围 == 固件钳幅。
GUI 侧先按此表校验提示, 固件仍兜底钳制/拒绝。
"""
from dataclasses import dataclass

NUM_JOINTS = 7          # 调参页列数 (J1..J7; 整臂 7J)

# ---------------------------------------------------------------------------
# ff_mask 位 (litearm.h FF_* —— bit0..bit8, FF_ALL = 0x1FF)
# ---------------------------------------------------------------------------
FF_MASTER = 0x00000001
FF_G = 0x00000002
FF_INERTIA = 0x00000004
FF_CORIOLIS = 0x00000008
FF_FRICTION = 0x00000010
FF_INTEGRAL = 0x00000020
FF_WALL = 0x00000040
FF_QUANT = 0x00000080
FF_VELREF = 0x00000100
FF_ALL_MASK = 0x000001FF

# (位下标0..8, 位名, 中文标签) —— 顺序 = 勾选框 UI 顺序
FF_BITS = [
    (0, "MASTER",   "主开关 (动力学总前馈)"),
    (1, "G",        "重力"),
    (2, "INERTIA",  "惯量"),
    (3, "CORIOLIS", "科氏"),
    (4, "FRICTION", "摩擦 (v1/v2 共用此位, 由 friction_model 选择)"),
    (5, "INTEGRAL", "积分"),
    (6, "WALL",     "限位虚拟墙"),
    (7, "QUANT",    "MIT 量化补偿"),
    (8, "VELREF",   "速度参考"),
]


def bits_to_mask(bits) -> int:
    """bool/0/1 可迭代(长度≤9) -> u32 ff_mask"""
    m = 0
    for i, on in enumerate(bits):
        if on:
            m |= (1 << i)
    return m & FF_ALL_MASK


def mask_to_bits(mask: int) -> list[bool]:
    """ff_mask -> 9 位 bool 列表 (下标 = 位号, 即 FF_BITS 顺序)"""
    m = int(mask) & FF_ALL_MASK
    return [bool(m & (1 << i)) for i in range(len(FF_BITS))]


def ff_bit_label(i: int) -> str:
    if 0 <= i < len(FF_BITS):
        return FF_BITS[i][1]
    return f"BIT{i}"


# ---------------------------------------------------------------------------
# 逐关节参数目录 (表行顺序)。kind:
#   'ctrl'   -> 0x22 写 (kp/kd/tau_max 按关节成组)
#   'limits' -> 0x23 写 (q_min/q_max 按关节成组, 须 q_min<q_max)
#   'vec'    -> 0x26 item 写 (一次写满 7 关节向量), item = 固件向量号
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class JointParam:
    key: str          # 规范键 (yaml 字段名/代码用)
    label: str        # 中文标签 (表行)
    unit: str
    lo: float
    hi: float
    decimals: int
    kind: str
    item: int = 0     # kind=='vec' 时的 0x26 item 号 (1..11)

    def range_text(self) -> str:
        return f"[{_fmt(self.lo)}, {_fmt(self.hi)}] {self.unit}"


def _fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return repr(v)


JOINT_PARAMS: list[JointParam] = [
    # key              label(中文)           unit        lo     hi      dec  kind      item
    JointParam("kp",           "kp 刚度",          "Nm/rad",  0.0,   500.0,  1, "ctrl"),
    JointParam("kd",           "kd 阻尼",          "Nm·s/rad", 0.0,  5.0,    3, "ctrl"),
    JointParam("tau_max",      "tau_max 力矩钳幅", "Nm",      0.1,   120.0,  2, "ctrl"),
    JointParam("q_min",        "q_min 软限位下界", "rad",     -15.0, 15.0,   4, "limits"),
    JointParam("q_max",        "q_max 软限位上界", "rad",     -15.0, 15.0,   4, "limits"),
    JointParam("friction",     "friction 库仑摩擦(v1)", "Nm",  0.0,  50.0,  4, "vec", 1),
    JointParam("ki",           "ki 积分增益",      "Nm/(rad·s)", 0.0, 1000.0, 2, "vec", 2),
    JointParam("i_max",        "i_max 积分钳幅",   "Nm",      0.0,   100.0,  2, "vec", 3),
    JointParam("wall_stiff",   "wall_stiff 限位墙刚度", "Nm/rad", 0.0, 2000.0, 1, "vec", 4),
    JointParam("wall_damp",    "wall_damp 限位墙阻尼", "Nm·s/rad", 0.0, 50.0, 3, "vec", 5),
    JointParam("wall_tau_max", "wall_tau_max 墙力钳幅", "Nm",  0.0,   50.0,  3, "vec", 6),
    JointParam("gravity_scale", "gs 重力缩放",     "",        0.0,   20.0,  3, "vec", 7),
    JointParam("inertia_scale", "is 惯量缩放",     "",        0.0,   20.0,  3, "vec", 8),
    JointParam("friction_v",   "friction_v 粘滞(v2)", "Nm·s/rad", 0.0, 20.0, 4, "vec", 9),
    JointParam("friction_fc0", "friction_fc0 正库仑(v2)", "Nm", 0.0, 50.0, 4, "vec", 10),
    JointParam("friction_fc1", "friction_fc1 负库仑(v2)", "Nm", -50.0, 0.0, 4, "vec", 11),
]
JOINT_BY_KEY = {p.key: p for p in JOINT_PARAMS}
JOINT_KEY_ORDER = [p.key for p in JOINT_PARAMS]

# 0x24 GET_JOINT_PARAM 读回的 5 项 (键 -> 读回列表下标顺序)
JOINT_CTRL_KEYS = ("kp", "kd", "tau_max", "q_min", "q_max")


# ---------------------------------------------------------------------------
# 全局标量目录 (0x28 写 / 0x2C 读)。subs 长度>1 => yaml/UI 里是长度为 3 的数组。
# model=True 的项只允许 {0,1} (friction_model), 不进通用范围校验。
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GlobalParam:
    key: str
    label: str
    unit: str
    lo: float
    hi: float
    decimals: int
    item: int         # 0x28/0x2C item
    subs: tuple = (0,)   # 分量下标; (0,1,2) = 数组
    model: bool = False  # 0/1 二值 (friction_model)

    @property
    def is_array(self) -> bool:
        return len(self.subs) > 1

    def range_text(self) -> str:
        if self.model:
            return "{0=v1 误差方向, 1=v2 SE1 速度方向}"
        return f"[{_fmt(self.lo)}, {_fmt(self.hi)}] {self.unit}".strip()


GLOBAL_PARAMS: list[GlobalParam] = [
    # key              label(中文)          unit     lo       hi       dec  item  subs       model
    GlobalParam("fric_db",       "摩擦死区 fric_db",  "rad",   1e-4,    0.5,    4, 1),
    GlobalParam("wall_margin",   "限位墙提前角",       "rad",   0.0,     0.5,    4, 2),
    GlobalParam("friction_slew", "摩擦变化率限",       "Nm/s",  0.0,     500.0,  2, 3),
    GlobalParam("payload_mass",  "负载质量",           "kg",    0.0,     20.0,   3, 4),
    GlobalParam("payload_com",   "负载质心 com",       "m",     -1.0,    1.0,    3, 5, (0, 1, 2)),
    GlobalParam("gravity",       "重力向量 g",         "m/s²",  -50.0,   50.0,   3, 6, (0, 1, 2)),
    GlobalParam("friction_model", "摩擦模型",          "",      0.0,     1.0,    0, 7, (0,), True),
    GlobalParam("fric_v2_eps",   "v2 tanh 平滑带宽",   "rad/s", 1e-3,    0.5,    4, 8),
]
GLOBAL_BY_KEY = {p.key: p for p in GLOBAL_PARAMS}
GLOBAL_KEY_ORDER = [p.key for p in GLOBAL_PARAMS]

# ff_mask: 0x27 写 / 0x2C item 9 读 (u32, 经 f32 读回; 值 ≤0x1FF 时两种编码可无损还原)
FF_MASK_SCALAR_ITEM = 9

# 逐关节读回向量号 (0x2B GET_FF_VEC item): 键 -> item (item 1..11 与写侧同号)
JOINT_VEC_ITEM_BY_KEY = {p.key: p.item for p in JOINT_PARAMS if p.kind == "vec"}
# 读回关节数 (写侧恒 7 宽; 读侧同协议 7 宽)
FF_VEC_LEN = 7


# ---------------------------------------------------------------------------
# 数值校验/钳制
# ---------------------------------------------------------------------------
def check_value(lo: float, hi: float, v, model: bool = False, label: str = "值") -> str | None:
    """返回错误信息 (None=合法)。model=True 时只允许 0/1。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return f"{label} 须为数值"
    f = float(v)
    if f != f:                                   # NaN
        return f"{label} 为 NaN"
    if model:
        return None if f in (0.0, 1.0) else f"{label} 摩擦模型仅允许 0 或 1"
    if not (lo <= f <= hi):
        return f"{label}={_fmt(f)} 超出范围 [{_fmt(lo)}, {_fmt(hi)}]"
    return None


def clamp_value(lo: float, hi: float, v: float) -> float:
    return min(max(float(v), lo), hi)


def check_joint(jp: JointParam, v, joint_idx: int = 0) -> str | None:
    """校验一个逐关节单元格值。q_min/q_max 的 q_min<q_max 关系在关节级另行校验。"""
    label = f"J{joint_idx + 1}.{jp.key}"
    err = check_value(jp.lo, jp.hi, v, label=label)
    if err:
        return err
    if jp.kind == "vec" and jp.item in (9, 10, 11):
        # 摩擦 v2 符号契约 (params.c): fv>=0/fc0>=0/fc1<=0 —— 已并入钳幅, 此处占位注释
        pass
    return None


def check_joint_limits_relation(joint: dict) -> str | None:
    """给定一个关节的参数 dict, 校验 q_min < q_max。"""
    qmin, qmax = joint.get("q_min"), joint.get("q_max")
    if qmin is not None and qmax is not None and float(qmin) >= float(qmax):
        return f"关节限位非法: q_min({qmin}) ≥ q_max({qmax})"
    return None


# ---------------------------------------------------------------------------
# yaml/json 快照 <-> 规范化结构; diff
# ---------------------------------------------------------------------------
# 规范化快照形如:
#   {"joints": [ {key: float,...} ×7 ], "global": { <单值键>: float,
#                 "payload_com":[..], "gravity":[..], "friction_model":0/1,
#                 "ff_mask": int }}
SCALAR_KEYS = {"fric_db", "wall_margin", "friction_slew", "payload_mass",
               "fric_v2_eps"}
ARRAY_KEYS = {"payload_com", "gravity"}


def joint_default(j) -> dict:
    """按 JointParam 目录把 yaml 单关节 dict 规范化 (丢掉未知键, 补齐缺失为 None)。"""
    out = {}
    for p in JOINT_PARAMS:
        if p.key in j:
            out[p.key] = j[p.key]
        else:
            out[p.key] = None
    return out


def normalize_snapshot(raw) -> dict:
    """把 yaml/json 解析出的 dict 规范化; 结构/类型错误抛 ValueError(中文)。

    只做结构 + 数值类型 + 数值范围 校验; 不校验 q_min<q_max (在关节级 list)。
    """
    if not isinstance(raw, dict):
        raise ValueError("参数文件顶层须为对象 (joints + global)")
    joints_raw = raw.get("joints")
    if not isinstance(joints_raw, (list, tuple)) or len(joints_raw) != NUM_JOINTS:
        raise ValueError(f"joints 须为长度 {NUM_JOINTS} 的数组 (J1..J7, 顺序即关节号)")
    joints = []
    for i, jr in enumerate(joints_raw):
        if not isinstance(jr, dict):
            raise ValueError(f"joints[{i}] 须为对象")
        name = jr.get("name")
        if name is not None and str(name) != f"J{i + 1}":
            raise ValueError(f"joints[{i}].name 应为 J{i + 1}, 实际 {name!r}")
        jd = joint_default(jr)
        for p in JOINT_PARAMS:
            v = jd[p.key]
            err = None
            if v is None:
                err = f"J{i + 1} 缺参数 {p.key}"
            else:
                err = check_value(p.lo, p.hi, v, label=f"J{i + 1}.{p.key}")
            if err:
                raise ValueError(err)
        rel = check_joint_limits_relation(jd)
        if rel:
            raise ValueError(f"J{i + 1}: {rel}")
        joints.append(jd)

    gr = raw.get("global")
    if not isinstance(gr, dict):
        raise ValueError("global 须为对象")
    glob = {}
    for key in SCALAR_KEYS:
        gp = GLOBAL_BY_KEY[key]
        if key not in gr:
            raise ValueError(f"global 缺 {key}")
        err = check_value(gp.lo, gp.hi, gr[key], label=f"global.{key}")
        if err:
            raise ValueError(err)
        glob[key] = float(gr[key])
    for key in ARRAY_KEYS:
        gp = GLOBAL_BY_KEY[key]
        arr = gr.get(key)
        if not isinstance(arr, (list, tuple)) or len(arr) != len(gp.subs):
            raise ValueError(f"global.{key} 须为长度 {len(gp.subs)} 的数组")
        vals = []
        for k, v in enumerate(arr):
            err = check_value(gp.lo, gp.hi, v, label=f"global.{key}[{k}]")
            if err:
                raise ValueError(err)
            vals.append(float(v))
        glob[key] = vals
    if "friction_model" not in gr:
        raise ValueError("global 缺 friction_model")
    err = check_value(0, 1, gr["friction_model"], model=True, label="global.friction_model")
    if err:
        raise ValueError(err)
    glob["friction_model"] = int(gr["friction_model"])
    if "ff_mask" not in gr:
        raise ValueError("global 缺 ff_mask")
    fm = gr["ff_mask"]
    if isinstance(fm, bool) or not isinstance(fm, (int, float)):
        raise ValueError("global.ff_mask 须为整数")
    fmi = int(fm)
    if fmi != float(fm) or not (0 <= fmi <= FF_ALL_MASK):
        raise ValueError(f"global.ff_mask 须为 [0, {FF_ALL_MASK}] 的整数, 实际 {fm}")
    glob["ff_mask"] = fmi
    return {"joints": joints, "global": glob}


def snapshot_flat(snap: dict) -> dict:
    """规范化快照 -> 打平: {"J1.kp": float, ..., "global.ff_mask": int}
    顺序即 diff/预览 的行顺序: 逐关节目录序 → 全局目录序。
    """
    flat = {}
    for i, jd in enumerate(snap["joints"]):
        for p in JOINT_PARAMS:
            v = jd[p.key]
            if v is not None:
                flat[f"J{i + 1}.{p.key}"] = float(v)
    g = snap["global"]
    for p in GLOBAL_PARAMS:
        v = g[p.key]
        if p.is_array:
            for k in range(len(p.subs)):
                flat[f"global.{p.key}[{k}]"] = float(v[k])
        else:
            flat[f"global.{p.key}"] = float(v)
    flat["global.ff_mask"] = int(g["ff_mask"])
    return flat


def leaf_decimals(label: str) -> int:
    """按打平标签取显示小数位 (供 diff 预览/状态行)。"""
    if label.startswith("J"):
        key = label.split(".", 1)[1]
        return JOINT_BY_KEY[key].decimals
    if label.startswith("global."):
        rest = label[len("global."):]
        if rest == "ff_mask":
            return 0
        if "[" in rest:
            key = rest.split("[", 1)[0]
        else:
            key = rest
        return GLOBAL_BY_KEY[key].decimals
    return 4


def diff_snapshots(old: dict | None, new: dict) -> list:
    """diff 两规范化快照 -> [(label, old_disp, new_disp)] (仅列出不同的叶)。
    old 为 None 时视作全量新增 (仅用于"无基线导入"提示)。
    """
    if old is None:
        return [(lab, None, v) for lab, v in snapshot_flat(new).items()]
    fo, fn = snapshot_flat(old), snapshot_flat(new)
    out = []
    for lab in fo:
        ov, nv = fo[lab], fn.get(lab)
        if ov != nv:
            out.append((lab, ov, nv))
    for lab, nv in fn.items():
        if lab not in fo:
            out.append((lab, None, nv))
    return out


def fmt_value(label: str, v) -> str:
    """数值 -> 按标签小数位的显示串 (None -> '—')"""
    if v is None:
        return "—"
    if label.endswith("ff_mask"):
        return f"{int(v)} (0x{int(v):X})"
    try:
        return f"{float(v):.{leaf_decimals(label)}f}"
    except (TypeError, ValueError):
        return str(v)
