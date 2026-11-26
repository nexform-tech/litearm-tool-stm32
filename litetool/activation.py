"""激活服务 (`act.nexform.tech`) 的客户端 —— 只用标准库。

契约与实现均从 `litearm-studio` 的 `daemon/.../activation.py` 移植（同 org、同契约），
刻意保留它已经踩过的判据：

* 凭据文件由 :func:`parse_license` **唯一**解析，在线领回来的也走这里；
* 注册信息由 :func:`build_request` 在**持有链路的那一层**判；界面上的禁用按钮挡不住
  别处构造的请求；
* 服务的路径、字段上限、同意书版本都对齐服务端（`litearm-activation`），本地判据
  **不许比服务端宽松**。

**本模块是 tool 里除激活以外唯一出网的地方**（只有 `request_license`）。

与 studio 的差异（刻意）：
* `User-Agent` 用 `litearm-tool`；
* 内部测试通道的令牌读取：环境变量沿用 studio（测试人员不用重配），配置文件先找
  `litearm-tool/activation-channel.json`，找不到再回落到 `litearm-studio/` 那份；
* 没有"打包期注入地址"：地址由 `--activation-url` / `LITEARM_ACTIVATION_URL` 决定。
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import urlsplit

__all__ = [
    "PRODUCTION_ACTIVATION_URL", "ACTIVATION_PATH", "LICENSE_FORMAT",
    "CONSENT_TEXT_VERSION", "DEFAULT_ACTIVATION_URL", "activation_url",
    "LicenseFileError", "ActivationError",
    "parse_license", "build_request", "request_license",
    "channel_token", "channel_headers", "default_config_paths",
]

#: 生产地址。域名没上线时任何提交都会如实报"连不上" —— **不要**改成"先假装成功"。
PRODUCTION_ACTIVATION_URL = "https://act.nexform.tech"

#: 服务路径 —— 契约的一部分。
ACTIVATION_PATH = "/api/v1/license"

#: 凭据文件的格式版本。认不出就**拒绝**，不猜。
LICENSE_FORMAT = 1

#: 同意书版本。用户同意的是**某一版文案**；文案改了靠它区分。
CONSENT_TEXT_VERSION = "draft-4"

#: 订单号/激活码上限，以服务端 `license-request.ts` 为准。
CODE_MAX_LEN = 128

#: 人等着的一次请求：短到操作员不会以为界面卡死。
REQUEST_TIMEOUT_S = 10.0
MAX_RESPONSE_BYTES = 64 * 1024

_U32_MAX = 0xFFFFFFFF

#: 设备 UID：24 位小写十六进制（= `LicenseInfo.uid_hex` = 签发器 `--uid`）。
_UID_RE = re.compile(r"[0-9a-f]{24}")

#: 这些 reason 要说给用户听（其余归成 `bad_response`）。
_TRANSPARENT_LICENSE_REASONS = frozenset({"unsupported_format", "uid_mismatch"})


class LicenseFileError(ValueError):
    """凭据文件本身不合法。`reason` 是给界面选文案的短码。"""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class ActivationError(RuntimeError):
    """激活服务这一侧的问题，或这次提交本身不成立（未同意 / UID 不对）。"""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


# --------------------------------------------------------------------------- 地址

def activation_url(environ: Optional[Mapping[str, str]] = None) -> str:
    """生效的激活服务地址：`LITEARM_ACTIVATION_URL` > 生产地址。

    `litetool.app` 的 `--activation-url` 会写进这个环境变量，页面只读这里。
    """
    env = os.environ if environ is None else environ
    url = str(env.get("LITEARM_ACTIVATION_URL", "")).strip()
    return url or PRODUCTION_ACTIVATION_URL


DEFAULT_ACTIVATION_URL = PRODUCTION_ACTIVATION_URL


# --------------------------------------------------------------------------- 凭据

def _hex_bytes(value: Any, n: int, field: str) -> bytes:
    if not isinstance(value, str):
        raise LicenseFileError("bad_field", f"{field} 必须是十六进制字符串")
    text = value.strip().lower()
    if len(text) != n * 2:
        raise LicenseFileError("bad_field", f"{field} 需 {n * 2} 位十六进制，给的是 {len(text)} 位")
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise LicenseFileError("bad_field", f"{field} 含非十六进制字符") from None


def _uint(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LicenseFileError("bad_field", f"{field} 必须是整数")
    if not 0 <= value <= _U32_MAX:
        raise LicenseFileError("bad_field", f"{field} 超出 u32 范围: {value}")
    return int(value)


def parse_license(raw: Any, *, expected_uid: Optional[str] = None) -> Dict[str, Any]:
    """凭据文件（dict 或 JSON 文本）→ `Arm.activate()` 要的四个参数 + uid。

    返回 `{"uid", "cust_id", "issued", "flags", "mac"(bytes)}`。
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise LicenseFileError("not_json", "这不是一份凭据文件（不是 JSON）") from None
    if not isinstance(raw, dict):
        raise LicenseFileError("not_json", "凭据文件的内容不是一个 JSON 对象")

    fmt = raw.get("format")
    if fmt is None:
        raise LicenseFileError("missing_field", "凭据文件缺少 format 字段")
    if fmt != LICENSE_FORMAT:
        raise LicenseFileError(
            "unsupported_format",
            f"凭据格式为 {fmt!r}，当前上位机只认 {LICENSE_FORMAT}（请升级上位机）")

    for field in ("uid", "cust_id", "issued", "mac"):
        if field not in raw:
            raise LicenseFileError("missing_field", f"凭据文件缺少 {field} 字段")

    uid = _hex_bytes(raw["uid"], 12, "uid").hex()
    if expected_uid is not None and uid != expected_uid.strip().lower():
        raise LicenseFileError(
            "uid_mismatch",
            f"这份凭据是给 {uid} 的，当前这台机器是 {expected_uid.strip().lower()}")

    flags = _uint(raw.get("flags", 0), "flags")
    if flags & ~0x1:
        raise LicenseFileError("bad_field", f"flags 只允许 bit0，给的是 0x{flags:X}")

    return {
        "uid": uid,
        "cust_id": _uint(raw["cust_id"], "cust_id"),
        "issued": _uint(raw["issued"], "issued"),
        "flags": flags,
        "mac": _hex_bytes(raw["mac"], 16, "mac"),
    }


