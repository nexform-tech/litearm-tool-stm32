"""单实例锁 —— 同一时间只允许一个上位机进程持有串口。

为什么需要：串口只能有一个所有者。两个实例同时打开同一条 CDC 端口，表现为
随机的"无应答(超时)" —— 和设备故障无法区分（见 `sdk_worker` 模块头）。所以第二个
实例不再打开串口，而是把已有窗口提到前台后退出。

实现用 `QLocalServer` / `QLocalSocket`：Linux 的 Unix socket 与 Windows 的命名管道
走同一套 Qt API，不引入第三方依赖。

判定顺序（避免竞态）：
1. `listen()` 成功 → 本进程是唯一实例；
2. 失败则 `connectToServer()`：连得上说明已有实例，发一条激活消息后退出；
3. 连不上说明是上次崩溃留下的陈旧套接字，`removeServer()` 后重试一次；
4. 重试仍失败（权限/资源异常）→ **仍然启动**，只记录锁错误。串口独占还有系统层
   兜底，因为建不出锁就拒绝启动，会让用户连程序都打不开。
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

#: 锁名同时是 Unix socket 名/Windows 管道名；改它等于换一把锁。
APP_KEY = "litearm-tool-stm32"

#: 连接已有实例的等待时间。本地套接字通常是毫秒级，300 ms 足够兜住繁忙机器。
CONNECT_TIMEOUT_MS = 300

#: 新实例发来的激活消息。**内容不参与判定** —— 能连上就说明已有实例在跑。
ACTIVATE = b"activate"


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
        #: `acquire()` 建锁失败时的原因；成功或"已有实例"时为 None。
        self.lock_error: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    def acquire(self) -> bool:
        """建锁。True = 可以继续启动；False = 已有实例，且已通知它前置。"""
        if self._server.listen(self._name):
            return True

        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if sock.waitForConnected(CONNECT_TIMEOUT_MS):
            sock.write(ACTIVATE)
            sock.flush()
            sock.waitForBytesWritten(CONNECT_TIMEOUT_MS)
            sock.disconnectFromServer()
            return False

        # 连不上：上次进程崩溃留下的陈旧套接字（Unix socket 文件 / 管道名）。
        QLocalServer.removeServer(self._name)
        if self._server.listen(self._name):
            return True

        # 建不出锁不能变成"程序打不开"：照常启动，但把原因留给调用方记录。
        self.lock_error = self._server.errorString() or "未知错误"
        return True

    def close(self) -> None:
        self._server.close()

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            if sock is None:
                break
            # 不读消息体：连通即"请前置"。断开交给 Qt 回收。
            sock.disconnectFromServer()
            self.activated.emit()
