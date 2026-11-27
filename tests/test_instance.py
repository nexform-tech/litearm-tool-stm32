"""单实例锁 —— 第二个进程不得打开串口，并把已有窗口提到前台。

测试不启动完整 `app.main()`（会进 Qt 事件循环），只验证 `InstanceGuard` 的锁语义：
第一个进程建锁成功；第二个被拒绝且第一个收到 `activated`；第一个退出后锁可复用。
"""
from __future__ import annotations

import os
import time
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication              # noqa: E402

from litetool.instance import InstanceGuard           # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _name(tag: str) -> str:
    """每个用例独立锁名：不与真实在跑的实例、也不与并行测试互相干扰。"""
    return f"litearm-test-{tag}-{os.getpid()}-{uuid.uuid4().hex}"


def _wait_for(app, predicate, timeout_s: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


def test_first_acquire_succeeds(app):
    guard = InstanceGuard(_name("first"))
    try:
        assert guard.acquire() is True
        assert guard.lock_error is None
    finally:
        guard.close()


def test_second_instance_is_rejected_and_activates_the_first(app):
    name = _name("second")
    first = InstanceGuard(name)
    try:
        assert first.acquire() is True
        hits = []
        first.activated.connect(lambda: hits.append(1))

        second = InstanceGuard(name)
        try:
            assert second.acquire() is False
        finally:
            second.close()

        assert _wait_for(app, lambda: bool(hits)), \
            "已有实例没有收到激活请求 —— 第二个进程会静默退出"
    finally:
        first.close()


def test_lock_is_reusable_after_close(app):
    name = _name("reuse")
    first = InstanceGuard(name)
    assert first.acquire() is True
    first.close()

    second = InstanceGuard(name)
    try:
        assert second.acquire() is True, "上一个实例退出后，锁必须能被重新拿到"
    finally:
        second.close()


def test_activation_is_delivered_once_per_connection(app):
    """每次第二个实例启动都应前置一次 —— 不能只响应第一次。"""
    name = _name("repeat")
    first = InstanceGuard(name)
    try:
        assert first.acquire() is True
        hits = []
        first.activated.connect(lambda: hits.append(1))

        for i in range(2):
            second = InstanceGuard(name)
            try:
                assert second.acquire() is False
            finally:
                second.close()
            assert _wait_for(app, lambda i=i: len(hits) == i + 1), \
                f"第 {i + 1} 次启动没有激活已有窗口"
    finally:
        first.close()
