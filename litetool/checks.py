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
