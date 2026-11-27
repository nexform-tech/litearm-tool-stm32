"""激活客户端（`litetool/activation.py`）的离线测试 —— 不出网。"""
from __future__ import annotations

import json
import sys

import pytest

from litetool import activation

GOOD = {
    "format": 1,
    "uid": "00112233445566778899aabb",
    "cust_id": 1042,
    "issued": 20261126,
    "flags": 0,
    "mac": "00" * 16,
}


# --------------------------------------------------------------------------- 凭据解析

def test_parse_license_accepts_good_file():
    lic = activation.parse_license(GOOD)
    assert lic["uid"] == GOOD["uid"]
    assert lic["cust_id"] == 1042
    assert lic["mac"] == b"\x00" * 16


def test_parse_license_accepts_json_text():
    assert activation.parse_license(json.dumps(GOOD))["uid"] == GOOD["uid"]


def test_parse_license_rejects_unknown_format():
    with pytest.raises(activation.LicenseFileError) as ei:
        activation.parse_license({**GOOD, "format": 2})
    assert ei.value.reason == "unsupported_format"


def test_parse_license_checks_uid():
    with pytest.raises(activation.LicenseFileError) as ei:
        activation.parse_license(GOOD, expected_uid="ffff" * 6)
    assert ei.value.reason == "uid_mismatch"


def test_parse_license_rejects_reserved_flags():
    with pytest.raises(activation.LicenseFileError) as ei:
        activation.parse_license({**GOOD, "flags": 0b10})
    assert ei.value.reason == "bad_field"


def test_parse_license_rejects_non_json():
    with pytest.raises(activation.LicenseFileError) as ei:
        activation.parse_license("not json")
    assert ei.value.reason == "not_json"


# --------------------------------------------------------------------------- 注册信息

def _payload(**over):
    base = {
        "uid": GOOD["uid"],
        "consent": {"granted": True},
        "contact": {
            "name": "张三",
            "phone": "13800000000",
            "organization": "测试单位",
            "email": "a@b.cn",
            "region": "杭州",
        },
    }
    base.update(over)
    return base


def test_build_request_requires_consent():
    with pytest.raises(activation.ActivationError) as ei:
        activation.build_request(_payload(consent={"granted": False}))
    assert ei.value.reason == "consent_required"


def test_build_request_validates_uid():
    with pytest.raises(activation.ActivationError) as ei:
        activation.build_request(_payload(uid="xyz"))
    assert ei.value.reason == "bad_uid"


@pytest.mark.parametrize("field,value,reason", [
    ("phone", "12345", "bad_phone"),
    ("email", "nope", "bad_email"),
    ("name", "张3", "bad_name"),
    ("organization", "", "missing_contact"),
])
def test_build_request_validates_contact(field, value, reason):
    contact = dict(_payload()["contact"])
    contact[field] = value
    with pytest.raises(activation.ActivationError) as ei:
        activation.build_request(_payload(contact=contact))
    assert ei.value.reason == reason


def test_build_request_shape_and_code_truncation():
    req = activation.build_request(_payload(code="x" * 200))
    assert req["uid"] == GOOD["uid"]
    assert req["consent"] == {"granted": True,
                              "text_version": activation.CONSENT_TEXT_VERSION}
    # ⚠ 服务端契约 (`licenseRequestSchema`) 的键集：`studio` / `sdk` / `firmware`。
    #   服务端用 zod 的 object 解析，多出来的键会被静默丢掉。
    assert set(req["diagnostics"]) == {"studio", "sdk", "firmware"}
    assert len(req["code"]) == activation.CODE_MAX_LEN


# --------------------------------------------------------------------------- 服务请求

def _post_ok(*_a, **_k):
    return 200, json.dumps(GOOD).encode()


def test_request_license_parses_success():
    lic = activation.request_license(
        "https://example.test", {"uid": GOOD["uid"]},
        post=_post_ok, expected_uid=GOOD["uid"])
    assert lic["cust_id"] == 1042


