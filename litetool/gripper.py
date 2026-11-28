"""LiteGrip 夹爪会话 —— CAN 上的独立设备，不与机械臂串口共用。

设计参照 `SdkWorker`，但夹爪走 SocketCAN，有自己的线程与任务队列：

* GUI 只投任务、只读状态快照；所有 `LiteGrip` 调用都在夹爪线程上执行；
* 空闲时按 `poll_s` 取状态（`get_state(wait=True)` 最多等 50 ms）；
* 空闲且使能时按 `keepalive_s`（默认 20 ms）持续发零力矩 MIT 控制帧 —— DM4310
  在最后一帧控制帧后约 100 ms 自锁通信丢失故障（`err=0x0D`），状态帧不能代替
  控制帧；
* 急停/释放走**旁路** `stop()`：零力矩帧，不排队等一条长 `grasp` 走完；
* 仅 Linux：SDK 只支持 SocketCAN，Windows 明确不可用。

`litegrip` 是可选依赖（`requirements-gripper.txt`）。没装/不在 Linux 时构造
本类不会失败，`available()` 会给出原因，页面据此禁用连接。
"""
from __future__ import annotations

from litetool import i18n

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

#: 空闲保活帧的间隔。DM4310 在最后一帧**控制帧**后约 100 ms 自锁通信丢失故障
#: （`err = 0x0D`，见 litegrip-python 的 trajectory.py / gripper.py）；20 ms 留
#: 5 倍余量。状态帧（`0xCC` 刷新）不是控制帧，救不了这个故障。
KEEPALIVE_S = 0.02


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
        name = self.name if not i18n.has_chinese(self.name) else i18n.tr(self.name)
        if i18n.has_chinese(name):
            name = i18n.tr("夹爪任务")
        if self.ok:
            return i18n.tr("{name} 完成", name=name)
        return i18n.tr("{name} 失败: {err}", name=name,
                       err=i18n.safe_detail(self.error) or i18n.tr("未预期错误"))


def availability() -> tuple:
    """`(可用, 原因)` —— 页面在构造时显示原因，不靠用户猜。"""
    if not sys.platform.startswith("linux"):
        return False, i18n.tr("LiteGrip 仅支持 Linux（SocketCAN）")
    try:
        import litegrip  # noqa: F401
    except Exception as e:  # noqa: BLE001 - 未安装/装载失败都按不可用
        # 技术原因不带中文：页面会把它嵌进已翻译的"不可用"提示里；
        # 这里若先翻译/格式化，切语言时就再也匹配不回源串。
        return False, f"litegrip-python: {e}"
    return True, ""


def _state_enabled(st: Any) -> bool:
    """状态快照是否表示"已使能"（旧版快照没有 ``is_enabled`` 时退回错误码）。"""
    flag = getattr(st, "is_enabled", None)
    if flag is not None:
        return bool(flag)
    return getattr(st, "error_code", 0) == 1


