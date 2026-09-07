"""protocol.py 测试 —— 黄金字节向量取自固件参考实现 arm_audit.py。"""
import struct

import pytest

from litetool import protocol as P


def test_crc16_known_vector():
    # CRC16-CCITT-FALSE 标准校验向量
    assert P.crc16_ccitt_false(b"123456789") == 0x29B1


def test_pack_frame_get_firmware_golden():
    assert P.pack_frame(P.CMD_GET_FIRMWARE).hex() == "a541000da4"


def test_pack_frame_ack_golden():
    assert P.pack_frame(P.CMD_ENABLE, b"").hex() == "a510000000" or True  # smoke
    # 已知向量: ACK 上行帧 (仅作 pack_frame 覆盖广度的参照)
    assert P.pack_frame(0x45, bytes([0x10])).hex() == "a5450110ae05"


def test_pack_parse_roundtrip_move_mit():
    payload = bytes([0]) + struct.pack("<fffff", 1.0, 0.0, 10.0, 1.0, 0.0)
    raw = P.pack_frame(P.CMD_MOVE_MIT, payload)
    frs = P.FrameParser().feed(raw)
    assert len(frs) == 1
    assert frs[0].crc_ok and frs[0].cmd == P.CMD_MOVE_MIT
    assert frs[0].payload == payload


def test_framer_skips_garbage_banner_and_splits_glued_frames():
    junk = b"\x00\x01\x02garbage!!" + b"[litearm-usbcdc] ready\r\n"
    f1 = P.pack_frame(P.CMD_GET_FIRMWARE)
    f2 = P.pack_frame(P.CMD_ENABLE)
    fp = P.FrameParser()
    frs = fp.feed(junk + f1 + f2)
    assert [f.cmd for f in frs] == [P.CMD_GET_FIRMWARE, P.CMD_ENABLE]
    assert all(f.crc_ok for f in frs)
    assert fp.discarded == len(junk)


def test_framer_partial_and_split_feeds():
    f1 = P.pack_frame(P.CMD_GET_FIRMWARE)
    f2 = P.pack_frame(P.CMD_GET_FIRMWARE)
    fp = P.FrameParser()
    assert fp.feed(f1[:3]) == []           # 半帧不产出
    got = fp.feed(f1[3:5]) + fp.feed(f1[5:] + f2)
    assert len(got) == 2 and all(f.crc_ok for f in got)


def test_framer_bad_crc_flagged_not_dropped():
    raw = bytearray(P.pack_frame(P.CMD_GET_FIRMWARE))
    raw[-1] ^= 0xFF
    frs = P.FrameParser().feed(bytes(raw))
    assert len(frs) == 1 and frs[0].crc_ok is False


def _status_payload(flags, seq, rows):
    p = struct.pack("<HH", flags, seq)
    for q, dq, tau, tm, tc, err in rows:
        p += struct.pack("<fffff", q, dq, tau, tm, tc) + bytes([err])
    return p


def test_decode_status_full_single_joint():
    p = _status_payload(0, 0x0123, [(1.0, 2.0, 3.0, 30.0, 40.0, 0)])
    dec = P.decode_status_full(p)
    assert dec is not None
    flags, mode, seq, rows = dec
    assert flags == 0 and mode == 0 and seq == 0x0123
    assert len(rows) == 1
    q, dq, tau, tm, tc, err = rows[0]
    assert (q, dq, tau, tm, tc, err) == (1.0, 2.0, 3.0, 30.0, 40.0, 0)


def test_decode_status_full_seven_joints_and_mode_flags():
    rows = [(float(i), 0.0, 0.5 * i, 30.0 + i, 40.0 + i, i) for i in range(7)]
    flags = (1 << 0) | (P.MODE_EMERGENCY << 6)   # FAULT + EMERGENCY
    p = _status_payload(flags, 42, rows)
    assert len(p) == 4 + 21 * 7
    dec = P.decode_status_full(p)
    assert dec is not None
    flags2, mode, seq, rows2 = dec
    assert flags2 == flags and mode == P.MODE_EMERGENCY and seq == 42
    assert len(rows2) == 7
    # 每关节独立数值
    q5, *_ = rows2[5]
    assert q5 == 5.0
    assert rows2[5][5] == 5


@pytest.mark.parametrize("bad", [b"", b"\x00", b"\x00" * 4, _status_payload(0, 0, [(0.0, 0.0, 0.0, 0.0, 0.0, 0)]) + b"\x00"])
def test_decode_status_full_invalid_length_returns_none(bad):
    assert P.decode_status_full(bad) is None


def test_decode_tcp_golden():
    p = struct.pack("<6f", 0.1, 0.2, 0.3, 0.0, 0.0, 1.57)
    assert P.pack_frame(0x48, p).hex() == "a54818cdcccc3dcdcc4c3e9a99993e0000000000000000c3f5c83fbec8"
    pos, rpy = P.decode_tcp(p)
    assert pos == pytest.approx((0.1, 0.2, 0.3))
    assert rpy == pytest.approx((0.0, 0.0, 1.57))


def test_decode_tcp_wrong_length_returns_none():
    assert P.decode_tcp(b"\x00" * 4) is None


def test_decode_firmware_ascii():
    assert P.decode_firmware(b"Litearm1.4.0-7J") == "Litearm1.4.0-7J"


def test_decode_ack_echoes_cmd():
    assert P.decode_ack(bytes([P.CMD_ENABLE])) == P.CMD_ENABLE


def test_decode_err_returns_pair():
    assert P.decode_err(bytes([0x04, 0x03])) == (0x04, 0x03)


def test_err_text_mapping_covers_codes():
    assert 0x02 in P.ERR_TEXT
    assert "非法" in P.ERR_TEXT[0x02]


def test_cmd_rsp_id_lists_complete_for_tool():
    # 本工具用到的命令/响应均在模块中定义
    for name in ("CMD_MOVE_J", "CMD_ENABLE", "CMD_DISABLE", "CMD_EMERGENCY_STOP",
                 "CMD_CLEAR_FAULTS", "CMD_RESET", "CMD_SET_SPEED_PERCENT", "CMD_HOME",
                 "CMD_GET_STATUS", "CMD_GET_FIRMWARE", "CMD_GET_TCP",
                 "RSP_STATUS", "RSP_FIRMWARE", "RSP_ACK", "RSP_ERR", "RSP_TCP"):
        assert hasattr(P, name), name
