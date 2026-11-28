"""界面语言核心 —— 检测/回落/占位符/源码覆盖率。

这些用例钉住三件事：

* 首屏语言按 ``LANGUAGE`` → POSIX locale → Qt ``uiLanguages`` 的顺序选；一个
  都认不出时回中文（产品默认）。
* 英文表漏项/占位符写坏时 ``tr()`` **回落中文源文案**，绝不把键名或半截英文
  显示给操作员。
* ``litetool/gui`` 与核心用户可见模块里的每个中文字面量都在英文表里 —— 这是
  "全覆盖"的静态守卫，新加一句中文忘了翻会在这里红。
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

import pytest

from litetool import i18n
from litetool.i18n import _EN

REPO = pathlib.Path(__file__).resolve().parents[1]
NO_FILE = pathlib.Path("/nonexistent/etc/default/locale")

#: 允许保持中文/不翻译的字面量。语言自称是刻意保留的：中文界面里写
#: "English"，英文界面里写 "简体中文"。
ALLOWED = {"简体中文", "中文"}

#: 覆盖范围：界面 + 会直接进界面的核心模块。``dfu/engine.py`` 的深层诊断、
#: ``scene/*`` 的资产解析异常、``settings.py`` 的 stderr 提示是开发者/现场
#: 排障文本，不参与界面语言；正常路径的进度文案已单独翻译。
COVERAGE = [
    *sorted(str(p.relative_to(REPO)) for p in (REPO / "litetool/gui").rglob("*.py")),
    "litetool/checks.py",
    "litetool/sdk_worker.py",
    "litetool/activation.py",
    "litetool/gripper.py",
    "litetool/params_io.py",
    "litetool/model_io.py",
    "litetool/hyy_config.py",
    "litetool/dfu/job.py",
    "litetool/dfu/controller.py",
    "litetool/dfu/fake.py",
    "litetool/ports.py",
    "litetool/csv_export.py",
    "litetool/app.py",
    "litetool/instance.py",
    "litetool/license_io.py",
]

_CJK = re.compile(r"[一-鿿]")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)")


def _docstring_ids(tree: ast.AST) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _chinese_literals(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in skip and _CJK.search(node.value):
            yield node.lineno, node.value


# ---------------------------------------------------------------------------
# 系统语言检测
# ---------------------------------------------------------------------------
def test_language_list_comes_first():
    assert i18n.desktop_languages(
        {"LANGUAGE": "zh_CN:zh", "LANG": "en_US.UTF-8"}, NO_FILE
    ) == ["zh-CN", "zh", "en-US"]


@pytest.mark.parametrize("value", ["zh_CN.UTF-8", "zh_CN.utf8", "zh_CN"])
def test_locale_names_are_normalized(value):
    assert i18n.desktop_languages({"LANG": value}, NO_FILE) == ["zh-CN"]


@pytest.mark.parametrize("value", ["C", "C.UTF-8", "POSIX", ""])
def test_c_locales_contribute_no_language(value):
    assert i18n.desktop_languages({"LANG": value}, NO_FILE) == []


def test_system_locale_file_is_the_last_resort(tmp_path):
    locale_file = tmp_path / "locale"
    locale_file.write_text('LANG="zh_CN.UTF-8"\nLANGUAGE="zh_CN:zh"\n',
                           encoding="utf-8")
    assert i18n.desktop_languages({}, locale_file) == ["zh-CN", "zh"]


def test_environment_beats_the_system_locale_file(tmp_path):
    locale_file = tmp_path / "locale"
    locale_file.write_text('LANG="zh_CN.UTF-8"\n', encoding="utf-8")
    assert i18n.desktop_languages({"LANG": "en_US.UTF-8"}, locale_file) == ["en-US"]


def test_explicit_c_locale_does_not_read_the_system_file(tmp_path):
    locale_file = tmp_path / "locale"
    locale_file.write_text('LANG="zh_CN.UTF-8"\n', encoding="utf-8")
    assert i18n.desktop_languages({"LANG": "C.UTF-8"}, locale_file) == []


def test_detect_prefers_posix_language_on_linux():
    """中文桌面 + 英文终端：`LANGUAGE=zh_CN:zh` 必须压过 Qt 的 en-US。"""
    assert i18n.detect_language(
        {"LANGUAGE": "zh_CN:zh", "LANG": "en_US.UTF-8"}, NO_FILE,
        ui_languages=["en-US", "en"], platform="linux") == "zh"


def test_detect_prefers_qt_on_windows():
    assert i18n.detect_language(
        {}, NO_FILE, ui_languages=["en-GB", "en"], platform="win32") == "en"


def test_unknown_system_falls_back_to_chinese():
    assert i18n.detect_language({}, NO_FILE, ui_languages=["fr-FR"],
                                platform="linux") == "zh"


def test_resolve_priority_override_then_saved_then_config():
    assert i18n.resolve_language("en", override="zh", environ={},
                                 locale_file=NO_FILE) == "zh"
    assert i18n.resolve_language("en", environ={}, locale_file=NO_FILE) == "en"
    # auto/空串 -> 系统检测
    assert i18n.resolve_language("auto", environ={"LANG": "zh_CN.UTF-8"},
                                 locale_file=NO_FILE) == "zh"


# ---------------------------------------------------------------------------
# 翻译回落与占位符
# ---------------------------------------------------------------------------
def test_tr_falls_back_to_the_chinese_source():
    try:
        i18n.set_language("en")
        assert i18n.tr("__definitely_missing__") == "__definitely_missing__"
    finally:
        i18n.set_language("zh")


def test_tr_formats_named_placeholders():
    try:
        i18n.set_language("zh")
        assert i18n.tr("识别到 {n} 个关节", n=7) == "识别到 7 个关节"
    finally:
        i18n.set_language("zh")


def test_tr_broken_english_format_falls_back_to_source():
    """英文漏了占位符也不能在 Qt 槽里抛 KeyError。"""
    try:
        i18n.set_language("en")
        # 找一个带占位符的现有条目，模拟英文表写坏
        original = _EN.get("识别到 {n} 个关节")
        if original is None:
            pytest.skip("该条翻译尚未提供")
        _EN["识别到 {n} 个关节"] = "joints detected"
        assert i18n.tr("识别到 {n} 个关节", n=3) == "识别到 3 个关节"
    finally:
        if original is not None:
            _EN["识别到 {n} 个关节"] = original
        i18n.set_language("zh")


def test_sdk_locale_tracks_ui_language():
    try:
        i18n.set_language("zh")
        assert i18n.sdk_locale() == "zh-CN"
        i18n.set_language("en")
        assert i18n.sdk_locale() == "en-US"
    finally:
        i18n.set_language("zh")


def test_every_english_entry_keeps_the_source_placeholders():
    broken = []
    for source, english in _EN.items():
        want = set(_PLACEHOLDER.findall(source))
        got = set(_PLACEHOLDER.findall(english))
        if want != got:
            broken.append((source[:60], sorted(want), sorted(got)))
    assert broken == []


def test_english_table_is_not_empty():
    assert len(_EN) > 500, f"英文表只有 {len(_EN)} 条 —— 翻译未装入？"


# ---------------------------------------------------------------------------
# 源码覆盖率
# ---------------------------------------------------------------------------
def test_every_chinese_literal_in_scope_has_an_english_entry():
    missing = []
    for rel in COVERAGE:
        path = REPO / rel
        if not path.is_file():
            continue
        for lineno, text in _chinese_literals(path):
            if text in ALLOWED or text in _EN:
                continue
            missing.append(f"{rel}:{lineno}  {text[:80]!r}")
    assert missing == [], "以下中文串没有英文翻译:\n" + "\n".join(missing)


def test_english_entries_do_not_contain_chinese():
    leftovers = [(s[:60], e[:80]) for s, e in _EN.items()
                 if _CJK.search(e) and e not in ALLOWED]
    assert leftovers == []


def test_safe_detail_drops_chinese_only_in_english():
    try:
        i18n.set_language("en")
        assert i18n.safe_detail("engine said 中文错误") == ""
        assert i18n.safe_detail("engine said error") == "engine said error"
        i18n.set_language("zh")
        assert i18n.safe_detail("engine said 中文错误") == "engine said 中文错误"
    finally:
        i18n.set_language("zh")


def test_task_result_uses_english_error_codes_and_titles():
    import litearm as pa
    from litetool.sdk_worker import TaskResult

    try:
        i18n.set_language("en")
        err = pa.CommandRejectedError("x", cmd=0x2B, code=0x02)
        text = TaskResult("Parameter write", False, error=err).text
        assert "[2B-02]" in text
        assert "invalid field" in text
        assert not _CJK.search(text)
    finally:
        i18n.set_language("zh")