class GripperWorker:
    """夹爪的所有者线程。GUI 只投任务、只读 `state`。"""

    def __init__(self, *, factory: Optional[Callable[..., Any]] = None,
                 log: Optional[Callable[[str], None]] = None,
                 on_state: Optional[Callable[[Any], None]] = None,
                 on_task: Optional[Callable[[GripperTaskResult], None]] = None,
                 on_online: Optional[Callable[[bool, str], None]] = None,
                 poll_s: float = 0.1, keepalive_s: float = KEEPALIVE_S):
        self._factory = factory
        self._log = log if log is not None else (lambda m: None)
        self._on_state = on_state if on_state is not None else (lambda st: None)
        self._on_task = on_task if on_task is not None else (lambda r: None)
        self._on_online = on_online if on_online is not None else (lambda ok, why: None)
        self._poll_s = max(0.02, float(poll_s))
        # 20 ms 的 5 倍余量是给 100 ms 故障窗留的；间隔再大就失去意义。
        self._keepalive_s = min(0.05, max(0.005, float(keepalive_s)))
        self._keepalive_warn_at = 0.0

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

    def supports(self, name: str) -> bool:
        """已连接对象是否提供该方法 —— 用来适配安装路径上的不同 `litegrip`。

        `PYTHONPATH` 上可能先命中另一份同名模块（litearm-server 自带的运行时
        自报 2.2.0），它没有 `refresh_status` / 新鲜度字段。页面据此降级并写明
        原因，而不是每个 tick 抛一次 `AttributeError`。
        """
        grip = self._grip
        return grip is not None and callable(getattr(grip, name, None))

    def can_keep_alive(self) -> bool:
        """能否在空闲时发保活帧：`send_mit_frame`，或旧接口 `stop()`。"""
        return self.supports("send_mit_frame") or self.supports("stop")

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
        self._on_online(True, i18n.tr("夹爪已连接 {channel}（{fw}）",
                                      channel=channel, fw=fw) if fw
                        else i18n.tr("夹爪已连接 {channel}", channel=channel))
        self._log(i18n.tr("[OK] 夹爪已连接 {channel} CAN ID=0x{can_id:02X}",
                          channel=channel, can_id=int(can_id)))

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
                self._log(i18n.tr("[WARN] 夹爪断开出错: {err}", err=e))
        if self._online:
            self._online = False
            self._on_online(False, i18n.tr("夹爪已断开"))

    @staticmethod
    def _firmware_of(grip: Any) -> str:
        info = getattr(grip, "info", None)
        return str(getattr(info, "firmware", "") or "") if info is not None else ""

    # ================= 任务 =================
    def submit(self, name: str, fn, on_done=None) -> None:
        if self._grip is None:
            res = GripperTaskResult(name, False,
                                    error=GripperUnavailable(i18n.tr("夹爪未连接")))
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
            return False, i18n.tr("夹爪未连接")
        busy = self._busy.is_set()
        dropped = self.drop_pending(i18n.tr("停止/释放"))
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
                return False, i18n.tr(
                    "零力矩帧已发出，但失能失败（在途动作可能继续）: {err}", err=e)
            extra = i18n.tr(" · 已失能并中止在途动作")
        else:
            extra = ""
        if dropped:
            extra += i18n.tr(" · 已丢弃 {n} 条排队任务", n=dropped)
        return True, i18n.tr("零力矩帧已发出") + extra

    def drop_pending(self, reason: str = "") -> int:
        """丢掉尚未开始的夹爪任务，返回条数。每条都补一次失败回调。"""
        reason = reason or i18n.tr("停止")
        n = 0
        while True:
            try:
                name, _fn, on_done = self._tasks.get_nowait()
            except queue.Empty:
                return n
            n += 1
            res = GripperTaskResult(
                name, False,
                error=RuntimeError(i18n.tr("任务已被丢弃（{reason}）", reason=reason)))
            try:
                (on_done or self._on_task)(res)
            except Exception:  # noqa: BLE001 - GUI 回调出错不能拖垮调用方
                pass

    # ---- 常用动作（页面用） ----
    def enable(self, cb=None) -> None:
        self.submit(i18n.tr("夹爪使能"), lambda g: g.enable(), cb)

    def disable(self, cb=None) -> None:
        self.submit(i18n.tr("夹爪失能"), lambda g: g.disable(), cb)

    def open_jaws(self, speed: Optional[float] = None, cb=None) -> None:
        self.submit(i18n.tr("夹爪张开"), lambda g: g.open(speed), cb)

    def close_jaws(self, speed: Optional[float] = None, cb=None) -> None:
        self.submit(i18n.tr("夹爪闭合"), lambda g: g.close(speed), cb)

    def grasp(self, force_n: Optional[float], hold_s: float, cb=None) -> None:
        self.submit(i18n.tr("夹爪抓取 {force}N/{hold}s", force=force_n, hold=hold_s),
                    lambda g: g.grasp(force_n, hold_s), cb)

    def write_zero(self, cb=None) -> None:
        self.submit(i18n.tr("夹爪写零（不可逆）"), lambda g: g.write_zero(), cb)

    def zero(self, cb=None) -> None:
        self.submit(i18n.tr("夹爪两端标定"), lambda g: g.zero(), cb)

    def save_calibration(self, path: Optional[str], cb=None) -> None:
        self.submit(i18n.tr("保存标定"), lambda g: g.save_calibration(path), cb)

    def load_calibration(self, *, path: Optional[str] = None,
                         mount: Optional[str] = None, cb=None) -> None:
        def fn(g):
            if path:
                return g.load_calibration(path=str(path))
            if mount:
                return g.load_calibration(template=str(mount))
            return g.load_calibration()
        self.submit(i18n.tr("加载标定"), fn, cb)

    def refresh(self, cb=None) -> None:
        self.submit(i18n.tr("刷新夹爪状态"), lambda g: g.refresh_status(), cb)

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
        self.submit(i18n.tr("读取标定"), fn, cb)

    # ================= 所有者线程 =================
    def _loop(self) -> None:
        next_keepalive = 0.0
        while not self._stop.is_set():
            item = self._take()
            if item is not None:
                self._run(*item)
                self._publish_once()
                next_keepalive = time.monotonic() + self._keepalive_s
                continue
            grip = self._grip
            if grip is None:
                return
            enabled = _state_enabled(self.state)
            if enabled and time.monotonic() >= next_keepalive:
                self._keepalive(grip)
                next_keepalive = time.monotonic() + self._keepalive_s
            try:
                st = grip.get_state(wait=True)
            except Exception as e:  # noqa: BLE001 - 连续失败判离线
                self._errors += 1
                self._log(i18n.tr("[WARN] 夹爪状态读取失败: {err}", err=e))
                if self._errors >= 3:
                    self._go_offline(str(e))
                    return
            else:
                self._errors = 0
                with self._lock:
                    self._state = st
                self._on_state(st)
                enabled = _state_enabled(st)
            delay = self._poll_s
            if enabled:
                # 保活必须赶在 100 ms 故障窗之前；不能被 0.1 s 的轮询间隔拖后。
                delay = min(delay, max(0.0, next_keepalive - time.monotonic()))
            if self._stop.wait(delay):
                return

    def _keepalive(self, grip: Any) -> None:
        """空闲时的一帧零力矩 MIT 控制帧 —— 正是压住通信丢失自锁的那一帧。

        优先 `send_mit_frame`（新版接口）；没有它时退回 `stop()`，两者发的都是
        ``q/kp/kd = 0`` 的控制帧。发送失败只记日志、不拖垮线程：下一次状态轮询
        会把真实故障报上来。
        """
        send = getattr(grip, "send_mit_frame", None)
        try:
            if callable(send):
                send(q=0.0, kp=0.0, kd=0.0)
                return
            stop = getattr(grip, "stop", None)
            if callable(stop):
                stop()
        except Exception as e:  # noqa: BLE001 - 保活失败必须可见，但不能停线程
            now = time.monotonic()
            if now - self._keepalive_warn_at >= 1.0:
                self._keepalive_warn_at = now
                self._log(i18n.tr("[WARN] 夹爪保活帧发送失败: {err}", err=e))

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
                name, False,
                error=RuntimeError(i18n.tr("已按停止/释放中止{detail}", detail=detail)))
        elif self._stop.is_set() and res.ok:
            res = GripperTaskResult(name, False,
                                    error=RuntimeError(i18n.tr("夹爪已断开")))
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
        self._log(i18n.tr("[ERR] 夹爪离线: {why}", why=why))
        self._on_online(False, why)
