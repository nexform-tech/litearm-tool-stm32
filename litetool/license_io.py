"""设备授权记录（`0x2F` 读 / `0x3F` 写）的形状层 —— 页面要的是 dict 与 `(ok, 文案)`。

⚠ 与 studio 的 `_license_dict` 同一口径：`supported` 是**三态**，不是布尔 ——
三者对用户说的话完全不同（详见 `read_record`）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import litearm as pa

from litetool.activation import ActivationError

__all__ = ["read_record", "write_license"]


def read_record(arm: Any) -> Dict[str, Any]:
    """读设备授权记录。

    * `supported=True` —— 读到了，其余字段有效（未激活时 `cust_id/issued/flags` 恒 0，
      但 **UID 照回**：签发凭据用的就是它）；
    * `supported=False` —— 固件明确回 `ERR{0x2F,0x00}`：没有授权命令（太旧）；
    * `supported=None` —— 没读到（本次无应答；旧固件今天实际走这一条）。
    """
    try:
        info = arm.license()
    except pa.UnsupportedByFirmwareError:
        return {"supported": False}
    except pa.MotionTimeoutError:
        return {"supported": None}
    return {
        "supported": True,
        "state": int(info.state),
        "stateName": info.state_name,
        "activated": bool(info.activated),
        "factoryMode": bool(info.factory_mode),
        "ver": int(info.ver),
        "uid": info.uid_hex,
        "custId": int(info.cust_id),
        "issued": int(info.issued),
        "flags": int(info.flags),
    }


def write_license(arm: Any, lic: Dict[str, Any]) -> Dict[str, Any]:
    """把凭据写进设备并**回读**（ACK 只说明固件答应了）。

    `ERR{0x3F,0x02}` 是聚合档（保留位 / 已激活 / MAC 不符 / 写读失败全折成它）：
    回读若显示已激活就按成功处理 —— 否则"已经激活过"会被误报成失败。
    """
    try:
        arm.activate(cust_id=lic["cust_id"], issued=lic["issued"],
                     flags=lic["flags"], mac=lic["mac"])
    except pa.CommandRejectedError as e:
        cmd = getattr(e, "cmd", None)
        code = getattr(e, "code", None)
        if cmd == 0x3F and code == 0x02:
            record = read_record(arm)
            if record.get("supported") is True and record.get("activated") is True:
                return record
        if cmd == 0x3F and code == 0x04:
            raise ActivationError("armed", "设备已使能 —— 请先失能，再提交激活") from None
        raise ActivationError("rejected", _describe(e)) from None
    return read_record(arm)


def _describe(exc: BaseException) -> str:
    try:
        text = pa.describe_exc(exc)
        parts = [getattr(text, "title", "") or "",
                 getattr(text, "cause", "") or "",
                 getattr(text, "action", "") or ""]
        joined = "；".join(p for p in parts if p)
        if joined:
            return joined
    except Exception:  # noqa: BLE001 - 文案是尽力而为, 不能反噬错误处理
        pass
    return str(exc) or type(exc).__name__


def uid_of(record: Optional[Dict[str, Any]]) -> Optional[str]:
    """记录里的 UID；`supported` 不是 True 时没有可信 UID。"""
    if not record or record.get("supported") is not True:
        return None
    return record.get("uid")
