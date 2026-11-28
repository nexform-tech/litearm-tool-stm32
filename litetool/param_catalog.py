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
from dataclasses import dataclass, replace

from litetool import i18n
from litetool import param_catalog_en as EN

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


#: 出厂 gs 基线 (固件 defaults.c, 2026-09-12 换辨识模型后 = 全 1.0)。
#: 单一定义, 指南/文案共用; `tests/test_tuning_guide.py` 与固件真源逐项比对。
GS_BASELINE = "[1, 1, 1, 1, 1, 1, 1]"

# [调参指南] 每个 ff_mask 位的详解 (与 FF_BITS 同序, 悬停/指南逐项用)
FF_BIT_DETAIL = [
    "主开关: 动力学前馈总开关。须置位 G/inertia 子位才生效。想整组关掉全部前馈(只剩 PD 电机内反馈)就清这一位; 其余位不动时把它关掉是回退到纯 PD 的最快路径。",
    "重力补偿: 开启 gs_j·G_j(q) 重力前馈。到位下垂/保持软先确认此位开 + gs 是否足够。关闭=完全不做重力补偿(持位会软)。",
    "惯量补偿: 开启 is_j·(M·q̈(+科氏)) 惯量前馈, 用于大惯量轴启停/动态跟不准。动态抖动时先降 kp 再看此位。",
    "科氏/离心: 仅在惯量组内决定是否含 C(q,q̇)·q̇ 科氏项。高速大臂段跟偏时可开; 低速几乎无感。与 INERTIA 位配合。",
    "摩擦前馈: 开启摩擦项 (v1/v2 共用本位的开关, 模型由 friction_model 选)。低速一顿一顿/粘滑先确认此位开再调 fv/fc0/fc1。",
    "积分项: 开启 ki·∫e 消除稳态残差。到位有静差但此位关了, 加 ki 无效。",
    "限位虚拟墙: 默认关。开启后在软限位附近加虚拟墙 (本固件无手动柔顺, movej 合法目标已被软限位挡)。",
    "MIT 量化补偿: 对电机 MIT 16bit 位置/12bit 力矩量化误差做前馈补偿。低速微动/贴点精度在意时开。",
    "速度参考力矩: MIT 模式把 kd·dq_d 作为速度参考前馈叠加。默认开; 关掉会改变低速跟踪手感。",
]
FF_DETAIL_BY_NAME = {name: FF_BIT_DETAIL[i] for i, (_b, name, _l) in enumerate(FF_BITS)}


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


def ff_label_text(i: int) -> str:
    """界面显示用的位含义（英文表缺失时回落中文）。"""
    if i18n.language() == "en" and 0 <= i < len(EN.FF_LABELS):
        return EN.FF_LABELS[i] or FF_BITS[i][2]
    return FF_BITS[i][2] if 0 <= i < len(FF_BITS) else ""


def ff_detail_text(i: int) -> str:
    if i18n.language() == "en" and 0 <= i < len(EN.FF_DETAILS):
        return EN.FF_DETAILS[i] or FF_BIT_DETAIL[i]
    return FF_BIT_DETAIL[i] if 0 <= i < len(FF_BIT_DETAIL) else ""


