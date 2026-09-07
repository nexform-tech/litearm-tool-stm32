"""设置 —— 本工具只读固件/协议，配置仅含交互层可选参数（无本地限位表）。"""
import os
from dataclasses import dataclass, fields

import yaml


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

    @classmethod
    def load(cls, path=None) -> "Settings":
        """读取 YAML 覆盖默认值；文件不存在/非法时静默回退默认（仅记入 stderr）。"""
        s = cls()
        if not path:
            return s
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:  # noqa: BLE001
            print(f"[config] 无法读取 {path}: {e}，使用默认配置", file=os.sys.stderr)
            return s
        known = {fld.name for fld in fields(cls)}
        for key, val in data.items():
            if key in known:
                setattr(s, key, val)
            else:
                print(f"[config] 忽略未知配置项: {key}", file=os.sys.stderr)
        return s
