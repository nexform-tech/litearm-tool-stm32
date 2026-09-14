"""安全交互检查（checks）—— 只做固件防不了的"操作意图"层。

注意：本模块**不**复刻固件防护（软限位/速度上限/NaN 等权威在固件）。它只负责
运动下发前的 Δq 阈值判断，防止手滑输错数量级导致的"合法但非本意"运动。
"""
from dataclasses import dataclass


@dataclass
class MotionPlan:
    """一次运动下发的逐关节 Δq 分析结果。"""
    current: list[float]
    targets: list[float]
    deltas: list[float]     # 每关节 |target - current| (rad)
    exceeds: list[int]      # 超阈值关节的 1-based 序号（升序）
    threshold: float

    @property
    def needs_confirm(self) -> bool:
        return bool(self.exceeds)

    @property
    def n(self) -> int:
        return len(self.current)


def plan_motion(current: list[float], targets: list[float], threshold: float = 0.5) -> MotionPlan:
    """比较当前角与目标角，标注需确认的关节。

    - current/target 长度必须一致，否则 ValueError（GUI 侧按首帧定 N）。
    - threshold: Δq 超过即需弹确认框（rad, 应 > 0）。
    """
    if len(current) != len(targets):
        raise ValueError(f"current({len(current)}) 与 targets({len(targets)}) 关节数不一致")
    deltas = [abs(t - c) for c, t in zip(current, targets)]
    exceeds = [i + 1 for i, d in enumerate(deltas) if d > threshold]
    return MotionPlan(current=list(current), targets=list(targets),
                      deltas=deltas, exceeds=exceeds, threshold=threshold)


def confirm_lines(plan: MotionPlan, labels=None) -> list[str]:
    """生成确认弹窗的行（只列超阈值关节）: 'J2: 当前 0.120 → 目标 1.400（Δ 1.280 rad）'"""
    labels = labels or [f"J{i + 1}" for i in range(plan.n)]
    lines = []
    for idx1 in plan.exceeds:
        i = idx1 - 1
        c, t, d = plan.current[i], plan.targets[i], plan.deltas[i]
        lines.append(f"{labels[i]}: 当前 {c:.3f} → 目标 {t:.3f}（Δ {d:.3f} rad）")
    return lines


# --------------------------------------------------------------------------
# 笛卡尔：movep 的位姿幅度确认
# --------------------------------------------------------------------------
@dataclass
class PosePlan:
    """一次 movep 的位姿变化量。current 为 None 表示拿不到当前 TCP（无从比较）。"""

    current: list | None
    target: list
    dpos: float | None          # 位置欧氏距离 (m)
    drot: float | None          # 姿态夹角 (rad)
    pos_threshold: float
    rot_threshold: float

    @property
    def needs_confirm(self) -> bool:
        """拿不到当前 TCP 时**也要确认**。

        原先这里返回 False（"交给用户核对输入框"），结果是：连上之后第一个 movep
        在没读过 TCP 的情况下**完全绕过幅度闸门** —— 而这正是"手滑输错数量级"最
        容易发生的时刻（输入框还是空白/默认值）。宁可多一次弹窗。
        """
        if self.current is None:
            return True
        return self.dpos > self.pos_threshold or self.drot > self.rot_threshold

    def summary(self) -> str:
        if self.current is None:
            return (f"⚠ 拿不到当前末端位姿，无法比较幅度。\n"
                    f"目标：{'  '.join(f'{v:+.4f}' for v in self.target)}\n"
                    f"（建议先 [读取当前末端位姿] 再下发）")
        return (f"位置移动 {self.dpos:.3f} m（阈值 {self.pos_threshold}）\n"
                f"姿态变化 {self.drot:.3f} rad（阈值 {self.rot_threshold}）")


def _rpy_to_R(rpy):
    """RPY(ZYX 内旋) -> 3x3 旋转矩阵，与固件/ SDK 的 RPY 约定一致。"""
    import math
    r, p, y = rpy
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    return ((cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
            (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
            (-sp,     cp * sr,                cp * cr))


def _orient_angle(a, b) -> float:
    """两个 RPY 之间的旋转夹角 (rad)。"""
    import math
    ra, rb = _rpy_to_R(a), _rpy_to_R(b)
    tr = sum(sum(ra[k][i] * rb[k][i] for k in range(3)) for i in range(3))
    return math.acos(max(-1.0, min(1.0, (tr - 1.0) / 2.0)))


def plan_pose(current, target, pos_threshold: float = 0.05,
              rot_threshold: float = 0.30) -> PosePlan:
    """比较当前 TCP 与目标 pose，判断幅度是否超过确认阈值。

    `current` 为 None 或长度不足 6 时无法比较幅度 —— 此时 `needs_confirm` 为 True
    （让调用方出示"无基线"确认），而不是静默放行。
    """
    tgt = [float(v) for v in target]
    if current is None or len(current) < 6 or len(tgt) < 6:
        return PosePlan(None, tgt, None, None, pos_threshold, rot_threshold)
    cur = [float(v) for v in current]
    import math
    dpos = math.sqrt(sum((tgt[i] - cur[i]) ** 2 for i in range(3)))
    drot = _orient_angle(cur[3:6], tgt[3:6])
    return PosePlan(cur, tgt, dpos, drot, pos_threshold, rot_threshold)
