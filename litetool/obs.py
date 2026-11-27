"""结构化日志 —— 一行一条 JSONL，字段名照 OpenTelemetry。

为什么要它：底部日志面板只留最近 200 行内存，进程一退就没了；现场问"刚才到底
发生了什么"时，连接、命令、故障、升级的先后顺序全在文件里。这里只做**单进程**
这一套，不引入 FastAPI/WebSocket/浏览器遥测库。

记录形状与 studio 的守护进程保持兼容（`time_unix_nano` 语义的 `ts_ns`、
`severity`/`severity_number`、`event`、`body`、`fields`），所以同一套 `jq`/Loki/
Fluent Bit 读取方式仍然适用。

两条硬规则：

1. **先脱敏再落盘**。`fields` 里任何一层出现 token/password/uid/contact 等键，
   值都替换成 `[redacted]`；长字符串截断；`Bearer ...` 只留前缀。
2. **写文件不能拖垮界面**。底层用标准库 `RotatingFileHandler`（轮转时持锁），
   格式器永不向调用方抛异常；文件系统坏了只丢那一行日志。
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import logging
import logging.handlers
import os
import platform
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

SERVICE_NAME = "litearm-tool"
LOG_FILE_NAME = "tool.jsonl"
LOG_DIR_ENV = "LITEARM_TOOL_LOG_DIR"

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUPS = 5
RING_SIZE = 5000

SEVERITY_NAMES: Tuple[str, ...] = ("TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL")
SEVERITY_NUMBERS = {"TRACE": 1, "DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17, "FATAL": 21}
SEVERITY_ALIASES = {
    "TRACE": "TRACE", "DEBUG": "DEBUG", "INFO": "INFO", "NOTICE": "INFO",
    "OK": "INFO", "WARN": "WARN", "WARNING": "WARN", "ERROR": "ERROR",
    "ERR": "ERROR", "CRITICAL": "FATAL", "FATAL": "FATAL",
}

#: 与 studio 相同的字段顺序：人读一行时总能在同一位置找到同一件事。
RECORD_KEYS: Tuple[str, ...] = (
    "ts", "ts_ns", "_seq", "observed_ts_ns", "severity", "severity_number",
    "event", "body", "trace_id", "span_id", "service", "version", "host",
    "pid", "thread", "source", "fields",
)

MAX_STRING_CHARS = 512
REDACTED = "[redacted]"

#: 任何层级出现这些键，值都不落盘。`uid` 是设备授权标识，按凭据处理。
SENSITIVE_KEYS = frozenset({
    "image", "blob", "raw", "payload", "token", "license", "licence", "lic",
    "uid", "device_uid", "deviceuid", "contact", "signature", "secret",
    "password", "api_key", "apikey", "auth", "authorization", "cookie",
})

_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+")


# --------------------------------------------------------------------------- 等级
def normalize_severity(value: object, *, default: str = "INFO") -> str:
    if isinstance(value, str):
        name = SEVERITY_ALIASES.get(value.strip().upper())
        if name is not None:
            return name
    return default


def severity_number(severity: str) -> int:
    return SEVERITY_NUMBERS.get(normalize_severity(severity), SEVERITY_NUMBERS["INFO"])


# --------------------------------------------------------------------------- 脱敏
def _shorten(text: str) -> str:
    if len(text) <= MAX_STRING_CHARS:
        return text
    return f"{text[:MAX_STRING_CHARS]}… ({len(text)} chars)"


def scrub_text(text: object) -> str:
    """自由文本里的 `Bearer <token>` 只留前缀；其余原样（不猜测更宽的凭据形状）。"""
    return _BEARER_RE.sub(r"\1[redacted]", str(text))


def sanitize(value: Any, *, _depth: int = 0) -> Any:
    """递归复制成 JSON 安全的值；敏感键、超长字符串、非 JSON 对象都在这里收口。"""
    if _depth > 12:
        return "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _shorten(scrub_text(value))
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            out[name] = REDACTED if name.strip().lower() in SENSITIVE_KEYS else \
                sanitize(item, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize(item, _depth=_depth + 1) for item in value]
    return _shorten(repr(value))


# --------------------------------------------------------------------------- 路径
def log_dir_choice(platform_name: str, os_name: str) -> tuple:
    """`(base env var, base fallback parts, trailing parts)` —— 便于不启平台就测试。"""
    if platform_name == "darwin":
        return (None, ("Library", "Logs"), ("litearm-tool",))
    if os_name == "nt":
        return ("LOCALAPPDATA", ("AppData", "Local"), ("litearm-tool", "Logs"))
    return ("XDG_STATE_HOME", (".local", "state"), ("litearm-tool",))


def default_log_dir() -> Path:
    override = os.environ.get(LOG_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # 测试跑 main()/MainWindow 时不能写进开发者自己的日志目录。
        return Path(tempfile.gettempdir()) / "litearm-tool-tests"
    env_name, fallback, trailing = log_dir_choice(platform.system().lower(), os.name)
    if env_name:
        base = os.environ.get(env_name, "").strip()
        if base:
            return Path(base).expanduser().joinpath(*trailing)
    return Path.home().joinpath(*fallback).joinpath(*trailing)


# --------------------------------------------------------------------------- 写盘
class _JsonlFormatter(logging.Formatter):
    """把 `record.obs_record` 原样写成一行 JSON；格式器自身永不向调用方抛异常。"""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003 - stdlib 名
        payload = getattr(record, "obs_record", None)
        if not isinstance(payload, Mapping):
            payload = {
                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
                "severity": "ERROR", "severity_number": SEVERITY_NUMBERS["ERROR"],
                "event": "tool.log.bad_record",
                "body": "日志记录缺少结构化字段",
                "fields": {},
            }
        try:
            return json.dumps(dict(payload), ensure_ascii=False, allow_nan=False,
                              separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            fallback = {k: payload.get(k) for k in RECORD_KEYS if k in payload}
            fallback.update({
                "severity": "ERROR", "severity_number": SEVERITY_NUMBERS["ERROR"],
                "event": "tool.log.serialization_failed",
                "body": f"无法序列化 {payload.get('event')!r} 这条日志记录",
                "fields": {"original_event": str(payload.get("event"))},
            })
            return json.dumps(fallback, ensure_ascii=False, default=str)


def _tool_version() -> str:
    try:
        from importlib.metadata import version
        return version("litearm-tool-stm32")
    except Exception:  # noqa: BLE001 - 未安装/元数据缺失都回退
        return "dev"


class StructuredLogger:
    """JSONL 写入器 + 最近若干条的环形缓冲。线程安全。"""

    def __init__(self, log_dir: Optional[os.PathLike] = None, *,
                 max_bytes: int = DEFAULT_MAX_BYTES,
                 backups: int = DEFAULT_BACKUPS,
                 ring_size: int = RING_SIZE,
                 clock=time.time_ns,
                 service: str = SERVICE_NAME,
                 version: Optional[str] = None):
        self._clock = clock
        self._service = service
        self._version = version if version is not None else _tool_version()
        self._host = platform.node()
        self.dir = Path(log_dir) if log_dir else default_log_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / LOG_FILE_NAME
        self._seq = 0
        self._lock = threading.Lock()
        self._ring = collections.deque(maxlen=int(ring_size))
        self._handler = logging.handlers.RotatingFileHandler(
            str(self.path), maxBytes=int(max_bytes), backupCount=int(backups),
            encoding="utf-8")
        self._handler.setFormatter(_JsonlFormatter())
        self._logger = logging.getLogger(f"{SERVICE_NAME}.jsonl.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self._logger.addHandler(self._handler)

    # ---------------- 写 ----------------
    def record(self, severity: object, body: str, *, category: str = "app",
               event: Optional[str] = None, fields: Optional[Mapping] = None,
               source: str = "litetool", **extra: Any) -> dict:
        sev = normalize_severity(severity)
        ts_ns = int(self._clock())
        payload = {"category": category}
        if fields:
            payload.update(fields)
        payload.update(extra)
        with self._lock:
            self._seq += 1
            seq = self._seq
        rec = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
            "ts_ns": ts_ns,
            "_seq": seq,
            "observed_ts_ns": ts_ns,
            "severity": sev,
            "severity_number": SEVERITY_NUMBERS[sev],
            "event": str(event or "tool.log"),
            "body": _shorten(scrub_text(body)),
            "trace_id": None,
            "span_id": None,
            "service": self._service,
            "version": self._version,
            "host": self._host,
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
            "source": source,
            "fields": sanitize(payload),
        }
        ordered = {k: rec.get(k) for k in RECORD_KEYS}
        self._ring.append(ordered)
        try:
            self._logger.log(logging.DEBUG, "", extra={"obs_record": ordered})
        except Exception:  # noqa: BLE001 - 日志坏了也不能把调用方拖垮
            pass
        return ordered

    def info(self, body: str, **kw) -> dict:
        return self.record("INFO", body, **kw)

    def warn(self, body: str, **kw) -> dict:
        return self.record("WARN", body, **kw)

    def error(self, body: str, **kw) -> dict:
        return self.record("ERROR", body, **kw)

    # ---------------- 读 ----------------
    def recent(self, limit: int = RING_SIZE) -> list:
        with self._lock:
            items = list(self._ring)
        return items[-int(limit):] if limit else items

    def _line_files(self) -> list:
        """当前文件 + 轮转备份，**从新到旧**。"""
        out = [self.path]
        for i in range(1, self._handler.backupCount + 1):
            p = Path(f"{self.path}.{i}")
            if p.exists():
                out.append(p)
        return out

    def read_history(self, limit: int = RING_SIZE) -> list:
        """从文件回读最近 `limit` 条（跨轮转），按时间顺序返回。"""
        if limit <= 0:
            return []
        remaining = int(limit)
        chunks = []
        for path in self._line_files():
            if remaining <= 0:
                break
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    tail = collections.deque(fh, maxlen=remaining)
            except OSError:
                continue
            chunks.append(tail)
            remaining -= len(tail)
        out = []
        for chunk in reversed(chunks):          # chunks 是新→旧，反成旧→新
            for line in chunk:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
        return out

    def close(self) -> None:
        try:
            self._logger.removeHandler(self._handler)
            self._handler.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def export_jsonl(path: os.PathLike, records: Iterable[Mapping]) -> int:
    """把记录写成 JSONL（原子替换）；返回行数。"""
    rows = list(records)
    directory = os.path.dirname(os.path.abspath(os.fspath(path))) or "."
    fd, tmp = tempfile.mkstemp(prefix=".litearm-log-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for rec in rows:
                fh.write(json.dumps(dict(rec), ensure_ascii=False,
                                    separators=(",", ":"), default=str) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(rows)
