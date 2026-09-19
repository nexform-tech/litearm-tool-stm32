"""鸭子类型的 `litearm_core.Arm` 替身 —— 离线跑 SdkWorker / 参数 I/O 的测试。

形状刻意与真 SDK 一致，**包括那个私有状态钩子缝隙** (`_a._on_status`)：
`tests/test_sdk_hook.py` 另有一条测试守着真 SDK 上这个缝隙仍在，故此替身不会
"替 SDK 保证"一个已经不存在的东西。

⚠ **[2026-09-19] 返回信封**：litearm-core 2.0 起 11 个"读一帧"型 getter 返回
`Msg(value, hz, timestamp)`（`get_state` / `get_status_now` / `get_tcp` /
`get_ff_vec` / `get_ff_scalar` / `params.get_joint_param` / `model.get_body` /
`model.get_jm` / `model.status` / `model.get_gravity` / `diag.kin_bench`），
本替身逐条跟着包 `_msg()`；两个**派生** getter（`get_ff_mask` -> int、
`all_joint_params` -> list）与 `move_*`/`home`（动作结果）**保持裸值**。
替身漏包会让"工具忘了 `.value`"这类错在离线全绿、真机必炸 —— 形状必须逐条对齐。
"""
from __future__ import annotations

import time
from typing import Optional

import litearm_core as pa
from litearm_core import _protocol as _P

DEFAULT_FW = "Litearm1.5.3-7J"


def _msg(value) -> pa.Msg:
    """替身的**返回信封** —— 与 SDK 2.0 的 11 个"读一帧"型 getter 同形状。

    ⚠ 替身只保**形状**, 不保 `hz`/`timestamp` 的语义: 那两个字段是"该类帧在本会话
    里的**实际到达**统计" (`Arm._ack.recv_stats`), 替身没有链路可统计, 一律填 `0.0`
    (SDK 自己定义的"样本不足"哨兵, 不是真值)。本工具当前**一个字段都不消费**它,
    故这个替身在此处**不能**替 SDK 作证 —— 将来若有人把 hz 画到界面上, 别信这里的 0.0。
    """
    return pa.Msg(value=value, hz=0.0, timestamp=0.0)


def make_state(n: int = 7, seq: int = 0, mode: int = 1, flags: int = 0x200,
               joint_fault: int = 0, q=None) -> pa.RobotState:
    names = [_P.FLAG_NAMES[b] for b in sorted(_P.FLAG_NAMES) if flags & (1 << b)]
    st = pa.RobotState(mode=mode, mode_name=_P.MODE_NAMES.get(mode, str(mode)),
                       flags=flags, flag_names=names, seq=seq,
                       joint_fault=joint_fault)
    st.joints = [pa.JointState(q=(q[i] if q else 0.1 * i), dq=0.0, tau=0.0,
                               t_mos=35.0, t_coil=36.0, err=1)
                 for i in range(n)]
    return st


class _FakeAck:
    """对应 SDK 的 `_Ack`：状态解码结果落在 `.state`，钩子挂在 `._on_status` 上。"""

    def __init__(self):
        self.state: Optional[pa.RobotState] = None
        self.raw_calls = 0

    def _on_status(self, payload: bytes) -> None:
        self.raw_calls += 1


class _FakeParams:
    """与真 `JointParams` 同款守卫。

    ⚠ 替身漏掉校验就会**替 SDK 撒谎**：台架 1J 上真 SDK 的 `_check_idx` 会对 j≥1
    抛 `关节索引越界`，而"宽容"的替身让它一路通过。本项目已经被这套替身坑过两次
    （IK seed 长度、这里的关节索引），所以凡是真 SDK 会拒的，替身也必须拒。
    """

    def __init__(self, arm):
        self._arm = arm
        self.kp = [400.0, 400.0, 300.0, 300.0, 50.0, 50.0, 50.0]
        self.kd = [2.0] * 7
        self.tau_max = [40.0] * 7
        self.q_min = [-3.0] * 7
        self.q_max = [3.0] * 7

    def _check_idx(self, idx):
        idx = int(idx)
        n = self._arm.n
        if not 0 <= idx < max(n, 1):
            raise pa.InvalidCommandError(f"关节索引越界: {idx} (有效 0..{n - 1})")
        return idx

    def get_joint_param(self, idx):
        idx = self._check_idx(idx)
        self._record("get_joint_param", idx)
        self._arm._maybe_raise()
        return _msg(pa.JointParam(idx, self.kp[idx], self.kd[idx], self.tau_max[idx],
                                  self.q_min[idx], self.q_max[idx]))

    def all_joint_params(self):
        """⚠ 真 SDK 上这个是**派生** getter, 刻意保持裸 `list[JointParam]` (N 帧的聚合,
        一个 hz 描述不了) —— 替身必须照样保持裸值, 否则替身会**替 SDK 撒谎**。"""
        return [self.get_joint_param(i).value for i in range(self._arm.n)]

    def set_joint_param(self, idx, kp, kd, tau_max):
        idx = self._check_idx(idx)
        self._record("set_joint_param", (idx, kp, kd, tau_max))
        self._arm._maybe_raise()
        self.kp[idx], self.kd[idx], self.tau_max[idx] = kp, kd, tau_max

    def set_joint_limits(self, idx, q_min, q_max):
        idx = self._check_idx(idx)
        if not float(q_min) < float(q_max):
            raise pa.InvalidCommandError("软限位需 q_min < q_max")
        self._record("set_joint_limits", (idx, q_min, q_max))
        self._arm._maybe_raise()
        self.q_min[idx], self.q_max[idx] = q_min, q_max

    def reset_factory(self):
        self._record("reset_factory", None)
        self._arm._maybe_raise()

    def _record(self, name, arg):
        self._arm.calls.append((name, arg))


