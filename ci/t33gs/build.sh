#!/usr/bin/env bash
# Run in the pinned builder, after fetch-sources.sh created a fresh workspace.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
fw=$(cd "$here/../.." && pwd)
export LUMI_WORKSPACE=$(dirname "$fw")
: "${LUMI_INPUTS:?Mount the verified SDK bundle}"
: "${LUMI_T33GS_INPUTS_SHA256:?}"
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$fw" show -s --format=%ct HEAD)}
export BUILD_SHA=$(git -C "$fw" rev-parse HEAD)
export GIT_HASH=${BUILD_SHA:0:12} GIT_BRANCH=lumi-ci
export BUILD_ID=${BUILD_ID:-lumi-t33gs-${BUILD_SHA:0:12}}
export BUILD_PLATFORM=t33_lite
out="$LUMI_WORKSPACE/build"
test ! -e "$out" || { echo 'Use a fresh workspace for each build' >&2; exit 1; }
python3 "$here/firmware.py" check-inputs "$LUMI_INPUTS" --sha256 "$LUMI_T33GS_INPUTS_SHA256"
mkdir -p "$out"
mkdir -p "$HOME"
export T33_SDK_ROOT="$LUMI_INPUTS/sdk"
export T33_TOOLCHAIN_ROOT="$LUMI_INPUTS/uclibc"
export T33GS_UCLIBC_TOOLCHAIN="$T33_TOOLCHAIN_ROOT"
export T33GS_MUSL_TOOLCHAIN="$LUMI_INPUTS/musl"
export RISCV_PREFIX="$LUMI_INPUTS/riscv/bin/riscv-none-embed-"
export T33GS_IMP_SDK="$LUMI_INPUTS/imp"
export T33GS_IMP_LIB_DIR="$LUMI_INPUTS/board/opt/ingenic-t33/lib"
export T33GS_NATIVE_PREFIX="$out/native"
export T33_4494_OUTPUT_DIR="$out/kernel"
export T33_AIC_SOURCE_ARCHIVE="$LUMI_INPUTS/aic8800.tar.gz"
if [[ -d "$LUMI_INPUTS/aic8800" ]]; then
  export T33_AIC_SOURCE_DIR="$LUMI_INPUTS/aic8800"
fi
export T33_HOST_TOOLS_DIR="$out/host-tools"
export T33_BUILD_JOBS=${LUMI_BUILD_JOBS:-4}
export CARGO_BUILD_JOBS="$T33_BUILD_JOBS"
mkdir -p "$T33_HOST_TOOLS_DIR/bin" "$T33_HOST_TOOLS_DIR/sbin"
ln -s "$(command -v mkimage)" "$T33_HOST_TOOLS_DIR/bin/mkimage"
ln -s "$(command -v depmod)" "$T33_HOST_TOOLS_DIR/sbin/depmod"
bash "$fw/contrib/build-t33gs-k4494.sh" --all

(cd "$LUMI_WORKSPACE/lumi-u-boot-t33"
 CROSS_COMPILE="$T33_TOOLCHAIN_ROOT/bin/mips-linux-uclibc-" bash build.sh PRJ008_n_sfcnor_config)

# Build the gateway's native dependency with the same static soft-float ABI.
opus="$LUMI_WORKSPACE/opus"
cmake -S "$opus" -B "$out/opus" -DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=mips \
  -DCMAKE_C_COMPILER="$T33GS_MUSL_TOOLCHAIN/bin/mipsel-linux-muslsf-gcc" \
  -DCMAKE_INSTALL_PREFIX="$T33GS_NATIVE_PREFIX/opus" -DCMAKE_INSTALL_LIBDIR=lib \
  -DCMAKE_BUILD_TYPE=MinSizeRel -DBUILD_SHARED_LIBS=OFF -DOPUS_FIXED_POINT=ON \
  -DOPUS_BUILD_TESTING=OFF -DOPUS_BUILD_PROGRAMS=OFF
cmake --build "$out/opus" --parallel "$T33_BUILD_JOBS"
cmake --install "$out/opus"
export IOT_RELAY_ROOT="$LUMI_WORKSPACE/iot-relay-cloud"
streamer="$LUMI_WORKSPACE/lumi-ipc-streamer"
export OKLUMI_TFLM_SOURCE="$LUMI_WORKSPACE/tflm"
if [[ "${LUMI_BUILD_VOICE:-1}" == 1 ]]; then
  (cd "$streamer" && CARGO_PROFILE_RELEASE_OPT_LEVEL=s \
    CARGO_PROFILE_RELEASE_LTO=fat CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 \
    T33GS_VOICE_WAKE_BACKEND=riscv bash scripts/build_voice_runtime.sh)
  export T33GS_VOICE_ARTIFACT_DIR="$streamer/target/artifacts/voice-runtime-t33gs"
  bash "$fw/lumi/scripts/build-t33-riscv-wake.sh" "$streamer" "$out/riscv-wakeword"
  export T33_RISCV_IMAGE="$out/riscv-wakeword/wake.rvpack"
elif [[ "${LUMI_BUILD_VOICE:-1}" != 0 ]]; then
  echo 'LUMI_BUILD_VOICE must be 0 or 1' >&2; exit 1
fi
make -C "$streamer" package-t33gs-p2p-runtime T33GS_RELAY_CERT_SOURCE="$LUMI_INPUTS/tunnel.cert"
export T33_RUNTIME_DIR="$streamer/target/artifacts/t33gs-runtime"

br="$LUMI_WORKSPACE/buildroot"
brout="$out/userspace"
config="$out/userspace_defconfig"
cp "$here/userspace_defconfig" "$config"
printf 'BR2_ROOTFS_POST_BUILD_SCRIPT="%s/general/scripts/rootfs_script.sh %s/lumi/scripts/post-build.sh %s/post-build.sh"\n' "$fw" "$fw" "$here" >> "$config"
export BR2_DL_DIR=${BR2_DL_DIR:-$out/dl}
make -C "$br" O="$brout" BR2_EXTERNAL="$fw/general:$fw/lumi" BR2_DEFCONFIG="$config" defconfig
make -C "$br" O="$brout" -j"$T33_BUILD_JOBS"
python3 "$fw/lumi/scripts/verify-t33-lumi-image.py" "$brout/target"
python3 "$here/firmware.py" package --kernel "$out/kernel/artifacts/uImage" \
  --rootfs "$brout/images/rootfs.squashfs" \
  --uboot "$LUMI_WORKSPACE/lumi-u-boot-t33/output/u-boot-with-spl.bin" \
  --sources "$LUMI_WORKSPACE/sources.json" --inputs-sha256 "$LUMI_T33GS_INPUTS_SHA256" \
  --output "$LUMI_WORKSPACE/artifacts"
cp "$out/kernel/artifacts/verification.json" "$LUMI_WORKSPACE/artifacts/kernel-verification.json"
cp "$brout/target/lumi/manifest.json" "$LUMI_WORKSPACE/artifacts/runtime-manifest.json"
cp "$brout/target/usr/sbin/lumi-sysupgrade" "$LUMI_WORKSPACE/artifacts/lumi-sysupgrade"
cp "$out/kernel/artifacts/kernel.config" "$LUMI_WORKSPACE/artifacts/kernel.config"
(cd "$LUMI_WORKSPACE/artifacts"
 find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$out/SHA256SUMS"
 mv "$out/SHA256SUMS" SHA256SUMS)
