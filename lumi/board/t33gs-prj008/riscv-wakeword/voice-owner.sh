#!/bin/sh
# Normal voice worker under the existing supervisor; no extra process/guardian.
set -eu
umask 077
owner_script=$(readlink -f "$0")
owner_root=${owner_script%/*}
[ "$owner_root" != "$0" ] || exit 64
case "$owner_root" in /*) ;; *) exit 64;; esac
if [ ! -c /dev/lumi-riscv-mem ]; then
 insmod "$owner_root/lumi_riscv_mem.ko"
fi
export LUMI_WAKE_BACKEND=riscv
export LUMI_RISCV_IMAGE="$owner_root/wake.rvpack"
unset LUMI_RISCV_MEM_FD LUMI_VOICE_PCM_TRIAL LUMI_VOICE_PCM_TIMING
exec "$owner_root/ipc-voice-worker.riscv" "$@"