def test_request_license_maps_service_error():
    body = json.dumps({"error": {"code": "invalid_request", "message": "bad"}}).encode()
    with pytest.raises(activation.ActivationError) as ei:
        activation.request_license("https://example.test", {}, post=lambda *a: (400, body))
    assert ei.value.reason == "invalid_request"


def test_request_license_maps_unknown_error_to_server():
    with pytest.raises(activation.ActivationError) as ei:
        activation.request_license("https://example.test", {}, post=lambda *a: (503, b""))
    assert ei.value.reason == "server"


def test_request_license_rejects_bad_json():
    with pytest.raises(activation.ActivationError) as ei:
        activation.request_license("https://example.test", {}, post=lambda *a: (200, b"nope"))
    assert ei.value.reason == "bad_response"


def test_request_license_reports_unreachable():
    def boom(*_a):
        raise OSError("no route")
    with pytest.raises(activation.ActivationError) as ei:
        activation.request_license("https://example.test", {}, post=boom)
    assert ei.value.reason == "unreachable"


def test_request_license_requires_url():
    with pytest.raises(activation.ActivationError) as ei:
        activation.request_license("", {}, post=_post_ok)
    assert ei.value.reason == "unconfigured"


def test_request_license_keeps_transparent_reasons():
    bad = {**GOOD, "uid": "ffff" * 6}
    with pytest.raises(activation.ActivationError) as ei:
        activation.request_license(
            "https://example.test", {}, post=lambda *a: (200, json.dumps(bad).encode()),
            expected_uid=GOOD["uid"])
    assert ei.value.reason == "uid_mismatch"


# --------------------------------------------------------------------------- 地址与通道

def test_activation_url_env_override(monkeypatch):
    monkeypatch.setenv("LITEARM_ACTIVATION_URL", "https://staging.test/")
    assert activation.activation_url() == "https://staging.test/"
    monkeypatch.delenv("LITEARM_ACTIVATION_URL")
    assert activation.activation_url() == activation.PRODUCTION_ACTIVATION_URL


def test_channel_token_env_wins_and_headers(monkeypatch):
    monkeypatch.setenv(activation.TOKEN_ENV, "tok")
    assert activation.channel_token() == "tok"
    assert activation.channel_headers("tok") == {
        activation.CHANNEL_HEADER: activation.TEST_CHANNEL,
        activation.TOKEN_HEADER: "tok",
    }
    assert activation.channel_headers("") == {}


def test_channel_token_reads_tool_config_then_studio(tmp_path, monkeypatch):
    monkeypatch.delenv(activation.TOKEN_ENV, raising=False)
    # 代码按平台选根目录：Windows 是 %APPDATA%，其他平台是 XDG_CONFIG_HOME。
    if sys.platform == "win32":
        monkeypatch.setenv("APPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "litearm-studio").mkdir()
    (tmp_path / "litearm-studio" / "activation-channel.json").write_text(
        '{"token": "studio-tok"}', encoding="utf-8")
    assert activation.channel_token() == "studio-tok"

    (tmp_path / "litearm-tool").mkdir()
    (tmp_path / "litearm-tool" / "activation-channel.json").write_text(
        '{"token": "tool-tok"}', encoding="utf-8")
    assert activation.channel_token() == "tool-tok"


def test_channel_token_honors_studio_config_override(tmp_path, monkeypatch):
    """测试人员按 studio 文档配的路径覆盖变量，也要生效（不用重配）。"""
    monkeypatch.delenv(activation.TOKEN_ENV, raising=False)
    monkeypatch.delenv(activation.CONFIG_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))     # 默认路径为空
    cfg = tmp_path / "studio-channel.json"
    cfg.write_text('{"token": "studio-override"}', encoding="utf-8")
    monkeypatch.setenv(activation.STUDIO_CONFIG_ENV, str(cfg))
    assert activation.channel_token() == "studio-override"

    # 本工具自己的变量优先于 studio 的。
    own = tmp_path / "tool-channel.json"
    own.write_text('{"token": "tool-override"}', encoding="utf-8")
    monkeypatch.setenv(activation.CONFIG_ENV, str(own))
    assert activation.channel_token() == "tool-override"
