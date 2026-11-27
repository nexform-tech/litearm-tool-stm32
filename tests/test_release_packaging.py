"""发布打包脚本的离线测试 —— checksums 与 Debian 包结构。"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          check=True, **kwargs)


def test_checksums_writes_one_sidecar_per_artifact(tmp_path):
    (tmp_path / "a.tar.gz").write_bytes(b"alpha")
    (tmp_path / "b.zip").write_bytes(b"beta")
    _run(sys.executable, "packaging/checksums.py", str(tmp_path))
    assert (tmp_path / "a.tar.gz.sha256").read_text().split()[0] == \
        hashlib.sha256(b"alpha").hexdigest()
    assert (tmp_path / "b.zip.sha256").read_text().split()[0] == \
        hashlib.sha256(b"beta").hexdigest()


def test_windows_build_script_keeps_a_utf8_bom():
    """Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI; this script has Chinese."""
    data = (ROOT / "packaging" / "build-windows.ps1").read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")


@pytest.mark.skipif(shutil.which("dpkg-deb") is None,
                    reason="dpkg-deb is only present on Debian/Ubuntu hosts")
def test_deb_contains_the_launcher_desktop_entry_and_udev_rule(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "litearm-tool").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(bundle / "litearm-tool", 0o755)
    (bundle / "config.yaml").write_text("temp_alert_c: 85.0\n", encoding="utf-8")
    out = tmp_path / "out"
    _run("bash", "packaging/build-deb.sh",
         "--bundle", str(bundle), "--version", "1.2.3", "--outdir", str(out))
    deb = out / "litearm-tool-stm32_1.2.3_amd64.deb"
    assert deb.is_file()

    contents = _run("dpkg-deb", "--contents", str(deb)).stdout
    for path in (
        "./usr/bin/litearm-tool",
        "./usr/share/applications/litearm-tool.desktop",
        "./usr/share/icons/hicolor/256x256/apps/litearm-tool.png",
        "./lib/udev/rules.d/49-litearm.rules",
        "./etc/litearm-tool/config.yaml",
        "./opt/litearm-tool/litearm-tool",
    ):
        assert path in contents, path

    info = _run("dpkg-deb", "--info", str(deb)).stdout
    assert "Package: litearm-tool-stm32" in info
    assert "Version: 1.2.3" in info
