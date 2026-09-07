"""协议层（纯函数，无 IO）—— 移植自固件审计工具 arm_audit.py 的权威实现。

帧格式（双向一致）：SOF(0xA5) | CMD(1B) | LEN(1B) | PAYLOAD(0..255B) | CRC16(2B, LE)
CRC16-CCITT-FALSE: poly 0x1021 init 0xFFFF, 覆盖 SOF..PAYLOAD。
状态帧 (RSP_STATUS) G8 布局: 头4B = flags(u16) + seq(u16), 每关节 21B:
q,dq,tau,t_mos,t_coil(f32) + err(u8)。
"""
import struct

# ---- 帧与命令/响应 ID（来源: 固件 User/litearm/hal/usb_cmd.h） ----
SOF = 0xA5

# 下行 CMD
CMD_MOVE_J = 0x01
CMD_MOVE_P = 0x02
CMD_MOVE_JS = 0x03
CMD_MOVE_MIT = 0x04
CMD_MOVE_MIT_ALL = 0x05
CMD_ENABLE = 0x10
CMD_DISABLE = 0x11
CMD_EMERGENCY_STOP = 0x12
CMD_CLEAR_FAULTS = 0x13
CMD_RESET = 0x14
CMD_SET_MOTION_MODE = 0x20
CMD_SET_SPEED_PERCENT = 0x21
CMD_GET_JOINT_PARAM = 0x24
CMD_HOME = 0x2A
CMD_GET_STATUS = 0x40        # 与 RSP_STATUS 同值, 仅方向区分
CMD_GET_FIRMWARE = 0x41
CMD_GET_TCP = 0x43

# 上行 RSP
RSP_STATUS = 0x40
RSP_DETAIL = 0x41            # G8 已移除, 仅兼容旧固件
RSP_FIRMWARE = 0x44
RSP_ACK = 0x45
RSP_ERR = 0x46
RSP_TCP = 0x48
RSP_JOINT_PARAM = 0x49

# 状态帧 seq 回绕周期：1.5.0/L1 起固件 seq 为真 uint16（且仅发送成功才递增），
# 65536 帧(≈11min@100Hz) 回绕。（1.4.0 及以前为 u8 装 16 位字段, 2.56s 回绕,
# 上位机曾按 256 模适配；连接 1.4.x 固件时丢帧统计会偏大, 属兼容降级。）
SEQ_MOD = 65536

# 固件安全/状态位（litearm.h）
ARM_FLAG_FAULT = 1 << 0
ARM_FLAG_WATCHDOG_TRIPPED = 1 << 1
ARM_FLAG_FEEDBACK_STALE = 1 << 2
ARM_FLAG_TEMP_WARNING = 1 << 3
ARM_FLAG_POSITION_VIOLATION = 1 << 4
ARM_FLAG_OVERSPEED = 1 << 5

MODE_INIT = 0
MODE_MOVE_J = 1
MODE_MOVE_P = 2
MODE_MOVE_JS = 3
MODE_MOVE_MIT = 4
MODE_MOVE_MIT_ALL = 5
MODE_EMERGENCY = 6

FLAG_NAMES = {0: "FAULT", 1: "WD_TRIPPED", 2: "FB_STALE",
              3: "TEMP_WARN", 4: "POS_VIOL", 5: "OVERSPEED"}
FLAG_LABELS = {0: "故障", 1: "看门狗", 2: "反馈过期", 3: "超温",
               4: "越限位", 5: "超速"}
MODE_NAMES = {0: "INIT", 1: "MOVE_J", 2: "MOVE_P", 3: "MOVE_JS",
              4: "MOVE_MIT", 5: "MIT_ALL", 6: "EMERGENCY"}

