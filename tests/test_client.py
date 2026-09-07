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
    p = P.decode_status_full(_status_frame_bytes()[3:-2])  # 取 payload
    link.inject(P.RSP_STATUS, _status_frame_bytes()[3:-2], cli)
    assert cli.online is True
    assert cli.status is not None
    assert cli.status.n == 1
    assert cli.status.mode == P.MODE_MOVE_J
    assert cli.status.joints[0].q == pytest.approx(1.0)
    assert cli.status.joints[0].t_mos == pytest.approx(25.0)


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