# --------------------------------------------------------------------------- 注册信息

#: 与激活网站 `activationFormSchema` 同序同判据： (字段, 必填, 最短, 最长)。
_CONTACT_RULES: Tuple[Tuple[str, bool, Optional[int], Optional[int]], ...] = (
    ("name", True, 2, 32),
    ("phone", True, None, None),
    ("organization", True, 1, 128),
    ("wechatId", False, None, 64),
    ("email", True, 1, 128),
    ("region", True, 1, 64),
    ("industry", False, None, 64),
    ("purpose", False, None, 500),
)

CONTACT_FIELDS: Tuple[str, ...] = tuple(f for f, required, _, _ in _CONTACT_RULES if required)

_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_NAME_PUNCT = frozenset("·・‧’'- 　")


def _is_person_name(text: str) -> bool:
    return all(
        ch in _NAME_PUNCT or ch.isalpha() or unicodedata.category(ch).startswith("M")
        for ch in text
    )


def _contact_fields(contact: dict) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for field, required, min_len, max_len in _CONTACT_RULES:
        raw = contact.get(field)
        if raw is None:
            raw = ""
        if not isinstance(raw, str):
            raise ActivationError("missing_contact", f"字段 {field} 必须是文本")
        text = raw.strip()
        if required and not text:
            raise ActivationError("missing_contact", f"缺少字段 {field}")
        if max_len is not None and len(text) > max_len:
            raise ActivationError("contact_too_long", f"字段 {field} 过长（上限 {max_len} 字）")
        if text and min_len is not None and len(text) < min_len:
            raise ActivationError("missing_contact", f"字段 {field} 至少 {min_len} 字")
        values[field] = text

    if not _PHONE_RE.fullmatch(values["phone"]):
        raise ActivationError("bad_phone", "字段 phone 格式不正确：需为 11 位手机号")
    if not _EMAIL_RE.fullmatch(values["email"]):
        raise ActivationError("bad_email", "字段 email 格式不正确：例如 name@example.com")
    if not _is_person_name(values["name"]):
        raise ActivationError("bad_name", "字段 name 格式不正确：只允许文字（2-32 字），不能含数字")
    return values


def build_request(payload: dict) -> dict:
    """界面提交的内容 → 发给激活服务的请求体（**最终门禁在这一层**）。"""
    uid = payload.get("uid")
    if not isinstance(uid, str) or not _UID_RE.fullmatch(uid.strip().lower()):
        raise ActivationError("bad_uid", "设备 UID 需为 24 位十六进制")

    consent = payload.get("consent")
    if not isinstance(consent, dict) or consent.get("granted") is not True:
        raise ActivationError("consent_required", "未同意《激活注册信息同意书》—— 请先阅读并同意")

    contact = payload.get("contact")
    if not isinstance(contact, dict):
        raise ActivationError("missing_contact", "缺少注册信息")

    diag = payload.get("diagnostics")
    diag = diag if isinstance(diag, dict) else {}

    request: Dict[str, Any] = {
        "uid": uid.strip().lower(),
        "contact": _contact_fields(contact),
        "consent": {"granted": True, "text_version": CONSENT_TEXT_VERSION},
        "diagnostics": {
            key: str(diag.get(key) or "")[:64] for key in ("tool", "sdk", "firmware")
        },
    }
    code = payload.get("code")
    if isinstance(code, str) and code.strip():
        request["code"] = code.strip()[:CODE_MAX_LEN]
    return request


