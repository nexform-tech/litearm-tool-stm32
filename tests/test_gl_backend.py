"""Windows 软件 GL 开关 —— 平台/环境变量判定，不加载 Qt/OpenGL。"""
from __future__ import annotations

import os
import sys

from litetool import app as tool_app
from litetool import settings
from litetool.scene.gl_backend import software_gl_requested


def test_flag_is_windows_only(monkeypatch):
    monkeypatch.setenv("LITEARM_TOOL_SOFTWARE_GL", "1")
    monkeypatch.setattr(sys, "platform", "linux")
    assert software_gl_requested() is False
    monkeypatch.setattr(sys, "platform", "win32")
    assert software_gl_requested() is True


def test_flag_accepts_common_truthy_spellings(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    for value in ("1", "true", "TRUE", "yes", "on", " 1 "):
        monkeypatch.setenv("LITEARM_TOOL_SOFTWARE_GL", value)
        assert software_gl_requested() is True, value
    for value in ("", "0", "false", "off"):
        monkeypatch.setenv("LITEARM_TOOL_SOFTWARE_GL", value)
        assert software_gl_requested() is False, value


def test_prepare_gl_sets_qt_software_from_env(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LITEARM_TOOL_SOFTWARE_GL", "1")
    monkeypatch.delenv("QT_OPENGL", raising=False)
    tool_app._prepare_gl(settings.Settings())
    assert os.environ["QT_OPENGL"] == "software"


def test_prepare_gl_sets_qt_software_from_config(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("LITEARM_TOOL_SOFTWARE_GL", raising=False)
    monkeypatch.delenv("QT_OPENGL", raising=False)
    tool_app._prepare_gl(settings.Settings(scene_software_gl=True))
    assert os.environ["LITEARM_TOOL_SOFTWARE_GL"] == "1"
    assert os.environ["QT_OPENGL"] == "software"