class _FakeModel:
    """`arm.model` 的替身 —— **必须实现真实语义**, 否则"替身替 SDK 撒谎"。

    ⚠ 三条不能省的:
      1. **模型恒 9 刚体**, 与 `arm.n` (关节数) 无关;
      2. `commit` 的**掩码语义**: `t_dirty != expected_mask` -> `ERR{0x32,0x07}`,
         已武装 -> `ERR{0x32,0x04}`;
      3. 惰性初始化按**位图分组**: 先写 jm 再写 body, jm 不能被打回。
    """

    NBODY = 9
    BODY_PARAMS = 10
    JM_N = 7

    def __init__(self, arm):
        self._arm = arm
        #: 生效 bank (无 payload 概念 —— 替身不模拟动力学)
        self.body = [[1.0] + [0.0] * 9 for _ in range(self.NBODY)]
        self.body[self.NBODY - 1][0] = 0.0            # body8 质量恒 0
        self.jm = [0.0] * self.JM_N
        #: staging
        self.stage_body = {}
        self.stage_jm = None
        self.override = False
        self.dirty = False
        #: 能力开关 (模拟旧固件)
        self.supported = True
        #: 强制某调用回指定码 (注入失败用)
        self.force_code = None

    # ---- 内部 ----
    def _maybe_fail(self, what):
        arm = self._arm
        arm.calls.append((what, None))
        if self.force_code is not None:
            raise pa.CommandRejectedError(
                f"{what} 被固件拒绝", cmd=0x30, code=self.force_code)

    def _staged_mask(self) -> int:
        m = 0
        for i in self.stage_body:
            m |= (1 << i)
        if self.stage_jm is not None:
            m |= (1 << 9)
        return m

    # ---- 0x34 ----
    def probe(self) -> bool:
        if not self.supported:
            raise pa.UnsupportedByFirmwareError("固件无此命令", cmd=0x34, code=0x00)
        self.get_body(0)
        return True

    def get_body(self, idx: int):
        self._arm.calls.append(("model.get_body", idx))
        if not self.supported:
            raise pa.UnsupportedByFirmwareError("固件无此命令", cmd=0x34, code=0x00)
        if not 0 <= int(idx) < self.NBODY:
            raise pa.InvalidCommandError(f"刚体索引越界: {idx}")
        return _msg(list(self.body[int(idx)]))

    def get_jm(self):
        self._arm.calls.append(("model.get_jm", None))
        if not self.supported:
            raise pa.UnsupportedByFirmwareError("固件无此命令", cmd=0x35, code=0x00)
        return _msg(list(self.jm))

    # ---- 0x30 / 0x33 ----
    def set_body(self, idx: int, vals):
        self._arm.calls.append(("model.set_body", (int(idx), list(vals))))
        if not 0 <= int(idx) < self.NBODY:
            raise pa.InvalidCommandError(f"刚体索引越界: {idx}")
        vals = [float(v) for v in vals]
        if len(vals) != self.BODY_PARAMS:
            raise pa.InvalidCommandError("body 参数个数不符")
        if any(v != v or abs(v) > 1e6 for v in vals):
            raise pa.CommandRejectedError("数值非法", cmd=0x30, code=0x02)
        if int(idx) == self.NBODY - 1 and vals[0] != 0.0:
            raise pa.CommandRejectedError("body8 质量必须为 0", cmd=0x30, code=0x02)
        self.stage_body[int(idx)] = vals
        self.dirty = True

    def set_jm(self, vals):
        self._arm.calls.append(("model.set_jm", list(vals)))
        vals = [float(v) for v in vals]
        if len(vals) != self.JM_N:
            raise pa.InvalidCommandError("jm 个数不符")
        if any(v != v or abs(v) > 1e6 for v in vals):
            raise pa.CommandRejectedError("数值非法", cmd=0x33, code=0x02)
        self.stage_jm = vals
        self.dirty = True

    # ---- 0x32 / 0x37 ----
    def commit(self, expected_mask: int):
        self._arm.calls.append(("model.commit", int(expected_mask)))
        if self._arm.enabled:
            raise pa.CommandRejectedError("需先失能", cmd=0x32, code=0x04)
        if int(expected_mask) != self._staged_mask():
            raise pa.CommandRejectedError("掩码不符", cmd=0x32, code=0x07)
        if int(expected_mask) == 0 or int(expected_mask) & ~0x3FF:
            raise pa.CommandRejectedError("数值非法", cmd=0x32, code=0x02)
        for i, v in self.stage_body.items():
            self.body[i] = list(v)
        if self.stage_jm is not None:
            self.jm = list(self.stage_jm)
        self.override = True
        self.stage_body = {}
        self.stage_jm = None

    def revert(self):
        self._arm.calls.append(("model.revert", None))
        if self._arm.enabled:
            raise pa.CommandRejectedError("需先失能", cmd=0x37, code=0x04)
        self.override = False
        self.stage_body = {}
        self.stage_jm = None
        self.dirty = True

    # ---- 0x38 / 0x39 ----
    def status(self):
        self._arm.calls.append(("model.status", None))

        class _St:
            pass
        st = _St()
        st.override = 1 if self.override else 0
        st.staged_mask = self._staged_mask()
        st.dirty = 1 if self.dirty else 0
        return _msg(st)

    def get_gravity(self, q):
        self._arm.calls.append(("model.get_gravity", list(q)))
        q = [float(v) for v in q]
        if len(q) != self.JM_N:
            raise pa.InvalidCommandError("q 个数不符")
        msum = sum(b[0] for b in self.body[1:])
        g = [msum * 9.81 * 0.001 * (i + 1) for i in range(7)]
        g[0] = msum * 9.81 * q[1] * 0.1
        return _msg(g)


