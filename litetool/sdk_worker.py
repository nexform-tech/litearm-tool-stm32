"""SdkWorker —— **唯一**持有 `litearm.Arm` 的线程，串口的唯一读者。

为什么要独占
------------
`litearm` 的 `Arm` 是按**单消费者**设计的：`_Ack.expect` / `pump` /
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
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import litearm as pa
from litearm import _protocol as _P

from litetool import i18n
from litetool.plot_model import PlotModel

__all__ = ["SdkWorker", "TaskResult", "StateHookMissing",
           "exit_zero_g_and_hold"]

#: seq 位宽 —— 固件 1.5.0 起为真 u16（仅发送成功才计数），旧布局 8 位回绕。
SEQ_MOD = 0x10000


class _RunToken:
    """一次 `open()` 的世代令牌 —— 每个所有者线程只认自己这一份。

    为什么不能共用一个 `Event`：`close()` 的 join 有上限（在途 SDK 调用不可抢占），
    旧线程可能还卡在 `_factory(port)` 里。原来的 `open()` 会对**同一个** Event 调
    `clear()`，等于把已停止的旧线程重新唤醒 —— 它和新线程同时跑 `_reconnect()`，
    抢 `_arm`/`_port`，还一直去拨已经不存在的口（issue #43）。

    现在 `close()` 只 set 当前令牌，`open()` 换一个**新**令牌；旧线程的令牌永远是
    set 状态，且 `token is not self._token` 让它无法再碰共享状态。
    """

    __slots__ = ("stop",)

    def __init__(self) -> None:
        self.stop = threading.Event()


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
            return i18n.tr("{name} 完成", name=self.name)
        code, title = _error_summary(self.error)
        return i18n.tr("{name} 失败 [{code}]: {title}",
                       name=self.name, code=code, title=title)


def _error_summary(e: Optional[BaseException]) -> tuple:
    """异常 -> (码, 标题)。码来自 SDK 的 `describe_exc`，旧 SDK 回退 E-??。

    本地错误（`E-xx`）的标题是通用文案，可能掩盖具体状态（例如 E-17 只知道
    "零重力进行中"，原异常里还有"先 zero_g_stop"）。把原始消息附在标题后。
    """
    try:
        t = pa.describe_exc(e, locale=i18n.sdk_locale())
    except Exception:  # noqa: BLE001 - 老 SDK / 异常对象不规整都回退
        return "E-??", (i18n.safe_detail(e) or i18n.tr("未预期错误"))
    if i18n.language() == "en" and i18n.has_chinese(t.title):
        # 老 SDK / 非结构化异常会把原始中文塞进 E-?? 标题；英文界面用通用文案接管。
        return "E-??", i18n.tr("未预期错误")
    msg = i18n.safe_detail(str(e or "").strip())
    if t.code.startswith("E-") and msg and msg not in t.title:
        if len(msg) > 120:
            msg = msg[:117] + "..."
        return t.code, f"{t.title}：{msg}"
    return t.code, t.title


def _attach_state_hook(arm, on_state: Callable[[Any], None]) -> None:
    """把 `_Ack._on_status` 包一层，让每帧解码结果也流向 GUI。

    这是本工具对 SDK 唯一的私有耦合。挂不上时抛 `StateHookMissing` ——
    宁可启动即报错，也不要"连上了但曲线不动"这种要查半天的静默降级。
    """
    ack = getattr(arm, "_a", None)
    if ack is None or not callable(getattr(ack, "_on_status", None)):
        raise StateHookMissing(i18n.tr(
            "litearm.Arm 上找不到 _a._on_status 状态钩子缝隙 —— "
            "SDK 内部结构变了。本工具依赖它把运动期间的 100Hz 状态也画到曲线上；"
            "请更新 litetool/sdk_worker.py::_attach_state_hook 以适配新版 SDK。"))
    orig = ack._on_status

    def hooked(payload: bytes) -> None:
        orig(payload)
        st = ack.state
        if st is not None:
            on_state(st)

    ack._on_status = hooked


def exit_zero_g_and_hold(arm, timeout: float = 1.0, speed: float = 0.15):
    """退出零重力后立刻补一条**零位移 `movej`**，把臂留在持位态。

    为什么需要：`zero_g_stop()` 只发一帧 `0x06 off`，之后没有命令；固件 0.1 s
    命令看门狗会进入 fail-soft hold（`tau=0`, `kp=0.6×`），臂按
    `G/(0.6·kp)` 下沉（本臂 J2 实测约 0.04 rad）。**显式退出不是 PC 掉线**，
    退出后应保持。`movej` 到当前实测 q 会把模式切到 `MOVE_J`；固件在该模式
    **每拍自动 kick 看门狗**，并持续给重力前馈。

    只在退出后的模式为 `INIT` 时补：若 `ctrl_zero_g_leave()` 已因越限启动了
    回程 `move_j`，模式已经是 `MOVE_J`，不能再发一条覆盖它。

    返回最终 `RobotState`（链路静默时可能为 `None`）；`zero_g_stop` / `movej`
    的异常原样上抛，由任务层显示。
    """
    arm.zero_g_stop(True)
    deadline = time.monotonic() + max(0.0, float(timeout))
    st = None
    while True:
        raw = arm.get_state()
        st = getattr(raw, "value", raw)
        if getattr(st, "mode_name", None) != "ZERO_G":
            break
        if time.monotonic() >= deadline:
            return st
        time.sleep(0.01)
    if st is not None and getattr(st, "mode_name", None) == "INIT":
        q = [j.q for j in st.joints]
        return arm.movej(q, speed=speed)
    return st


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
                 on_reconnect: Optional[Callable[[int, str], None]] = None,
                 clock: Callable[[], float] = time.monotonic,
                 offline_timeout: float = 1.0,
                 idle_timeout: float = 0.15,
                 plot_window_s: float = 30.0,
                 auto_reconnect: bool = True,
                 reconnect_initial_s: float = 0.5,
                 reconnect_max_s: float = 5.0,
                 close_join_s: float = 3.0):
        self._factory = arm_factory or (lambda port: pa.Arm(port=port).connect())
        self._log = log if log is not None else (lambda m: None)
        self._on_online = on_online if on_online is not None else (lambda ok, why: None)
        self._on_task = on_task if on_task is not None else (lambda r: None)
        self._on_reconnect = on_reconnect if on_reconnect is not None else \
            (lambda attempt, why: None)
        self._clock = clock
        self._offline_timeout = offline_timeout
        self._idle_timeout = idle_timeout
        self._auto_reconnect = bool(auto_reconnect)
        self._reconnect_initial = max(0.01, float(reconnect_initial_s))
        self._reconnect_max = max(self._reconnect_initial, float(reconnect_max_s))
        #: `close()` 等待在途所有者线程的上限。生产上 3 s；测试需要快速模拟
        #: "join 超时、旧线程还活着"的现场，所以可注入更短的值。
        self._close_join_s = max(0.0, float(close_join_s))

        self.model = PlotModel(window_s=plot_window_s, clock=clock)

        self._arm: Any = None
        self._thread: Optional[threading.Thread] = None
        #: 当前世代。`_stop` 是它的只读兼容入口（测试模拟"关闭中"）。
        self._token = _RunToken()
        self._gen_lock = threading.Lock()
        self._tasks: "queue.Queue[tuple]" = queue.Queue()
        self._busy = threading.Event()
        self._lock = threading.Lock()
        self._state: Any = None
        self._last_pushed = None
        self._prev_seq: Optional[int] = None
        self._drops = 0
        self._online = False
        self._firmware = ""
        self._port: Optional[str] = None       # 上次成功的口；重连优先试它
        self._reconnect_attempt = 0

    # ================= 生命周期 =================
    @property
    def _stop(self) -> threading.Event:
        """当前世代的停止标志。**只读** —— 不要在各世代之间共用/clear 它。"""
        return self._token.stop

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
        # 每次 open 一个全新令牌。旧线程的令牌在 close() 里已被 set 且不再被
        # 任何路径 clear —— 它只能退出，不能再和新线程抢串口。
        token = _RunToken()
        arm = self._factory(port)
        try:
            _attach_state_hook(arm, lambda st: self._on_state(st, token))
        except Exception:
            arm.close()
            raise
        with self._gen_lock:
            self._token = token
            self._arm = arm
            self._firmware = getattr(arm, "firmware", "") or ""
            self._port = port
            self._reconnect_attempt = 0
            self._online = True
        with self._lock:
            self._state = None
            self._last_pushed = None
            self._prev_seq = None
            self._drops = 0
        self.model.reset()
        self._thread = threading.Thread(target=self._loop, args=(token,),
                                        name="sdk-worker", daemon=True)
        self._thread.start()
        where = port or i18n.tr("自动")
        self._on_online(True, i18n.tr("已连接 {port} · {fw}", port=where,
                                      fw=self._firmware))
        self._log(i18n.tr("[OK] 已连接 {port} · 固件 {fw} · N={n}",
                          port=where, fw=self._firmware, n=self.n_joints))

    def close(self) -> None:
        """停线程 → 关链路（顺序不能反：先让所有者退出，再释放串口）。"""
        with self._gen_lock:
            token = self._token
            token.stop.set()
            th, self._thread = self._thread, None
        if th is not None and th.is_alive():
            th.join(timeout=self._close_join_s)
            if th.is_alive():
                # 在途的 SDK 调用（如十几秒的 movej）不可抢占。放开串口会让它
                # 带着 TransportError 退出，属可接受降级 —— 但必须留痕。
                self._log(i18n.tr(
                    "[WARN] 关闭时所有者线程仍在执行任务（阻塞调用不可抢占），"
                    "已直接释放串口"))
        with self._gen_lock:
            arm, self._arm = self._arm, None
            was_online = self._online
            self._online = False
        if arm is not None:
            try:
                arm.close()
            except Exception as e:  # noqa: BLE001 - 关闭失败不该阻断退出
                self._log(i18n.tr("[WARN] 关闭链路出错: {err}", err=e))
        with self._lock:
            self._state = None
            self._last_pushed = None
        if was_online:
            self._on_online(False, i18n.tr("已断开"))

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

    @property
    def cart_supported(self) -> Optional[bool]:
        """固件的笛卡尔规划能力（connect 时探测）。None = 未知/未连接。

        `Arm` 把结果缓存在私有 `_cart_supported`（SDK 明确不提供公开属性），
        这里读取它只用于**界面预判**；真正的发令守卫仍在 SDK 的 `move_l`。
        """
        arm = self._arm
        if arm is None:
            return None
        value = getattr(arm, "_cart_supported", None)
        return None if value is None else bool(value)

    @property
    def cart_probe_silent(self) -> bool:
        """能力探测是否"没等到应答"（不等于固件不支持，见 SDK 的 `_cart_probe_silent`）。"""
        arm = self._arm
        return bool(getattr(arm, "_cart_probe_silent", False)) if arm is not None else False

    # ================= 命令 =================
    def submit(self, name: str, fn: Callable[[Any], Any],
               on_done: Optional[Callable[[TaskResult], None]] = None) -> None:
        """把 `fn(arm)` 排进所有者线程执行。`fn` 里可以放任意阻塞的 SDK 调用。"""
        if self._arm is None:
            res = TaskResult(name, False,
                             error=pa.NotConnectedError(i18n.tr("未连接")))
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
            return False, i18n.tr("未连接")
        try:
            arm._write_cmd(_P.CMD_EMERGENCY_STOP, guarded=False)
        except Exception as e:  # noqa: BLE001 - 任何失败都必须如实上报
            return False, str(e)
        return True, i18n.tr("急停帧已发出")

    def takeover_movej(self, q, speed: float = 0.15) -> tuple:
        """**旁路**写一条 `movej`：作废在途笛卡尔规划并接管运动。

        为什么不能 `submit`：队列正被在途的 `move_l(wait=True)` 占着，排队等于
        等它走完。这里与急停走同一条"只写不读"旁路 —— `guarded=True` 保留 SDK
        对零重力保活期的拒绝，但不等 ACK。

        ⚠ 在途任务会以 `MotionSupersededError` 结束（笛卡尔规划被作废）；若在途
        的是 `movej`，SDK 会一直等到**原目标**超时/到位才返回 —— 固件已经改走新目标，
        但所有者线程要等旧调用收尾。界面必须如实说明这一点。

        返回 `(ok, 说明)`；ok=False 表示帧没发出去。
        """
        arm = self._arm
        if arm is None:
            return False, i18n.tr("未连接")
        try:
            n = int(getattr(arm, "n", 0) or 0)
            qs = [float(v) for v in q]
            if n and len(qs) != n:
                return False, i18n.tr("需要 {n} 个关节角，收到 {got} 个",
                                      n=n, got=len(qs))
            if not 0.0 <= float(speed) <= 1.0:
                return False, i18n.tr("speed 需 0..1")
            payload = _P.pack_f32s(qs) + struct.pack("<f", float(speed))
            arm._write_cmd(_P.CMD_MOVE_J, payload, guarded=True)
        except Exception as e:  # noqa: BLE001 - 任何失败都必须如实上报
            return False, str(e)
        return True, i18n.tr("接管 movej 帧已发出")

    def stop_jog_now(self) -> tuple:
        """受控停止点动：`movej` 到**当前实测关节角**，作废在途笛卡尔规划。

        走 `takeover_movej` 的旁路；没有状态帧时拒绝（拿不到"当前"就等于盲停）。
        """
        st = self.state
        if st is None:
            return False, i18n.tr("还没有状态帧，无法取当前关节角")
        return self.takeover_movej(list(st.q), 0.1)

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

    def drop_pending(self, reason: str = "") -> int:
        """丢掉尚未开始执行的任务，返回丢弃条数。

        急停之后不该再执行任何排队中的动作 —— 用户按急停的语义就是"停下"。
        正在执行的**那一条**没法中断（SDK 调用不可抢占），但它的结果会被固件的
        EMERGENCY 锁存拒掉（`ERR{cmd,0x06}`），不会真的动臂。

        ⚠ **[2026-09-14] 被丢的每一条都必须补一次 `on_done(TaskResult(ok=False))`**。
        静默丢弃会让发起方的"忙"态永远解不开 —— 页面的 `_busy` 是在 `_start` 里置位、
        只在 `_on_*_done` 里清除的, 回调不来就**只能重启进程**。急停路径尤其致命:
        参数页按钮全灰, 而用户按急停恰恰是最需要界面还能用的时候。
        """
        reason = reason or i18n.tr("急停")
        n = 0
        while True:
            try:
                name, _fn, on_done = self._tasks.get_nowait()
            except queue.Empty:
                return n
            n += 1
            res = TaskResult(
                name, False,
                error=RuntimeError(i18n.tr("任务已被丢弃（{reason}）", reason=reason)))
            try:
                (on_done or self._on_task)(res)
            except Exception:                 # noqa: BLE001 - GUI 回调出错不能拖垮所有者线程
                pass

    # ================= 所有者线程 =================
    def _loop(self, token: _RunToken) -> None:
        silent_since: Optional[float] = None
        while not token.stop.is_set():
            if token is not self._token:
                # 这一代已被新的 open()/close() 取代。绝不能碰当前会话的
                # `_arm`/`_port`/`_online`，也不能再拿队列里的任务。
                return
            arm = self._arm
            if arm is None:
                # 链路已断：重新枚举端口并重拨。用户主动 close() 时令牌已置位，
                # 这里不会执行；重连失败会按退避继续，直到成功或用户断开。
                if not self._reconnect(token):
                    return
                silent_since = None
                continue
            item = self._take()
            if item is not None:
                self._run(*item, token=token)
                silent_since = None
                continue
            try:
                # ⚠ 2.0 起 `get_state` 返回 `Msg(value, hz, timestamp)` 信封,
                # 而**"取不到帧"这件事仍然只体现在 `.value is None`** (信封本身恒非 None)
                # —— 下面那段静默判定离线 (silent_since) 的判据必须继续看 `.value`,
                # 忘记 `.value` 会让"链路静默"永远判不出来。
                st = arm.get_state(refresh=True,
                                   timeout=self._idle_timeout).value
            except pa.CommandRejectedError as e:
                # 固件对读状态回 ERR（罕见）：不判离线，记一次继续
                self._log(i18n.tr("[WARN] 状态读取被固件拒绝: {err}", err=e))
                continue
            except pa.LiteArmError as e:
                self._go_offline(i18n.tr("链路异常: {err}", err=e), token=token)
                continue
            except Exception as e:  # noqa: BLE001 - 线程不能带着异常死掉
                self._go_offline(i18n.tr("未预期异常: {err}", err=repr(e)),
                                 token=token)
                continue
            if st is None:
                if silent_since is None:
                    silent_since = self._clock()
                elif self._clock() - silent_since > self._offline_timeout:
                    self._go_offline(i18n.tr("状态流静默 >{timeout:.1f}s",
                                             timeout=self._offline_timeout),
                                     token=token)
                    continue
            else:
                silent_since = None

    def _candidate_ports(self) -> list:
        """重连候选：**上次成功的口优先**，然后按 `ports.find_ports()` 的顺序。

        跳过没有 USB VID/PID 的内核占位节点（Windows 的幽灵 COM60–COM67、
        Linux 的 ttyS0..31）：它们不是 USB 设备，拨一次只会白等一个写超时，
        期间还挡住了真正可用的口。
        """
        out = []
        if self._port:
            out.append(self._port)
        try:
            from litetool import ports as ports_mod
            for row in ports_mod.find_ports():
                dev = row.get("device")
                if not dev or dev in out:
                    continue
                if row.get("_rank") == 2:      # 系统串口占位节点，不是 USB 设备
                    continue
                out.append(dev)
        except Exception as e:  # noqa: BLE001 - 枚举失败仍可试上次的口
            self._log(i18n.tr("[WARN] 重连时串口枚举失败: {err}", err=e))
        return out

    def _reconnect(self, token: _RunToken) -> bool:
        """按退避重拨，直到成功或这一代的令牌置位。返回是否已恢复在线。"""
        if not self._auto_reconnect:
            return False
        attempt = 0
        while not token.stop.is_set():
            with self._gen_lock:
                if token.stop.is_set() or token is not self._token:
                    return False
                attempt += 1
                self._reconnect_attempt = attempt
            try:
                self._on_reconnect(attempt,
                                   i18n.tr("正在自动重连（第 {n} 次）…", n=attempt))
            except Exception:  # noqa: BLE001 - 通知失败不能中断重连
                pass
            failures = []
            for port in self._candidate_ports():
                if token.stop.is_set() or token is not self._token:
                    return False
                arm = None
                try:
                    arm = self._factory(port)
                    _attach_state_hook(arm, lambda st: self._on_state(st, token))
                except Exception as e:  # noqa: BLE001 - 这个口不行，试下一个
                    if arm is not None:
                        try:
                            arm.close()
                        except Exception:  # noqa: BLE001
                            pass
                    failures.append((port, e))
                    continue
                with self._gen_lock:
                    # 工厂调用可能卡了几秒。期间用户手动 open() 成功的话，这个
                    # 令牌已经不是当前世代 —— 这条新链路只能关掉，绝不能装进
                    # 新会话（issue #43 的"抢 _arm / 抢端口"）。
                    stale = token.stop.is_set() or token is not self._token
                    if not stale:
                        self._arm = arm
                        self._port = port
                        self._firmware = getattr(arm, "firmware", "") or ""
                        self._online = True
                if stale:
                    try:
                        arm.close()
                    except Exception:  # noqa: BLE001
                        pass
                    return False
                with self._lock:
                    self._state = None
                    self._last_pushed = None
                    self._prev_seq = None
                    self._drops = 0
                self.model.reset()
                self._log(i18n.tr("[OK] 已重连 {port} · 固件 {fw} · N={n}",
                                  port=port, fw=self._firmware, n=self.n_joints))
                self._on_online(True, i18n.tr("已重连 {port} · {fw}",
                                              port=port, fw=self._firmware))
                return True
            # 每一轮只留一行摘要：原来每个口一条 WARN，幽灵口能刷几分钟。
            if failures:
                first_port, first_err = failures[0]
                self._log(i18n.tr(
                    "[WARN] 第 {n} 次重连失败：{count} 个端口均无响应"
                    "（{port}: {err}）",
                    n=attempt, count=len(failures), port=first_port,
                    err=first_err))
            delay = min(self._reconnect_max,
                        self._reconnect_initial * (2 ** min(attempt - 1, 10)))
            if token.stop.wait(delay):
                return False
        return False

    def _take(self):
        try:
            return self._tasks.get_nowait()
        except queue.Empty:
            return None

    def _run(self, name: str, fn, on_done, token: Optional[_RunToken] = None) -> None:
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
        token = token or self._token
        if token.stop.is_set() and res.ok:
            res = TaskResult(name, False, error=RuntimeError(i18n.tr("已断开")))
        try:
            (on_done or self._on_task)(res)
        except Exception:  # noqa: BLE001 - GUI 回调出错不能拖垮所有者线程
            pass

    def _go_offline(self, why: str, token: Optional[_RunToken] = None) -> None:
        """链路断开：丢快照、关旧句柄、丢弃排队命令，并通知 GUI。

        排队中的命令必须丢弃 —— 它们是在**上一条链路**上受理的意图；重连后
        在新链路上执行一条旧的 movej，正是"断线后臂突然动一下"的来源。
        """
        with self._gen_lock:
            if token is not None and (token.stop.is_set()
                                      or token is not self._token):
                # 过期世代的读失败只是它自己那条旧链路的收尾，不能动新会话。
                return
            arm, self._arm = self._arm, None
            was_online = self._online
            self._online = False
        self._busy.clear()
        # 丢弃快照：链路已死还把最后一帧当实时数据回显，会让人以为臂还在那里。
        # 清掉之后 GUI 的 20Hz tick 拿到 None，状态条/表格如实显示"—"。
        with self._lock:
            self._state = None
            self._last_pushed = None
        if arm is not None:
            try:
                arm.close()
            except Exception:  # noqa: BLE001 - 关旧句柄失败不影响重连
                pass
        if token is not None and (token.stop.is_set()
                                  or token is not self._token):
            # 关旧句柄期间用户已经手动 open()：不要把新会话排队的命令丢掉，
            # 也不要再发一条过期的"离线"（它会把顶栏从"已连接"拉回去）。
            return
        dropped = self.drop_pending(i18n.tr("断线"))
        if not was_online and arm is None:
            return
        self._log(i18n.tr("[ERR] 离线: {why}", why=why))
        if dropped:
            self._log(i18n.tr("[WARN] 断线：已丢弃 {n} 条排队中的命令", n=dropped))
        self._on_online(False, why)

    # ================= 状态流入（所有者线程上下文） =================
    def _on_state(self, st, token: Optional[_RunToken] = None) -> None:
        if token is not None and (token.stop.is_set()
                                  or token is not self._token):
            return                     # 过期世代/关闭中的帧，不能覆盖新会话
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
