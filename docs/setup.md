English | [简体中文](setup.zh-CN.md)

This guide installs LiteArm Tool STM32, verifies it with the offline test suite, and connects it to an arm.

# Setup

## Prerequisites

- Python 3.9 or newer. CI runs 3.12; the tests also pass on 3.13.
- `pip` and a C toolchain are not required. The GUI ships as wheels.
- A Linux user in the `dialout` group, or root, to open `/dev/ttyACM0`.
- An arm running firmware `27961a1+` if you need parameter readback (0x2B/0x2C).

## 1. Install dependencies

`litearm-python` 2.1.0 or newer is not on PyPI. PyPI only has 1.3.0, which lacks the APIs this tool uses. Install the pinned public commit, then the remaining dependencies:

```bash
cd litearm-tool-stm32
pip install "litearm-python @ git+https://github.com/nexform-tech/litearm-python.git@5643e477db6dd74c3283bb92cdad8b62ec627f02"
pip install -r requirements.txt
```

If you work on the SDK locally, install it editable instead and skip the first command:

```bash
pip install -e ../litearm-python
```

**Do not** run `pip install -e .` in this repository. The flat layout (`presets/`, `templates/`, `litetool/`) makes setuptools package discovery fail. Tests use `pythonpath = ["."]` from `pyproject.toml` instead.

## 2. Build

There is no build step. The application runs from source:

```bash
python3 main.py
```

## 3. Verify

Run the offline suite. It needs no hardware:

```bash
QT_QPA_PLATFORM=offscreen python3 -m pytest -q
```

Expected result: `119 passed`.

Then start the GUI, choose the serial port, and connect. The top bar shows the firmware version, for example `Litearm1.4.0-7J`, and the status indicator turns green.

## Troubleshooting

**`ModuleNotFoundError: No module named 'litearm'`**

The SDK is not installed. Run the pinned `pip install` command from step 1. A PyPI install of 1.3.0 does not satisfy the `litearm-python>=2.1.0` requirement.

**`Permission denied: /dev/ttyACM0`**

Add your user to the `dialout` group and log in again:

```bash
sudo usermod -aG dialout "$USER"
```

**`qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`**

Run the tests headless with `QT_QPA_PLATFORM=offscreen`, or install the Qt system libraries (`libegl1`, `libgl1`, `libxkbcommon-x11-0`, `libdbus-1-3`) for a desktop session.

**Parameter page reports that readback is unsupported**

The firmware predates `27961a1`. Readback on 0x2B/0x2C is unavailable; writes still work. Update the firmware.
