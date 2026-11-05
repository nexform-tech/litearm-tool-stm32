[English](setup.md) | 简体中文

本指南安装 LiteArm Tool STM32，用离线测试套件验证，并连接机械臂。

# 安装与验证

## 前置条件

- Python 3.9 或更新版本。CI 使用 3.12；测试在 3.13 上也通过。
- 不需要 `pip` 之外的构建工具；GUI 依赖以 wheel 安装。
- Linux 用户需在 `dialout` 组（或使用 root）才能打开 `/dev/ttyACM0`。
- 需要参数读回（0x2B/0x2C）时，机械臂固件需为 `27961a1+`。

## 1. 安装依赖

`litearm-python` 2.1.0 或更新版本未发布到 PyPI。PyPI 只有 1.3.0，缺少本工具使用的 API。先安装固定的公开提交，再安装其余依赖：

```bash
cd litearm-tool-stm32
pip install "litearm-python @ git+https://github.com/nexform-tech/litearm-python.git@5643e477db6dd74c3283bb92cdad8b62ec627f02"
pip install -r requirements.txt
```

如果本地正在开发 SDK，改用可编辑安装并跳过第一条命令：

```bash
pip install -e ../litearm-python
```

**不要**在本仓库执行 `pip install -e .`。扁平布局（`presets/`、`templates/`、`litetool/`）会让 setuptools 的包发现失败。测试通过 `pyproject.toml` 中的 `pythonpath = ["."]` 找到源码。

## 2. 构建

没有构建步骤，直接从源码运行：

```bash
python3 main.py
```

## 3. 验证

运行离线测试套件，不需要硬件：

```bash
QT_QPA_PLATFORM=offscreen python3 -m pytest -q
```

预期结果：`119 passed`。

然后启动 GUI，选择串口并连接。顶栏会显示固件版本（如 `Litearm1.4.0-7J`），状态指示变绿。

## 故障排查

**`ModuleNotFoundError: No module named 'litearm'`**

SDK 未安装。执行第 1 步中固定版本的 `pip install`。从 PyPI 安装 1.3.0 不满足 `litearm-python>=2.1.0`。

**`Permission denied: /dev/ttyACM0`**

把用户加入 `dialout` 组并重新登录：

```bash
sudo usermod -aG dialout "$USER"
```

**`qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`**

无显示环境下用 `QT_QPA_PLATFORM=offscreen` 跑测试；桌面环境需安装 Qt 系统库（`libegl1`、`libgl1`、`libxkbcommon-x11-0`、`libdbus-1-3`）。

**参数页提示不支持读回**

固件早于 `27961a1`，0x2B/0x2C 读回不可用，但写入仍可用。请更新固件。