class FakeArm:
    """实现的正是本工具用到的 SDK 面。"""

    #: 状态帧节奏。真固件 100Hz 主动推，`_read_status` 等一帧约 10ms 就返回；
    #: 替身若不睡，worker 空闲循环会全速空转 —— 曲线缓冲会被灌到几十万点，
    #: 测试慢到不可用，而且验的也不是真实节奏。
    frame_period = 0.01

    def __init__(self, n: int = 7, firmware: str = DEFAULT_FW, silent: bool = False):
        self._a = _FakeAck()
        self.n = n
        self.firmware = firmware
        self.calls: list = []
        #: [2026-09-14] 使能态 —— `model.commit()` / `model.revert()` 的门控要用。
        #: 真固件的判据是 `ctrl_is_armed() = enabled || enable_pending`, 替身无法表达
        #: `enable_pending` 的窗口 (SDK 也不上报它), 故只跟踪 `enabled`。
        self.enabled = False
        #: 模型状态机 (见 _FakeModel)
        self.model = _FakeModel(self)
        self.closed = False
        self.raise_error: Optional[BaseException] = None
        self._reject: Optional[BaseException] = None
        self.silent = silent                  # True -> get_state 恒 None（链路静默）
        self.repeat_same = False              # True -> 反复回同一帧（序列号不推进）
        self.write_error: Optional[BaseException] = None
        self._seq = 0
        self._zg = False
        self._zg_error = None
        self.frames: list = []                # [(cmd, payload, guarded)]
        self.params = _FakeParams(self)
        self.log = _FakeLog(self)
        self.diag = _FakeDiag(self)
        # 逐向量取各参数**合法区间下沿**，这样读回的快照能过 param_catalog 的校验
        from litetool import param_catalog as _C
        self.ff_vec = {p.item: [float(p.lo if p.lo is not None else 0.0)] * 7
                       for p in _C.JOINT_PARAMS if p.kind == "vec"}
        self.ff_scalar = {(gp.item, s): float(gp.lo if gp.lo is not None else 0.0)
                          for gp in _C.GLOBAL_PARAMS for s in gp.subs}
        self.ff_scalar[(9, 0)] = 0x1BF        # ff_mask（只读扩展项）
        self.last_reset_reason = "normal"

    # ---- 错误注入 ----
    def _maybe_raise(self):
        if self._reject is not None:
            err, self._reject = self._reject, None
            raise err
        if self.raise_error is not None:
            raise self.raise_error

    def reject(self, cmd: int, code: int, what: str = ""):
        """让**下一次**调用抛固件拒绝（用于验证 ERR 码映射）。"""
        self._reject = pa.CommandRejectedError(f"{what} 被拒", cmd=cmd, code=code)

    # ---- 生命周期 ----
    def close(self):
        self.closed = True

    # ---- 状态 ----
    def get_state(self, refresh: bool = False, timeout: float = 0.5):
        self.calls.append(("get_state", refresh))
        if self.raise_error is not None:
            raise self.raise_error
        if self.silent:
            if self.frame_period:
                time.sleep(self.frame_period)
            return _msg(None)             # 真 SDK 同款: "取不到帧" = `Msg.value is None`
        if self.frame_period:
            time.sleep(self.frame_period)
        if self.repeat_same and self._a.state is not None:
            st = self._a.state            # 同一帧再喂一遍，不推进 seq
        else:
            self._seq = (self._seq + 1) % 65536
            st = make_state(self.n, self._seq)
            self._a.state = st
        self._a._on_status(b"")           # 真实 SDK 里由 _read_status 调用
        return _msg(st)

    def bump_seq(self, gap: int):
        self._seq = (self._seq + gap) % 65536

    def get_status_now(self, timeout: float = 0.5):
        """与真 SDK 同款: 返回 `Msg` (取不到就抛 —— 替身用 `Msg.value is None` 表达)。"""
        return self.get_state(refresh=True)

    # ---- 命令 ----
    def _write_cmd(self, cmd: int, payload: bytes = b"", *, guarded: bool = True):
        if self.write_error is not None:
            raise self.write_error
        self.frames.append((cmd, payload, guarded))

    def _cmd(self, cmd, payload=b"", label="", timeout=1.0):
        self.calls.append((label or cmd, payload))
        self._maybe_raise()
        self.frames.append((cmd, payload, True))

    def enable(self, attempts: int = 12):
        self.enabled = True
        self.calls.append(("enable", attempts))
        self._maybe_raise()

    def disable(self):
        self.enabled = False
        self.calls.append(("disable", None))
        self._maybe_raise()

    def reset(self):
        self.calls.append(("reset", None))
        self._maybe_raise()

    def clear_faults(self):
        self.calls.append(("clear_faults", None))
        self._maybe_raise()

    def emergency_stop(self):
        self.calls.append(("emergency_stop", None))
        self._maybe_raise()

    def movej(self, q, speed=1.0):
        self.calls.append(("movej", (list(q), speed)))
        self._maybe_raise()
        # ⚠ `move_*`/`home` 是**动作结果**, 真 SDK **不**包信封 (返回裸 `RobotState`)
        # —— 替身照抄这条, 别顺手把它们也包起来。
        return self.get_state(refresh=True).value

    def move_p(self, pose, speed=1.0):
        self.calls.append(("move_p", (list(pose), speed)))
        self._maybe_raise()
        return self.get_state(refresh=True).value

    def home(self, *, timeout=None):
        self.calls.append(("home", timeout))
        self._maybe_raise()
        return self.get_state(refresh=True).value

    def move_js(self, q, dq=None, tau_ff=None):
        self.calls.append(("move_js", (list(q), dq, tau_ff)))
        self._maybe_raise()

    def send_mit(self, idx, q, dq, kp, kd, tau):
        self.calls.append(("send_mit", (idx, q, dq, kp, kd, tau)))
        self._maybe_raise()

    def send_mit_all(self, q, dq, kp, kd, tau):
        self.calls.append(("send_mit_all", None))
        self._maybe_raise()

    def park(self):
        self.calls.append(("park", None))
        self._maybe_raise()

    def set_speed(self, percent: int):
        self.calls.append(("set_speed", percent))
        self._maybe_raise()

    def get_tcp(self, timeout: float = 0.6):
        self.calls.append(("get_tcp", None))
        self._maybe_raise()
        return _msg((0.30, 0.0, 0.35, 3.1416, 0.0, 0.0))

    def ik(self, pose, q_seed=None, timeout: float = 3.0):
        self.calls.append(("ik", (list(pose), q_seed)))
        self._maybe_raise()
        # 与真 SDK 同款校验：seed 恒为**模型 7 轴**，与关节数解耦。
        # 替身漏了这条，就会把"台架上 seed 长度不对"这类真缺陷藏起来 —— 发生过一次。
        if q_seed is not None and len(q_seed) != _P.KIN_N:
            raise pa.InvalidCommandError(
                f"q_seed 需 {_P.KIN_N} 个 (固件 IK seed 恒为模型 7 轴)")
        if len(pose) != 6:
            raise pa.InvalidCommandError("ik 需要 pose[6]")
        return [0.1] * _P.KIN_N

    def get_ff_vec(self, item: int, timeout: float = 1.0):
        self.calls.append(("get_ff_vec", item))
        self._maybe_raise()
        return _msg(list(self.ff_vec[item]))

    def get_ff_scalar(self, item: int, sub: int = 0, timeout: float = 1.0):
        self.calls.append(("get_ff_scalar", (item, sub)))
        self._maybe_raise()
        return _msg(self.ff_scalar[(item, sub)])

    def get_ff_mask(self, timeout: float = 1.0):
        """⚠ 真 SDK 上这是**派生** getter, 刻意保持裸 `int` —— 替身照样保持。"""
        return int(self.get_ff_scalar(9, 0).value)

    def set_ff_vec(self, item: int, values):
        self.calls.append(("set_ff_vec", (item, list(values))))
        self._maybe_raise()
        self.ff_vec[item] = list(values)

    def set_ff_scalar(self, item: int, sub: int, value: float):
        self.calls.append(("set_ff_scalar", (item, sub, value)))
        self._maybe_raise()
        self.ff_scalar[(item, sub)] = value

    def set_ff_mask(self, mask: int):
        self.calls.append(("set_ff_mask", mask))
        self._maybe_raise()
        self.ff_scalar[(9, 0)] = float(mask)

    def save_params(self):
        self.calls.append(("save_params", None))
        self._maybe_raise()

    # ---- 零重力 ----
    @property
    def zero_g_active(self) -> bool:
        return self._zg

    @property
    def zero_g_error(self):
        return self._zg_error

    def zero_g_start(self, period: float = 0.04):
        self.calls.append(("zero_g_start", period))
        self._maybe_raise()
        self._zg = True

    def zero_g_stop(self, raise_on_lost: bool = False):
        self.calls.append(("zero_g_stop", raise_on_lost))
        self._maybe_raise()
        self._zg = False