# --------------------------------------------------------------------------- 出网

def _post_json(url: str, payload: dict, timeout: float) -> Tuple[int, bytes]:
    """标准库 HTTPS POST —— 不为一个请求引第三方 HTTP 客户端。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": "litearm-tool",
    }
    token = channel_token()
    if token:
        if is_https(url):
            headers.update(channel_headers(token))
        else:
            print("[activation] 内部通道令牌只在 HTTPS 上发送；本次按正式请求发送",
                  file=sys.stderr)

    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 地址来自本模块常量/环境
            return int(resp.status), resp.read(MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as e:                             # 4xx/5xx 也是应答
        try:
            return int(e.code), e.read(MAX_RESPONSE_BYTES)
        finally:
            e.close()


def _service_error(status: int, body: bytes) -> ActivationError:
    code = None
    message = ""
    try:
        doc = json.loads(body.decode("utf-8", "replace"))
        err = doc.get("error") if isinstance(doc, dict) else None
        if isinstance(err, dict):
            code = err.get("code")
            message = str(err.get("message") or "")
    except ValueError:
        pass
    known = {"not_found", "invalid_uid", "consent_required", "rate_limited",
             "maintenance", "code_required", "invalid_request"}
    reason = code if code in known else "server"
    detail = message or f"激活服务返回 HTTP {status}"
    return ActivationError(reason, f"{detail} (HTTP {status})")


def request_license(base_url: str, request: dict, *, timeout: float = REQUEST_TIMEOUT_S,
                    post: Callable[[str, dict, float], Tuple[int, bytes]] = _post_json,
                    expected_uid: Optional[str] = None) -> Dict[str, Any]:
    """提交注册信息，拿回这台机器的凭据（已按 `parse_license` 解析）。

    `post` 可注入 —— 测试用它替换真网络。
    """
    if not base_url:
        raise ActivationError("unconfigured", "未配置激活服务地址 —— 请用 --activation-url 指定")
    url = base_url.rstrip("/") + ACTIVATION_PATH
    try:
        status, body = post(url, request, timeout)
    except ActivationError:
        raise
    except urllib.error.URLError as e:
        raise ActivationError("unreachable", f"连不上激活服务: {e.reason}") from None
    except OSError as e:
        raise ActivationError("unreachable", f"连不上激活服务: {e}") from None

    if not 200 <= status < 300:
        raise _service_error(status, body)
    try:
        doc = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        raise ActivationError("bad_response", "激活服务返回的不是合法 JSON") from None
    try:
        return parse_license(doc, expected_uid=expected_uid)
    except LicenseFileError as e:
        reason = e.reason if e.reason in _TRANSPARENT_LICENSE_REASONS else "bad_response"
        raise ActivationError(reason, f"激活服务返回的凭据不可用: {e}") from None


# --------------------------------------------------------------------------- 内部测试通道

#: 与 studio 用同一组环境变量：内部测试人员的既有配置不用改。
CONFIG_ENV = "LITEARM_ACTIVATION_CHANNEL_CONFIG"
TOKEN_ENV = "LITEARM_ACTIVATION_CHANNEL_TOKEN"

CHANNEL_HEADER = "X-Litearm-Channel"
TOKEN_HEADER = "X-Litearm-Channel-Token"
TEST_CHANNEL = "test"


def default_config_paths(environ: Optional[Mapping[str, str]] = None) -> Tuple[Path, ...]:
    """令牌配置文件：tool 自己的位置优先，回落到 studio 的位置。

    `LITEARM_ACTIVATION_CHANNEL_CONFIG` 覆盖时只读那一个。
    """
    env = os.environ if environ is None else environ
    override = str(env.get(CONFIG_ENV, "")).strip()
    if override:
        return (Path(override).expanduser(),)

    if sys.platform == "win32":
        appdata = str(env.get("APPDATA", "")).strip()
        if appdata:
            root = Path(appdata).expanduser()
            return (root / "litearm-tool" / "activation-channel.json",
                    root / "litearm-studio" / "activation-channel.json")

    base = str(env.get("XDG_CONFIG_HOME", "")).strip()
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return (root / "litearm-tool" / "activation-channel.json",
            root / "litearm-studio" / "activation-channel.json")


def channel_token(*, environ: Optional[Mapping[str, str]] = None) -> str:
    """已配置的令牌；环境变量优先。读不到时**静默返回空串**（激活不该被它卡住）。"""
    env = os.environ if environ is None else environ
    token = str(env.get(TOKEN_ENV, "")).strip()
    if token:
        return token
    for path in default_config_paths(env):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value = document.get("token") if isinstance(document, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def channel_headers(token: str) -> Dict[str, str]:
    if not token:
        return {}
    return {CHANNEL_HEADER: TEST_CHANNEL, TOKEN_HEADER: token}


def is_https(url: str) -> bool:
    try:
        return urlsplit(url).scheme.lower() == "https"
    except ValueError:
        return False
