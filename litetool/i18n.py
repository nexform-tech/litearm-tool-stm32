"""界面语言 —— 中文源文案为键的轻量字符串表（不引入 Qt Linguist / Web i18n）。

为什么用"中文源文案即键"
------------------------
本工具的界面文字本来就是中文，直接把它当键有三个好处：

* 新加一句中文不用先起一个键名，漏翻时 ``tr()`` **原样回落到中文** —— 永远不会
  把 ``settings.language`` 之类的键名显示给操作员；
* 英文翻译集中在一张表里，代码里读得出来"这句话在哪"；
* 覆盖率可以用 AST 静态检查：源码里任何中文串都必须出现在表里（见
  ``tests/test_i18n.py``）。

语言选择
--------
``配置/config.yaml`` 的 ``language: auto`` 是**默认值**（``auto`` = 跟随系统）：
操作员在设置页选过语言后，选择存进 ``QSettings`` 并优先于配置；把设置页选回
"跟随系统"则清掉该记录，重新跟随配置/系统。``--lang`` 只覆盖本次运行，不落盘。

系统语言检测
------------
Linux 桌面"中文界面 + 英文终端"的常见配置是 ``LANG=en_US.UTF-8`` +
``LANGUAGE=zh_CN:zh``。GTK/Qt 的翻译跟 ``LANGUAGE`` 走，所以这里也以
``LANGUAGE`` 优先，再退 ``LC_ALL`` / ``LC_MESSAGES`` / ``LANG``；进程里一个
locale 变量都没有时才读 ``/etc/default/locale``。Windows 上则优先 Qt 给的
``QLocale.system().uiLanguages()``（``ui_languages`` 参数）。
"""
from __future__ import annotations

import contextlib
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

#: 产品支持的界面语言。顺序 = 设置页下拉框顺序。
LANGUAGES = ("zh", "en")

#: 语言自称 —— 不翻译：中文界面里写 "English"，英文界面里写 "简体中文"。
LANGUAGE_NAMES = {"zh": "简体中文", "en": "English"}

#: 认不出系统语言时的默认值。本产品以中文为源语言。
DEFAULT_LANGUAGE = "zh"

#: 桌面登录写下的系统级默认值。只在进程环境里**完全没有** locale 变量时才读它：
#: 有 ``LANG=C.UTF-8`` 的服务进程是刻意留在 C locale 的，不该被系统文件改回中文。
DEFAULT_LOCALE_FILE = Path("/etc/default/locale")

#: 这两个不是"语言"，它们只表示"不做本地化"。
_C_LOCALES = frozenset({"c", "posix"})

#: ``zh_CN.UTF-8`` / ``en_US.utf8`` / ``sr_RS@latin`` 里的语言与地区。
_LOCALE_RE = re.compile(
    r"^(?P<lang>[A-Za-z]{2,3})(?:[_-](?P<region>[A-Za-z]{2}|[0-9]{3}))?$")

#: 我们认的 locale 变量，按 gettext 的优先级排列（LANGUAGE 单独处理，它是列表）。
_LOCALE_NAMES = ("LC_ALL", "LC_MESSAGES", "LANG")

_language = DEFAULT_LANGUAGE

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def has_chinese(text) -> bool:
    return bool(_CJK_RE.search(str(text or "")))


def safe_detail(text) -> str:
    """英文界面里的"下層透传文本"：含中文就丢掉，宁可少一句也不留中文残留。

    用在 SDK/引擎/资产解析这类**不受本工具翻译表控制**的异常消息上。中文界面
    原样返回；英文界面里中文详情既不翻译也不显示，由调用方的英文错误码文案接管。
    """
    text = str(text or "")
    if _language == "en" and has_chinese(text):
        return ""
    return text


# ---------------------------------------------------------------------------
# 语言状态
# ---------------------------------------------------------------------------
def language() -> str:
    """当前界面语言（``"zh"`` / ``"en"``）。"""
    return _language


def normalize_language(value) -> Optional[str]:
    """``zh`` / ``zh_CN`` / ``zh-CN`` / ``en_US`` → 受支持的语言；认不出 → None。"""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text == "auto":
        return None
    tag = _bcp47(text) or text
    tag = tag.lower().replace("_", "-")
    for lang in LANGUAGES:
        if tag == lang or tag.startswith(lang + "-"):
            return lang
    return None


def set_language(value) -> str:
    """切换界面语言（未知值按默认语言处理），返回生效的语言。"""
    global _language
    _language = normalize_language(value) or DEFAULT_LANGUAGE
    return _language


@contextlib.contextmanager
def source_language():
    """在构建界面时强制中文源文案 —— 静态控件的源串取自 ``text()`` 的初始值。

    ``Tr*`` 控件保存的是**构造时传入的源串**，不依赖当前语言，所以这里主要是
    给"构建期拼出来的动态标签"兜底：它们在源语言下生成，切语言时由页面刷新。
    """
    previous = language()
    set_language(DEFAULT_LANGUAGE)
    try:
        yield
    finally:
        set_language(previous)


