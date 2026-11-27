"""结构化日志 —— schema、脱敏、轮转、历史回读、导出与路径约定。"""
from __future__ import annotations

import json

import pytest

from litetool import obs


def _lines(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_record_has_opentelemetry_shape(tmp_path):
    log = obs.StructuredLogger(tmp_path)
    try:
        rec = log.info("连接成功", category="session",
                       event="session.connect.succeeded", fields={"online": True})
    finally:
        log.close()

    assert set(rec) == set(obs.RECORD_KEYS)
    assert rec["severity"] == "INFO" and rec["severity_number"] == 9
    assert rec["event"] == "session.connect.succeeded"
    assert rec["body"] == "连接成功"
    assert rec["fields"]["category"] == "session"
    assert rec["fields"]["online"] is True
    assert rec["service"] == obs.SERVICE_NAME
    assert rec["version"]
    assert rec["_seq"] == 1
    on_disk = _lines(tmp_path / obs.LOG_FILE_NAME)
    assert on_disk[0]["body"] == "连接成功"


def test_severity_aliases_and_numbers(tmp_path):
    log = obs.StructuredLogger(tmp_path)
    try:
        assert log.record("ERR", "x")["severity"] == "ERROR"
        assert log.record("WARNING", "x")["severity"] == "WARN"
        assert log.record("OK", "x")["severity"] == "INFO"
        assert log.record("nonsense", "x")["severity"] == "INFO"
        assert obs.severity_number("ERROR") == 17
    finally:
        log.close()


def test_sensitive_fields_are_redacted_at_any_depth(tmp_path):
    log = obs.StructuredLogger(tmp_path)
    try:
        rec = log.info("x", fields={
            "token": "t-123", "uid": "UID-9",
            "nested": {"password": "pw", "contact": {"name": "张三"}, "ok": 1},
            "safe": "visible",
        })
    finally:
        log.close()
    f = rec["fields"]
    assert f["token"] == obs.REDACTED
    assert f["uid"] == obs.REDACTED
    assert f["nested"]["password"] == obs.REDACTED
    assert f["nested"]["contact"] == obs.REDACTED
    assert f["nested"]["ok"] == 1
    assert f["safe"] == "visible"


def test_long_strings_are_truncated_and_bearer_tokens_scrubbed(tmp_path):
    log = obs.StructuredLogger(tmp_path)
    try:
        rec = log.info("Authorization: Bearer abc.def", fields={"note": "a" * 600})
    finally:
        log.close()
    assert "abc.def" not in rec["body"]
    assert "[redacted]" in rec["body"]
    assert "600 chars" in rec["fields"]["note"]


def test_rotation_and_history_across_backups(tmp_path):
    log = obs.StructuredLogger(tmp_path, max_bytes=1200, backups=3)
    try:
        for i in range(20):
            log.info(f"line-{i:02d}", category="test")
        assert (tmp_path / f"{obs.LOG_FILE_NAME}.1").exists(), "小上限必须轮转"
        hist = log.read_history(5)
        assert [r["body"] for r in hist] == [f"line-{i:02d}" for i in range(15, 20)]
    finally:
        log.close()


def test_history_survives_a_restart(tmp_path):
    first = obs.StructuredLogger(tmp_path)
    first.info("before-close")
    first.close()

    second = obs.StructuredLogger(tmp_path)
    try:
        bodies = [r["body"] for r in second.read_history(10)]
        assert bodies == ["before-close"], "重启后要能从文件读回上一次会话"
    finally:
        second.close()


def test_export_jsonl_round_trip(tmp_path):
    log = obs.StructuredLogger(tmp_path)
    try:
        for i in range(3):
            log.info(f"e{i}")
        records = log.recent(10)
    finally:
        log.close()
    out = tmp_path / "export.jsonl"
    n = obs.export_jsonl(out, records)
    assert n == 3
    got = _lines(out)
    assert [r["body"] for r in got] == ["e0", "e1", "e2"]


def test_log_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv(obs.LOG_DIR_ENV, str(tmp_path / "chosen"))
    assert obs.default_log_dir() == tmp_path / "chosen"


def test_log_dir_choice_per_platform():
    assert obs.log_dir_choice("linux", "posix")[0] == "XDG_STATE_HOME"
    assert obs.log_dir_choice("darwin", "posix")[0] is None
    assert obs.log_dir_choice("windows", "nt")[0] == "LOCALAPPDATA"


def test_unserialisable_field_does_not_raise(tmp_path):
    log = obs.StructuredLogger(tmp_path)
    try:
        rec = log.info("x", fields={"obj": object()})
    finally:
        log.close()
    assert "object" in rec["fields"]["obj"] or "0x" in rec["fields"]["obj"]