def model_body_label_text(i: int) -> str:
    if i18n.language() == "en" and i < len(EN.MODEL_BODY_LABELS):
        return EN.MODEL_BODY_LABELS[i] or MODEL_BODY_LABELS[i]
    return MODEL_BODY_LABELS[i] if i < len(MODEL_BODY_LABELS) else ""


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
    item: int = 0     # kind=='vec' 时的 0x26 item 号 (1..11, 15, 16)
    safety: bool = False  # [2026-09-14] 安全类字段: 变化必须独立高亮 + 强制说明, 不适用比率阈值
    role: str = ""    # [调参指南] 作用一句话 (tooltip 用)
    hint: str = ""    # [调参指南] 改参提示 (tooltip 用)
    detail: str = ""  # [调参指南] 详解 2-4 句 (tooltip 与指南页同源)

    def range_text(self) -> str:
        return f"[{_fmt(self.lo)}, {_fmt(self.hi)}] {self.unit}"

    def label_text(self) -> str:
        return self._en("LABELS", self.label)

    def role_text(self) -> str:
        return self._en_meta(0, self.role)

    def hint_text(self) -> str:
        return self._en_meta(1, self.hint)

    def detail_text(self) -> str:
        return self._en_meta(2, self.detail)

    def _en(self, table: str, fallback: str) -> str:
        if i18n.language() == "en":
            return getattr(EN, table, {}).get(self.key) or fallback
        return fallback

    def _en_meta(self, index: int, fallback: str) -> str:
        if i18n.language() == "en":
            hit = EN.META.get(self.key)
            if hit and index < len(hit) and hit[index]:
                return hit[index]
        return fallback


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
    safety: bool = False  # [2026-09-14] 安全类字段 (见 JointParam.safety)
    role: str = ""
    hint: str = ""
    detail: str = ""

    @property
    def is_array(self) -> bool:
        return len(self.subs) > 1

    def range_text(self) -> str:
        if self.model:
            return i18n.tr("{0=v1 误差方向, 1=v2 SE1 速度方向, 2=drag 版(拖动用)}")
        return f"[{_fmt(self.lo)}, {_fmt(self.hi)}] {self.unit}".strip()

    def label_text(self) -> str:
        return self._en("LABELS", self.label)

    def role_text(self) -> str:
        return self._en_meta(0, self.role)

    def hint_text(self) -> str:
        return self._en_meta(1, self.hint)

    def detail_text(self) -> str:
        return self._en_meta(2, self.detail)

    def _en(self, table: str, fallback: str) -> str:
        if i18n.language() == "en":
            return getattr(EN, table, {}).get(self.key) or fallback
        return fallback

    def _en_meta(self, index: int, fallback: str) -> str:
        if i18n.language() == "en":
            hit = EN.META.get(self.key)
            if hit and index < len(hit) and hit[index]:
                return hit[index]
        return fallback


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
    # ---- [段③/段②] ----
    # [2026-11-09] 固件 1.11.0 起 0x26 item 12/13/14 (zg_kp/zg_kd/zg_damping)
    #   **确定删除**, item 15 (kd_extra) 之后编号留空不复用 —— 固件对 12..14 回
    #   ERR{0x26,0x02}。目录里不留已删项: 留着会让「导入」把老 yaml 的键原样下发,
    #   一整串 0x02 把导入判成部分失败。是否支持仍由**板子探测**决定
    #   (params_io.read_snapshot), 老固件真有的项会由 supported 集合暴露。
    JointParam("kd_extra",     "kd_extra τ域软件阻尼", "Nm·s/rad", 0.0, 50.0,  3, "vec", 15),
    # [1.12.0] 逐关节拖动摩擦补偿比例 (厂商 MITDragDemo 的 coeff[i]); 与物理摩擦参数
    #   fv/fc0/fc1 分工: 后者是摩擦模型, 本项是"补多少"的比例。
    JointParam("drag_gain",    "drag_gain 拖动补偿比例", "", 0.0, 5.0, 3, "vec", 16),
]

