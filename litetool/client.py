"""客户端（LiteArmClient）—— 状态缓存 + 命令 ACK/RSP 配对。

与物理层解耦：构造时注入一个 link 对象（须提供 send_bytes(data) 与 is_open 属性），
上行帧由读线程调用 client.handle_frame(cmd, payload) 喂入。
"""
import struct
import threading
import time
from dataclasses import dataclass

from litetool import protocol as P


class LinkClosedError(Exception):
    """链路未打开/已关闭时尝试发送。"""


@dataclass
class JointState:
    index: int
    q: float
    dq: float
    tau: float
    t_mos: float
    t_coil: float
    err: int


@dataclass
class StatusView:
    flags: int
    mode: int
    seq: int
    joints: list[JointState]
    received: float
    joint_fault: int = 0        # [1.5.0/M7] G7 固件断轴位图 (旧固件帧=0)
    enabled: bool = False       # [1.5.0/M7] flags bit9 固件侧使能位

    @property
    def n(self) -> int:
        return len(self.joints)

    @property
    def mode_name(self) -> str:
        return P.MODE_NAMES.get(self.mode, f"0x{self.mode}")

    def flag_names(self) -> list[str]:
        return [P.FLAG_NAMES[i] for i in range(6) if self.flags & (1 << i)]

    @property
    def has_fault(self) -> bool:
        return bool(self.flags & P.ARM_FLAG_FAULT)

    def joint_fault_axes(self) -> list[int]:
        """被固件锁存断开的轴号 (1-based)"""
        return [i + 1 for i in range(self.n) if self.joint_fault & (1 << i)]


