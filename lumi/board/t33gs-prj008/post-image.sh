#!/usr/bin/env bash
set -euo pipefail
images=$1
fw=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
: "${LUMI_WORKSPACE:?}"
: "${LUMI_T33GS_INPUTS_SHA256:?}"
# An intermediate directory allows Buildroot to rerun post-image after rebuilds.
work=$(mktemp -d "$images/lumi-package.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
python3 "$fw/ci/t33gs/firmware.py" package --kernel "$images/uImage" \
  --rootfs "$images/rootfs.squashfs" --uboot "$images/u-boot-with-spl.bin" \
  --sources "$LUMI_WORKSPACE/sources.json" --inputs-sha256 "$LUMI_T33GS_INPUTS_SHA256" \
  --output "$work/artifacts"
cp "$images/kernel.config" "$images/kernel-verification.json" "$work/artifacts/"
cp "$TARGET_DIR/lumi/manifest.json" "$work/artifacts/runtime-manifest.json"
cp "$TARGET_DIR/usr/sbin/lumi-sysupgrade" "$work/artifacts/lumi-sysupgrade"
cp "$BUILD_DIR/overlay-inventory.json" "$work/artifacts/overlay-inventory.json"
(cd "$work/artifacts"; find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$work/SHA256SUMS")
mv "$work/SHA256SUMS" "$work/artifacts/SHA256SUMS"
mkdir -p "$LUMI_WORKSPACE/artifacts"
cp -a "$work/artifacts/." "$LUMI_WORKSPACE/artifacts/"
