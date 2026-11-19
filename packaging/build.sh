#!/usr/bin/env bash
# 一键打出 litearm-tool-stm32 的自包含包 (PyInstaller onedir + tar.gz)。
#
#   ./packaging/build.sh                 # 产物在 packaging/out/
#   PYTHON=/usr/bin/python3 ./packaging/build.sh
#   BUILD_VENV=/tmp/bv ./packaging/build.sh
#
# 产出的包**不需要目标机装 Python 或任何依赖** —— 解包双击/命令行即可运行。
#
# ⚠ 三条硬约束 (2026-09-16 实测踩过, 别改):
#
#  1. **必须在干净 venv 里打, 且 SDK 必须非可编辑安装。**
#     开发机的 litearm-python 平时是 `pip install -e`, 装的是一个自定义 finder;
#     PyInstaller 的模块图常常跟不进去 -> 打出来的包运行期 ModuleNotFoundError。
#     这里显式用 venv + `pip install <源码路径>` 避开。
#
#  2. **conda 环境里不能直接打**: conda 装了个过时的 `pathlib` backport,
#     PyInstaller 启动时会直接拒绝 (The 'pathlib' package is an obsolete backport...)。
#     新建的 venv 不继承 site-packages, 天然绕开。
#
#  3. **glibc 上限 = 本打包机的 glibc**。当前是 Ubuntu 22.04 / glibc 2.35 ——
#     产物的最低要求就是 glibc 2.35。要在更老的机器上跑, 得在那台上打。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-$ROOT/packaging/out}"
BUILD_VENV="${BUILD_VENV:-/tmp/litearm-tool-build-venv}"
PYTHON="${PYTHON:-python3}"
SDK_SRC="${PYLITEARM_STM32:-$ROOT/../litearm-python}"
PKG_NAME="litearm-tool-stm32"
VERSION="$(sed -n 's/^version *= *"\(.*\)"/\1/p' "$ROOT/pyproject.toml" | head -1)"
ARCH="$(uname -m)"
BUNDLE="$PKG_NAME-$VERSION-linux-$ARCH"

say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

say "环境"
echo "仓库      : $ROOT"
echo "版本      : $VERSION"
echo "SDK 源码  : $SDK_SRC"
echo "构建 venv : $BUILD_VENV"
echo "解释器    : $($PYTHON -c 'import sys; print(sys.version.split()[0], sys.executable)')"

[ -f "$SDK_SRC/pyproject.toml" ] || {
  echo "✗ 找不到 SDK 源码: $SDK_SRC (用 PYLITEARM_STM32= 指定)"; exit 1; }

say "1/6 备好干净 venv"
mkdir -p "$OUT"
if [ ! -x "$BUILD_VENV/bin/python" ]; then
  rm -rf "$BUILD_VENV"
  "$PYTHON" -m venv "$BUILD_VENV" || {
    echo "✗ 建 venv 失败。Ubuntu 系统 python 需先装 python3-venv:"
    echo "    sudo apt install python3-venv"; exit 1; }
fi
VPY="$BUILD_VENV/bin/python"

say "2/6 装 SDK (非可编辑) + 运行期依赖 + PyInstaller"
"$VPY" -m pip install -q --upgrade pip
"$VPY" -m pip install -q "$SDK_SRC"
"$VPY" -m pip install -q "PyQt5>=5.15" "pyqtgraph>=0.13" "numpy>=1.21" \
                           "PyYAML>=6.0" "pyserial>=3.5" pyinstaller
"$VPY" - <<'PY'
import sys
import PyQt5.QtCore as c, pyqtgraph, numpy, yaml, serial, litearm as s
print(f"  Python {sys.version.split()[0]} | PyQt5 {c.QT_VERSION_STR} | "
      f"pyqtgraph {pyqtgraph.__version__} | numpy {numpy.__version__} | "
      f"SDK {getattr(s, '__version__', '?')}")
PY

say "3/6 在构建环境里跑全量测试 (证明这个环境是完备的, 再冻结它)"
# 装 pytest 只为这道闸; 测试全离线, 不需要硬件。
"$VPY" -m pip install -q pytest
( cd "$ROOT" && "$VPY" -m pytest -q ) || { echo "✗ 测试未过 —— 拒绝打包"; exit 1; }

say "4/6 PyInstaller 构建 (onedir)"
rm -rf "$OUT/dist" "$OUT/build"
"$VPY" -m PyInstaller --clean --noconfirm \
      --distpath "$OUT/dist" --workpath "$OUT/build" \
      "$ROOT/packaging/litearm-tool.spec" >"$OUT/pyinstaller.log" 2>&1 || {
  echo "✗ 构建失败, 见 $OUT/pyinstaller.log"; tail -20 "$OUT/pyinstaller.log"; exit 1; }
echo "  日志: $OUT/pyinstaller.log"

say "5/6 组装交付目录 (用户可见文件与可执行文件同级)"
STAGE="$OUT/$BUNDLE"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -a "$OUT/dist/litearm-tool/." "$STAGE/"
# config.yaml / presets / templates / docs 放在**可执行文件同级**: 现场可直接看/改。
# (litetool/app.py::config_path 的冻结候选优先取这一份; 找不到才回落到 _internal 里的基线)
cp "$ROOT/config.yaml" "$STAGE/"
for d in presets templates docs; do
  [ -d "$ROOT/$d" ] && cp -a "$ROOT/$d" "$STAGE/"
done
cp "$ROOT/packaging/README-运行说明.md" "$STAGE/" 2>/dev/null || true

say "6/6 打包 tar.gz"
TAR="$OUT/$BUNDLE.tar.gz"
tar -C "$OUT" -czf "$TAR" "$BUNDLE"
SIZE="$(du -sh "$STAGE" | cut -f1)"

say "完成"
echo "目录 : $STAGE   ($SIZE)"
echo "压缩 : $TAR   ($(du -h "$TAR" | cut -f1))"
echo
echo "现场用法: tar xzf $(basename "$TAR") && cd $BUNDLE && ./litearm-tool"
echo "⚠ 串口权限: 用户需在 dialout 组 (sudo usermod -aG dialout \$USER, 重新登录)"
