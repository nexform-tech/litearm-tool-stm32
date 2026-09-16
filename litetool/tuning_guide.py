"""调参指南内容 —— 动力学/控制律公式 + 读前须知 + "症状→建议参数"速查表。

纯 Python 无 Qt, 内容以固件 litearm-stm32 master 源码为准 (控制律/摩擦/前馈合成):
  - User/litearm/control/law.c            (law_friction / law_friction_v2 / 积分 / 墙)
  - User/litearm/control/control_loop.c    (ff_mask 前馈合成段, gs/is 乘项)
  - User/litearm/litearm.h                (FF_* 位)
  - User/litearm/params/defaults.c        (出厂默认 / gs 基线)
GUI 页签只负责渲染本模块拼好的 HTML (QTextBrowser)。
"""
from litetool import param_catalog as C

#: 出厂 gs 基线 —— 与 param_catalog 共用一份 (2026-09-12 换辨识模型后全 1.0)
GS_BASELINE = C.GS_BASELINE

# ---- (a) 动力学/控制律公式 (纯文本, unicode 即可) ----
FORMULA_TEXT = """τ_joint = PD_j + gs_j·G_j(q) + is_j·[M(q)·q̈ + C(q,q̇)·q̇]_j + τ_fric_j + τ_int_j + τ_wall_j(默认关) + τ_quant_j + τ_velref_j

PD_j      = kp_j·(q_d − q) + kd_j·(q̇_d − q̇)      （电机 MIT 内执行, kp≤500, kd≤5）
G/M/C     = 固件内置辨识模型 (litearm_id.urdf: MDH 几何 + 辨识惯量); gs/is = 逐关节缩放旋钮
τ_fric v2 = fv_j·q̇_d + fc0_j·max(tanh(q̇_d/ε),0) + fc1_j·max(−tanh(q̇_d/ε),0)   （friction_model=1, 速度方向, slew 限速）
v1(回退)  = friction_j·tanh(e/fric_db)      （friction_model=0, 误差方向）
τ_int     = ki_j·∫(q_d−q)dt, 钳 ±i_max
最后一律 τ = clamp(τ, ±tau_max)   ← 力矩钳幅=安全天花板
"""

# 符号 ↔ 界面参数 对照 (每条: (符号, 说明))
SYMBOL_MAP = [
    ("kp_j / kd_j", "表中 kp/kd 列 (该关节 MIT 刚度/阻尼; PD 在电机内执行)"),
    ("gs_j", "表中 gs (gravity_scale) 列 —— 逐关节重力旋钮, 实测基线 " + GS_BASELINE),
    ("is_j", "表中 is (inertia_scale) 列; FF_CORIOLIS 位决定是否含 C(q,q̇)·q̇"),
    ("G_j(q) / M(q) / C(q,q̇)", "固件内置辨识动力学 (litearm_id.urdf), 编译期常量, GUI 不直接改"),
    ("q_d / q̇_d", "期望位置/期望速度 = 轨迹规划输出 (非测量值); 故 v2 摩擦不吃编码器噪声"),
    ("q / q̇", "编码器测量位置/速度"),
    ("fv_j / fc0_j / fc1_j", "表中 friction_v / friction_fc0 / friction_fc1 列 (v2, 符号 fv≥0,fc0≥0,fc1≤0)"),
    ("ε", "全局 friction_model v2: fric_v2_eps (tanh 平滑带宽)"),
    ("friction_j / fric_db", "v1 摩擦: friction 列 + 全局 fric_db (仅 friction_model=0)"),
    ("τ_int, ki_j, i_max_j", "积分项: ki 列, 输出钳 ±i_max (表中 i_max)"),
    ("τ_wall_j", "限位虚拟墙 (wall_stiff/wall_damp/wall_tau_max 列; FF_WALL 默认关)"),
    ("τ_quant_j / τ_velref_j", "MIT 量化补偿 (FF_QUANT) / 速度参考力矩 (FF_VELREF), 默认由 ff_mask 位开关"),
    ("±tau_max", "每关节 tau_max 列 = 力矩钳幅 (安全天花板; 饱和见症状表)"),
]

