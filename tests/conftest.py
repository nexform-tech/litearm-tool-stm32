"""测试公共夹具。

结构化日志默认写 `~/.local/state/litearm-tool`；测试必须写进各自的临时目录，
否则跑一次套件就会污染开发者自己的日志，也会让历史断言受上一次运行影响。
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LITEARM_TOOL_LOG_DIR", str(tmp_path / "litearm-logs"))
    # 界面语言选择存 QSettings INI；测试必须隔离，否则开发机上一次点选会让
    # 整套用例按英文跑（字符串断言全红）。
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "litearm-config"))
    # 既有用例的断言都是中文文案；开发机的桌面语言可能是英文（`LANGUAGE=en`），
    # 不钉住就会让"默认跟随系统"把整套断言翻成英文。界面语言自己的用例会显式
    # 设置 en，不受这里影响。
    monkeypatch.setenv("LANGUAGE", "zh_CN:zh")
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    from litetool import i18n
    i18n.set_language("zh")
    yield
    i18n.set_language("zh")
