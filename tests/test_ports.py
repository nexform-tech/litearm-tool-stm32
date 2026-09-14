"""串口枚举 —— 标签必须**如实**。

2026-09-13 实测事故：本机同时插着板载 CDC（`1d50:606f` → ttyACM2）和 ATK 调试探针
（`04d8:00df` → ttyACM0），另有 31 个内核占位节点 `/dev/ttyS*`。旧实现给**每一个**
串口都套上 "LiteArm STM32" 前缀，于是下拉框里 34 个条目全叫 LiteArm —— 用户照着
一个写着 LiteArm 的条目点 [连接]，只拿到一句超时，完全不知道为什么。
"""
import pytest

from litetool import ports as P


class _Port:
    def __init__(self, device, vid=None, pid=None, description=""):
        self.device = device
        self.vid = vid
        self.pid = pid
        self.description = description


@pytest.fixture
def fake_ports(monkeypatch):
    from serial.tools import list_ports
    rows = [
        _Port("/dev/ttyS0"),                                     # 内核占位节点
        _Port("/dev/ttyS1"),
        _Port("/dev/ttyACM0", 0x04D8, 0x00DF, "ATK-FS-HID-CMSIS-DAP"),
        _Port("/dev/ttyACM2", P.USB_VID, P.USB_PID, "STM32 Virtual ComPort"),
    ]
    monkeypatch.setattr(list_ports, "comports", lambda: rows)
    return rows


def test_board_is_first(fake_ports):
    f = P.find_ports()
    assert f[0]["device"] == "/dev/ttyACM2"
    assert f[0]["_ours"] is True
    assert "板载 CDC" in f[0]["description"]


def test_non_board_ports_do_not_claim_to_be_litearm(fake_ports):
    """这是本次事故的核心：非板载口绝不能自称 LiteArm。"""
    for r in P.find_ports():
        if not r["_ours"]:
            assert "LiteArm" not in r["description"], r["description"]


def test_probe_shows_its_own_name_and_vid_pid(fake_ports):
    row = next(r for r in P.find_ports() if r["device"] == "/dev/ttyACM0")
    assert "ATK-FS-HID-CMSIS-DAP" in row["description"]
    assert "04D8:00DF" in row["description"]


def test_system_placeholders_sorted_last_and_labelled(fake_ports):
    f = P.find_ports()
    assert f[-1]["device"].startswith("/dev/ttyS")
    row = next(r for r in f if r["device"] == "/dev/ttyS0")
    assert "非 USB" in row["description"]


def test_order_is_board_then_usb_then_system(fake_ports):
    ranks = [r["_rank"] for r in P.find_ports()]
    assert ranks == sorted(ranks)


def test_no_ports_at_all(monkeypatch):
    from serial.tools import list_ports
    monkeypatch.setattr(list_ports, "comports", lambda: [])
    assert P.find_ports() == []


def test_missing_device_name_is_skipped(monkeypatch):
    from serial.tools import list_ports
    monkeypatch.setattr(list_ports, "comports", lambda: [_Port(""), _Port("/dev/x")])
    assert [r["device"] for r in P.find_ports()] == ["/dev/x"]
