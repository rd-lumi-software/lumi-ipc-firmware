#!/usr/bin/env bash
# Buildroot invokes this recipe inside its runtime package build directory.
set -euo pipefail
# Buildroot sets GIT_DIR=. for package recipes. Source-owned pin/ABI checks
# must discover the real .git directories in these isolated source copies.
unset GIT_DIR
: "${LUMI_RUNTIME_BUILD:?}"
: "${LUMI_WORKSPACE:?}"
: "${T33GS_MUSL_TOOLCHAIN:?}"
: "${T33GS_UCLIBC_TOOLCHAIN:?}"
root=$LUMI_RUNTIME_BUILD
mkdir -p "$root/source"
for role in lumi-ipc-streamer iot-relay-cloud tflm opus; do
  if [[ ! -d $root/source/$role ]]; then
    mkdir -p "$root/source/$role"
    rsync -a --exclude=/target --exclude=/output "$LUMI_WORKSPACE/$role/" "$root/source/$role/"
  fi
done
# Source-owned ABI checks refer to the Linux repository next to streamer.
ln -sfn "$LUMI_WORKSPACE/lumi-ipc-linux" "$root/source/lumi-ipc-linux"
export T33GS_NATIVE_PREFIX="$root/native"
export CARGO_BUILD_JOBS=${LUMI_BUILD_JOBS:-4}
export WAKEWORD_BUILD_JOBS=$CARGO_BUILD_JOBS SNAPSHOT_BUILD_JOBS=$CARGO_BUILD_JOBS AAC_BUILD_JOBS=$CARGO_BUILD_JOBS
# Voice also builds the gateway: select the same profile before either entrypoint.
# The preceding full firmware enabled all three; gateway defaults enable DMA only.
export T33GS_GATEWAY_DMA_AES=1 T33GS_GATEWAY_DMA_GCM_BATCH=1 T33GS_GATEWAY_DMA_GCM_MXU2=1
# Opus encode is CPU-bound on Xburst; retain fixed-point controls and use its
# supported MIPS32 ISA, without enabling the upstream DSPR2 assembly path.
cmake -S "$root/source/opus" -B "$root/opus" -DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=mips \
  -DCMAKE_C_COMPILER="$T33GS_MUSL_TOOLCHAIN/bin/mipsel-linux-muslsf-gcc" \
  -DCMAKE_INSTALL_PREFIX="$T33GS_NATIVE_PREFIX/opus" -DCMAKE_INSTALL_LIBDIR=lib \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="-march=mips32 -mtune=mips32" \
  -DBUILD_SHARED_LIBS=OFF -DOPUS_FIXED_POINT=ON \
  -DOPUS_BUILD_TESTING=OFF -DOPUS_BUILD_PROGRAMS=OFF
cmake --build "$root/opus" --parallel "$CARGO_BUILD_JOBS"
cmake --install "$root/opus"
export IOT_RELAY_ROOT="$root/source/iot-relay-cloud"
export OKLUMI_TFLM_SOURCE="$root/source/tflm"
streamer=$root/source/lumi-ipc-streamer
if [[ ${LUMI_BUILD_VOICE:-1} == 1 ]]; then
  (cd "$streamer" && CARGO_PROFILE_RELEASE_OPT_LEVEL=s \
    CARGO_PROFILE_RELEASE_LTO=fat CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 \
    T33GS_VOICE_WAKE_BACKEND=riscv bash scripts/build_voice_runtime.sh)
  export T33GS_VOICE_ARTIFACT_DIR="$streamer/target/artifacts/voice-runtime-t33gs"
  bash "$(dirname "$0")/build-t33-riscv-wake.sh" "$streamer" "$root/riscv-wakeword"
else
  unset T33GS_VOICE_ARTIFACT_DIR
fi
make -C "$streamer" package-t33gs-p2p-runtime T33GS_RELAY_CERT_SOURCE="$LUMI_INPUTS/tunnel.cert"
