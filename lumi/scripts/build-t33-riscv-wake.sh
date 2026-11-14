#!/usr/bin/env bash
# Build the wake-only MCU payload from the same immutable source snapshot.
set -euo pipefail
streamer=${1:?streamer source}
output=${2:?MCU output directory}
fw=$(cd "$(dirname "$0")/../.." && pwd)
: "${RISCV_PREFIX:?set the verified RV32IMC/newlib compiler prefix}"
test -x "${RISCV_PREFIX}gcc"
test -x "${RISCV_PREFIX}g++"
(cd "$streamer" && bash scripts/build_wakeword_riscv.sh)
make -C "$fw/lumi/board/t33gs-prj008/riscv-wakeword" \
  STREAMER_SOURCE="$streamer" BUILD_DIR="$output" RISCV_PREFIX="$RISCV_PREFIX"
test -s "$output/wake.rvpack"
