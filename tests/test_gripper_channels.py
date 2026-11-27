"""CAN 通道枚举 —— 只认 /sys/class/net 的 ARPHRD_CAN (280)。"""
from __future__ import annotations

from pathlib import Path

from litetool.gripper import list_channels


def _iface(root: Path, name: str, type_value: str | None = None) -> None:
    d = root / name
    d.mkdir()
    if type_value is not None:
        (d / "type").write_text(type_value, encoding="ascii")


def test_lists_only_arp_hrd_can(tmp_path):
    _iface(tmp_path, "can0", "280\n")
    _iface(tmp_path, "can1", "280")
    _iface(tmp_path, "vcan0", "280")
    _iface(tmp_path, "eth0", "1")
    _iface(tmp_path, "wlan0", "1")
    _iface(tmp_path, "broken")                 # 没有 type 文件
    _iface(tmp_path, "bad", "not-an-int")      # 内容不是整数
    assert list_channels(str(tmp_path)) == ["can0", "can1", "vcan0"]


def test_missing_sysfs_is_empty(tmp_path):
    assert list_channels(str(tmp_path / "missing")) == []
