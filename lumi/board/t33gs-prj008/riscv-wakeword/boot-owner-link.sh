#!/bin/sh
# Opt-in after the existing base runtime has staged its launch directory.
set -eu
owner_script=$(readlink -f "$0")
owner_root=${owner_script%/*}
[ "$owner_root" != "$0" ] || exit 64
if [ ! -f "$owner_root/ENABLED" ]; then
 echo 'Lumi wake: backend=cpu reason=riscv-disabled'
 exit 0
fi
[ "$(cat "$owner_root/ENABLED")" = owned-riscv-abi3 ]
(cd "$owner_root" && sha256sum -c runtime.sha256 >/dev/null)
[ -x "$owner_root/voice-owner.sh" ]
ln -sfn "$owner_root/voice-owner.sh" /tmp/lumi-runtime-ram/launch/ipc-voice-worker
echo 'Lumi wake: backend=riscv selected; waiting for voice worker'
