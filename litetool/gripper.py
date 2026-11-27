"""LiteGrip 夹爪会话 —— CAN 上的独立设备，不与机械臂串口共用。

设计参照 `SdkWorker`，但夹爪走 SocketCAN，有自己的线程与任务队列：

* GUI 只投任务、只读状态快照；所有 `LiteGrip` 调用都在夹爪线程上执行；
* 空闲时按 `poll_s` 取状态（`get_state(wait=True)` 最多等 50 ms）；
* 急停/释放走**旁路** `stop()`：零力矩帧，不排队等一条长 `grasp` 走完；
* 仅 Linux：SDK 只支持 SocketCAN，Windows 明确不可用。

`litegrip` 是可选依赖（`requirements-gripper.txt`）。没装/不在 Linux 时构造
本类不会失败，`available()` 会给出原因，页面据此禁用连接。
"""
from __future__ import annotations

import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = ["GripperWorker", "GripperTaskResult", "GripperUnavailable",
           "list_channels"]

#: ``ARPHRD_CAN``, the ``type`` value ``/sys/class/net/<dev>/type`` reports for a
#: SocketCAN interface. Enumerating through this rather than trying ``can0``,
#: ``can1``, ``can2`` is what lets a machine whose adapter the driver called
#: ``can3``, or ``vcan0``, be configured without editing code.
ARPHRD_CAN = 280

#: Where the kernel keeps the per-interface attributes. Overridable so the
#: enumeration can be tested against a fake tree instead of the test machine's
#: real interfaces.
SYS_CLASS_NET = "/sys/class/net"


def list_channels(sys_class_net: str = SYS_CLASS_NET) -> list:
    """Every CAN interface the kernel knows about, sorted by name.

    Reads ``/sys/class/net/*/type`` and keeps the entries whose value is
    ``ARPHRD_CAN`` (280). A missing or unreadable ``/sys/class/net`` returns an
    empty list rather than raising: a machine with no CAN support has no
    channels, which is a fact the UI shows rather than an error to handle.
    """
    root = Path(sys_class_net)
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    out = []
    for entry in entries:
        try:
            value = (entry / "type").read_text(encoding="ascii").strip()
        except OSError:
            continue
        try:
            if int(value) == ARPHRD_CAN:
                out.append(entry.name)
        except ValueError:
            continue
    return out


class GripperUnavailable(RuntimeError):
    """夹爪 SDK 不可用（平台不对/未安装）。"""


@dataclass
class GripperTaskResult:
    name: str
    ok: bool
    value: Any = None
    error: Optional[BaseException] = None

    @property
    def text(self) -> str:
        if self.ok:
            return f"{self.name} 完成"
        return f"{self.name} 失败: {self.error}"


def availability() -> tuple:
    """`(可用, 原因)` —— 页面在构造时显示原因，不靠用户猜。"""
    if not sys.platform.startswith("linux"):
        return False, "LiteGrip 仅支持 Linux（SocketCAN）"
    try:
        import litegrip  # noqa: F401
    except Exception as e:  # noqa: BLE001 - 未安装/装载失败都按不可用
        return False, f"未安装 litegrip-python: {e}"
    return True, ""


