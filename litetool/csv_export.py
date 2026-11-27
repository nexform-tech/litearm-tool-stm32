"""CSV 导出 —— 状态曲线窗口与 300 Hz 控制拍采集。

两条数据源形状不同，**不要合并**：

* 曲线（`PlotModel`）：100 Hz 状态帧，含 q/dq/tau、MOS/线圈温度、驱动错误码，
  保留最近 `plot_window_s` 秒；
* 采集（`LogReader`）：300 Hz 控制拍，固件 `log_sample_t` 只有 tick/q_ref/dq/tau
  ——**没有**温度和错误码（那些在状态帧里，不在采集缓冲里）。导出时如实只写有的列。

列名一律带单位（`J1 q (rad)` / `J1 T_mos (°C)`），文件名带固件版本与时间。
写盘走同目录临时文件 + `os.replace`：中途失败不会留下半截 CSV。
"""
from __future__ import annotations

import csv
import datetime as _dt
import os
import re
import tempfile
from typing import Iterable, Optional, Sequence

#: 曲线列：字段名 + 单位。`err` 是固件驱动状态码（0 失能 / 1 使能 / 13 超时保护）。
PLOT_FIELDS = (("q", "rad"), ("dq", "rad/s"), ("tau", "Nm"),
               ("T_mos", "°C"), ("T_coil", "°C"), ("err", ""))

#: 采样的真实字段 —— 固件 300Hz 缓冲里没有温度/错误码，别在这里编造。
CAPTURE_FIELDS = (("q_ref", "rad"), ("dq", "rad/s"), ("tau", "Nm"))

#: 固件 tick 是 u32，采集短于 2^32 拍（约 165 天）不会回绕；按模差算时间更稳。
_TICK_MOD = 1 << 32

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: object, default: str) -> str:
    s = _UNSAFE.sub("_", str(text or "")).strip("._-")
    return s or default


def timestamped_name(prefix: str, firmware: str = "", when: Optional[_dt.datetime] = None,
                     ext: str = "csv") -> str:
    """`litearm_<prefix>_<firmware>_<YYYYmmdd-HHMMSS>.csv`，各段已做文件名净化。"""
    when = when or _dt.datetime.now()
    return (f"litearm_{_slug(prefix, 'export')}_"
            f"{_slug(firmware, 'unknown')}_{when:%Y%m%d-%H%M%S}.{_slug(ext, 'csv')}")


def _num(value: object) -> str:
    """浮点用 9 位有效数字（f32 的精度上限），整数/异常值原样。"""
    try:
        return f"{float(value):.9g}"
    except (TypeError, ValueError):
        return str(value)


def _atomic_write(path: str, write_rows) -> None:
    """同目录临时文件 → 原子替换；任何异常都清掉临时文件。"""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".litearm-csv-", dir=directory)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            write_rows(w)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _rect(name: str, rows: Sequence[Sequence], n_rows: int, n_cols: int) -> None:
    if len(rows) != n_rows:
        raise ValueError(f"{name} 有 {len(rows)} 行，时间轴有 {n_rows} 行 —— 拒绝导出错位数据")
    for i, row in enumerate(rows):
        if len(row) != n_cols:
            raise ValueError(f"{name} 第 {i} 行有 {len(row)} 列，期望 {n_cols} —— 拒绝导出错位数据")


def _joints(n: int, joints: Optional[Iterable[int]]) -> list:
    if joints is None:
        return list(range(n))
    out = sorted({int(j) for j in joints})
    for j in out:
        if not 0 <= j < n:
            raise ValueError(f"关节索引 {j} 超出 0..{n - 1}")
    return out


def write_plot_csv(path: str, snapshot: dict, joints: Optional[Iterable[int]] = None,
                   firmware: str = "") -> int:
    """导出曲线窗口。`snapshot` 来自 `PlotModel.snapshot_full()`；返回写出的数据行数。

    `joints` 是 0 基索引；缺省导出全部关节。时间列相对**本次导出的第一行**。
    """
    times = list(snapshot.get("times") or [])
    if not times:
        raise ValueError("曲线窗口里没有数据 —— 连接后等几帧再导出")
    q = list(snapshot.get("q") or [])
    dq = list(snapshot.get("dq") or [])
    tau = list(snapshot.get("tau") or [])
    t_mos = list(snapshot.get("t_mos") or [])
    t_coil = list(snapshot.get("t_coil") or [])
    err = list(snapshot.get("err") or [])
    fault = list(snapshot.get("fault") or [])
    n_rows = len(times)
    n = len(q[0]) if q else 0
    for name, rows in (("q", q), ("dq", dq), ("tau", tau), ("t_mos", t_mos),
                       ("t_coil", t_coil), ("err", err)):
        _rect(name, rows, n_rows, n)
    if len(fault) != n_rows:
        raise ValueError(f"joint_fault 有 {len(fault)} 行，时间轴有 {n_rows} 行")

    picked = _joints(n, joints)
    header = ["t (s)", "joint_fault (mask)"]
    for j in picked:
        for field, unit in PLOT_FIELDS:
            header.append(f"J{j + 1} {field} ({unit})" if unit else f"J{j + 1} {field}")

    t0 = float(times[0])

    def rows(w):
        w.writerow(header)
        for i in range(n_rows):
            line = [f"{float(times[i]) - t0:.6f}", str(int(fault[i]))]
            for j in picked:
                line.extend((_num(q[i][j]), _num(dq[i][j]), _num(tau[i][j]),
                             _num(t_mos[i][j]), _num(t_coil[i][j]), _num(err[i][j])))
            w.writerow(line)

    _atomic_write(path, rows)
    return n_rows


def write_capture_csv(path: str, samples: Sequence, firmware: str = "",
                      hz: float = 300.0) -> int:
    """导出 300 Hz 采集的解析结果；返回写出的数据行数。

    只写固件缓冲里真实存在的字段（tick / q_ref / dq / tau）。温度与错误码在
    100 Hz 状态流里，请用曲线窗口的 CSV。
    """
    if not samples:
        raise ValueError("还没有读回采集数据 —— 先 [读回并预览] 再导出")
    n = len(samples[0].q_ref)
    for i, s in enumerate(samples):
        if not (len(s.q_ref) == len(s.dq) == len(s.tau) == n):
            raise ValueError(f"第 {i} 拍各字段轴数不一致 —— 拒绝导出错位数据")
    if hz <= 0:
        raise ValueError(f"控制频率必须为正: {hz}")

    header = ["tick", "t (s)"]
    for j in range(n):
        for field, unit in CAPTURE_FIELDS:
            header.append(f"J{j + 1} {field} ({unit})")

    t0 = int(samples[0].tick)

    def rows(w):
        w.writerow(header)
        for s in samples:
            ticks = (int(s.tick) - t0) % _TICK_MOD
            line = [str(int(s.tick)), f"{ticks / float(hz):.6f}"]
            for j in range(n):
                line.extend((_num(s.q_ref[j]), _num(s.dq[j]), _num(s.tau[j])))
            w.writerow(line)

    _atomic_write(path, rows)
    return len(samples)
