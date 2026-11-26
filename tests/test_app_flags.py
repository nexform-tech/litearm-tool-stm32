"""启动参数解析 —— `--activation-url` 的取值/删除边界（不启动 GUI）。"""
from __future__ import annotations

from litetool import app


def test_flag_value_space_form():
    assert app._flag_value(["m", "--activation-url", "https://x"],
                           "--activation-url") == "https://x"


def test_flag_value_equals_form():
    assert app._flag_value(["m", "--activation-url=https://y"],
                           "--activation-url") == "https://y"


def test_flag_value_reports_missing():
    assert app._flag_value(["m", "--activation-url"], "--activation-url") is None
    # 下一个 token 是另一个选项：不能把它当值。
    assert app._flag_value(["m", "--activation-url", "-platform", "offscreen"],
                           "--activation-url") is None


def test_drop_option_space_form():
    assert app._drop_option(["m", "--activation-url", "https://x", "z"],
                            "--activation-url") == ["m", "z"]


def test_drop_option_equals_form():
    assert app._drop_option(["m", "--activation-url=https://x"],
                            "--activation-url") == ["m"]


def test_drop_option_missing_value_keeps_next_option():
    """缺值不能把后面的 Qt 参数一起吞掉（曾经会删掉 `-platform`）。"""
    assert app._drop_option(["m", "--activation-url", "-platform", "offscreen"],
                            "--activation-url") == ["m", "-platform", "offscreen"]


def test_drop_option_trailing_flag():
    assert app._drop_option(["m", "--activation-url"], "--activation-url") == ["m"]


def test_has_option():
    assert app._has_option(["m", "--activation-url"], "--activation-url")
    assert app._has_option(["m", "--activation-url=https://x"], "--activation-url")
    assert not app._has_option(["m", "--fake"], "--activation-url")
