"""`litetool.app.config_path()` 的查找顺序 —— 含 PyInstaller 冻结分支。

冻结分支是**打包后才生效**的代码路径: 源码树里跑 `python3 -m litetool` 永远走不到它。
不 monkeypatch 就永远测不到, 而这正是打包最易翻车的地方 —— 冻结后 `__file__` 指向
`_internal/`, 原来的"仓库根"候选会失效, 现场就会出现"改了 config.yaml 没生效"。
"""
from __future__ import annotations

import os
import sys

import pytest

from litetool import app as A


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """每个用例都从"干净环境 + 空 CWD"起步, 免得受开发机真实文件影响。"""
    monkeypatch.delenv("LITEARM_TOOL_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    yield


def _freeze(monkeypatch, exe_dir=None, meipass=None):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable",
                        os.path.join(str(exe_dir), "litearm-tool") if exe_dir else "/nonexistent/x")
    if meipass is None:
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    else:
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)


def _unfreeze(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)


# ------------------------------------------------------------ 通用优先级
def test_env_var_wins(monkeypatch, tmp_path):
    p = tmp_path / "from_env.yaml"
    p.write_text("{}")
    monkeypatch.setenv("LITEARM_TOOL_CONFIG", str(p))
    assert A.config_path() == str(p)


def test_cwd_wins_over_everything(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("{}")           # CWD
    exe_dir = tmp_path / "bundle"
    exe_dir.mkdir()
    (exe_dir / "config.yaml").write_text("{}")            # 冻结包同级
    _freeze(monkeypatch, exe_dir=exe_dir)
    # 注意: 上面 mkdir 后 CWD 里已有一个 config.yaml, 断言取到的是 CWD 那份
    assert A.config_path() == os.path.join(str(tmp_path), "config.yaml")


# ------------------------------------------------------------ 非冻结 (回归)
def test_non_frozen_ignores_meipass(monkeypatch, tmp_path):
    """非冻结时**不得**去看 `_MEIPASS` —— 老行为一字不变。"""
    mp = tmp_path / "meipass"
    mp.mkdir()
    (mp / "config.yaml").write_text("{}")
    _unfreeze(monkeypatch)
    monkeypatch.setattr(sys, "_MEIPASS", str(mp), raising=False)
    got = A.config_path()
    assert got != os.path.join(str(mp), "config.yaml"), \
        "非冻结环境下把 _MEIPASS 当候选是错的 (那是打包专用变量)"


def test_non_frozen_falls_back_to_source_tree(monkeypatch):
    """非冻结、无 env 无 CWD 时, 落到源码树的仓库根 config.yaml。"""
    _unfreeze(monkeypatch)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(A.__file__)))
    assert A.config_path() == os.path.join(repo_root, "config.yaml")


def test_returns_none_when_nothing_found(monkeypatch, tmp_path):
    """全都找不到 -> None (调用方用 dataclass 默认值), 不抛异常。"""
    _unfreeze(monkeypatch)
    monkeypatch.setattr(A, "__file__", os.path.join(str(tmp_path), "nowhere", "app.py"))
    assert A.config_path() is None


# ------------------------------------------------------------ 冻结分支
def test_frozen_prefers_exe_adjacent(monkeypatch, tmp_path):
    """冻结包: **优先取可执行文件同级**那份 —— 那是现场能直接改的。"""
    exe_dir = tmp_path / "bundle"
    exe_dir.mkdir()
    (exe_dir / "config.yaml").write_text("{}")
    mp = tmp_path / "_internal"
    mp.mkdir()
    (mp / "config.yaml").write_text("{}")                 # 随包基线, 优先级更低
    _freeze(monkeypatch, exe_dir=exe_dir, meipass=mp)
    assert A.config_path() == os.path.join(str(exe_dir), "config.yaml")


def test_frozen_falls_back_to_meipass(monkeypatch, tmp_path):
    """同级那份被删了 -> 回落到随包基线, 而不是报"找不到配置"。"""
    exe_dir = tmp_path / "bundle"
    exe_dir.mkdir()
    mp = tmp_path / "_internal"
    mp.mkdir()
    (mp / "config.yaml").write_text("{}")
    _freeze(monkeypatch, exe_dir=exe_dir, meipass=mp)
    assert A.config_path() == os.path.join(str(mp), "config.yaml")


def test_frozen_without_meipass(monkeypatch, tmp_path):
    """onefile 形态没有 `_MEIPASS`... 实际有; 这里守"取不到也不炸"。"""
    exe_dir = tmp_path / "bundle"
    exe_dir.mkdir()
    (exe_dir / "config.yaml").write_text("{}")
    _freeze(monkeypatch, exe_dir=exe_dir, meipass=None)
    assert A.config_path() == os.path.join(str(exe_dir), "config.yaml")


def test_frozen_dirs_empty_when_not_frozen(monkeypatch):
    _unfreeze(monkeypatch)
    assert A._frozen_dirs() == []
