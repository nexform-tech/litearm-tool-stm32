"""诊断包 —— 一次故障的现场快照，**白名单生成**。

为什么白名单而不是排除法：漏掉一个排除项就会泄露。这里只挑明列出的字段，
多出任何键都按缺陷处理（`tests/test_diagnostics.py` 钉住）。

包内容（P0）: 元信息 / 错误 / 状态快照 / 链路统计 / 日志尾部 / 结构化日志路径。
参数摘要留到 P1（需要额外读 0x2B/0x2C，不在故障路径上做阻塞读）。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from typing import Any, Iterable, Optional

SCHEMA = "litearm.diag/1"

#: 顶层允许出现的键 —— 测试以此为判据。
WHITELIST_KEYS = frozenset({
    "schema", "exported_at", "tool", "sdk", "firmware",
    "error", "state", "link", "log_tail", "log",
})

_LOG_TAIL_MAX = 200


def _tool_version() -> str:
    try:
        from importlib.metadata import version
        return version("litearm-tool-stm32")
    except Exception:  # noqa: BLE001 - 未安装/元数据缺失都回退
        return "dev"


def _sdk_version() -> str:
    try:
        import litearm
        return getattr(litearm, "__version__", "?")
    except Exception:  # noqa: BLE001
        return "?"


def _sanitize(text: str) -> str:
    """把用户主目录路径折成 `~`；其余原样。"""
    return re.sub(r"/home/[^/\s]+", "~", str(text))


def _state_dict(st: Any) -> Optional[dict]:
    if st is None:
        return None
    joints = []
    for i, j in enumerate(getattr(st, "joints", []) or []):
        joints.append({
            "i": i,
            "q": round(float(j.q), 6),
            "dq": round(float(j.dq), 6),
            "tau": round(float(j.tau), 6),
            "t_mos": round(float(j.t_mos), 2),
            "t_coil": round(float(j.t_coil), 2),
            "err": int(j.err),
        })
    return {
        "mode": getattr(st, "mode_name", "?"),
        "enabled": bool(getattr(st, "enabled", False)),
        "flags": f"0x{int(getattr(st, 'flags', 0)):04X}",
        "joint_fault": f"0x{int(getattr(st, 'joint_fault', 0)):04X}",
        "fault_reason": list(getattr(st, "fault_reason", []) or []),
        "drop_hold_reason": int(getattr(st, "drop_hold_reason", 0) or 0),
        "joints": joints,
    }


def _error_dict(err: Any) -> Optional[dict]:
    if err is None:
        return None
    return {
        "code": err.code,
        "text": {"title": err.title, "cause": err.cause, "action": err.action},
    }


def build_diag_package(*, firmware: str, n_joints: int, state: Any,
                       error_text: Any = None, drops: int = 0,
                       log_tail: Iterable[str] = (),
                       log_path: Optional[str] = None,
                       locale: str = "zh-CN") -> dict:
    """构造诊断包。只返回白名单字段。"""
    tail = [_sanitize(x) for x in list(log_tail)[-_LOG_TAIL_MAX:]]
    return {
        "schema": SCHEMA,
        "exported_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "tool": {"version": _tool_version(), "locale": locale},
        "sdk": {"version": _sdk_version()},
        "firmware": {"version": firmware or "?", "n_joints": int(n_joints or 0)},
        "error": _error_dict(error_text),
        "state": _state_dict(state),
        "link": {"drops": int(drops or 0)},
        "log_tail": tail,
        # 只给路径，不内联文件内容：诊断包是白名单快照，完整历史在 JSONL 里。
        "log": {"path": _sanitize(log_path)} if log_path else None,
    }


def save_diag_package(pkg: dict, directory: Optional[str] = None) -> str:
    """写 `~/litearm-diag-<时间>.json`，返回路径。"""
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(directory or os.path.expanduser("~"),
                        f"litearm-diag-{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pkg, f, ensure_ascii=False, indent=2)
    return path
