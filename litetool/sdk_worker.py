"""SdkWorker —— **唯一**持有 `litearm_core.Arm` 的线程，串口的唯一读者。

为什么要独占
------------
`litearm_core` 的 `Arm` 是按**单消费者**设计的：`_Ack.expect` / `pump` /
`_read_status` / `get_status_now` 都直接从同一条串口抢帧。若 GUI 一边轮询状态、
一边下命令（两条读线程），状态轮询会把命令的 ACK 吃掉 —— 表现为随机的
"无应答(超时)"。所以本模块把**全部** SDK 调用收进一个线程：

    空闲 ──▶ arm.get_state(refresh=True)   # 固件 100Hz 主动推 → 天然 100Hz 状态源
    有任务 ─▶ 执行 fn(arm)                  # 与空闲轮询串行，永不并发

`Arm` 的读写各一把锁、且读写之间不互斥的设计因此完全成立；SDK **零改动**。

状态钩子（唯一一处私有耦合）
----------------------------
`arm.movej()` 这类阻塞调用会在内部 `_Ack.pump()` 里消费串口帧，但不会交给 GUI ——
运动期间曲线会冻住，而那恰恰是最该看曲线的时刻。故在 connect 后把
`arm._a._on_status` 包一层：解码出的 `RobotState` 除喂给 SDK 自己外，也推给
`PlotModel`。所有路径都收敛到这一个方法，一处挂钩即全覆盖。

`_attach_state_hook()` 挂不上时**抛错**而非静默降级，`tests/test_sdk_hook.py`
守着该缝隙存在 —— SDK 若改名，测试先红，而不是曲线悄悄不画了。
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import litearm_core as pa
from litearm_core import _protocol as _P

from litetool.plot_model import PlotModel

__all__ = ["SdkWorker", "TaskResult", "StateHookMissing"]

#: seq 位宽 —— 固件 1.5.0 起为真 u16（仅发送成功才计数），旧布局 8 位回绕。
SEQ_MOD = 0x10000


class StateHookMissing(RuntimeError):
    """`Arm` 上找不到状态钩子缝隙（SDK 改了内部结构）。"""


@dataclass
class TaskResult:
    """一次已提交任务的结果，回调给 GUI 主线程。"""

    name: str
    ok: bool
    value: Any = None
    error: Optional[BaseException] = None

    @property
    def text(self) -> str:
        if self.ok:
            return f"{self.name} 完成"
        return f"{self.name} 失败: {self.error}"


def _attach_state_hook(arm, on_state: Callable[[Any], None]) -> None:
    """把 `_Ack._on_status` 包一层，让每帧解码结果也流向 GUI。

    这是本工具对 SDK 唯一的私有耦合。挂不上时抛 `StateHookMissing` ——
    宁可启动即报错，也不要"连上了但曲线不动"这种要查半天的静默降级。
    """
    ack = getattr(arm, "_a", None)
    if ack is None or not callable(getattr(ack, "_on_status", None)):
        raise StateHookMissing(
            "litearm_core.Arm 上找不到 _a._on_status 状态钩子缝隙 —— "
            "SDK 内部结构变了。本工具依赖它把运动期间的 100Hz 状态也画到曲线上；"
            "请更新 litetool/sdk_worker.py::_attach_state_hook 以适配新版 SDK。")
    orig = ack._on_status

    def hooked(payload: bytes) -> None:
        orig(payload)
        st = ack.state
        if st is not None:
            on_state(st)

    ack._on_status = hooked


class SdkWorker:
    """串口 + SDK 的所有者线程。GUI 只投任务、只读快照。

    用法::

        w = SdkWorker(log=print, on_online=..., on_task=...)
        w.open("/dev/ttyACM0")          # 连接并起线程（阻塞 < 2s）
        w.submit("enable", lambda arm: arm.enable())
        st = w.state                    # 最近一帧（线程安全）
        w.close()
    """

    def __init__(self, *, arm_factory: Optional[Callable[[Optional[str]], Any]] = None,
                 log: Optional[Callable[[str], None]] = None,
                 on_online: Optional[Callable[[bool, str], None]] = None,
                 on_task: Optional[Callable[[TaskResult], None]] = None,
                 clock: Callable[[], float] = time.monotonic,
                 offline_timeout: float = 1.0,
                 idle_timeout: float = 0.15,
                 plot_window_s: float = 30.0):
        self._factory = arm_factory or (lambda port: pa.Arm(port=port).connect())
        self._log = log if log is not None else (lambda m: None)
        self._on_online = on_online if on_online is not None else (lambda ok, why: None)
        self._on_task = on_task if on_task is not None else (lambda r: None)
        self._clock = clock
        self._offline_timeout = offline_timeout
        self._idle_timeout = idle_timeout

        self.model = PlotModel(window_s=plot_window_s, clock=clock)

        self._arm: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._tasks: "queue.Queue[tuple]" = queue.Queue()
        self._busy = threading.Event()
        self._lock = threading.Lock()
        self._state: Any = None
        self._last_pushed = None
        self._prev_seq: Optional[int] = None
        self._drops = 0
        self._online = False
        self._firmware = ""

    # ================= 生命周期 =================
    @property
    def arm(self) -> Any:
        """**仅供只读/无阻塞调用**（读缓存属性等）。写命令一律走 `submit()`。"""
        return self._arm

    def open(self, port: Optional[str] = None) -> None:
        """连接并启动所有者线程。失败抛 SDK 的异常（由 GUI 捕获提示）。

        连接在调用方线程上完成（此时线程还没起，不存在并发持有者），
        随后才启动循环 —— `Arm` 对象跨线程移交是安全的，因为任一时刻只有一个持有者。
        """
        self.close()
        arm = self._factory(port)
        try:
            _attach_state_hook(arm, self._on_state)
        except Exception:
            arm.close()
            raise
        self._arm = arm
        self._firmware = getattr(arm, "firmware", "") or ""
        with self._lock:
            self._state = None
            self._last_pushed = None
            self._prev_seq = None
            self._drops = 0
        self.model.reset()
        self._stop.clear()
        self._online = True
        self._thread = threading.Thread(target=self._loop, name="sdk-worker", daemon=True)
        self._thread.start()
        self._on_online(True, f"已连接 {port or '自动'} · {self._firmware}")
        self._log(f"[OK] 已连接 {port or '自动'} · 固件 {self._firmware} · N={self.n_joints}")

    def close(self) -> None:
        """停线程 → 关链路（顺序不能反：先让所有者退出，再释放串口）。"""
        self._stop.set()
        th, self._thread = self._thread, None
        if th is not None and th.is_alive():
            th.join(timeout=3.0)
            if th.is_alive():
                # 在途的 SDK 调用（如十几秒的 movej）不可抢占。放开串口会让它
                # 带着 TransportError 退出，属可接受降级 —— 但必须留痕。
                self._log("[WARN] 关闭时所有者线程仍在执行任务（阻塞调用不可抢占），"
                          "已直接释放串口")
        arm, self._arm = self._arm, None
        if arm is not None:
            try:
                arm.close()
            except Exception as e:  # noqa: BLE001 - 关闭失败不该阻断退出
                self._log(f"[WARN] 关闭链路出错: {e}")
        with self._lock:
            self._state = None
            self._last_pushed = None
        if self._online:
            self._online = False
            self._on_online(False, "已断开")

    # ================= 快照（线程安全只读） =================
    @property
    def state(self):
        """最近一帧 `RobotState`，或 None。"""
        with self._lock:
            return self._state

    @property
    def online(self) -> bool:
        return self._online

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    @property
    def firmware(self) -> str:
        return self._firmware

    @property
    def n_joints(self) -> int:
        return int(getattr(self._arm, "n", 0) or 0)

    @property
    def drops(self) -> int:
        """按 seq 差分累计的**接收侧**丢帧。"""
        return self._drops

    @property
    def last_reset_reason(self) -> Optional[str]:
        """上次启动原因（`"normal"` / `"iwdg-rst"`），未收到开机签名时 None。"""
        arm = self._arm
        try:
            return arm.last_reset_reason if arm is not None else None
        except Exception:  # noqa: BLE001
            return None

    # ================= 命令 =================
    def submit(self, name: str, fn: Callable[[Any], Any],
               on_done: Optional[Callable[[TaskResult], None]] = None) -> None:
        """把 `fn(arm)` 排进所有者线程执行。`fn` 里可以放任意阻塞的 SDK 调用。"""
        if self._arm is None:
            res = TaskResult(name, False, error=pa.NotConnectedError("未连接"))
            (on_done or self._on_task)(res)
            return
        self._tasks.put((name, fn, on_done))

    def emergency_now(self) -> tuple:
        """**插队**急停：GUI 线程直接写帧，不排队、不等 ACK。

        在途的 `movej` 可能正把所有者线程占住十几秒 —— 急停必须绕开队列。这里只
        **写不读**：`Arm._write_cmd(guarded=False)` 在 SDK 的写锁内原子交帧，既不会
        被在途命令阻塞，也不会与所有者线程的读抢帧（SDK 的读者锁与写者锁本就分离，
        它自己的 `zero_g` 保活线程用的就是这条路径）。

        返回 `(ok, 说明)`。ok=False 表示帧**没发出去** —— 调用方必须如实提示用户
        "急停未下发，请用硬件急停/断电"，绝不宣称已失能。
        """
        arm = self._arm
        if arm is None:
            return False, "未连接"
        try:
            arm._write_cmd(_P.CMD_EMERGENCY_STOP, guarded=False)
        except Exception as e:  # noqa: BLE001 - 任何失败都必须如实上报
            return False, str(e)
        return True, "急停帧已发出"

    def stop_zero_g_now(self) -> Optional[str]:
        """急停时收掉零重力会话 —— 返回错误说明，正常则 None。

        为什么必须做：`zero_g` 保活线程每 40ms 重发一条 `CMD_ZERO_G(on=1)`。固件在
        EMERGENCY 下会拒收它（`ctrl_accept_zero_g` 开头就 `return false`），所以
        **不会**把臂从急停里顶出来 —— 但那条线程会一直空转发帧，而界面还显示
        "拖动中"，与实际状态相反。

        与 `emergency_now` 同理走**旁路**（直接调 SDK、不经任务队列）：队列可能正被
        在途的长命令占住。`zero_g_stop` 只写一帧 off + join 自己的保活线程，不读串口。
        """
        arm = self._arm
        if arm is None or not getattr(arm, "zero_g_active", False):
            return None
        try:
            arm.zero_g_stop(raise_on_lost=False)
        except Exception as e:  # noqa: BLE001 - 收不掉也要让上层知道
            return str(e)
        return None

    def drop_pending(self) -> int:
        """丢掉尚未开始执行的任务，返回丢弃条数。

        急停之后不该再执行任何排队中的动作 —— 用户按急停的语义就是"停下"。
        正在执行的**那一条**没法中断（SDK 调用不可抢占），但它的结果会被固件的
        EMERGENCY 锁存拒掉（`ERR{cmd,0x06}`），不会真的动臂。

        ⚠ **[2026-09-14] 被丢的每一条都必须补一次 `on_done(TaskResult(ok=False))`**。
        静默丢弃会让发起方的"忙"态永远解不开 —— 页面的 `_busy` 是在 `_start` 里置位、
        只在 `_on_*_done` 里清除的, 回调不来就**只能重启进程**。急停路径尤其致命:
        参数页按钮全灰, 而用户按急停恰恰是最需要界面还能用的时候。
        """
        n = 0
        while True:
            try:
                name, _fn, on_done = self._tasks.get_nowait()
            except queue.Empty:
                return n
            n += 1
            res = TaskResult(name, False,
                             error=RuntimeError("任务已被丢弃（急停）"))
            try:
                (on_done or self._on_task)(res)
            except Exception:                 # noqa: BLE001 - GUI 回调出错不能拖垮所有者线程
                pass

    # ================= 所有者线程 =================
    def _loop(self) -> None:
        silent_since: Optional[float] = None
        while not self._stop.is_set():
            item = self._take()
            if item is not None:
                self._run(*item)
                silent_since = None
                continue
            try:
                st = self._arm.get_state(refresh=True, timeout=self._idle_timeout)
            except pa.CommandRejectedError as e:
                # 固件对读状态回 ERR（罕见）：不判离线，记一次继续
                self._log(f"[WARN] 状态读取被固件拒绝: {e}")
                continue
            except pa.LiteArmError as e:
                self._go_offline(f"链路异常: {e}")
                return
            except Exception as e:  # noqa: BLE001 - 线程不能带着异常死掉
                self._go_offline(f"未预期异常: {e!r}")
                return
            if st is None:
                if silent_since is None:
                    silent_since = self._clock()
                elif self._clock() - silent_since > self._offline_timeout:
                    self._go_offline(f"状态流静默 >{self._offline_timeout:.1f}s")
                    return
            else:
                silent_since = None

    def _take(self):
        try:
            return self._tasks.get_nowait()
        except queue.Empty:
            return None

    def _run(self, name: str, fn, on_done) -> None:
        self._busy.set()
        try:
            value = fn(self._arm)
            res = TaskResult(name, True, value=value)
        except BaseException as e:  # noqa: BLE001 - 用户代码里的任何异常都要报给 GUI
            res = TaskResult(name, False, error=e)
        finally:
            self._busy.clear()
        # [2026-09-14] **回调必达是本类的契约** —— 原实现在 `_stop` 已置位时直接
        # `return`, 于是"断开/关闭时正在跑的那一条"永远等不到回调, 发起方的忙态
        # 卡死。改成照常投递 (只是把 ok 标成 False 并附上原因)。
        if self._stop.is_set() and res.ok:
            res = TaskResult(name, False, error=RuntimeError("已断开"))
        try:
            (on_done or self._on_task)(res)
        except Exception:  # noqa: BLE001 - GUI 回调出错不能拖垮所有者线程
            pass

    def _go_offline(self, why: str) -> None:
        if not self._online:
            return
        self._online = False
        self._busy.clear()
        # 丢弃快照：链路已死还把最后一帧当实时数据回显，会让人以为臂还在那里。
        # 清掉之后 GUI 的 20Hz tick 拿到 None，状态条/表格如实显示"—"。
        with self._lock:
            self._state = None
            self._last_pushed = None
        self._log(f"[ERR] 离线: {why}")
        self._on_online(False, why)

    # ================= 状态流入（所有者线程上下文） =================
    def _on_state(self, st) -> None:
        with self._lock:
            self._state = st
            fresh = st is not self._last_pushed
            if fresh:
                self._last_pushed = st
        if not fresh:
            return                     # 空闲轮询会重复拿到同一帧，只推一次
        self._count_drops(st.seq)
        self.model.push(st)

    def _count_drops(self, seq: int) -> None:
        prev = self._prev_seq
        if prev is not None:
            gap = (seq - prev) % SEQ_MOD
            if 1 < gap < SEQ_MOD // 2:      # 只认小正向跳变；半圈以上视为序号重置
                self._drops += gap - 1
        self._prev_seq = seq
