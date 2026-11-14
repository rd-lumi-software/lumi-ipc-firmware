#!/usr/bin/env bash
# Install source-built runtime files; board configuration is merged separately.
set -euo pipefail
target=$1
runtime=$(realpath "${T33_RUNTIME_DIR:?}")
destination=$target/lumi
mkdir -p "$destination/bin" "$destination/lib"
required=(lumi-gateway-permissions install-security ipc-stream-core ipc-stream-services ipc-stream-supervisor lumi-config lumi-snapshot-ffmpeg lumi-t33gs-relay-agent)
for name in "${required[@]}"; do test -x "$runtime/bin/$name" || { echo "Missing runtime executable: $name" >&2; exit 1; }; done
test -x "$runtime/recording/bin/ipc-stream-recorder"
test -s "$runtime/bin/relay-agent.t33gs.gz"
test -s "$runtime/tunnel.cert"
if find "$runtime" -name relay-key.json -print -quit | grep -q .; then echo 'Refusing embedded relay identity' >&2; exit 1; fi
(cd "$runtime" && sha256sum -c SHA256SUMS)
python3 "$(dirname "$0")/t33-gateway-profile.py" create "$runtime" "$destination/gateway-profile.json"
rm -rf "$target/usr/lib/lumi-ipc-streamer"
mkdir -p "$destination/bin" "$destination/lib"
for name in "${required[@]}"; do install -m 755 "$runtime/bin/$name" "$destination/bin/$name"; done
# Incremental builds must remove executables whose owners were merged.
for name in ipc-stream-worker ipc-stream-motor media-worker-p2p.t33 lumi-t33gs-p2p ipc-wakeword-worker ipc-luvox-worker voice-ram-supervisor; do
 rm -f "$destination/bin/$name"
done
if [ -x "$runtime/voice/bin/ipc-voice-worker" ]; then
 test -s "${T33_RISCV_IMAGE:?Build the RISC-V wake payload with the voice worker}"
 install -m 755 "$runtime/voice/bin/ipc-voice-worker" "$destination/bin/ipc-voice-worker"
 mkdir -p "$destination/firmware"
 install -m 644 "$T33_RISCV_IMAGE" "$destination/firmware/wake.rvpack"
else
 rm -f "$destination/bin/ipc-voice-worker"
 rm -f "$destination/firmware/wake.rvpack"
fi
# SquashFS compresses the ELF more efficiently than an already gzipped ELF.
gzip -dc "$runtime/bin/relay-agent.t33gs.gz" > "$destination/bin/relay-agent.t33gs"
chmod 755 "$destination/bin/relay-agent.t33gs"
rm -f "$destination/bin/relay-agent.t33gs.gz"
cat "$runtime/bin/lumi-snapshot-ffmpeg.COPYING.LGPLv2.1" "$runtime/bin/lumi-snapshot-ffmpeg.COPYING.zlib" "$runtime/bin/lumi-snapshot-ffmpeg.COPYING.libjpeg-turbo" > "$destination/LICENSES.txt"
cat "${T33_KERNEL_COPYING:-${BUILD_DIR:?}/linux-custom/COPYING}" >> "$destination/LICENSES.txt"
cp -a "$runtime/recording/bin/ipc-stream-recorder" "$destination/bin/"
cp -a "$runtime/tunnel.cert" "$destination/"