class LiteArmClient:
    """状态缓存 + 串行命令收发。

    - 同一时刻最多一个未完成命令（_tx_lock），ACK/ERR 用 threading.Event 配对。
    - 固件 100Hz 主动推 RSP_STATUS；online 判定 = 最近一次状态帧在 offline_timeout 内。
    - log 回调接收纯文本行（GUI 侧再按 [ERR]/[WARN] 前缀着色）。
    """

    def __init__(self, link, offline_timeout: float = 0.5, log=None,
                 clock=time.monotonic):
        self._link = link
        self._offline_timeout = offline_timeout
        self._log = log if log is not None else (lambda msg: None)
        self._clock = clock

        self._latest: StatusView | None = None
        self._last_status_t = None

        self._tx_lock = threading.Lock()
        self._pending = None          # 当前在等应答的命令 ID
        self._pending_rsp = None      # 等的是哪种上行 RSP (None=等 ACK/ERR)
        self._pending_ev = threading.Event()
        self._reply = (False, None)   # ACK 路径: (ok, errcode|None)
        self._rsp_payload = None      # RSP 路径: 收到的 payload

    # ---- 上行帧入口（由读线程调用） ----
    def handle_frame(self, cmd: int, payload: bytes):
        if cmd == P.RSP_STATUS:
            dec = P.decode_status_full(payload)
            if dec is not None:
                flags, mode, seq, rows, jf = dec
                joints = [JointState(i, *row) for i, row in enumerate(rows)]
                self._latest = StatusView(
                    flags, mode, seq, joints, self._clock(),
                    joint_fault=(jf if jf is not None else 0),
                    enabled=P.flag_enabled(flags))
                self._last_status_t = self._latest.received
            return
        if self._pending is None:
            return                     # 无待定命令，忽略其它上行帧
        if self._pending_rsp is not None:
            if cmd == self._pending_rsp:
                self._rsp_payload = payload
                self._pending_ev.set()
            return
        # ACK/ERR 路径: 只接受回显 cmd == 待定命令的应答
        if cmd == P.RSP_ACK and payload and payload[0] == self._pending:
            self._reply = (True, None)
            self._pending_ev.set()
        elif cmd == P.RSP_ERR and payload:
            ecmd, code = P.decode_err(payload)
            if ecmd == self._pending:
                self._reply = (False, code)
                self._pending_ev.set()

    # ---- 命令原语 ----
    def _transact(self, cmd: int, payload: bytes = b"", timeout: float = 0.5,
                  rsp: int | None = None):
        """发一帧并等待应答。

        - rsp is None: 等 ACK/ERR → 返回 (ok, errcode|None)
        - rsp 给定:    等该 RSP 上行帧 → 返回 (ok, payload|None)
        """
        with self._tx_lock:
            self._pending = cmd
            self._pending_rsp = rsp
            self._pending_ev.clear()
            self._reply = (False, None)
            self._rsp_payload = None
            try:
                self._link.send_bytes(P.pack_frame(cmd, payload))
            except Exception as e:  # noqa: BLE001
                self._pending = None
                self._log(f"[ERR] 无法发送 cmd 0x{cmd:02X}: {e}")
                return False, None
            got = self._pending_ev.wait(timeout)
            self._pending = None
            if not got:
                self._log(f"[WARN] cmd 0x{cmd:02X} 应答超时 ({timeout:.1f}s)")
                return False, None
            if rsp is not None:
                return True, self._rsp_payload
            return self._reply

    def _cmd(self, cmd: int, payload: bytes = b"", timeout: float = 0.5):
        """等 ACK/ERR（测试与内部共用）"""
        return self._transact(cmd, payload, timeout=timeout, rsp=None)

    def _simple(self, name: str, cmd: int) -> bool:
        ok, code = self._cmd(cmd, timeout=1.0)
        if ok:
            self._log(f"[OK] {name}: ACK")
        else:
            self._log(f"[ERR] {name}: 失败"
                      + (f"（{P.ERR_TEXT.get(code, f'code 0x{code:02X}')}）" if code is not None else "（超时/无应答）"))
        return ok

    # ---- 高层 API ----
    @property
    def status(self) -> StatusView | None:
        return self._latest

    @property
    def online(self) -> bool:
        return (self._last_status_t is not None
                and self._clock() - self._last_status_t < self._offline_timeout)

    def enable(self, retries: int = 6, delay: float = 0.4) -> bool:
        """ENABLE：反馈未就绪时固件回 ERR(0x10,0x03)，自动重试至 ACK。"""
        for i in range(retries + 1):
            ok, code = self._cmd(P.CMD_ENABLE, timeout=1.0)
            if ok:
                self._log(f"[OK] enable 成功（第 {i + 1} 次尝试）")
                return True
            if code != 0x03:            # 非"未就绪"错误 → 直接失败
                self._log(f"[ERR] enable 失败：{P.ERR_TEXT.get(code, f'code 0x{code:02X}')}")
                return False
            time.sleep(delay)
        self._log(f"[ERR] enable {retries + 1} 次重试后仍未就绪（检查电机供电/CAN 在线）")
        return False

    def disable(self) -> bool:
        return self._simple("disable", P.CMD_DISABLE)

    def emergency_stop(self) -> bool:
        """急停（等 ACK 版）：无确认框语义在 GUI 层；此方法本身只发命令。"""
        return self._simple("emergency_stop", P.CMD_EMERGENCY_STOP)

    def emergency_now(self) -> bool:
        """急停旁路通道：不加锁、不等 ACK，立即写帧。

        用途：GUI 常驻急停按钮 —— 不允许被"在途等待 ACK 的运动命令"阻塞排队。
        """
        try:
            self._link.send_bytes(P.pack_frame(P.CMD_EMERGENCY_STOP))
            self._log("[OK] EMERGENCY_STOP 已发送（旁路通道）")
            return True
        except Exception as e:  # noqa: BLE001
            self._log(f"[ERR] 急停发送失败: {e}")
            return False

    def clear_faults(self) -> bool:
        return self._simple("clear_faults", P.CMD_CLEAR_FAULTS)

    def reset(self) -> bool:
        return self._simple("reset", P.CMD_RESET)

    def home(self) -> bool:
        return self._simple("home", P.CMD_HOME)

    def set_speed_percent(self, v: int) -> bool:
        v = int(v) & 0xFF
        ok, code = self._cmd(P.CMD_SET_SPEED_PERCENT, bytes([v]), timeout=1.0)
        if ok:
            self._log(f"[OK] 速度倍率已设 {v}%")
        else:
            self._log(f"[ERR] 设置速度倍率失败 code={code}")
        return ok

    def get_firmware(self, timeout: float = 1.0) -> str | None:
        ok, payload = self._transact(P.CMD_GET_FIRMWARE, rsp=P.RSP_FIRMWARE,
                                     timeout=timeout)
        if ok and payload is not None:
            return P.decode_firmware(payload)
        return None

    def get_tcp(self, timeout: float = 1.0):
        """返回 (pos(x,y,z), rpy(roll,pitch,yaw))；失败 None"""
        ok, payload = self._transact(P.CMD_GET_TCP, rsp=P.RSP_TCP, timeout=timeout)
        return P.decode_tcp(payload) if ok and payload is not None else None

    # ---- [调参页] 运行时参数读/写（写口固件已支持; 读口 0x2B/0x2C 以协议为准） ----
    def set_joint_param(self, idx: int, kp: float, kd: float, tau_max: float,
                        timeout: float = 1.0):
        """0x22 单关节 kp/kd/tau_max 运行时改写 -> RAM"""
        payload = bytes([int(idx) & 0xFF]) + struct.pack("<3f", kp, kd, tau_max)
        return self._cmd(P.CMD_SET_JOINT_PARAM, payload, timeout=timeout)

    def set_joint_limits(self, idx: int, q_min: float, q_max: float,
                         timeout: float = 1.0):
        """0x23 单关节软限位运行时改写 -> RAM (须 q_min < q_max)"""
        payload = bytes([int(idx) & 0xFF]) + struct.pack("<2f", q_min, q_max)
        return self._cmd(P.CMD_SET_JOINT_LIMITS, payload, timeout=timeout)

    def get_joint_param(self, idx: int, timeout: float = 1.0):
        """0x24 读回单关节参数 -> (idx, kp, kd, tau_max, q_min, q_max) | None"""
        ok, payload = self._transact(P.CMD_GET_JOINT_PARAM, bytes([int(idx) & 0xFF]),
                                     rsp=P.RSP_JOINT_PARAM, timeout=timeout)
        if ok and payload is not None:
            return P.decode_joint_param(payload)
        return None

    def param_save(self, timeout: float = 5.0):
        """0x25 固化参数到 Flash (异步擦写; 固件要求 disable 态, 否则 ERR code 0x04)"""
        return self._cmd(P.CMD_PARAM_SAVE, timeout=timeout)

    def set_ff_vec(self, item: int, values, timeout: float = 1.0):
        """0x26 逐关节前馈向量 (item 1..11, 7×f32) -> RAM"""
        vals = [float(v) for v in values]
        payload = bytes([int(item) & 0xFF]) + struct.pack("<7f", *vals)
        return self._cmd(P.CMD_SET_FF_VEC, payload, timeout=timeout)

    def set_ff_flags(self, mask: int, timeout: float = 1.0):
        """0x27 ff_mask u32 (LE) -> RAM"""
        return self._cmd(P.CMD_SET_FF_FLAGS, struct.pack("<I", int(mask) & 0xFFFFFFFF),
                         timeout=timeout)

    def set_ff_scalar(self, item: int, sub: int, value: float, timeout: float = 1.0):
        """0x28 全局标量 (item 1..8, sub 为分量下标) -> RAM"""
        payload = bytes([int(item) & 0xFF, int(sub) & 0xFF]) + struct.pack("<f", value)
        return self._cmd(P.CMD_SET_FF_SCALAR, payload, timeout=timeout)

    def get_ff_vec(self, item: int, timeout: float = 1.0):
        """0x2B 读回逐关节前馈向量 -> (item, 7-tuple) | None"""
        ok, payload = self._transact(P.CMD_GET_FF_VEC, bytes([int(item) & 0xFF]),
                                     rsp=P.RSP_FF_VEC, timeout=timeout)
        if ok and payload is not None:
            return P.decode_ff_vec(payload)
        return None

    def get_ff_scalar(self, item: int, sub: int = 0, timeout: float = 1.0):
        """0x2C 读回全局标量 -> (item, sub, f32) | None"""
        ok, payload = self._transact(P.CMD_GET_FF_SCALAR,
                                     bytes([int(item) & 0xFF, int(sub) & 0xFF]),
                                     rsp=P.RSP_FF_SCALAR, timeout=timeout)
        if ok and payload is not None:
            return P.decode_ff_scalar(payload)
        return None

    # ---- 运动下发（安全收口在 GUI 侧 checks.py；本层直发） ----
    def move_j(self, qs: list[float], speed: float = 0.2):
        payload = b"".join(struct.pack("<f", v) for v in qs) + struct.pack("<f", speed)
        return self._cmd(P.CMD_MOVE_J, payload, timeout=1.0)

    def move_mit(self, idx: int, q: float, dq: float, kp: float, kd: float, tau: float):
        payload = bytes([int(idx) & 0xFF]) + struct.pack("<fffff", q, dq, kp, kd, tau)
        return self._cmd(P.CMD_MOVE_MIT, payload, timeout=1.0)

    def move_js(self, qs: list[float], dqs: list[float]):
        payload = b"".join(struct.pack("<f", v) for v in qs + dqs)
        return self._cmd(P.CMD_MOVE_JS, payload, timeout=1.0)

    def move_mit_all(self, qs: list[float], dqs: list[float],
                     kps: list[float], kds: list[float], taus: list[float]):
        payload = b"".join(struct.pack("<fffff", *v)
                           for v in zip(qs, dqs, kps, kds, taus))
        return self._cmd(P.CMD_MOVE_MIT_ALL, payload, timeout=1.0)
