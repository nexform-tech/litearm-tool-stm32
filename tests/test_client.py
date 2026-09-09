"""client.py 测试 —— 用 FakeLink 注入串口行为，测状态缓存/ACK 配对/离线判定。"""
import struct
import threading
import time

import pytest

from litetool import client as C
from litetool import protocol as P

SEQ = 0x0100


def _status_frame_bytes(seq=SEQ):
    """1 关节状态帧（q=1.0, dq=0, tau=0, t=25/35, err=0, mode=MOVE_J）。"""
    flags = (P.MODE_MOVE_J << 6)
    payload = struct.pack("<HHfffffB", flags, seq, 1.0, 0.0, 0.0, 25.0, 35.0, 0x00)
    return P.pack_frame(P.RSP_STATUS, payload)


class FakeLink:
    """模拟物理层：记录发送，允许测试侧主动喂入上行帧。"""

    def __init__(self):
        self.sent = []          # list[bytes]
        self.is_open = True

    def send_bytes(self, data: bytes):
        if not self.is_open:
            raise C.LinkClosedError("link closed")
        self.sent.append(data)

    def inject(self, cmd: int, payload: bytes, client):
        client.handle_frame(cmd, payload)


def _mk_client(offline_timeout=0.5):
    link = FakeLink()
    logs = []
    cli = C.LiteArmClient(link, offline_timeout=offline_timeout, log=logs.append)
    return link, cli, logs


def test_status_updates_latest_view():
    link, cli, _ = _mk_client()
    assert cli.status is None and cli.online is False
    link.inject(P.RSP_STATUS, _status_frame_bytes()[3:-2], cli)
    assert cli.online is True
    assert cli.status is not None
    assert cli.status.n == 1
    assert cli.status.mode == P.MODE_MOVE_J
    assert cli.status.joints[0].q == pytest.approx(1.0)
    assert cli.status.joints[0].t_mos == pytest.approx(25.0)


def test_status_v15_enabled_and_joint_fault():
    """[1.5.0/M7] 新布局: flags bit9=enabled, 尾 joint_fault 透传到 StatusView"""
    link, cli, _ = _mk_client()
    payload = (struct.pack("<HH", (1 << 9) | (P.MODE_MOVE_J << 6), 5)
               + struct.pack("<fffffB", 1.0, 0.0, 0.0, 25.0, 35.0, 0x01)
               + struct.pack("<H", 0x0001))          # joint_fault = J1 锁存(单关节帧)
    link.inject(P.RSP_STATUS, payload, cli)
    st = cli.status
    assert st is not None and st.enabled is True
    assert st.joint_fault == 0x0001
    assert st.joint_fault_axes() == [1]


def test_ack_pairs_with_sent_command():
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["ok"], result["code"] = cli._cmd(P.CMD_ENABLE, timeout=1.0)

    import threading
    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)                      # 让发送发生
    assert len(link.sent) == 1
    assert link.sent[0][1] == P.CMD_ENABLE
    link.inject(P.RSP_ACK, bytes([P.CMD_ENABLE]), cli)
    t.join(timeout=2.0)
    assert result["ok"] is True and result["code"] is None


def test_err_resolves_command_with_code():
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["ok"], result["code"] = cli._cmd(P.CMD_ENABLE, timeout=1.0)

    import threading
    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    link.inject(P.RSP_ERR, bytes([P.CMD_ENABLE, 0x03]), cli)
    t.join(timeout=2.0)
    assert result["ok"] is False and result["code"] == 0x03


def test_ack_for_other_cmd_does_not_resolve():
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["ok"], result["code"] = cli._cmd(P.CMD_DISABLE, timeout=0.2)

    import threading
    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    link.inject(P.RSP_ACK, bytes([P.CMD_ENABLE]), cli)   # 错误命令的 ACK
    t.join(timeout=1.0)
    assert result["ok"] is False            # 超时，未被错误 ACK 解除


def test_command_timeout_logs_and_returns_false():
    link, cli, logs = _mk_client()
    ok, code = cli._cmd(P.CMD_DISABLE, timeout=0.1)   # 无任何应答
    assert ok is False and code is None
    assert any("超时" in m for m in logs)


def test_link_write_error_reported():
    link, cli, logs = _mk_client()
    link.is_open = False
    ok, code = cli._cmd(P.CMD_DISABLE, timeout=0.2)
    assert ok is False
    assert any("无法发送" in m for m in logs)


def test_enable_retries_on_not_ready_then_succeeds():
    link, cli, _ = _mk_client()
    state = {"count": 0}

    class _AutoLink(FakeLink):
        def send_bytes(self, data):
            super().send_bytes(data)
            if data[1] == P.CMD_ENABLE:
                state["count"] += 1
                if state["count"] < 3:
                    self.inject(P.RSP_ERR, bytes([P.CMD_ENABLE, 0x03]), cli)  # 未就绪
                else:
                    self.inject(P.RSP_ACK, bytes([P.CMD_ENABLE]), cli)

    link = _AutoLink()
    logs = []
    cli = C.LiteArmClient(link, log=logs.append)
    assert cli.enable(retries=4, delay=0.01) is True
    assert state["count"] == 3


