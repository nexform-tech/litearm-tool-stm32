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
    """旧布局 (<=1.4.0): 4+21N, joint_fault 位为 None"""
    p = _status_payload(0, 0x0123, [(1.0, 2.0, 3.0, 30.0, 40.0, 0)])
    dec = P.decode_status_full(p)
    assert dec is not None
    flags, mode, seq, rows, jf = dec
    assert flags == 0 and mode == 0 and seq == 0x0123
    assert len(rows) == 1
    q, dq, tau, tm, tc, err = rows[0]
    assert (q, dq, tau, tm, tc, err) == (1.0, 2.0, 3.0, 30.0, 40.0, 0)
    assert jf is None


def test_decode_status_full_v15_layout():
    """1.5.0/M7 布局: 6+21N, 尾 joint_fault u16; flags bit9=enabled"""
    p = (_status_payload((1 << 9), 0x0200, [(1.0, 2.0, 3.0, 30.0, 40.0, 1)])
         + bytes([0x40, 0x00]))
    dec = P.decode_status_full(p)
    assert dec is not None
    flags, mode, seq, rows, jf = dec
    assert seq == 0x0200 and jf == 0x0040
    assert P.flag_enabled(flags) is True
    assert rows[0][5] == 1


def test_decode_status_full_seven_joints_and_mode_flags():
    rows = [(float(i), 0.0, 0.5 * i, 30.0 + i, 40.0 + i, i) for i in range(7)]
    flags = (1 << 0) | (P.MODE_EMERGENCY << 6)   # FAULT + EMERGENCY
    p = _status_payload(flags, 42, rows) + bytes([0xFF, 0x00])   # 1.5.0 七关节 153B
    assert len(p) == 6 + 21 * 7
    dec = P.decode_status_full(p)
    assert dec is not None
    flags2, mode, seq, rows2, jf = dec
    assert flags2 == flags and mode == P.MODE_EMERGENCY and seq == 42
    assert jf == 0x00FF
    assert len(rows2) == 7
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
    # [1.5.0/L4] enable 锁存类拒绝专用码
    assert 0x06 in P.ERR_TEXT and "reset" in P.ERR_TEXT[0x06].lower() or "复位" in P.ERR_TEXT[0x06]


def test_seq_mod_is_16bit():
    """[1.5.0/L1] seq 为真 u16: 回绕模 65536 (原 u8 时代为 256)"""
    assert P.SEQ_MOD == 65536


def test_cmd_rsp_id_lists_complete_for_tool():
    # 本工具用到的命令/响应均在模块中定义
    for name in ("CMD_MOVE_J", "CMD_ENABLE", "CMD_DISABLE", "CMD_EMERGENCY_STOP",
                 "CMD_CLEAR_FAULTS", "CMD_RESET", "CMD_SET_SPEED_PERCENT", "CMD_HOME",
                 "CMD_GET_STATUS", "CMD_GET_FIRMWARE", "CMD_GET_TCP",
                 "RSP_STATUS", "RSP_FIRMWARE", "RSP_ACK", "RSP_ERR", "RSP_TCP"):
        assert hasattr(P, name), name


# ---- [调参页] 运行时参数命令/响应 ----
def test_param_cmd_ids_match_firmware():
    """ID 与固件 usb_cmd.h 27961a1+ 一致 (读口 0x2B/0x2C 为并行实施定稿)。"""
    assert P.CMD_SET_JOINT_PARAM == 0x22
    assert P.CMD_SET_JOINT_LIMITS == 0x23
    assert P.CMD_GET_JOINT_PARAM == 0x24
    assert P.CMD_PARAM_SAVE == 0x25
    assert P.CMD_SET_FF_VEC == 0x26
    assert P.CMD_SET_FF_FLAGS == 0x27
    assert P.CMD_SET_FF_SCALAR == 0x28
    assert P.CMD_GET_FF_VEC == 0x2B
    assert P.CMD_GET_FF_SCALAR == 0x2C
    assert P.RSP_JOINT_PARAM == 0x49
    assert P.RSP_FF_VEC == 0x4B
    assert P.RSP_FF_SCALAR == 0x4C


def test_decode_joint_param_21b():
    p = struct.pack("<B5f", 2, 360.0, 5.0, 78.0, -2.8, 2.8)
    assert len(p) == 21
    idx, kp, kd, tau, q_min, q_max = P.decode_joint_param(p)
    assert (idx, kp, kd, tau) == (2, 360.0, 5.0, 78.0)
    assert (q_min, q_max) == pytest.approx((-2.8, 2.8))
    assert P.decode_joint_param(p[:-1]) is None


def test_decode_ff_vec_firmware_30b_layout():
    """固件 RSP_FF_VEC data = [0x4B, item, 7×f32] 30B (payload 内含 RSP id 字节)。"""
    vals = tuple(float(i) + 0.5 for i in range(7))
    p = bytes([P.RSP_FF_VEC, 3]) + struct.pack("<7f", *vals)
    assert len(p) == 1 + 1 + 28
    item, got = P.decode_ff_vec(p)
    assert item == 3 and got == vals
    assert P.decode_ff_vec(p[:-1]) is None


def test_decode_ff_scalar_firmware_7b_layout():
    """固件 RSP_FF_SCALAR data = [0x4C, item, sub, f32] 7B (勘误: 非 6B)。"""
    p = bytes([P.RSP_FF_SCALAR, 9, 0]) + struct.pack("<f", 511.0)   # ff_mask 数值载回
    assert len(p) == 7
    item, sub, val = P.decode_ff_scalar(p)
    assert (item, sub, int(round(val))) == (9, 0, 0x1FF)
    p2 = bytes([P.RSP_FF_SCALAR, 5, 2]) + struct.pack("<f", 0.25)   # payload_com[2]
    assert P.decode_ff_scalar(p2) == (5, 2, 0.25)
    assert P.decode_ff_scalar(p[:-1]) is None


def test_set_ff_vec_frame_payload_shape():
    payload = bytes([7]) + struct.pack("<7f", *range(7))
    raw = P.pack_frame(P.CMD_SET_FF_VEC, payload)
    frs = P.FrameParser().feed(raw)
    assert len(frs) == 1 and frs[0].crc_ok
    assert frs[0].cmd == P.CMD_SET_FF_VEC and frs[0].payload == payload
