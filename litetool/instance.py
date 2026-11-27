"""单实例锁 —— 同一时间只允许一个上位机进程持有串口。

为什么需要：串口只能有一个所有者。两个实例同时打开同一条 CDC 端口，表现为
随机的"无应答(超时)" —— 和设备故障无法区分（见 `sdk_worker` 模块头）。所以第二个
实例不再打开串口，而是把已有窗口提到前台后退出。

实现分两件事，**不能合成一件**：

* **独占**用 `QLockFile`（操作系统级文件锁）。不能用 `QLocalServer.listen()`
  当判据：2026-11-27 在宿主 Windows 上实测，同一个管道名允许两个进程（甚至同进程
  两个 `QLocalServer`）同时 `listen()` 成功 —— 第二个实例会照常启动、再去开一次
  串口。Linux 的 Unix socket 恰好是独占的，所以这个差异只在 Windows 上暴露。
* **前置已有窗口**用 `QLocalServer` / `QLocalSocket`：它不是锁，只是同一台机器上
  两个进程之间的一根消息管。

判定顺序（避免竞态）：
1. `QLockFile.tryLock(0)` 成功 → 本进程是唯一实例，再起 `QLocalServer` 等激活消息；
2. 失败且原因是 `LockFailedError` → 已有实例，连过去发一条激活消息后退出；
   连不上则说明对方恰好在退出，再抢一次锁；
3. 锁文件本身不可用（权限/资源异常）→ **仍然启动**，只记录锁错误。串口独占还有
   系统层兜底，因为建不出锁就拒绝启动，会让用户连程序都打不开。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QLockFile, QObject, QStandardPaths, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

#: 锁名同时是 Unix socket 名/Windows 管道名；改它等于换一把锁。
APP_KEY = "litearm-tool-stm32"

#: 连接已有实例的等待时间。本地套接字通常是毫秒级，300 ms 足够兜住繁忙机器。
CONNECT_TIMEOUT_MS = 300

#: 新实例发来的激活消息。**内容不参与判定** —— 能连上就说明已有实例在跑。
ACTIVATE = b"activate"


def _lock_path(name: str) -> str:
    """文件锁的落点：用户数据目录优先，不可写时退到临时目录。

    刻意**不用** `%TEMP%` 作为首选：磁盘清理/重启会删掉锁文件，而锁是"进程还活着"
    的证据。`GenericDataLocation` 是 Windows `%LOCALAPPDATA%` / Linux
    `~/.local/share`，不会被日常清理顺手删掉。
    """
    for location in (QStandardPaths.GenericDataLocation,
                     QStandardPaths.TempLocation):
        base = QStandardPaths.writableLocation(location)
        if not base:
            continue
        directory = Path(base) / "litearm-tool"
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return str(directory / f"{name}.lock")
    return str(Path(tempfile.gettempdir()) / f"{name}.lock")


class InstanceGuard(QObject):
    """单实例守卫。`acquire()` 返回 False 时调用方应退出。

    第一个实例把 `activated` 接到主窗口的 `activate()`，之后每次有第二个实例
    尝试启动，都能把窗口拉到前台。
    """

    activated = pyqtSignal()

    def __init__(self, name: str = APP_KEY, parent=None):
        super().__init__(parent)
        self._name = name
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        #: 文件锁对象必须活到 `close()` —— 它一旦被回收，锁就释放了。
        self._lock_file: Optional[QLockFile] = None
        #: `acquire()` 建锁失败时的原因；成功或"已有实例"时为 None。
        self.lock_error: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    def acquire(self) -> bool:
        """建锁。True = 可以继续启动；False = 已有实例，且已通知它前置。"""
        got, error = self._try_lock()
        if not got and error is None:
            # 文件锁被另一个进程持有。先试激活；连不上说明它正好在退出，再抢一次。
            if self._notify_existing():
                return False
            got, error = self._try_lock()
            if not got and error is None:
                self._notify_existing()
                return False

        if error is not None:
            # 建不出锁不能变成"程序打不开"：照常启动，但把原因留给调用方记录。
            self.lock_error = error
        self._start_server()
        return True

    def _try_lock(self) -> tuple[bool, Optional[str]]:
        """返回 `(拿到了吗, 锁文件本身的错误)`。

        第二个返回值只在"不是另一个实例、但锁也建不出来"时非 None —— 调用方据此
        决定是照常启动（权限问题）还是让位（已有实例）。
        """
        if self._lock_file is None:
            self._lock_file = QLockFile(_lock_path(self._name))
        if self._lock_file.tryLock(0):
            return True, None
        if self._lock_file.error() == QLockFile.LockFailedError:
            return False, None
        return False, (self._lock_file.errorString() or "锁文件不可用")

    def _start_server(self) -> None:
        """起激活通道。它**不承担排他**，起不来只影响"前置已有窗口"。"""
        if self._server.listen(self._name):
            return
        # 上次进程崩溃可能留下陈旧的 socket / 管道名；有文件锁兜底，这里可以安全清。
        QLocalServer.removeServer(self._name)
        if not self._server.listen(self._name) and not self.lock_error:
            self.lock_error = self._server.errorString() or "未知错误"

    def _notify_existing(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if not sock.waitForConnected(CONNECT_TIMEOUT_MS):
            return False
        sock.write(ACTIVATE)
        sock.flush()
        sock.waitForBytesWritten(CONNECT_TIMEOUT_MS)
        sock.disconnectFromServer()
        return True

    def close(self) -> None:
        self._server.close()
        if self._lock_file is not None:
            self._lock_file.unlock()
            self._lock_file = None

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            if sock is None:
                break
            # 不读消息体：连通即"请前置"。断开交给 Qt 回收。
            sock.disconnectFromServer()
            self.activated.emit()
