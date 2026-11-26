"""升级编排的 tool 侧适配 —— 把 `job.run_upgrade` 的六个动作接到 SdkWorker + pyusb。

`job` / `image` / `engine` 三个模块是从 studio 原样搬来的（见各自文件头）；本文件只
负责"这台桌面程序里，失能/进 DFU/等枚举/烧录/复位/重连分别怎么做"。

线程模型（与 studio 守护进程同一套纪律）：

* 升级跑在**页面自建的线程**上，不占 SDK 所有者线程；
* `disarm` / `enter_dfu` 通过 `SdkWorker.submit` 投给所有者线程，再用 Event 等结果；
* `enter_dfu` 成功（或设备已经跳走）后关掉 worker，释放 CDC 端口；
* 网络式的等待（DFU 枚举、重连）在升级线程里轮询；重连本身由界面线程执行并通过
  阻塞回调把结果交回来 —— 这样界面状态（顶栏、各页 online）始终在 GUI 线程更新。

本文件**不 import PyQt**，于是可以在没有 QApplication 的测试里直接跑。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional, Tuple

import litearm as pa

from . import engine, job

#: 等 `0483:DF11` 枚举出来的上限（秒）。与 studio 的 `DFU_APPEAR_TIMEOUT_S` 同值。
DFU_APPEAR_TIMEOUT_S = 10.0

#: 失能之后等状态帧确认 `enabled == False` 的上限（秒）。同 studio。
UPGRADE_DISARM_TIMEOUT_S = 3.0

#: 烧完等 CDC 回来并重建会话的上限（秒）。同 studio。
UPGRADE_RECONNECT_WINDOW_S = 30.0

#: 一次"界面去重连"的阻塞回调上限（秒）。
RECONNECT_RPC_TIMEOUT_S = 10.0

#: 两次重连尝试之间的间隔（秒）。
RECONNECT_PERIOD_S = 0.5

#: 单个 SDK 任务（失能/读状态/进 DFU）等回调的上限（秒）。SDK 自己还有更短的超时，
#: 这里只是防止 worker 线程死掉时把升级线程永远挂住。
SDK_TASK_TIMEOUT_S = 30.0


class UpgradeController:
    """一次固件升级的编排器。生命周期 = 一次 start 到 result。"""

    def __init__(self, *,
                 sdk: Any,
                 engine_module: Any = engine,
                 reconnect: Callable[[str], Tuple[bool, str, str, str]],
                 on_progress: Callable[[job.Progress], None],
                 on_result: Callable[[job.Result], None],
                 on_log: Callable[[str], None],
                 on_upgrading: Callable[[bool], None]):
        """
        `sdk`            —— `SdkWorker` 同形：`online` / `submit(name, fn, done)` / `close()`。
        `engine_module`  —— `litetool.dfu.engine` 或测试用的 `FakeEngine`。
        `reconnect`      —— 阻塞回调 `(hint) -> (ok, port, firmware, error)`；由界面线程
                            执行真正的重连（见 `firmware_page._reconnect_rpc`）。
        `on_*`           —— 只被升级线程调用；界面侧负责把它们转成 Qt 信号。
        """
        self._sdk = sdk
        self._engine = engine_module
        self._reconnect = reconnect
        self._on_progress = on_progress
        self._on_result = on_result
        self._on_log = on_log
        self._on_upgrading = on_upgrading
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._dfu_session: Any = None
        self._port_hint = ""

    # ------------------------------------------------------------------ 页面接口
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        """请求取消。只在相位之间与等待类相位生效（烧录相位内不生效）。"""
        self._cancel.set()

    def start(self, blob: bytes, base: int, summary: Any, *,
              from_dfu: bool) -> bool:
        """预检 → 起升级线程 → 立刻返回。预检失败走 `on_result`，不进入升级态。"""
        if self.is_running():
            return False
        try:
            self._precheck(from_dfu)
        except job.UpgradeError as e:
            self._on_result(job.Result(False, e.reason, str(e)))
            return False
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run, args=(blob, base, summary, from_dfu),
            name="litearm-dfu", daemon=True)
        self._on_upgrading(True)
        self._thread.start()
        return True

    # ------------------------------------------------------------------ 预检
    def _precheck(self, from_dfu: bool) -> None:
        """在任何硬件动作之前说清缺什么 —— 尤其不能等跳进 DFU 才发现没引擎。"""
        if not self._engine.available():
            raise job.UpgradeError("engine_unavailable", self._engine.backend_status())
        if from_dfu:
            if self._find_device() is None:
                raise job.UpgradeError(
                    "dfu_device_absent",
                    "没有检测到处于 DFU (0483:DF11) 的板子 —— 它可能刚被拔掉, "
                    "或已经复位回应用态")
            return
        if not getattr(self._sdk, "online", False):
            raise job.UpgradeError("not_connected", "机械臂未连接 —— 请先连接设备")

    # ------------------------------------------------------------------ 线程主体
    def _run(self, blob: bytes, base: int, summary: Any, from_dfu: bool) -> None:
        """**不许让异常逃出去** —— 逃出去操作员就看不到是哪一步坏的。"""
        try:
            result = job.run_upgrade(
                blob=blob, base=base, summary=summary, hooks=self,
                emit=self._on_progress, is_cancelled=self._cancel.is_set,
                from_dfu=from_dfu)
        except Exception as e:                                     # noqa: BLE001
            result = job.Result(False, "flash_failed", f"{type(e).__name__}: {e}")
        finally:
            self._dfu_session = None
        try:
            self._on_result(result)
        finally:
            self._on_upgrading(False)

    # ------------------------------------------------------------------ hooks
    def disarm(self) -> None:
        """失能，并等状态帧确认。见 `UPGRADE_DISARM_TIMEOUT_S` 的注释。"""
        if not getattr(self._sdk, "online", False):
            raise job.UpgradeError("not_connected", "机械臂未连接 —— 请先连接设备")
        try:
            self._sdk_task("失能机械臂", lambda arm: arm.disable())
        except job.UpgradeError:
            raise
        except pa.NotConnectedError as e:
            raise job.UpgradeError("not_connected", str(e)) from None
        except Exception as e:  # noqa: BLE001
            raise job.UpgradeError("arm_enabled", f"失能失败: {e}") from None
        deadline = time.monotonic() + UPGRADE_DISARM_TIMEOUT_S
        while time.monotonic() < deadline:
            state = self._sdk_task(
                "读状态", lambda arm: arm.get_state(refresh=True).value)
            if state is None or not bool(getattr(state, "enabled", False)):
                # 读不到状态帧就不拦：门禁的权威在固件（enabled || enable_pending
                # 一律回 0x03），本地预检只为可读性。
                return
            time.sleep(0.05)
        raise job.UpgradeError(
            "arm_enabled",
            f"机械臂在 {UPGRADE_DISARM_TIMEOUT_S:.0f}s 内没有失能 —— 不冒险进入 DFU "
            f"(跳转会停 TIM3, 电机 100ms 松开, 有重力负载会下垂)")

    def enter_dfu(self) -> None:
        """发 `CMD_ENTER_DFU (0x15)`；成功（或设备已经跳走）后释放 CDC 端口。"""
        try:
            self._sdk_task("进入 DFU", lambda arm: arm.enter_dfu())
        except pa.InvalidCommandError as e:
            # SDK 的本地预检：使能中不跳，一个字节都没发。
            raise job.UpgradeError("arm_enabled", str(e)) from None
        except pa.CommandRejectedError as e:
            if getattr(e, "cmd", 0) == 0x15 and getattr(e, "code", 0) == 0x03:
                raise job.UpgradeError("arm_enabled", str(e)) from None
            raise
        except Exception as e:  # noqa: BLE001
            # 传输层失败时设备**可能已经跳了**（ACK 被应答 FIFO 丢掉，见 SDK 文档）。
            # 放掉串口，让失败收尾能去设备上发 DFU_DETACH。
            self._close_sdk()
            if isinstance(e, pa.LiteArmError):
                raise job.UpgradeError("dfu_not_entered", str(e)) from None
            raise
        else:
            self._close_sdk()          # 设备已经不在应用态，串口必须放开

    def wait_for_dfu(self, is_cancelled: Callable[[], bool]) -> None:
        """等 `0483:DF11` **可用**（不只是"存在"），并把引擎会话开好。

        ⚠ "存在" ≠ "可用"：设备 attach 后内核先建设备节点（默认 0644），udev 随后
        才 chmod 成 0666；pyusb 在这个窗口里已经能枚举到它，`open()` 却会 Access
        denied。所以这里必须**真开一次**，开不了就继续等（udev 只慢几十毫秒）。
        """
        if not self._engine.available():
            raise job.UpgradeError("engine_unavailable", self._engine.backend_status())
        deadline = time.monotonic() + DFU_APPEAR_TIMEOUT_S
        denied = False
        while time.monotonic() < deadline:
            if is_cancelled():
                raise job.UpgradeError("cancelled", "已取消")
            dev = self._find_device()
            if dev is not None:
                session = self._engine.DfuDevice(dev)
                try:
                    session.open()
                except Exception as e:                             # noqa: BLE001
                    if not _is_permission_error(e):
                        raise
                    denied = True
                    time.sleep(0.2)
                    continue
                self._dfu_session = session
                return
            time.sleep(0.2)
        if denied:
            raise job.UpgradeError(
                "dfu_permission_denied",
                "DFU 设备在, 但当前用户打不开它 (打开时报 Access denied)。"
                "Linux 上需要一条 udev 规则："
                'SUBSYSTEM=="usb", ATTR{idVendor}=="0483", '
                'ATTR{idProduct}=="df11", MODE="0666"')
        raise job.UpgradeError(
            "dfu_device_absent",
            f"等 {DFU_APPEAR_TIMEOUT_S:.0f}s 没等到 DFU 设备 (0483:DF11) —— "
            f"检查 USB 线; Windows 上还需要 ST 的 WinUSB 驱动")

    def flash(self, blob: bytes, base: int,
              on_progress: Callable[[int, int, str], None]) -> None:
        if self._dfu_session is None:
            raise job.UpgradeError("dfu_device_absent", "没有可用的 DFU 设备")
        # `param_policy="abort"`: `image.inspect` 已经拦过一道, 这里让引擎**自己**
        # 再拦一道 —— 许可证与出厂标定只存在于设备上, 擦掉不可恢复。
        self._dfu_session.flash(blob, base, progress=on_progress,
                                param_policy="abort", verify=True)

    def detach(self) -> None:
        """让设备离开 DFU 并复位回应用。失败收尾也走这里 —— 尽力而为，不抛。"""
        session, self._dfu_session = self._dfu_session, None
        if session is not None:
            try:
                session.leave(reset=True)
            except Exception:                                       # noqa: BLE001
                pass
            return
        # 没有会话时**也要试一次**：失败可能落在 enter_dfu 与 wait_for_dfu 之间，
        # 板子已经跳进 bootloader 而我们还来不及打开它。
        try:
            dev = self._find_device()
            if dev is None:
                return
            probe = self._engine.DfuDevice(dev)
            probe.open()
        except Exception:                                           # noqa: BLE001
            return
        try:
            probe.leave(reset=True)
        except Exception:                                           # noqa: BLE001
            pass

    def reconnect(self, is_cancelled: Callable[[], bool]) -> Tuple[str, str]:
        """等 CDC 回来并重建会话 —— 真正的打开动作由界面线程执行。"""
        deadline = time.monotonic() + UPGRADE_RECONNECT_WINDOW_S
        attempts = 0
        last = ""
        while time.monotonic() < deadline:
            if is_cancelled():
                raise job.UpgradeError("cancelled", "已取消 (镜像已写入)")
            attempts += 1
            ok, port, firmware, error = self._reconnect(self._port_hint)
            if ok:
                return port, firmware
            last = error
            time.sleep(RECONNECT_PERIOD_S)
        raise job.UpgradeError(
            "reconnect_failed",
            f"固件已写入并通过读回校验, 但 {UPGRADE_RECONNECT_WINDOW_S:.0f}s 内没能"
            f"重新连上 ({attempts} 次): {last or '没有发现 STM32 CDC 设备'} —— "
            f"断电重上电即可")

    # ------------------------------------------------------------------ 内部
    def _sdk_task(self, name: str, fn: Callable[[Any], Any],
                  timeout: float = SDK_TASK_TIMEOUT_S) -> Any:
        """在 SDK 所有者线程上跑一段，**阻塞等结果**（本方法在升级线程上）。"""
        event = threading.Event()
        box: dict = {}

        def done(res) -> None:
            box["res"] = res
            event.set()

        self._sdk.submit(name, fn, done)
        if not event.wait(timeout):
            raise job.UpgradeError("flash_failed", f"{name} 超时")
        res = box.get("res")
        if res is None:
            raise job.UpgradeError("flash_failed", f"{name} 没有结果")
        if not res.ok:
            error = getattr(res, "error", None)
            if isinstance(error, Exception):
                raise error
            raise job.UpgradeError("flash_failed", str(error or res.text))
        return res.value

    def _close_sdk(self) -> None:
        try:
            self._sdk.close()
        except Exception as e:                                      # noqa: BLE001
            self._on_log(f"[WARN] 关闭串口失败: {e}")

    def _find_device(self):
        try:
            return self._engine.find_device()
        except Exception as e:                                      # noqa: BLE001
            raise job.UpgradeError("dfu_device_absent",
                                   f"无法枚举 USB 设备: {type(e).__name__}: {e}") from None


def _is_permission_error(exc: BaseException) -> bool:
    """异常链里有没有 `EACCES` —— 把"打不开设备"与"设备没到"分开。

    判据是 `errno`，不是消息文本：引擎会把 libusb 的 `USBError` 包成 `DfuError`，
    顺着 `__cause__`/`__context__` 找 errno 才是可靠的。
    """
    seen: set[int] = set()
    e: Optional[BaseException] = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if getattr(e, "errno", None) == 13:
            return True
        e = e.__cause__ or e.__context__
    return False
