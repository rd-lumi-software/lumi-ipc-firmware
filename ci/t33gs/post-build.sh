#!/usr/bin/env bash
set -euo pipefail
target=$1
here=$(cd "$(dirname "$0")" && pwd)
: "${LUMI_INPUTS:?}"
: "${T33_4494_OUTPUT_DIR:?}"
if [[ ${T33_PLATFORM_PREINSTALLED:-0} != 1 ]]; then
cp -a "$LUMI_INPUTS/board/." "$target/"
mkdir -p "$target/lumi/bin" "$target/lib/modules" "$target/opt/ingenic-t33"
cp -a "$T33_4494_OUTPUT_DIR/artifacts/modules-root/lib/modules/." "$target/lib/modules/"
"$T33GS_UCLIBC_TOOLCHAIN/bin/mips-linux-uclibc-gcc" -Os -s -march=mips32r2 \
  -I"$LUMI_WORKSPACE/lumi-ipc-linux/kernel/ingenic/t33gs-tnpu" \
  -Wl,--dynamic-linker=/opt/ingenic-t33/lib/ld-uClibc-0.9.33.2.so \
  -Wl,-rpath,/opt/ingenic-t33/lib \
  "$LUMI_WORKSPACE/lumi-ipc-linux/kernel/ingenic/t33gs-tnpu/vendor-monitor/utilization.c" \
  -o "$target/lumi/bin/utilization"
fi
python3 "$here/firmware.py" hardware-env "$target/etc/hardware.env"

# The shared installer records the kernel's license with the runtime licenses.
if [[ ${T33_RUNTIME_PREINSTALLED:-0} != 1 ]]; then
 mkdir -p "$BUILD_DIR/linux-custom"
 cp "$T33_4494_OUTPUT_DIR/sdk/kernel-4.4.94/COPYING" "$BUILD_DIR/linux-custom/COPYING"
fi
python3 "$here/firmware.py" install-updater "$here/../../lumi/overlay/usr/sbin/sysupgrade" \
  "$target/usr/sbin/lumi-sysupgrade"
bash "$here/../../lumi/scripts/post-build-t33-runtime.sh" "$target"
