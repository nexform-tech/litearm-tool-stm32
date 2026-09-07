"""transport.py 测试 —— FakeSerial 注入字节流，测读线程分帧交付与生命周期。"""
import time

import pytest

from litetool import client
from litetool import protocol as P
from litetool import transport


class FakeSerial:
    """模拟 pyserial：按预置 chunks 出数据，read 超时返回 b''。"""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.is_open = True
        self.written = []

    def read(self, n):
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def write(self, data):
        self.written.append(bytes(data))
        return len(data)

    def close(self):
        self.is_open = False


def _frame_bytes(cmd):
    return P.pack_frame(cmd)


def test_find_ports_returns_list_of_dicts():
    ports = transport.find_ports()
    assert isinstance(ports, list)
    for p in ports:
        assert "device" in p and "description" in p


def test_find_ports_board_first_over_other_acm(monkeypatch):
    """[真机踩坑] JLink 虚拟口(ttyACM1, 1366:0105)按名字排序会抢在板载
    (ttyACM2, 1d50:606f)之前 —— VID:PID 精确匹配必须恒排最前。"""
    class _P:
        def __init__(self, device, vid, pid, description=""):
            self.device, self.vid, self.pid, self.description = device, vid, pid, description

    fake = [_P("/dev/ttyACM1", 0x1366, 0x0105, "J-Link CDC"),
            _P("/dev/ttyACM2", 0x1D50, 0x606F, "STM32 VCP")]
    import serial.tools.list_ports as lp
    monkeypatch.setattr(lp, "comports", lambda: fake)
    ports = transport.find_ports()
    assert ports[0]["device"] == "/dev/ttyACM2"
    assert "板载" in ports[0]["description"]


def test_serial_link_delivers_crc_ok_frames_in_order():
    frames = [_frame_bytes(P.CMD_ENABLE),
              _frame_bytes(P.CMD_DISABLE),
              _frame_bytes(P.CMD_GET_FIRMWARE)]
    data = b"".join(frames)
    ser = FakeSerial([data[:9], data[9:18], data[18:]])   # 任意切分
    got = []
    errs = []
    link = transport.SerialLink("/dev/fake", lambda c, p: got.append((c, p)),
                                on_error=errs.append, ser=ser)
    link.connect()
    deadline = time.time() + 2.0
    while time.time() < deadline and len(got) < 3:
        time.sleep(0.005)
    assert [c for c, _ in got] == [P.CMD_ENABLE, P.CMD_DISABLE, P.CMD_GET_FIRMWARE]
    assert link.stats["frames"] == 3
    link.close()
    assert not link.is_open
    assert errs == []


def test_serial_link_skips_garbage_before_frame():
    junk = b"\x00\x01garbage!!" + b"[litearm-usbcdc] ready\r\n"
    f1 = _frame_bytes(P.CMD_GET_FIRMWARE)
    ser = FakeSerial([junk + f1])
    got = []
    link = transport.SerialLink("/dev/fake", lambda c, p: got.append((c, p)),
                                ser=ser)
    link.connect()
    deadline = time.time() + 2.0
    while time.time() < deadline and len(got) < 1:
        time.sleep(0.005)
    assert got == [(P.CMD_GET_FIRMWARE, b"")]
    assert link.stats["discarded"] == len(junk)
    link.close()


def test_send_when_closed_raises_link_closed():
    ser = FakeSerial([])
    link = transport.SerialLink("/dev/fake", lambda c, p: None, ser=ser)
    with pytest.raises(client.LinkClosedError):
        link.send_bytes(P.pack_frame(P.CMD_ENABLE))
    link.close()


def test_send_bytes_writes_after_connect():
    ser = FakeSerial([])
    link = transport.SerialLink("/dev/fake", lambda c, p: None, ser=ser)
    link.connect()
    link.send_bytes(P.pack_frame(P.CMD_ENABLE))
    assert ser.written and ser.written[0][1] == P.CMD_ENABLE
    link.close()