class _FakeReader:
    def __init__(self, arm):
        self._arm = arm

    def total(self):
        self._arm.calls.append(("log.total", None))
        self._arm._maybe_raise()
        return 42

    def wait_for(self, n_ticks, timeout=None, **kw):
        self._arm.calls.append(("log.wait_for", n_ticks))
        return True

    def read_all(self):
        self._arm.calls.append(("log.read_all", None))
        return b""

    def iter_chunks(self):
        yield b""

    def samples(self):
        self._arm.calls.append(("log.samples", None))
        self._arm._maybe_raise()
        return [pa.LogSample(tick=i, q_ref=(0.1,) * self._arm.n,
                             dq=(0.0,) * self._arm.n, tau=(0.0,) * self._arm.n)
                for i in range(3)]


class _FakeLog:
    def __init__(self, arm):
        self._arm = arm
        self.started = 0

    def start(self, n_ticks):
        self._arm.calls.append(("log.start", n_ticks))
        self._arm._maybe_raise()
        self.started = n_ticks

    def stop(self):
        self._arm.calls.append(("log.stop", None))
        self._arm._maybe_raise()

    def reader(self, timeout=1.0, retries=3):
        return _FakeReader(self._arm)

    def capture(self, n_ticks, **kw):
        self._arm.calls.append(("log.capture", n_ticks))
        self._arm._maybe_raise()
        return self.reader().samples()

    def dump(self, path, wait=True, **kw):
        self._arm.calls.append(("log.dump", path))
        with open(path, "wb") as f:
            f.write(b"\x00" * 16)
        return 16


class _FakeDiag:
    def __init__(self, arm):
        self._arm = arm

    def kin_bench(self, timeout: float = 8.0):
        from litearm_core import parse_kin_bench
        self._arm.calls.append(("kin_bench", None))
        self._arm._maybe_raise()
        return _msg(parse_kin_bench(
            "LOOP14000 \nLINK crc=0 rfd=1 txf=0 ovr=2 loop_k=13\n"))


def wait_for(pred, timeout: float = 3.0, interval: float = 0.005) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(interval)
    return pred()


def worker_arm_factory(arms):
    """返回一个 arm_factory：每次 open 造一个新 FakeArm（或弹出预置的）。"""
    def factory(port):
        return arms.pop(0) if arms else FakeArm()
    return factory
