#!/usr/bin/env bash
# 从 build.sh 的 Linux onedir 产物打一个 Debian 包。
#
#   ./packaging/build-deb.sh \
#       --bundle packaging/out/litearm-tool-stm32-0.12.0-linux-x86_64 \
#       --version 0.12.0 --outdir upload
#
# 这个包只做三件 tar.gz 做不到的事：
#   * 把 PyInstaller 目录装到 /opt/litearm-tool（不用解压到用户目录）；
#   * 装一条 udev 规则：机械臂 CDC 用 uaccess（不用加 dialout / 重新登录），
#     DFU bootloader 也授予桌面用户访问；
#   * 注册桌面项和图标。
#
# 包里的程序仍是 build.sh 打出的自包含 bundle；本脚本只加安装层，不重新冻结。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="litearm-tool-stm32"
# 与 litearm-studio 共用的产品图标（Apache-2.0；256×256 PNG）。
ICON="$ROOT/packaging/icons/litearm-tool.png"

BUNDLE=""
VERSION=""
OUTDIR=""
ARCH="${ARCH:-amd64}"

usage() {
    echo "用法: $0 --bundle <dir> --version <ver> [--outdir <dir>] [--arch <deb-arch>]" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --bundle) BUNDLE="${2:-}"; shift 2 ;;
        --version) VERSION="${2:-}"; shift 2 ;;
        --outdir) OUTDIR="${2:-}"; shift 2 ;;
        --arch) ARCH="${2:-}"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "未知参数: $1" >&2; usage ;;
    esac
done

[ -n "$BUNDLE" ] && [ -d "$BUNDLE" ] || { echo "✗ --bundle 目录不存在: $BUNDLE" >&2; exit 1; }
[ -n "$VERSION" ] || { echo "✗ --version 不能为空" >&2; exit 1; }
VERSION="${VERSION#v}"
[ -n "$OUTDIR" ] || OUTDIR="$ROOT/packaging/out"
command -v dpkg-deb >/dev/null 2>&1 || { echo "✗ 找不到 dpkg-deb（仅 Linux 需要）" >&2; exit 1; }
[ -x "$BUNDLE/litearm-tool" ] || { echo "✗ bundle 里没有可执行的 litearm-tool: $BUNDLE" >&2; exit 1; }
[ -f "$BUNDLE/config.yaml" ] || { echo "✗ bundle 里没有 config.yaml: $BUNDLE" >&2; exit 1; }
[ -f "$ICON" ] || { echo "✗ 找不到图标: $ICON" >&2; exit 1; }

BUNDLE="$(cd "$BUNDLE" && pwd)"
mkdir -p "$OUTDIR"
OUTDIR="$(cd "$OUTDIR" && pwd)"
DEB="$OUTDIR/${PKG}_${VERSION}_${ARCH}.deb"

STAGE="$(mktemp -d)"
chmod 755 "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

# ---- 目录树 ----
install -d "$STAGE/DEBIAN" \
           "$STAGE/opt/litearm-tool" \
           "$STAGE/usr/bin" \
           "$STAGE/usr/share/applications" \
           "$STAGE/usr/share/icons/hicolor/256x256/apps" \
           "$STAGE/lib/udev/rules.d" \
           "$STAGE/usr/share/doc/$PKG" \
           "$STAGE/etc/litearm-tool"

cp -a "$BUNDLE/." "$STAGE/opt/litearm-tool/"
cp "$ICON" "$STAGE/usr/share/icons/hicolor/256x256/apps/litearm-tool.png"
cp "$BUNDLE/config.yaml" "$STAGE/etc/litearm-tool/config.yaml"
cp "$BUNDLE/README-运行说明.md" "$STAGE/usr/share/doc/$PKG/" 2>/dev/null || true

# ---- /usr/bin/litearm-tool ----
cat > "$STAGE/usr/bin/litearm-tool" <<'LAUNCHER'
#!/bin/sh
# Installed by the litearm-tool-stm32 Debian package. The program itself is a
# self-contained PyInstaller bundle under /opt; this wrapper only gives it a
# name on PATH and points it at the system-wide configuration file (a conffile,
# so local edits survive upgrades).
if [ -f /etc/litearm-tool/config.yaml ]; then
    LITEARM_TOOL_CONFIG=/etc/litearm-tool/config.yaml
    export LITEARM_TOOL_CONFIG