def test_offline_detects_when_status_stops():
    link, cli, _ = _mk_client(offline_timeout=0.2)
    link.inject(P.RSP_STATUS, _status_frame_bytes()[3:-2], cli)
    assert cli.online is True
    time.sleep(0.35)
    assert cli.online is False


def test_emergency_now_bypasses_lock_and_sends_immediately():
    """急停走旁路通道：不加锁、不等 ACK，立刻写帧（忙等 ACK 的命令不能阻塞急停）。"""
    link, cli, _ = _mk_client()
    # 先占用 tx_lock（模拟一条在途等待 ACK 的命令）
    cli._tx_lock.acquire()
    try:
        ok = cli.emergency_now()
        assert ok is True
        assert link.sent[-1][1] == P.CMD_EMERGENCY_STOP
    finally:
        cli._tx_lock.release()


def test_emergency_now_failure_when_closed():
    link, cli, logs = _mk_client()
    link.is_open = False
    assert cli.emergency_now() is False
    assert any("急停" in m for m in logs)


def test_status_frame_does_not_resolve_pending():
    """状态帧与 ACK 同 ID(0x40)不同方向不同 cmd 值, 状态帧不得解除待定命令。"""
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["ok"], _ = cli._cmd(P.CMD_RESET, timeout=0.25)

    import threading
    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    link.inject(P.RSP_STATUS, _status_frame_bytes()[3:-2], cli)
    t.join(timeout=1.0)
    assert result["ok"] is False            # 未被状态帧误解除


# ---- [调参页] 参数读写 client 层 ----
def test_set_joint_param_frames_bytes():
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["r"] = cli.set_joint_param(2, 360.0, 5.0, 78.0)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    assert link.sent[-1] == P.pack_frame(P.CMD_SET_JOINT_PARAM,
                                         bytes([2]) + struct.pack("<3f", 360.0, 5.0, 78.0))
    link.inject(P.RSP_ACK, bytes([P.CMD_SET_JOINT_PARAM]), cli)
    t.join(timeout=2.0)
    assert result["r"] == (True, None)


def test_get_joint_param_receives_decoded():
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["v"] = cli.get_joint_param(0)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    assert link.sent[-1] == P.pack_frame(P.CMD_GET_JOINT_PARAM, bytes([0]))
    payload = struct.pack("<B5f", 0, 360.0, 5.0, 78.0, -2.8, 2.8)
    link.inject(P.RSP_JOINT_PARAM, payload, cli)
    t.join(timeout=2.0)
    idx, kp, kd, tau, q_min, q_max = result["v"]
    assert (idx, kp, kd, tau) == (0, 360.0, 5.0, 78.0)


def test_get_ff_vec_receives_decoded_30b():
    """0x2B -> 0x4B 应答 payload=[0x4B, item, 7×f32] 30B; 前导 RSP id 被解码剥离。"""
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["v"] = cli.get_ff_vec(3)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    assert link.sent[-1] == P.pack_frame(P.CMD_GET_FF_VEC, bytes([3]))
    vals = tuple(float(i) for i in range(7))
    payload = bytes([P.RSP_FF_VEC, 3]) + struct.pack("<7f", *vals)
    link.inject(P.RSP_FF_VEC, payload, cli)
    t.join(timeout=2.0)
    assert result["v"] == (3, vals)


def test_get_ff_scalar_receives_decoded_7b():
    """0x2C -> 0x4C 应答 payload=[0x4C, item, sub, f32] 7B; ff_mask 数值载回。"""
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["v"] = cli.get_ff_scalar(9, 0)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    assert link.sent[-1] == P.pack_frame(P.CMD_GET_FF_SCALAR, bytes([9, 0]))
    payload = bytes([P.RSP_FF_SCALAR, 9, 0]) + struct.pack("<f", 511.0)
    link.inject(P.RSP_FF_SCALAR, payload, cli)
    t.join(timeout=2.0)
    item, sub, val = result["v"]
    assert (item, sub, int(round(val))) == (9, 0, 0x1FF)


def test_set_ff_flags_frames_u32_le():
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["r"] = cli.set_ff_flags(0x1BF)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    assert link.sent[-1] == P.pack_frame(P.CMD_SET_FF_FLAGS, struct.pack("<I", 0x1BF))
    link.inject(P.RSP_ACK, bytes([P.CMD_SET_FF_FLAGS]), cli)
    t.join(timeout=2.0)
    assert result["r"] == (True, None)


def test_param_save_roundtrip_ack():
    link, cli, _ = _mk_client()
    result = {}

    def run():
        result["r"] = cli.param_save(timeout=2.0)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    assert link.sent[-1] == P.pack_frame(P.CMD_PARAM_SAVE)
    link.inject(P.RSP_ACK, bytes([P.CMD_PARAM_SAVE]), cli)
    t.join(timeout=3.0)
    assert result["r"] == (True, None)
