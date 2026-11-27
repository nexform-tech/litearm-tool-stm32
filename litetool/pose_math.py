"""笛卡尔点动的位姿数学 —— 纯函数，不依赖 Qt/SDK。

位姿统一是 `[x, y, z, roll, pitch, yaw]`（米 / 弧度），与 `litearm.get_tcp()` /
`move_l()` 的入参同形。矩阵用嵌套列表，`R[i][j]`。

两个坐标系的差别（与 studio 的前端实现逐项一致）：

* **基座系**：平移沿世界轴；旋转左乘 `dR · R`（绕世界轴转）；
* **工具系**：平移方向 = `R · 轴`；旋转右乘 `R · dR`（绕末端自身轴转）。

点动的每一步都从**当前实测位姿**重新取起点，不做积分，所以连续点动不会累积浮点漂移
（代价是段与段之间有一次 TCP 回读）。
"""
from __future__ import annotations

import math
from typing import Sequence

AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
_TAU = 2.0 * math.pi


def rpy_to_mat3(roll: float, pitch: float, yaw: float) -> list:
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ]


def mat3_to_rpy(r: Sequence[Sequence[float]]) -> tuple:
    """ZYX 欧拉角反解；万向锁附近走与 studio 相同的分支。"""
    if abs(r[2][0]) < 0.99999:
        pitch = -math.asin(max(-1.0, min(1.0, r[2][0])))
        cp = math.cos(pitch)
        roll = math.atan2(r[2][1] / cp, r[2][2] / cp)
        yaw = math.atan2(r[1][0] / cp, r[0][0] / cp)
    else:
        yaw = 0.0
        if r[2][0] <= -0.99999:
            pitch = math.pi / 2.0
            roll = math.atan2(r[0][1], r[0][2])
        else:
            pitch = -math.pi / 2.0
            roll = math.atan2(-r[0][1], -r[0][2])
    return roll, pitch, yaw


def mat_mul3(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> list:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def mat_vec3(m: Sequence[Sequence[float]], v: Sequence[float]) -> tuple:
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def rot_axis(axis: str, rad: float) -> list:
    c, s = math.cos(rad), math.sin(rad)
    if axis == "X":
        return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]
    if axis == "Y":
        return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]
    if axis == "Z":
        return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
    raise ValueError(f"未知旋转轴: {axis}")


def jog_pose(pose: Sequence[float], axis: str, kind: str, amount: float,
             frame: str = "base") -> list:
    """返回点动一步后的新位姿；`kind` 是 `translate` / `rotate`。

    `amount`：平移为**米**，旋转为**弧度**（带符号）。调用方负责把 mm/度换算好。
    """
    if len(pose) != 6:
        raise ValueError(f"位姿需要 6 个数 (pos3+rpy3)，收到 {len(pose)} 个")
    if axis not in AXES:
        raise ValueError(f"未知轴: {axis}")
    if frame not in ("base", "tool"):
        raise ValueError(f"未知坐标系: {frame}")
    x, y, z, roll, pitch, yaw = (float(v) for v in pose)
    r = rpy_to_mat3(roll, pitch, yaw)

    if kind == "translate":
        direction = AXES[axis] if frame == "base" else mat_vec3(r, AXES[axis])
        return [x + direction[0] * amount, y + direction[1] * amount,
                z + direction[2] * amount, roll, pitch, yaw]

    if kind == "rotate":
        d = rot_axis(axis, amount)
        new_r = mat_mul3(d, r) if frame == "base" else mat_mul3(r, d)
        nr, np_, ny = mat3_to_rpy(new_r)
        return [x, y, z, nr, np_, ny]

    raise ValueError(f"未知点动类型: {kind}")


def wrap_angle(rad: float) -> float:
    """把角度折进 (-pi, pi]，方便 UI 显示。"""
    while rad <= -math.pi:
        rad += _TAU
    while rad > math.pi:
        rad -= _TAU
    return rad
