"""`--fake` 演示模式 —— 用 SDK 自带的 `FakeTransport` 起一条完整假会话。

生产路径不 import 本模块；只有 `litetool.app` 解析到 `--fake` 时才用到，于是
`litearm.testing` 不会拖慢正常启动。假设备不碰串口，界面/参数/曲线都能走，
适合演示、培训和没有硬件时的 UI 开发。

⚠ 假固件的动力学/参数行为只做到"帧格式与命令语义可走"；它不是真机，不能用来
判断机械臂的真实运动或安全边界。
"""
from __future__ import annotations

from typing import Any, Callable


def build_fake_arm_factory(*, n: int = 7, fw: str = "Litearm1.12.3-7J") -> Callable[[Any], Any]:
    """返回 `SdkWorker(arm_factory=...)` 需要的工厂。

    每次 `open()` 新建一条 `FakeTransport`，所以断开再连不会复用上一条已关闭的
    假链路。`port` 只作占位（SDK 在注入工厂之前会先做 `find_cdc_port()` 空值检查，
    必须给一个非空值）。
    """

    def factory(port: Any) -> Any:
        from litearm import Arm
        from litearm.testing import FakeTransport

        fake_port = str(port or "fake")

        def transport_factory(_port: str) -> FakeTransport:
            return FakeTransport(port=fake_port, timeout=0.2, fw=fw, n=n)

        return Arm(port=fake_port, transport_factory=transport_factory).connect()

    return factory