# ---- (b) 读前须知 ----
READ_FIRST = [
    "改动即时进 RAM：下发即生效, 不影响 Flash (下电后回出厂/上次固化值)。",
    "固化才持久：param_save (0x25) 写 Flash, 固件要求关节处于 disable 态 (enable 态拒绝 0x04)。",
    "使能中写 = 实时改控制律：臂 enable 时写 kp/kd/tau/gs/is/摩擦/ff_mask 等会立刻改变电机指令 —— GUI 有二次确认, 操作前请确认周围安全、急停可及。",
    "固件永远兜底：NaN/越界静默钳制或拒绝 (0x02); 软限位/速度包络/看门狗在固件内, GUI 只提示不兜底。",
    "摩擦 v2 为出厂默认 (friction_model=1, FF_FRICTION 开): 摩擦 v1/friction 列在 v2 下不生效, 保持 0。",
    "调参原则: 一次只动 1~2 个参数, 小步 (<10%), 每次记录旧值以便回退。",
]

# ---- "症状→建议参数"速查表 (每行: (症状, 先动什么, 备注)) ----
SYMPTOM_TABLE = [
    ("到位下垂 / 保持软", "ki↑ (承重轴)；**先核对安装方向**",
     "别急着调 gs/is —— 辨识模型下它们应恒为基线的 " + GS_BASELINE + "，"
     "拿它凑下垂等于把模型误差伪装成标定值。先到 [安装方向] 页看当前装向对不对；"
     "挂重物先填 payload_mass"),
    ("侧装 / 倒装后重力补偿方向不对", "改 gravity 向量 (0x28 item6)",
     "[安装方向] 页选装向（按钮自带向量标注，不必猜「侧装 +y」是哪边）。"
     "**须先失能** —— 固件 1.5.3 起 armed 态回 ERR{0x28,0x04}，"
     "且三条分量非原子（中途模长 13.87、方向偏 45°）"),
    ("稳态残差 / 画方拐角不准", "kp↑ (承重轴)、is↑", "kp 受 500 上限 + 振荡拐点约束, 逐轴小步"),
    ("低速一顿一顿 (粘滑)", "friction_v/fc0↑、速度包络降", "摩擦 v2 默认开; 过大过零会顿挫"),
    ("抖动 / 啸叫 / 高频振", "kp↓、kd↑ (≤5)", "jerk/acc 为编译期常量, 只读提示见 defaults.c 注释"),
    ("过冲 / 到位回冲", "kd↑ (≤5)", "另有 S 曲线常数在 defaults.c (编译期)"),
    ("τ 恒贴 ±tau_max (饱和)", "降速度包络 / 减负载, 勿加 kp", "饱和=力矩预算不足, 不是刚度不够"),
    ("触发跟随误差 FAULT", "speed_limit / vel_max 降", "跟随误差上限在固件 (0.25~0.35 rad 依轴)"),
    ("手感试验参考", "friction_model 0/1 切换、ff_mask 位开关", "见下方 ff_mask 位含义脚注"),
]

FF_BITS_ROWS = [(bit, name, label) for bit, name, label in C.FF_BITS]


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _table(headers, rows) -> str:
    out = ["<table border='1' cellspacing='0' cellpadding='4' "
           "style='border-collapse:collapse;font-size:13px;'>",
           "<tr>" + "".join(f"<th align='left'>{_esc(h)}</th>" for h in headers) + "</tr>"]
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{_esc(str(c))}</td>" for c in r) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def build_guide_html() -> str:
    """拼整页 HTML (QTextBrowser 渲染; 无第三方渲染依赖)。"""
    pre = f"<pre style='font-size:13px;line-height:1.45;'>{_esc(FORMULA_TEXT)}</pre>"
    sym = _table(["符号", "对应界面参数"], SYMBOL_MAP)
    read = "".join(f"<li>{_esc(x)}</li>" for x in READ_FIRST)
    symp = _table(["症状", "先动", "备注"], SYMPTOM_TABLE)
    ff_rows = [(f"FF_{name}", f"0x{mask:02X}", label) for mask, name, label in FF_BITS_ROWS]
    ff = _table(["位", "值", "含义"], ff_rows)
    html = f"""<html><body style='font-family:sans-serif;'>
<h2>公式 &amp; 调参指南</h2>

<h3>1) 动力学 / 控制律公式</h3>
{pre}
<p><b>说明:</b> PD 与各种前馈在固件内按 <code>ff_mask</code> 使能位合成; 出厂默认 ff_mask=0x1BF(447)。
符号对应界面参数见下表（悬停参数页相应行列亦可看到同款说明）。</p>
{sym}

<h3>2) 读前须知</h3>
<ul>{read}</ul>

<h3>3) 症状 → 建议参数</h3>
{symp}
<p><i>以上为经验起点, 每次小步试并记录; 权威钳幅/限位始终在固件。</i></p>

<h3>4) ff_mask 位含义脚注</h3>
{ff}
</body></html>"""
    return html
