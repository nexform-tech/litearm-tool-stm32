"""设置 —— 本工具只读固件/协议，配置仅含交互层可选参数（无本地限位表）。"""
import os
from dataclasses import dataclass, fields

import yaml


#: 数值字段的合法区间 (含端点)。范围以"不会让固件整片拒绝/不会崩 GUI"为准。
#: speed_max_ui 卡在 1.0: 固件对 move_j 的 sp>1.0 一律回 ERR 0x02 (不静默钳),
#: 配置写错会让用户以为"臂坏了", 所以直接回退默认而不是放行。
_RANGES = {
    "confirm_threshold": (1e-9, 100.0),
    "default_speed": (1e-9, 1.0),
    "speed_max_ui": (1e-9, 1.0),
    "mit_kp_default": (0.0, 500.0),
    "mit_kd_default": (0.0, 5.0),
    "mit_tau_default": (-120.0, 120.0),
    "temp_alert_c": (1.0, 200.0),
    "plot_window_s": (1.0, 3600.0),
    "pose_confirm_pos": (1e-9, 10.0),     # movep 位置幅度确认阈值 (m)
    "pose_confirm_rot": (1e-9, 6.28),     # movep 姿态幅度确认阈值 (rad)
}


@dataclass
class Settings:
    confirm_threshold: float = 0.5        # Δq 超过即弹确认框 (rad)
    default_speed: float = 0.2            # move_j 默认速度倍率 (低速起步)
    speed_max_ui: float = 1.0             # 运动页速度上限
    mit_kp_default: float = 30.0
    mit_kd_default: float = 2.0
    mit_tau_default: float = 0.0
    temp_alert_c: float = 85.0            # 超温告警阈值 (°C)
    plot_window_s: float = 30.0           # 曲线滚动窗口（秒）
    pose_confirm_pos: float = 0.05        # movep 位置幅度确认阈值 (m)
    pose_confirm_rot: float = 0.30        # movep 姿态幅度确认阈值 (rad)

    @classmethod
    def load(cls, path=None) -> "Settings":
        """读取 YAML 覆盖默认值; 文件不存在/非法时回退默认（stderr 提示）。

        逐字段做**类型 + 区间**校验: 坏值要么让固件整片拒绝(sp>1.0), 要么在 Qt 槽内
        抛 TypeError 直接崩 GUI —— 都发生在用户即将下发运动时, 故一律回退默认。
        """
        s = cls()
        if not path:
            return s
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:  # noqa: BLE001
            print(f"[config] 无法读取 {path}: {e}，使用默认配置", file=os.sys.stderr)
            return s
        if not isinstance(data, dict):
            print(f"[config] {path} 顶层不是映射，使用默认配置", file=os.sys.stderr)
            return s
        known = {fld.name for fld in fields(cls)}
        for key, val in data.items():
            if key not in known:
                print(f"[config] 忽略未知配置项: {key}", file=os.sys.stderr)
                continue
            default = getattr(s, key)
            if key not in _RANGES:
                # dataclass 加了字段但忘了登记区间 -> 回退默认, 不能 KeyError 崩掉启动
                print(f"[config] {key} 未登记合法区间，使用默认 {default}",
                      file=os.sys.stderr)
                continue
            lo, hi = _RANGES[key]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                print(f"[config] {key} 类型非法 ({type(val).__name__})，"
                      f"使用默认 {default}", file=os.sys.stderr)
                continue
            if not lo <= float(val) <= hi:
                print(f"[config] {key}={val} 超出合法区间 [{lo}, {hi}]，"
                      f"使用默认 {default}", file=os.sys.stderr)
                continue
            setattr(s, key, float(val))
        return s