# [调参指南] 逐关节 tooltip 元数据: key -> (role, hint, detail)。
# role/hint = 短 (悬停标题/改法); detail = 详解 2-4 句 (tooltip 与指南页逐项同源)。
_JP_META = {
    "kp": ("MIT 位置刚度 (PD 的 P 项)",
           "跟手/抗下垂旋钮: 大→更紧、下垂小; 过大→易振/啸叫。上限 500, "
           "在振荡拐点前逐轴小步加 (见症状表'到位下垂/保持软')",
           "含义: MIT 控制的位置刚度 kp, PD_j=kp·(q_d−q)+kd·(q̇_d−q̇) 在电机内执行。"
           "单位 Nm/rad, 范围 [0,500]。典型值按电机: 6248 轴 360~420, 4340 轴 220, "
           "4310 小臂 50。改大→跟手更紧、抗下垂/残差更小; 改太大→该轴抖动/啸叫/振荡"
           "(振荡拐点前停)。常见误用: 全轴一起大改(应先从承重大轴入手小步试)或把饱和误当"
           "刚度不足。" ),
    "kd": ("MIT 阻尼 (PD 的 D 项)",
           "抑制振荡/回冲: 抖动啸叫、到位回冲→kd↑ (≤5)。过大偏僵硬且放大高频噪声。",
           "含义: MIT 控制阻尼 kd, 抑制速度差 (q̇_d−q̇)。单位 Nm·s/rad, 范围 [0,5]。"
           "典型值 2.5(小臂)~5(大臂)。抖动/啸叫/到位回冲→先加 kd (≤5), 配合降 kp。"
           "改太大→轴显僵硬、跟不上且放大测量噪声。常见误用: 用 kd 硬压 kp 造成的振"
           "(应同时降 kp)。"),
    "tau_max": ("单轴力矩钳幅 (安全天花板)",
                "该轴输出力矩 ±上限。常贴 ±tau_max=饱和: 降速度包络/减负载, 别加 kp "
                "(见症状表 'τ 恒贴 ±tau_max')",
                "含义: 该轴命令力矩的绝对钳幅, 公式最终 τ=clamp(τ,±tau_max)。"
                "单位 Nm, 范围 [0.1,120], 电机型号有硬件上限 (6248→120, 4340→28, 4310→10)。"
                "若 τ 常贴 ±tau_max 说明在饱和: 先降速度包络或减负载, 加 kp 只会更冲。"
                "常见误用: 为压饱和而调大 tau_max 超过电机硬件扭矩。"),
    "q_min": ("软限位下界 (rad)",
              "角度下限, 越界触发 POS_VIOL/FAULT。改前请确认当前 q 仍在新限位内。",
              "含义: 该关节允许的最小角度 (软限位, rad)。范围 [-15,15], 须 q_min<q_max。"
              "越界运动会触发 POS_VIOL/FAULT。出厂值 = URDF 硬限位内缩约 1°。"
              "改前 GUI 会校验当前 q 是否在新限位内; 改太大可能让臂够不到原工作点。"),
    "q_max": ("软限位上界 (rad)",
              "角度上限, 越界触发 POS_VIOL/FAULT。改前请确认当前 q 仍在新限位内。",
              "含义: 该关节允许的最大角度 (软限位, rad)。范围 [-15,15], 须 q_min<q_max。"
              "越界运动触发 POS_VIOL/FAULT。注意 J4 上限接近 0 (非对称限位)。"
              "常见误用: 放宽限位以规避越限告警——真正该查的是运动目标/速度包络。"),
    "friction": ("库仑摩擦前馈 v1 (误差方向)",
                 "仅 friction_model=0 生效: 摩擦·tanh(e/fric_db)。v2(出厂)开着时应保持 0。",
                 "含义: v1 摩擦前馈幅值, 沿位置误差方向输出 摩擦·tanh(e/fric_db) (friction_model=0 时)。"
                 "单位 Nm, 范围 [0,50]。出厂为 0 (v2 摩擦已接管)。若手动切回 v1, 值大约等于该轴"
                 "启动所需力矩并叠加余量。常见误用: v2 默认开启时仍去改 friction 列(不生效)。"),
    "ki": ("积分增益 (消静态残差)",
           "稳态残差/到位下垂→ki↑; 过大易振荡/超调。输出受 i_max 钳, 运动起点固件自动清零。",
           "含义: 位置误差积分项增益 τ_int=ki·∫(q_d−q)dt。单位 Nm/(rad·s), 范围 [0,1000]。"
           "用于消除稳态残差/静差 (重力被 gs 补偿后剩下的)。运动起点固件自动清零积分, "
           "避免 windup 冲击; 输出被 i_max 钳制。典型值 10~40 (小臂 10, 大臂 40)。"
           "过大→振荡/超调。"),
    "i_max": ("积分钳幅 (anti-windup)",
              "积分输出上限: 大→抗下垂更强但启停更冲。防 windup 的刹车。",
              "含义: 积分项输出钳幅 ±i_max (anti-windup)。单位 Nm, 范围 [0,100]。"
              "典型值 3~20 (小臂 3~4, 大臂 20)。值越大抗下垂越强但启停冲得越明显。"
              "常见误用: ki/i_max 双双拉满试图「永不动」, 极易起振荡。"),
    "wall_stiff": ("限位虚拟墙刚度 (默认 FF_WALL 关)",
                   "接近限位时弹簧-阻尼推回。本固件 movej 合法目标一般不触发。",
                   "含义: 软限位处虚拟墙的弹簧刚度 (墙力=k·δ+墙阻尼项)。单位 Nm/rad, 范围 [0,2000]。"
                   "FF_WALL 位默认关; 开启后仅在 q 逼近限位时才出力。本固件无手动柔顺模式, "
                   "movej 合法目标已被软限位挡住, 墙主要兜底。"),
    "wall_damp": ("限位墙阻尼", "墙区阻尼 (只阻碍出墙方向)。",
                  "含义: 虚拟墙的速度阻尼, 只阻碍向墙外运动方向 (出墙钳 0), 防撞限弹回。"
                  "单位 Nm·s/rad, 范围 [0,50]。"),
    "wall_tau_max": ("限位墙力钳幅", "虚拟墙输出力矩上限 (±tau_max)。",
                     "含义: 墙力的力矩钳幅 (输出前 sign·clamp)。单位 Nm, 范围 [0,50]。"
                     "设太小墙形同虚设, 设过大接近 tau_max 也受其兜底。"),
    "gravity_scale": ("逐关节重力补偿缩放 gs",
                      "重力项输出旋钮: 到位下垂/保持软→该轴 gs↑ (重力偏小)。"
                      "出厂基线 " + GS_BASELINE + "。",
                      "含义: 重力前馈 gs_j·G_j(q) 的逐关节缩放 (输出端乘法旋钮)。无量纲 [0,20]。"
                      "出厂基线 " + GS_BASELINE + " (2026-09-12 随模型换源重定: 辨识惯量模型下必须归 1.0, "
                      "旧的 CAD 口径补偿值已废弃)。"
                      "到位下垂/保持软→相关轴 gs↑; 抬过头/往上顶→gs↓。常见误用: 全局改 g"
                      "ravity 向量代替逐关节 gs (应先用 gs 旋钮), 或只加大臂 gs 不管小臂。"),
    "inertia_scale": ("逐关节惯量缩放 is",
                      "惯量/科氏项旋钮: 大惯量轴动态跟不准→is↑。过大易振。",
                      "含义: 惯量/科氏前馈 is_j·[M·q̈+C·q̇]_j 的逐关节缩放。无量纲 [0,20], 出厂全 1。"
                      "启停/换向跟不上、画方拐角被拽歪→大惯量轴 is↑。过大会前馈过冲、起振。"
                      "常见误用: 拿 is 当「更大力」去压大 kp 才出现的饱和 (应先看 tau_max 是否贴顶)。"),
    "friction_v": ("v2 粘滞摩擦 fv (速度方向)",
                   "τ= fv·q̇_d。低速一顿一顿(粘滑)→fv↑; 过大会过零顿挫。",
                   "含义: v2 摩擦的粘滞项 fv·q̇_d (q̇_d=期望速度, 非测量)。单位 Nm·s/rad, 范围 [0,20]。"
                   "出厂为 SE1 辨识值 (J1~J7 ≈ 0.75/0.64/0.20/0.26/0.03/0.08/0.04)。"
                   "低速粘滑/一顿一顿→fv↑; 过大会过零时反向顿挫。"),
    "friction_fc0": ("v2 正库仑 fc0 (≥0)",
                     "速度方向正半支; 低速爬行/静止摩擦补偿。",
                     "含义: v2 库仑正半支 (速度>0 侧) 幅值, 要求 ≥0。单位 Nm, 范围 [0,50]。"
                     "出厂 SE1 值约 J1~J7=1.24/2.28/0.39/0.59/0.09/0.12/0.08。"
                     "低速爬行补偿不足→fc0↑; 太大→停止/起步有顿挫。"),
    "friction_fc1": ("v2 负库仑 fc1 (≤0, 存负)",
                     "速度方向负半支; 与 fc0 合出非对称静摩擦 (符号契约 ≤0)。",
                     "含义: v2 库仑负半支 (速度<0 侧) 幅值, 存为负值 (≤0, 符号契约)。"
                     "单位 Nm, 范围 [-50,0]。与 fc0 合成非对称静摩擦 (SE1 辨识负向常略大)。"
                     "常见误用: 填成正数会被固件整组拒绝/回钳 0。"),
    # ---- [段③/段②] ----
    "kd_extra": ("τ 域软件微分阻尼 (治 movej 起步振铃)",
                 "运动模式专用: τ += kd_extra·(q̇_d−q̇)。出厂 [6,6,6,6,0,0,0] —— 腕部必须 0。",
                 "含义: 加在【力矩】字段上的额外微分阻尼, 用于治 movej 起步振铃。单位 Nm·s/rad, "
                 "范围 [0,50], 出厂 [6,6,6,6,0,0,0]。为什么放 τ 而不是 kd: MIT 的 kd 走 12-bit q̇ 通道"
                 "且硬上限 5, 而 τ 虽同为 12-bit 但量程是力矩, 分辨率高得多。⚠ **腕部(J5/J6/J7)必须保持 0**: "
                 "J7 惯量极小(≈0.0002 kg·m²), kd_extra/J 远快于控制周期, 延迟阻尼会反向激发"
                 "(上游实测全轴加 3 时 J7 冲到 −3.33 rad/s 被速度包络中止)。"),
    # ---- [1.12.0] 逐关节拖动摩擦补偿比例 ----
    "drag_gain": ("拖动摩擦补偿比例 (逐关节)",
                  "零重力/拖动专用: 每个关节单独补多少摩擦。出厂全 0.6 (厂商 coeff 同值); "
                  "调大=补得更狠, 调小=更涩。只影响拖动路径。",
                  "含义: 拖动摩擦补偿 τ_drag = drag_gain_j·(fv_j·q̇ + 库仑_j) 的逐关节比例。"
                  "单位无量纲, 范围 [0,5], 出厂全 0.6 (与厂商 MITDragDemo 的 coeff[ROBOT_MAX_DOF] 同值)。"
                  "与 friction_v/fc0/fc1 分工: 后者是辨识出来的物理摩擦参数, 本项只是补偿比例。"
                  "⚠ 本固件(1.12.0)零重力律固定 kd=0.1、drag_db=0=硬 sign, 不再有 kd 下限/二次稳定项; "
                  "gain 调得明显大于 1 会过补偿, 可能出现单向漂移。"
                  "只在【零重力】与 friction_model=2 路径生效, 常规模运动控制不吃本项。"),
}
#: [2026-09-14] 安全类字段 —— 它们**同时是控制包络**: `tau_max` 是力矩幅值的唯一兜底
#: (`control_loop.c` 的 clampf), `q_min/q_max` 是软限位。yaml 的 `torque_max`
#: (20,20,28,28,10,10,10) 与固件默认 (78,78,21,21,10,10,10) 相差极大 (J1/J2 砍到 1/4),
#: 而 `[0.1,120]` 的范围校验**不会响**、比率型阈值也覆盖不到 (|20-78|/78 ≈ 0.74)
#: ⇒ 只能靠显式标记让 UI 独立高亮。
SAFETY_JOINT_KEYS = frozenset({"tau_max", "q_min", "q_max"})
SAFETY_GLOBAL_KEYS = frozenset({"gravity"})

