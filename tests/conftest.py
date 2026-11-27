"""测试公共夹具。

结构化日志默认写 `~/.local/state/litearm-tool`；测试必须写进各自的临时目录，
否则跑一次套件就会污染开发者自己的日志，也会让历史断言受上一次运行影响。
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LITEARM_TOOL_LOG_DIR", str(tmp_path / "litearm-logs"))
    yield