class GripperWorker:
    """夹爪的所有者线程。GUI 只投任务、只读 `state`。"""

    def __init__(self, *, factory: Optional[Callable[..., Any]] = None,
                 log: Optional[Callable[[str], None]] = None,
                 on_state: Optional[Callable[[Any], None]] = None,
                 on_task: Optional[Callable[[GripperTaskResult], None]] = None,
                 on_online: Optional[Callable[[bool, str], None]] = None,
                 poll_s: float = 0.1):
        self._factory = factory
        self._log = log if log is not None else (lambda m: None)
        self._on_state = on_state if on_state is not None else (lambda st: None)
        self._on_task = on_task if on_task is not None else (lambda r: None)
        self._on_online = on_online if on_online is not None else (lambda ok, why: None)
        self._poll_s = max(0.02, float(poll_s))

        self._grip: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._tasks: "queue.Queue[tuple]" = queue.Queue()
        self._busy = threading.Event()
        #: 停止/释放请求落在**在途任务**上：任务返回后按"已中止"上报，而不是成功。
        self._interrupted = threading.Event()
        self._lock = threading.Lock()
        self._state: Any = None
        self._online = False
        self._errors = 0

    # ================= 可用性 / 生命周期 =================
    def available(self) -> tuple:
        if self._factory is not None:
            return True, ""
        return availability()

    @property
    def state(self) -> Any:
        with self._lock:
            return self._state

    @property
    def online(self) -> bool:
        return self._online

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    @property
    def grip(self) -> Any:
        """**仅供只读/无阻塞调用**（读缓存属性等）。写命令一律走 `submit()`。"""
        return self._grip

    def _make(self, *, channel: str, can_id: int, mst_id: Optional[int]) -> Any:
        if self._factory is not None:
            return self._factory(channel=channel, can_id=can_id, mst_id=mst_id)
        from litegrip import LiteGrip
        return LiteGrip(channel=channel, can_id=can_id, mst_id=mst_id)

    def open(self, *, channel: str = "can0", can_id: int = 0x08,
             mst_id: Optional[int] = None, mount: Optional[str] = None,
             calibration_path: Optional[str] = None) -> None:
        """连接并加载标定。失败原样抛出（页面显示原因）。

        `calibration_path` 优先；否则 `mount`（`normal` / `reverse`）；
        都没有时加载 SDK 附带**出厂标定**（正装）。未标定的夹爪不允许运动，
        SDK 自己会拒绝。
        """
        ok, why = self.available()
        if not ok:
            raise GripperUnavailable(why)
        self.close()
        grip = self._make(channel=channel, can_id=int(can_id),
                          mst_id=None if not mst_id else int(mst_id))
        try:
            grip.connect()
            if calibration_path:
                grip.load_calibration(path=str(calibration_path))
            elif mount:
                grip.load_calibration(template=str(mount))
            else:
                grip.load_calibration()
        except Exception:
            try:
                grip.disconnect()
            except Exception:  # noqa: BLE001
                pass
            raise
        self._grip = grip
        with self._lock:
            self._state = None
        self._errors = 0
        self._stop.clear()
        self._online = True
        self._thread = threading.Thread(target=self._loop, name="gripper-worker",
                                        daemon=True)
        self._thread.start()
        fw = self._firmware_of(grip)
        self._on_online(True, f"夹爪已连接 {channel}（{fw}）" if fw
                        else f"夹爪已连接 {channel}")
        self._log(f"[OK] 夹爪已连接 {channel} CAN ID=0x{int(can_id):02X}")

    def close(self) -> None:
        """停线程 → 断开（SDK 默认先失能）。"""
        self._stop.set()
        th, self._thread = self._thread, None
        if th is not None and th.is_alive():
            th.join(timeout=3.0)
        grip, self._grip = self._grip, None
        with self._lock:
            self._state = None
        if grip is not None:
            try:
                grip.disconnect()
            except Exception as e:  # noqa: BLE001 - 关闭失败不该阻断退出
                self._log(f"[WARN] 夹爪断开出错: {e}")
        if self._online:
            self._online = False
            self._on_online(False, "夹爪已断开")

    @staticmethod
    def _firmware_of(grip: Any) -> str:
        info = getattr(grip, "info", None)
        return str(getattr(info, "firmware", "") or "") if info is not None else ""

    # ================= 任务 =================
    def submit(self, name: str, fn, on_done=None) -> None:
        if self._grip is None:
            res = GripperTaskResult(name, False,
                                    error=GripperUnavailable("夹爪未连接"))
            (on_done or self._on_task)(res)
            return
        self._tasks.put((name, fn, on_done))

    def stop_now(self) -> tuple:
        """**旁路**停止/释放：零力矩帧，动作在途时再失能，并丢弃排队任务。

        与机械臂的急停同一类通道：只写不读、不经过任务队列。但**一帧零力矩挡不住
        正在跑的 `grasp` 保力循环** —— 它下一拍就会把力矩写回来。所以：

        * 有动作在途（`_busy`）→ 补一次 `disable()`：SDK 的下一次 `send_mit_frame`
          会因未使能直接失败，保力/行进循环随即退出，`_interrupt` 让这次任务按
          "已中止"上报，而不是成功；
        * 排队中的任务一律丢弃（语义同机械臂的 `drop_pending`）—— 用户按"停止"之后
          不该再执行任何排队的抓取；
        * 空闲时只发零力矩帧，不动使能态。

        返回 `(ok, 说明)`；ok=False 表示停止没有完整生效，调用方必须如实提示。
        """
        grip = self._grip
        if grip is None:
            return False, "夹爪未连接"
        busy = self._busy.is_set()
        dropped = self.drop_pending("停止/释放")
        if busy:
            # 只标记在途任务；排队任务已经被丢掉，不会误伤下一条新任务。
            self._interrupted.set()
        try:
            grip.stop()
        except Exception as e:  # noqa: BLE001 - 失败必须如实上报
            return False, str(e)
        if busy:
            # 零力矩帧已经发出；失能失败必须说清楚 —— 在途动作可能还在继续。
            try:
                grip.disable()
            except Exception as e:  # noqa: BLE001
                return False, (f"零力矩帧已发出，但失能失败（在途动作可能继续）: {e}")
            extra = " · 已失能并中止在途动作"
        else:
            extra = ""
        if dropped:
            extra += f" · 已丢弃 {dropped} 条排队任务"
        return True, "零力矩帧已发出" + extra

    def drop_pending(self, reason: str = "停止") -> int:
        """丢掉尚未开始的夹爪任务，返回条数。每条都补一次失败回调。"""
        n = 0
        while True:
            try:
                name, _fn, on_done = self._tasks.get_nowait()
            except queue.Empty:
                return n
            n += 1
            res = GripperTaskResult(
                name, False, error=RuntimeError(f"任务已被丢弃（{reason}）"))
            try:
                (on_done or self._on_task)(res)
            except Exception:  # noqa: BLE001 - GUI 回调出错不能拖垮调用方
                pass

    # ---- 常用动作（页面用） ----
    def enable(self, cb=None) -> None:
        self.submit("夹爪使能", lambda g: g.enable(), cb)

    def disable(self, cb=None) -> None:
        self.submit("夹爪失能", lambda g: g.disable(), cb)

    def open_jaws(self, speed: Optional[float] = None, cb=None) -> None:
        self.submit("夹爪张开", lambda g: g.open(speed), cb)

    def close_jaws(self, speed: Optional[float] = None, cb=None) -> None:
        self.submit("夹爪闭合", lambda g: g.close(speed), cb)

    def grasp(self, force_n: Optional[float], hold_s: float, cb=None) -> None:
        self.submit(f"夹爪抓取 {force_n}N/{hold_s}s",
                    lambda g: g.grasp(force_n, hold_s), cb)

    def write_zero(self, cb=None) -> None:
        self.submit("夹爪写零（不可逆）", lambda g: g.write_zero(), cb)

    def zero(self, cb=None) -> None:
        self.submit("夹爪两端标定", lambda g: g.zero(), cb)

    def save_calibration(self, path: Optional[str], cb=None) -> None:
        self.submit("保存标定", lambda g: g.save_calibration(path), cb)

    def load_calibration(self, *, path: Optional[str] = None,
                         mount: Optional[str] = None, cb=None) -> None:
        def fn(g):
            if path:
                return g.load_calibration(path=str(path))
            if mount:
                return g.load_calibration(template=str(mount))
            return g.load_calibration()
        self.submit("加载标定", fn, cb)

    def refresh(self, cb=None) -> None:
        self.submit("刷新夹爪状态", lambda g: g.refresh_status(), cb)

    def calibration(self, cb=None) -> None:
        """读回当前标定的摘要（给页面显示行程/方向/是否已标定）。"""
        def fn(g):
            c = g.config
            return {
                "channel": g.channel, "can_id": g.can_id, "mst_id": g.mst_id,
                "calibrated": bool(c.calibrated), "mount": c.mount,
                "closed_rad": float(c.pos_closed_rad),
                "open_rad": float(c.pos_open_rad),
                "travel_mm": abs(float(c.pos_open_rad) - float(c.pos_closed_rad))
                * float(c.rad_to_mm),
            }
        self.submit("读取标定", fn, cb)

    # ================= 所有者线程 =================
    def _loop(self) -> None:
        while not self._stop.is_set():
            item = self._take()
            if item is not None:
                self._run(*item)
                self._publish_once()
                continue
            grip = self._grip
            if grip is None:
                return
            try:
                st = grip.get_state(wait=True)
            except Exception as e:  # noqa: BLE001 - 连续失败判离线
                self._errors += 1
                self._log(f"[WARN] 夹爪状态读取失败: {e}")
                if self._errors >= 3:
                    self._go_offline(str(e))
                    return
            else:
                self._errors = 0
                with self._lock:
                    self._state = st
                self._on_state(st)
            if self._stop.wait(self._poll_s):
                return

    def _publish_once(self) -> None:
        grip = self._grip
        if grip is None:
            return
        try:
            st = grip.get_state(wait=False)
        except Exception:  # noqa: BLE001 - 任务后的顺手刷新失败不算离线
            return
        with self._lock:
            self._state = st
        self._on_state(st)

    def _take(self):
        try:
            return self._tasks.get_nowait()
        except queue.Empty:
            return None

    def _run(self, name: str, fn, on_done) -> None:
        self._busy.set()
        try:
            value = fn(self._grip)
            res = GripperTaskResult(name, True, value=value)
        except BaseException as e:  # noqa: BLE001 - 全部报给 GUI
            res = GripperTaskResult(name, False, error=e)
        finally:
            self._busy.clear()
        if self._interrupted.is_set():
            # 这一条是在途任务，被 stop_now() 中止：不管底层返回什么，都按"已中止"
            # 上报 —— 否则界面会把一次被打断的抓取显示成"完成"。
            self._interrupted.clear()
            detail = f"（{res.error}）" if not res.ok and res.error else ""
            res = GripperTaskResult(
                name, False, error=RuntimeError(f"已按停止/释放中止{detail}"))
        elif self._stop.is_set() and res.ok:
            res = GripperTaskResult(name, False,
                                    error=RuntimeError("夹爪已断开"))
        self._log(f"[{'OK' if res.ok else 'ERR'}] {res.text}")
        try:
            (on_done or self._on_task)(res)
        except Exception:  # noqa: BLE001 - GUI 回调出错不能拖垮线程
            pass

    def _go_offline(self, why: str) -> None:
        grip, self._grip = self._grip, None
        self._online = False
        if grip is not None:
            try:
                grip.disconnect()
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            self._state = None
        self._log(f"[ERR] 夹爪离线: {why}")
        self._on_online(False, why)