for _i, _p in enumerate(JOINT_PARAMS):
    _r, _h, _d = _JP_META[_p.key]
    JOINT_PARAMS[_i] = replace(_p, role=_r, hint=_h, detail=_d,
                               safety=(_p.key in SAFETY_JOINT_KEYS))

JOINT_BY_KEY = {p.key: p for p in JOINT_PARAMS}
JOINT_KEY_ORDER = [p.key for p in JOINT_PARAMS]

# 0x24 GET_JOINT_PARAM 读回的 5 项 (键 -> 读回列表下标顺序)
JOINT_CTRL_KEYS = ("kp", "kd", "tau_max", "q_min", "q_max")


# ---------------------------------------------------------------------------
# 全局标量目录 (0x28 写 / 0x2C 读)。subs 长度>1 => yaml/UI 里是长度为 3 的数组。
# model=True 的项只允许 {0,1} (friction_model), 不进通用范围校验。
# ---------------------------------------------------------------------------
GLOBAL_PARAMS: list[GlobalParam] = [
    # key              label(中文)          unit     lo       hi       dec  item  subs       model
    GlobalParam("fric_db",       "摩擦死区 fric_db",  "rad",   1e-4,    0.5,    4, 1),
    GlobalParam("wall_margin",   "限位墙提前角",       "rad",   0.0,     0.5,    4, 2),
    GlobalParam("friction_slew", "摩擦变化率限",       "Nm/s",  0.0,     500.0,  2, 3),
    GlobalParam("payload_mass",  "负载质量",           "kg",    0.0,     20.0,   3, 4),
    GlobalParam("payload_com",   "负载质心 com",       "m",     -1.0,    1.0,    3, 5, (0, 1, 2)),
    GlobalParam("gravity",       "重力向量 g",         "m/s²",  -50.0,   50.0,   3, 6, (0, 1, 2)),
    GlobalParam("friction_model", "摩擦模型",          "",      0.0,     2.0,    0, 7, (0,), True),
    GlobalParam("fric_v2_eps",   "v2 tanh 平滑带宽",   "rad/s", 1e-3,    0.5,    4, 8),
    # ---- [段② 零重力] item 从 10 起 (9 = ff_mask 读回保留) ----
    # [1.12.0] item 10 全局 drag_gain **已删除**, 改为 0x26 item16 逐关节 (见 JOINT_PARAMS)。
    # drag_db 允许 0: 0 = 硬 sign (零速满幅库仑); 出厂 0.0 (厂商 MITDragDemo 同款)
    GlobalParam("drag_db",        "拖动库仑死区带宽",    "rad/s",   0.0,    0.5,   4, 11),
    # [2026-11-09] 12..16 (drag_kd_margin/zg_vel_thr/zg_engage_*) 固件 1.11.0
    #   已删除, 编号留空不复用 (同见 JOINT_PARAMS 注)。
    GlobalParam("wall_fw_kd",     "墙区叠加固件 kd",     "Nm·s/rad", 0.0,  5.0,   3, 17),
    # ---- [段③ §6.2] ----
    GlobalParam("hold_kp_gain",   "到位增刚倍数",        "",        0.0,    5.0,   3, 18),
]

