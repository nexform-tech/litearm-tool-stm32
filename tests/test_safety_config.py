"""config.yaml 的健壮性 —— 坏值不得变成"全部 move_j 被固件拒绝"或 GUI 槽内异常。

背景 (2026-09-13 评审): `Settings.load` 只做 key 白名单, 不校验类型/范围 ——
  - `speed_max_ui: 30` 会让运动页允许 30 倍速, 固件对 sp>1.0 一律回 ERR 0x02(不静默钳),
    用户只看到"被固件拒绝", 无从判断是配置问题;
  - `confirm_threshold` 填成字符串时 `plan_motion` 抛 TypeError, 发生在 Qt 槽内 ——
    PyQt5 默认对槽内未捕获异常 abort(), GUI 直接崩溃(恰好发生在用户即将下发运动时)。
"""
from __future__ import annotations

import pytest

from litetool import settings as S


def _load(tmp_path, body: str):
    p = tmp_path / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return S.Settings.load(str(p))


def test_valid_config_applied(tmp_path):
    s = _load(tmp_path, "confirm_threshold: 0.25\nspeed_max_ui: 0.5\n")
    assert s.confirm_threshold == pytest.approx(0.25)
    assert s.speed_max_ui == pytest.approx(0.5)


@pytest.mark.parametrize("body,field", [
    ("speed_max_ui: 30\n", "speed_max_ui"),        # 倍率写成百分数
    ("speed_max_ui: 0\n", "speed_max_ui"),
    ("speed_max_ui: -1\n", "speed_max_ui"),
    ("confirm_threshold: 0\n", "confirm_threshold"),
    ("confirm_threshold: -0.5\n", "confirm_threshold"),
    ("temp_alert_c: 0\n", "temp_alert_c"),
    ("plot_window_s: 0\n", "plot_window_s"),
    ("mit_kp_default: -1\n", "mit_kp_default"),
])
def test_out_of_range_falls_back_to_default(tmp_path, body, field):
    s = _load(tmp_path, body)
    assert getattr(s, field) == getattr(S.Settings(), field), f"{field} 未回退默认"


@pytest.mark.parametrize("body,field", [
    ("speed_max_ui: fast\n", "speed_max_ui"),
    ("confirm_threshold: '0.5'\n", "confirm_threshold"),
    ("confirm_threshold: [1]\n", "confirm_threshold"),
    ("mit_kd_default: null\n", "mit_kd_default"),
])
def test_wrong_type_falls_back_to_default(tmp_path, body, field):
    """类型不对必须回退默认 —— 否则会在 Qt 槽内抛 TypeError 崩掉 GUI。"""
    s = _load(tmp_path, body)
    assert isinstance(getattr(s, field), (int, float))
    assert getattr(s, field) == getattr(S.Settings(), field)


def test_broken_yaml_falls_back(tmp_path):
    s = _load(tmp_path, "speed_max_ui: [unclosed\n")
    assert s == S.Settings()


def test_new_field_without_range_entry_does_not_crash(tmp_path):
    """给 Settings 加字段却忘了加 _RANGES 项 -> 不能启动即崩 (KeyError)。

    这是"以后加配置项"的必踩陷阱: `_RANGES[key]` 无兜底 = 配置文件在场时启动崩溃。
    """
    from dataclasses import dataclass

    @dataclass
    class S2(S.Settings):
        new_knob: float = 1.0

    p = tmp_path / "config.yaml"
    p.write_text("new_knob: 2.5\nconfirm_threshold: 0.25\n", encoding="utf-8")
    s = S2.load(str(p))                      # 不得抛异常
    assert s.confirm_threshold == pytest.approx(0.25)   # 已知项照常生效
    assert s.new_knob == pytest.approx(1.0)  # 未登记项回退默认
