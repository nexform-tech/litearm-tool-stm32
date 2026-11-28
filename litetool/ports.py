"""串口枚举 —— 板载 CDC 排最前，其余按名称排序。

SDK 的 `find_cdc_port()` 只回**第一个** VID:PID 匹配的口（够用于自动连接）；
下拉框需要看得到全部候选，故这里另列一份。
"""
from __future__ import annotations

from typing import Dict, List

from litetool import i18n

# 板载复合 USB (gs_usb + CDC) 的 VID:PID
USB_VID = 0x1D50
USB_PID = 0x606F

DEFAULT_BAUD = 921600          # CDC 虚拟串口忽略波特率，此处仅占位


def find_ports() -> List[Dict[str, str]]:
    """返回 [{device, description, _ours}]，板载 CDC 恒排最前。

    ⚠ 标签必须**如实**：早先的实现给**每一个**串口都套上 "LiteArm STM32" 前缀
    （连 JLink 探针和 31 个不存在的 /dev/ttyS* 占位节点都是），用户照着一个
    写着 LiteArm 的条目点 [连接]，只会拿到一句超时 —— 而且完全不知道为什么。
    这里改成：板载口显式标出，其余一律用**设备自己的名字**。
    """
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for p in list_ports.comports():
        dev = p.device
        if not dev:
            continue
        desc = (p.description or "").strip()
        ours = (p.vid == USB_VID and p.pid == USB_PID)
        if ours:
            label = i18n.tr("✔ LiteArm STM32（板载 CDC）— {desc}",
                            desc=desc or dev)
            rank = 0
        elif p.vid is not None:
            vid_pid = (f"{p.vid:04X}:{p.pid:04X}" if p.pid is not None
                       else f"{p.vid:04X}")
            label = i18n.tr("{desc}（VID:PID {vid_pid}）— {dev}",
                            desc=desc or i18n.tr("USB 串口"),
                            vid_pid=vid_pid, dev=dev)
            rank = 1
        else:
            # 没有 VID/PID 的是内核占位节点（典型是 ttyS0..31），不是 USB 设备
            label = i18n.tr("{dev}（系统串口，非 USB）", dev=dev)
            rank = 2
        rows.append({"device": dev, "description": label,
                     "_ours": ours, "_rank": rank})
    # 板载口最前（JLink 等其它 USB 串口不得抢占首位），系统占位节点垫底
    rows.sort(key=lambda r: (r["_rank"], r["device"]))
    return rows