# [调参指南] 全局 tooltip 元数据: key -> (role, hint, detail)
_GP_META = {
    "fric_db": ("v1 摩擦 tanh 死区带宽",
                "v1: 摩擦·tanh(e/fric_db) 的平滑带宽, 越小摩擦切换越陡。v2(出厂)不用但保留默认。",
                "含义: v1 摩擦 tanh 死区带宽 ε (误差方向)。单位 rad, 范围 [1e-4,0.5], 出厂 0.02。"
                "越小摩擦在误差 0 附近越陡(接近硬库仑), 越大越平滑。只在 friction_model=0 时参与。"
                "常见误用: v2 开着时调它无感; v1 下调太大会让到位 0 附近力矩软。"),
    "wall_margin": ("限位墙提前角", "距软限位多远开始进入虚拟墙区。",
                    "含义: 虚拟墙的提前角 (距软限位多远开始出力)。单位 rad, 范围 [0,0.5], 出厂 0.0524。"
                    "FF_WALL 关时不参与。"),
    "friction_slew": ("摩擦/墙输出变化率限 Nm/s",
                      "摩擦与墙力矩的 slew 上限, 消启停阶跃异响; 0=输出冻结于历史。",
                      "含义: 摩擦与虚拟墙输出的变化率上限 (一阶 slew)。单位 Nm/s, 范围 [0,500], 出厂 60。"
                      "用于消启停时摩擦力矩的阶跃异响。0=输出冻结于历史值。"
                      "常见误用: 调太小会感觉摩擦补偿跟不上(慢), 调太大失去平滑作用。"),
    "payload_mass": ("末端负载质量 (kg)",
                     "抓/挂重物下垂或跟不准→填负载质量, 别只猛加 kp。与 payload_com 配合。",
                     "含义: 末端挂载质量, 并入动力学重力项 (改质量等价于动态重算)。单位 kg, 范围 [0,20]。"
                     "抓/挂重物后下垂或跟不准→先填真实负载 (含夹爪), 而不是只加 kp。"
                     "与 payload_com 一起给才准确; 填错方向可能反而让补偿过量。"),
    "payload_com": ("负载质心偏移 (ee 系, m)", "负载质心相对末端的偏移, 供重力项正确折算。",
                    "含义: 负载质心在末端坐标系的偏移 (x,y,z)。单位 m, 范围 [-1,1]×3, 出厂 0。"
                    "负载挂得偏→补偿会算歪, 造成某些姿态下垂/上顶。量好偏移填入。"
                    "典型误用: 只有质量没有偏置(重物悬臂时补偿仍不准)。"),
    "gravity": ("base 系重力向量 (m/s²)",
                "默认 (0,0,-9.81)。侧装/倒装/桌面斜置改这里 (或先用 gs 逐关节旋钮)。",
                "含义: 基座系的重力向量, 方向+大小。单位 m/s², 每分量 [-50,50], 出厂 (0,0,-9.81)。"
                "侧装/倒装/斜置机座→改这里让模型重力方向贴合实际。小偏差优先用逐关节 gs 旋钮微调。"
                "常见误用: 拿它当 gs 用(它是全局几何, gs 才是逐轴残差旋钮)。"),
    "friction_model": ("摩擦模型开关 0=v1 / 1=v2",
                       "出厂=1 (v2 速度方向, SE1 三元组); 0 回 v1 (误差方向 tanh, 用 friction/fric_db)。",
                       "含义: 选择摩擦前馈实现。1=v2 速度方向 (fv/fc0/fc1 三元组, 出厂默认), "
                       "0=v1 误差方向 (friction + fric_db)。v1/v2 共用 FF_FRICTION 位。"
                       "切 0 前把 friction/fric_db 调到接近该轴启动力矩再试; 切回 1 恢复三元组。"),
    "fric_v2_eps": ("v2 tanh 平滑带宽 (rad/s)",
                    "v2: tanh(q̇_d/ε) 的 ε。越小滑移切换越陡(硬), 太大则摩擦被抹平。",
                    "含义: v2 摩擦 tanh 平滑带宽 ε (tanh(q̇_d/ε))。单位 rad/s, 范围 [1e-3,0.5], 出厂 0.02。"
                    "ε 越小速度方向切换越陡(更贴理想库仑, 但过零更冲); 越大摩擦被抹平(补偿不足)。"
                    "通常保持出厂, 需要「硬一点」才小步减小。"),
    # ---- [段② 零重力] ----
    # [1.12.0] drag_gain 已移到 JOINT_PARAMS/_JP_META (0x26 item16, 逐关节)。
    "drag_db": ("拖动库仑死区带宽",
                "零重力专用库仑的死区带宽。出厂 0.0 = 硬 sign (与厂商 MITDragDemo 同款); "
                "真机抖振时再退 0.02/0.05 走 tanh。",
                "含义: 拖动摩擦里 u=(q̇/drag_db)² 的死区带宽。单位 rad/s, 范围 [0,0.5], 出厂 0.0。"
                "0.0 = 硬 sign 库仑: 只要 q̇≠0 就给满幅库仑推力, 零速处没有死区 —— "
                "真机出现零速抖振时再改 0.02/0.05, 走 tanh (零速一阶导为 0)。"
                "与 fric_v2_eps 不同: 这个只在【拖动】用。"),
    "wall_fw_kd": ("墙区叠加固件速度阻尼",
                   "进入限位墙区时给电机 kd 额外叠加的量(封顶 5)。治手-工具-墙耦合振荡。",
                   "含义: 关节进入限位墙区时, 给 MIT kd 叠加的量 (叠加后封顶 5)。单位 Nm·s/rad, "
                   "范围 [0,5], 出厂 0.8。理由: 固件的 kd 在电机 kHz 电流环执行、无控制环延迟, "
                   "是治「手-工具-墙」耦合振荡的干净耗散通道(上位机侧阻尼相位滞后不够)。"
                   "⚠ 仅在【零重力模式】的墙区生效 —— movej 路径的墙默认关。"),
    # ---- [段③ §6.2] ----
    "hold_kp_gain": ("到位增刚倍数",
                     "movej 到位后 0.2s 内把 kp 渐变到 kp×本值(封顶 500), 同时 τ 渐变到 G(q_hold)。出厂 2.0。",
                     "含义: 运动到位后持位刚度的放大倍数。单位无量纲, 范围 [0,5], 出厂 2.0。"
                     "到位后固件用 smoothstep 在 0.2s 内把 kp 渐变到 mit_kp×本值(封顶 500), "
                     "同时令 τ=G(q_hold)、冻结 q_ref —— 即「到位增刚」，由 kp 而非积分承担持位刚度。"
                     "⚠ 命名: 本项与固件里另一个同名参数(hold_kp_scale=0.6, 看门狗 fail-soft 的降额倍数)"
                     "语义完全不同, 故此处命名为 gain。调大→到位后更硬; 调小→到位后更软/可能下垂。"),
}
for _i, _p in enumerate(GLOBAL_PARAMS):
    _r, _h, _d = _GP_META[_p.key]
    GLOBAL_PARAMS[_i] = replace(_p, role=_r, hint=_h, detail=_d,
                                safety=(_p.key in SAFETY_GLOBAL_KEYS))