# ERR 码中文映射（RSP_ERR payload = [echoed_cmd, code]）
ERR_TEXT = {
    0x00: "未知命令",
    0x01: "载荷过短（参数校验不通过，未执行）",
    0x02: "数值非法（NaN/超限），固件已拒绝",
    0x03: "未就绪/未使能（反馈未齐可重试；运动命令需先 enable）",
    0x04: "需先 disable（先失磁再做此操作）",
    0x05: "忙（上一条命令/IK 求解仍在执行）",
    0x06: "锁存中，须先 reset 复位（EMERGENCY/单轴故障，重试无效）",
}


def flag_enabled(flags: int) -> bool:
    """[1.5.0/M7] flags bit9 = 固件侧 enabled（旧固件无此位, 恒 False 降级）"""
    return bool(flags & (1 << 9))


# ---- CRC16-CCITT-FALSE (poly 0x1021 init 0xFFFF; 与固件 crc16.c 一致) ----
def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def pack_frame(cmd: int, payload: bytes = b"") -> bytes:
    """下行帧打包: SOF CMD LEN PAYLOAD CRC16_LE。"""
    body = bytes([SOF, cmd, len(payload)]) + payload
    crc = crc16_ccitt_false(body)
    return body + bytes([crc & 0xFF, crc >> 8])


# ---- 上行帧流式解析 ----
class Frame:
    __slots__ = ("cmd", "payload", "crc_ok")

    def __init__(self, cmd: int, payload: bytes, crc_ok: bool):
        self.cmd, self.payload, self.crc_ok = cmd, payload, crc_ok


class FrameParser:
    """喂入原始字节, 产出完整帧; 容忍任意垃圾/文本 banner 并 SOF 重同步。"""

    def __init__(self):
        self.buf = bytearray()
        self.discarded = 0

    def feed(self, data: bytes):
        out = []
        self.buf += data
        while len(self.buf) >= 3:
            if self.buf[0] != SOF:
                self.discarded += 1
                del self.buf[0]
                continue
            ln = self.buf[2]
            need = 3 + ln + 2
            if len(self.buf) < need:
                break
            body = bytes(self.buf[:3 + ln])
            crc = self.buf[3 + ln] | (self.buf[4 + ln] << 8)
            del self.buf[:need]
            out.append(Frame(body[1], bytes(body[3:3 + ln]), crc16_ccitt_false(body) == crc))
        return out


# ---- 上行帧解码 ----
def decode_status_full(p: bytes):
    """状态帧完整解析: (flags, mode, seq, [(q,dq,tau,t_mos,t_coil,err)...], joint_fault)

    兼容两种布局: ≤1.4.0 = 4+21N（joint_fault 返回 None）;
    1.5.0/M7 = 6+21N（尾部 joint_fault u16 = G7 固件断轴位图）。
    flags bit9 = enabled（1.5.0 起，用 flag_enabled() 取）。结构异常返回 None。
    """
    n = (len(p) - 4) // 21
    if n < 1 or len(p) not in (4 + n * 21, 6 + n * 21):
        return None
    flags = struct.unpack_from("<H", p, 0)[0]
    seq = struct.unpack_from("<H", p, 2)[0]
    rows = [struct.unpack_from("<fffff", p, 4 + i * 21) + (p[4 + i * 21 + 20],)
            for i in range(n)]
    jf = None
    if len(p) == 6 + n * 21:
        jf = p[4 + n * 21] | (p[5 + n * 21] << 8)
    return flags, (flags >> 6) & 0x7, seq, rows, jf


def decode_tcp(p: bytes):
    """TCP 帧 -> (pos(x,y,z), rpy(roll,pitch,yaw)); 长度异常返回 None"""
    if len(p) != 24:
        return None
    vals = struct.unpack("<6f", p)
    return vals[:3], vals[3:]


def decode_firmware(p: bytes) -> str:
    return p.decode(errors="replace")


def decode_ack(p: bytes) -> int:
    """ACK payload = [echoed cmd u8]"""
    return p[0] if p else 0


def decode_err(p: bytes):
    """ERR payload = [echoed cmd u8, code u8]"""
    if len(p) < 2:
        return (p[0] if p else 0), 0
    return p[0], p[1]
