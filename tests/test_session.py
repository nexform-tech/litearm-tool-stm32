"""session.py 测试 —— 丢帧按读线程 seq 差分统计（100Hz 全量，非 GUI 抽稀）。"""
import struct
import types

from litetool import client as C
from litetool import protocol as P
from litetool.gui import session as sess_mod


def _status_bytes(seq):
    payload = struct.pack("<HH", 0, seq) + struct.pack("<fffffB", 1.0, 0, 0, 25.0, 35.0, 0)
    return P.pack_frame(P.RSP_STATUS, payload)


def _mk_session():
    link = types.SimpleNamespace(send_bytes=lambda data: None)
    cli = C.LiteArmClient(link)
    sess = sess_mod.Session()
    sess.client = cli           # 绕过 connect（避免真串口）
    return sess


def test_no_loss_counts_zero_drops():
    sess = _mk_session()
    for seq in range(0, 10):
        sess._on_frame(P.RSP_STATUS, _status_bytes(seq)[3:-2])
    assert sess.drops() == 0


def test_seq_gaps_count_missing_frames():
    sess = _mk_session()
    for seq in (0, 1, 2, 5, 6, 6, 40):      # 2→5 缺2帧; 6 重复不计; 6→40 缺33
        sess._on_frame(P.RSP_STATUS, _status_bytes(seq)[3:-2])
    assert sess.drops() == (2 + 33)


def test_seq_8bit_wraparound_no_false_drops():
    # 固件 seq 是 uint8_t (usb_cmd.c g_arm.seq++): 255->0 每 2.56s 回绕, 不得误计
    sess = _mk_session()
    for seq in (253, 254, 255, 0, 1, 2):
        sess._on_frame(P.RSP_STATUS, _status_bytes(seq)[3:-2])
    assert sess.drops() == 0


def test_seq_8bit_genuine_loss_across_wrap():
    # 253 -> 5: 中间 254,255,0,1,2,3,4 共 7 帧缺失 (mod 256 判据)
    sess = _mk_session()
    sess._on_frame(P.RSP_STATUS, _status_bytes(253)[3:-2])
    sess._on_frame(P.RSP_STATUS, _status_bytes(5)[3:-2])
    assert sess.drops() == 7


def test_connect_resets_counters():
    sess = _mk_session()
    for seq in (0, 1, 2, 7):
        sess._on_frame(P.RSP_STATUS, _status_bytes(seq)[3:-2])
    assert sess.drops() == 4
    # 模拟重连重置
    sess._prev_seq = None
    sess._drops = 0
    assert sess.drops() == 0