# ---------------------------------------------------------------------------
# 翻译
# ---------------------------------------------------------------------------
def tr(source: str, **fmt) -> str:
    """中文源文案 → 当前语言；英文缺项时**自动回落中文源文案**。

    ``fmt`` 用命名占位符：``tr("识别到 {n} 个关节", n=7)``。英文译文若漏了某个
    占位符或格式串写坏，退回中文源文案再格式化 —— 界面宁可显示中文，也不能在
    Qt 槽里抛 ``KeyError`` 把窗口打挂。
    """
    source = str(source)
    target = _EN.get(source, source) if _language == "en" else source
    if not fmt:
        return target
    if _language == "en":
        # 下层异常对象常带中文；英文界面直接丢掉这类详情（调用方的英文
        # 错误码/短码文案接管），避免日志和弹窗里冒出中文。
        clean = {}
        for key, value in fmt.items():
            if isinstance(value, BaseException):
                clean[key] = safe_detail(value) or _EN.get("未知错误", "unknown error")
            else:
                clean[key] = value
        fmt = clean
    try:
        return target.format(**fmt)
    except (KeyError, IndexError, ValueError):
        try:
            return source.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return target


def sdk_locale() -> str:
    """传给 ``litearm.describe_*`` 的 locale —— SDK 自带中英文错误码文案。"""
    return "zh-CN" if _language == "zh" else "en-US"


# ---------------------------------------------------------------------------
# 系统语言检测
# ---------------------------------------------------------------------------
def _bcp47(value: str) -> Optional[str]:
    """``zh_CN.UTF-8@x`` → ``zh-CN``；``C`` / ``POSIX`` / 认不出的值 → None。"""
    text = value.strip()
    if not text:
        return None
    text = text.split("@", 1)[0]          # 丢掉 @modifier
    text = text.split(".", 1)[0]          # 丢掉 .encoding
    if text.lower() in _C_LOCALES:
        return None
    match = _LOCALE_RE.match(text)
    if match is None:
        return None
    lang = match.group("lang").lower()
    region = match.group("region")
    return f"{lang}-{region.upper()}" if region else lang


def _ordered(values: Mapping[str, str]) -> List[str]:
    """按桌面翻译的优先级把一份 locale 变量摊成候选列表。"""
    candidates: List[str] = []
    language_list = values.get("LANGUAGE", "")
    if language_list:
        candidates.extend(language_list.split(":"))
    for name in _LOCALE_NAMES:
        value = values.get(name, "")
        if value:
            candidates.append(value)
    return candidates


def _read_locale_file(path: Path) -> dict:
    """读 ``/etc/default/locale`` 的 ``NAME=value`` 行 —— 读不到就是空，绝不抛。"""
    values: dict = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw = line.split("=", 1)
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export "):].strip()
        if name not in ("LANGUAGE", *_LOCALE_NAMES):
            continue
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        values[name] = raw
    return values


def desktop_languages(environ: Optional[Mapping[str, str]] = None,
                      locale_file: Optional[Path] = DEFAULT_LOCALE_FILE) -> List[str]:
    """桌面翻译用的语言列表 (BCP 47)，去重且保持优先级；认不出就是空列表。"""
    env = os.environ if environ is None else environ
    candidates = _ordered(env)
    if not candidates and locale_file is not None:
        candidates = _ordered(_read_locale_file(locale_file))

    languages: List[str] = []
    seen: set = set()
    for candidate in candidates:
        tag = _bcp47(candidate)
        if tag is None or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        languages.append(tag)
    return languages


def detect_language(environ: Optional[Mapping[str, str]] = None,
                    locale_file: Optional[Path] = DEFAULT_LOCALE_FILE,
                    ui_languages: Optional[Iterable[str]] = None,
                    platform: Optional[str] = None) -> str:
    """从系统环境选一个受支持的语言；一个都没有时回默认语言。

    ``ui_languages`` 是 Qt 的 ``QLocale.system().uiLanguages()``。Windows 上它
    比 POSIX 环境变量可靠；Linux 上反过来 —— WebKit/Qt 只看 ``LANG``，桌面实际
    用的 ``LANGUAGE`` 才是中文桌面的证据，所以 POSIX 列表优先。
    """
    env = os.environ if environ is None else environ
    plat = sys.platform if platform is None else platform
    posix = desktop_languages(env, locale_file)
    ui = [_bcp47(item) for item in (ui_languages or [])]
    ui = [tag for tag in ui if tag]
    candidates = ui + posix if plat.startswith("win") else posix + ui
    for tag in candidates:
        lang = normalize_language(tag)
        if lang is not None:
            return lang
    return DEFAULT_LANGUAGE


def resolve_language(preference=None, override=None, *,
                     environ: Optional[Mapping[str, str]] = None,
                     locale_file: Optional[Path] = DEFAULT_LOCALE_FILE,
                     ui_languages: Optional[Iterable[str]] = None,
                     platform: Optional[str] = None) -> str:
    """优先级：本次运行覆盖 > 已保存选择 > 配置默认 > 系统。"""
    for value in (override, preference):
        lang = normalize_language(value)
        if lang is not None:
            return lang
    return detect_language(environ, locale_file, ui_languages, platform)


#: 英文翻译表在单独模块里（纯数据，便于审查/测试）。
from litetool.i18n_en import EN as _EN  # noqa: E402  (避免循环导入: 该模块不 import 本模块)
