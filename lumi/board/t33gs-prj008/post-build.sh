#!/usr/bin/env bash
# Finalize files after Buildroot has merged the three reviewed overlay layers.
set -euo pipefail
target=$1
fw=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
: "${BUILD_DIR:?}"
export T33_4494_OUTPUT_DIR="$BUILD_DIR/lumi-t33-platform-4.4.94/sdk-build"
export T33_RUNTIME_PREINSTALLED=1 T33_PLATFORM_PREINSTALLED=1
export T33_RUNTIME_DIR="$BUILD_DIR/lumi-t33-runtime-compact/source/lumi-ipc-streamer/target/artifacts/t33gs-runtime"
# Buildroot merges package trees without deleting old target files on rebuild.
# Enforce the selected feature in the final merged root as well.
if grep -qx 'BR2_PACKAGE_LUMI_T33_VOICE=y' "${BR2_CONFIG:?}"; then
  test -x "$target/lumi/bin/ipc-voice-worker"
else
  rm -f "$target/lumi/bin/ipc-voice-worker"
fi
python3 "$fw/ci/t33gs/firmware.py" check-board \
  --kernel-config "$T33_4494_OUTPUT_DIR/artifacts/kernel.config" \
  --uboot-header "$BUILD_DIR/lumi-t33-uboot-prj008/source/include/configs/PRJ.h" \
  --uboot-config "$BUILD_DIR/lumi-t33-uboot-prj008/source/include/autoconf.mk" \
  --fw-env "$target/etc/fw_env.config" > "$BUILD_DIR/board-layout.json"
python3 "$fw/ci/t33gs/firmware.py" overlay-inventory > "$BUILD_DIR/overlay-inventory.json"
# Require the profile even if a stale/incremental target lost its receipt.
python3 "$fw/lumi/scripts/t33-gateway-profile.py" verify "$target/lumi"
# Preserve the existing finalizer until baseline/rootfs parity is established.
bash "$fw/ci/t33gs/post-build.sh" "$target"