IS_SAFETY_KEY = {p.key: p.safety for p in JOINT_PARAMS}
IS_SAFETY_KEY.update({p.key: p.safety for p in GLOBAL_PARAMS})

GLOBAL_BY_KEY = {p.key: p for p in GLOBAL_PARAMS}
GLOBAL_KEY_ORDER = [p.key for p in GLOBAL_PARAMS]

# ---------------------------------------------------------------------------
# [2026-09-14] 动力学模型段 —— 固件 `0x30/0x32/0x33/0x34/0x35/0x37/0x38` 的镜像。
#
# ⚠ 与上面两段的关键差别: 模型参数是**辨识基系数**, 单个无物理意义 (m 全是归一化占位值
#   1.0、I 含负值、M 非正定)。故:
#     - **不做物理范围钳制** (物理钳制会把正确模型判成非法), 只做有限性 + |v| <= 1e6;
#     - 由 `litetool/model_io.py` 走**独立通道**读写, 不进 `snapshot_flat` 的常规叶
#       (缺 `model` 键时**不产出**任何叶, 保证既有预设/模板文件仍可导入)。
# ---------------------------------------------------------------------------
MODEL_BODY_KEYS = ("m", "cmx", "cmy", "cmz", "ixx", "ixy", "ixz", "iyy", "iyz", "izz")
MODEL_BODY_LABELS = ("质量(辨识基)", "质心x(辨识基)", "质心y(辨识基)", "质心z(辨识基)",
                     "惯量ixx", "惯量ixy", "惯量ixz", "惯量iyy", "惯量iyz", "惯量izz")