fi
exec /opt/litearm-tool/litearm-tool "$@"
LAUNCHER
chmod 755 "$STAGE/usr/bin/litearm-tool"

# ---- 桌面项 ----
cat > "$STAGE/usr/share/applications/litearm-tool.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Version=1.0
Name=LiteArm Tool
Comment=LiteArm STM32 host tool
Exec=litearm-tool
Icon=litearm-tool
StartupWMClass=litearm-tool
Terminal=false
Categories=Utility;Science;
Keywords=robot;arm;litearm;can;
DESKTOP
chmod 644 "$STAGE/usr/share/applications/litearm-tool.desktop"

# ---- udev：机械臂 CDC（uaccess，不用 dialout）+ STM32 DFU bootloader ----
cat > "$STAGE/lib/udev/rules.d/49-litearm.rules" <<'UDEV'
# Installed by the litearm-tool-stm32 Debian package.
#
# The arm's USB CDC port: TAG+="uaccess" grants the logged-in desktop user an
# ACL on the device, so there is no dialout group and no re-login.
# ID_MM_DEVICE_IGNORE stops ModemManager from probing the CDC port.
SUBSYSTEM=="tty", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="606f", ENV{ID_MM_DEVICE_IGNORE}="1", TAG+="uaccess"

# The STM32 ROM bootloader used by the firmware-upgrade page: the same desktop
# user needs access to the DFU device, not just the application CDC port.
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="df11", TAG+="uaccess"
UDEV
chmod 644 "$STAGE/lib/udev/rules.d/49-litearm.rules"

# ---- control / maintainer scripts ----
SIZE_KB="$(du -sk "$STAGE/opt/litearm-tool" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Laurence Young <yangdong@nexform.tech>
Installed-Size: $SIZE_KB
Depends: libc6 (>= 2.35), libegl1, libgl1, libdbus-1-3, libfontconfig1, libfreetype6, libglib2.0-0, libxkbcommon0, libxkbcommon-x11-0, libxcb1, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-util1, libxcb-xinerama0, libxcb-xkb1
Homepage: https://github.com/nexform-tech/litearm-tool-stm32
Description: LiteArm STM32 host tool
 PyQt5 desktop host tool for the LiteArm motion-control firmware: 100 Hz
 state, plots, joint/cartesian motion, parameter tuning, diagnostics, logs,
 activation and USB DFU firmware upgrade.
 .
 The package installs a self-contained PyInstaller bundle, a desktop entry,
 and a udev rule that grants the logged-in desktop user access to the arm's
 USB CDC port (no dialout group and no re-login) and to the STM32 DFU
 bootloader.
CONTROL

cat > "$STAGE/DEBIAN/conffiles" <<CONFFILES
/etc/litearm-tool/config.yaml
CONFFILES

cat > "$STAGE/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v udevadm >/dev/null 2>&1; then
        udevadm control --reload-rules || true
        udevadm trigger --subsystem-match=tty || true
        udevadm trigger --subsystem-match=usb || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q || true
    fi
fi
exit 0
POSTINST
chmod 755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v udevadm >/dev/null 2>&1; then
        udevadm control --reload-rules || true
        udevadm trigger --subsystem-match=tty || true
        udevadm trigger --subsystem-match=usb || true
    fi
fi
exit 0
POSTRM
chmod 755 "$STAGE/DEBIAN/postrm"

cat > "$STAGE/usr/share/doc/$PKG/copyright" <<'COPYRIGHT'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: LiteArm Tool STM32
Source: https://github.com/nexform-tech/litearm-tool-stm32

Files: *
Copyright: 2026 NexForm
License: Apache-2.0
 On Debian systems, the complete text of the Apache License 2.0 can be found in
 /usr/share/common-licenses/Apache-2.0.
COPYRIGHT

# ---- 打包 ----
rm -f "$DEB"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null
echo "deb  : $DEB"
dpkg-deb --info "$DEB" | sed -n '1,12p'
