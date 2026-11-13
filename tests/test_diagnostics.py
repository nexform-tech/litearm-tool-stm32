"""诊断包与错误码显示 —— 白名单/脱敏/码可见。"""
from __future__ import annotations

from types import SimpleNamespace

import litearm as pa

from litetool.diagnostics import (SCHEMA, WHITELIST_KEYS, build_diag_package,
                                  save_diag_package)
from litetool.sdk_worker import TaskResult


def _state():
    return SimpleNamespace(
        mode_name="MOVE_J", enabled=True, flags=0x0245, joint_fault=0x0008,
        fault_reason=[0, 0, 0, 1, 0, 0, 0], drop_hold_reason=1,
        joints=[SimpleNamespace(q=0.1 * i, dq=0.0, tau=0.0,
                                t_mos=40.0, t_coil=38.0, err=1)
                for i in range(7)],
    )


def test_package_only_whitelisted_keys():
    pkg = build_diag_package(firmware="Litearm1.12.2-7J", n_joints=7,
                             state=_state(), log_tail=["a", "b"])
    assert set(pkg) <= WHITELIST_KEYS
    assert pkg["schema"] == SCHEMA


def test_state_snapshot_contains_reason():
    pkg = build_diag_package(firmware="x", n_joints=7, state=_state())
    st = pkg["state"]
    assert st["joint_fault"] == "0x0008"
    assert st["fault_reason"][3] == 1
    assert st["drop_hold_reason"] == 1
    assert len(st["joints"]) == 7


def test_home_path_is_sanitized():
    pkg = build_diag_package(firmware="x", n_joints=7, state=None,
                             log_tail=["open /home/llx/secret.yaml failed"])
    assert "/home/llx" not in pkg["log_tail"][0]
    assert pkg["log_tail"][0].startswith("open ~/")


def test_no_sensitive_keys():
    pkg = build_diag_package(firmware="x", n_joints=7, state=_state(),
                             log_tail=[])
    blob = repr(pkg).lower()
    for word in ("serial", "mac", "hostname", "token", "key", "password"):
        assert word not in blob


def test_error_text_is_rendered():
    t = pa.describe_fault(1)
    pkg = build_diag_package(firmware="x", n_joints=7, state=None, error_text=t)
    assert pkg["error"]["code"] == "FF-01"
    assert pkg["error"]["text"]["title"]


def test_save_writes_file(tmp_path):
    pkg = build_diag_package(firmware="x", n_joints=7, state=None)
    path = save_diag_package(pkg, directory=str(tmp_path))
    assert path.endswith(".json")
    with open(path, encoding="utf-8") as f:
        assert SCHEMA in f.read()


def test_task_result_text_contains_code():
    e = pa.CommandRejectedError("x", cmd=0x2B, code=0x02)
    r = TaskResult("参数写入", False, error=e)
    assert "[2B-02]" in r.text
    assert "GET_FF_VEC" in r.text


def test_task_result_ok_has_no_code():
    assert TaskResult("读状态", True).text == "读状态 完成"