MODEL_BODY_DECIMALS = 8          # 辨识基参数需要高精度显示 (6 位会看到两行"看起来一样")
MODEL_NBODY = 9                  # 与固件 DYN_MODEL_NBODY / SDK MODEL_NBODY 同值
MODEL_JM_N = 7
MODEL_ABS_MAX = 1e6              # 与固件写口同口径
MODEL_MASK_WRITTEN = (sum(1 << i for i in range(1, 8))) | (1 << 9)   # 0x2FE

# ff_mask: 0x27 写 / 0x2C item 9 读 (u32, 经 f32 读回; 值 ≤0x1FF 时两种编码可无损还原)
FF_MASK_SCALAR_ITEM = 9

# 逐关节读回向量号 (0x2B GET_FF_VEC item): 键 -> item (item 1..11 与写侧同号)
JOINT_VEC_ITEM_BY_KEY = {p.key: p.item for p in JOINT_PARAMS if p.kind == "vec"}
# 读回关节数 (写侧恒 7 宽; 读侧同协议 7 宽)
FF_VEC_LEN = 7


# ---------------------------------------------------------------------------
# 数值校验/钳制
# ---------------------------------------------------------------------------
def check_value(lo: float, hi: float, v, model: bool = False,
                label: str = "") -> str | None:
    """返回错误信息 (None=合法)。model=True 时只允许 0/1。"""
    label = label or i18n.tr("值")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return i18n.tr("{label} 须为数值", label=label)
    f = float(v)
    if f != f:                                   # NaN
        return i18n.tr("{label} 为 NaN", label=label)
    if model:
        return None if f in (0.0, 1.0, 2.0) else \
            i18n.tr("{label} 摩擦模型仅允许 0/1/2", label=label)
    if not (lo <= f <= hi):
        return i18n.tr("{label}={value} 超出范围 [{lo}, {hi}]",
                       label=label, value=_fmt(f), lo=_fmt(lo), hi=_fmt(hi))
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
        return i18n.tr("关节限位非法: q_min({qmin}) ≥ q_max({qmax})",
                       qmin=qmin, qmax=qmax)
    return None


