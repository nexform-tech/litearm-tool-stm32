"""传输层 —— USB CDC 串口发现 + SerialLink 后台读线程。

读线程独占串口 read，跑 FrameParser 分帧，CRC-ok 的帧交给 on_frame(cmd, payload)；
坏帧/丢弃字节计入 stats（监控页显示坏帧计数）。
物理层与 client 解耦：SerialLink 实现 client 需要的 send_bytes/is_open 契约。
"""
import threading
import time

from litetool import client
from litetool.protocol import FrameParser

# 板载复合 USB (gs_usb + CDC) 的 VID:PID
USB_VID = 0x1D50
USB_PID = 0x606F

DEFAULT_BAUD = 921600          # CDC 虚拟串口忽略波特率，此处仅占位


def find_ports():
    """枚举可用串口；LiteArm 板载 CDC 排最前，其余按名称排序。返回 [{device, description}]"""
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for p in list_ports.comports():
        dev = p.device
        if not dev:
            continue
        tag = "LiteArm STM32"
        if p.vid == USB_VID and p.pid == USB_PID:
            tag += " (板载 CDC)"
        elif p.vid:
            tag += f" VID:PID={p.vid:04X}:{p.pid:04X}"
        rows.append({"device": dev, "description": f"{tag} — {p.description or ''}".strip()})
    # 优先板载，其次 ttyACM*，再其余（保持稳定顺序）
    rows.sort(key=lambda r: (0 if r["device"].startswith("/dev/ttyACM") else 1, r["device"]))
    return rows


class SerialLink:
    """串口后台读线程封装。

    - connect(): 打开串口并启动读线程；ser 参数仅供测试注入。
    - 上行帧分帧后仅把 CRC-ok 帧交给 on_frame；帧解析错误只累计到 stats。
    - 任何底层读异常 → on_error(msg) 一次并停止线程（GUI 据此转离线态）。
    """

    def __init__(self, port: str, on_frame, on_error=None, baud: int = DEFAULT_BAUD,
                 ser=None):
        self.port = port
        self.baud = baud
        self._on_frame = on_frame
        self._on_error = on_error
        self._ser = ser
        self.parser = FrameParser()
        self.stats = {"frames": 0, "bad_crc": 0, "discarded": 0}
        self._stop = threading.Event()
        self._thread = None
        self._tx_lock = threading.Lock()
        self._connected = False

    @property
    def is_open(self) -> bool:
        return self._connected and self._ser is not None and bool(self._ser.is_open)

    def connect(self):
        if self._ser is None:
            import serial
            self._ser = serial.Serial(self.port, self.baud, timeout=0.05)
        self._stop.clear()
        self._connected = True
        self._thread = threading.Thread(target=self._reader_loop,
                                        name=f"serial-{self.port}", daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        self._connected = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass

    def send_bytes(self, data: bytes):
        if not self._connected or self._ser is None or not self._ser.is_open:
            raise client.LinkClosedError(f"串口 {self.port} 未打开")
        with self._tx_lock:
            self._ser.write(data)

    def _reader_loop(self):
        ser = self._ser
        reported = False
        while not self._stop.is_set():
            try:
                chunk = ser.read(4096)
            except Exception as e:  # noqa: BLE001
                if not reported:
                    reported = True
                    if self._on_error is not None:
                        self._on_error(f"串口读异常: {e}")
                break
            if not chunk:
                time.sleep(0.001)
                continue
            for fr in self.parser.feed(chunk):
                if fr.crc_ok:
                    self.stats["frames"] += 1
                    self._on_frame(fr.cmd, fr.payload)
                else:
                    self.stats["bad_crc"] += 1
            self.stats["discarded"] = self.parser.discarded