# ---------------------------------------------------------------------------
# yaml/json 快照 <-> 规范化结构; diff
# ---------------------------------------------------------------------------
# 规范化快照形如:
#   {"joints": [ {key: float,...} ×7 ], "global": { <单值键>: float,
#                 "payload_com":[..], "gravity":[..], "friction_model":0/1,
#                 "ff_mask": int }}
SCALAR_KEYS = {"fric_db", "wall_margin", "friction_slew", "payload_mass",
               "fric_v2_eps",
               # [段② 零重力] + [段③ §6.2]
               # [1.12.0] drag_gain 已移到 JOINT_PARAMS (0x26 item16)
               "drag_db",
               "wall_fw_kd", "hold_kp_gain"}
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
        raise ValueError(i18n.tr("参数文件顶层须为对象 (joints + global)"))
    joints_raw = raw.get("joints")
    if not isinstance(joints_raw, (list, tuple)) or len(joints_raw) != NUM_JOINTS:
        raise ValueError(i18n.tr(
            "joints 须为长度 {n} 的数组 (J1..J7, 顺序即关节号)", n=NUM_JOINTS))
    joints = []
    for i, jr in enumerate(joints_raw):
        if not isinstance(jr, dict):
            raise ValueError(i18n.tr("joints[{i}] 须为对象", i=i))
        name = jr.get("name")
        if name is not None and str(name) != f"J{i + 1}":
            raise ValueError(i18n.tr(
                "joints[{i}].name 应为 J{axis}, 实际 {name}",
                i=i, axis=i + 1, name=repr(name)))
        jd = joint_default(jr)
        for p in JOINT_PARAMS:
            v = jd[p.key]
            # ⚠ 缺失/None 合法: 导出文件只含**本板支持**的项 (见 params_io.read_snapshot),
            #   拿它回导时其余项必然缺键。缺项 = 不下发, 不是文件损坏。
            if v is None:
                continue
            err = check_value(p.lo, p.hi, v, label=f"J{i + 1}.{p.key}")
            if err:
                raise ValueError(err)
        rel = check_joint_limits_relation(jd)
        if rel:
            raise ValueError(f"J{i + 1}: {rel}")
        joints.append(jd)

    gr = raw.get("global")
    if not isinstance(gr, dict):
        raise ValueError(i18n.tr("global 须为对象"))
    glob = {}
    for key in SCALAR_KEYS:
        gp = GLOBAL_BY_KEY[key]
        if key not in gr:            # 缺项 = 本板不支持 / 文件只含支持项 (见上)
            continue
        err = check_value(gp.lo, gp.hi, gr[key], label=f"global.{key}")
        if err:
            raise ValueError(err)
        glob[key] = float(gr[key])
    for key in ARRAY_KEYS:
        gp = GLOBAL_BY_KEY[key]
        if key not in gr:
            continue
        arr = gr.get(key)
        if not isinstance(arr, (list, tuple)) or len(arr) != len(gp.subs):
            raise ValueError(i18n.tr("global.{key} 须为长度 {n} 的数组",
                                     key=key, n=len(gp.subs)))
        vals = []
        for k, v in enumerate(arr):
            err = check_value(gp.lo, gp.hi, v, label=f"global.{key}[{k}]")
            if err:
                raise ValueError(err)
            vals.append(float(v))
        glob[key] = vals
    if "friction_model" in gr:
        err = check_value(0, 1, gr["friction_model"], model=True,
                          label="global.friction_model")
        if err:
            raise ValueError(err)
        glob["friction_model"] = int(gr["friction_model"])
    if "ff_mask" in gr:
        fm = gr["ff_mask"]
        if isinstance(fm, bool) or not isinstance(fm, (int, float)):
            raise ValueError(i18n.tr("global.ff_mask 须为整数"))
        fmi = int(fm)
        if fmi != float(fm) or not (0 <= fmi <= FF_ALL_MASK):
            raise ValueError(i18n.tr(
                "global.ff_mask 须为 [0, {mask}] 的整数, 实际 {value}",
                mask=FF_ALL_MASK, value=fm))
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
        v = g.get(p.key)             # 缺 = 本板不支持, 不进 diff/预览
        if v is None:
            continue
        if p.is_array:
            for k in range(len(p.subs)):
                flat[f"global.{p.key}[{k}]"] = float(v[k])
        else:
            flat[f"global.{p.key}"] = float(v)
    if g.get("ff_mask") is not None:
        flat["global.ff_mask"] = int(g["ff_mask"])
    return flat


def leaf_decimals(label: str) -> int:
    """按打平标签取显示小数位 (供 diff 预览/状态行)。

    ⚠ 标签前缀是**有语义的**:
      `J{n}.` -> 关节项; `global.` -> 全局项; `B{n}.` / `jm.` -> 模型项 (高精度)。
    **模型项不得用 `J` 开头** —— `J1.mass` 会去查 `JOINT_BY_KEY["mass"]` 直接 KeyError
    崩掉 diff 对话框; 而落回默认的 `return 4` 又会让 `0.0141869443` 显示成 `0.0142`。
    """
    if label.startswith("B") or label.startswith("jm."):
        return MODEL_BODY_DECIMALS
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
