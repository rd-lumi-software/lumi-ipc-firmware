#!/bin/bash
# Install verified source-built apps into immutable /lumi; mutable config stays separate.
set -euo pipefail
target=$1
: "${T33_RUNTIME_DIR:?Build a verified compact package-t33gs first}"
runtime=$(realpath "$T33_RUNTIME_DIR")
destination="$target/lumi"
# Never reuse an unrelated account/group at the fixed IPC boundary IDs.
if grep -qE '^[^:]+:[^:]*:200:' "$target/etc/passwd"; then
 grep -qx 'lumi-gateway:x:200:200:Camera network gateway:/nonexistent:/bin/false' "$target/etc/passwd" || { echo 'Gateway UID 200 collision' >&2; exit 1; }
else
 ! grep -q '^lumi-gateway:' "$target/etc/passwd"
 echo 'lumi-gateway:x:200:200:Camera network gateway:/nonexistent:/bin/false' >> "$target/etc/passwd"
 echo 'lumi-gateway:!:0:0:99999:7:::' >> "$target/etc/shadow"
fi
if grep -qE '^[^:]+:[^:]*:200:' "$target/etc/group"; then
 grep -qx 'lumi-gateway:x:200:' "$target/etc/group" || { echo 'Gateway GID 200 collision' >&2; exit 1; }
else
 ! grep -q '^lumi-gateway:' "$target/etc/group"
 echo 'lumi-gateway:x:200:' >> "$target/etc/group"
fi
# The root SSH authorized_keys and host key share persistent, root-only storage.
# Never package an administrator identity in the immutable image.
if [ -d "$target/etc/dropbear" ] && [ ! -L "$target/etc/dropbear" ]; then
 test -z "$(find "$target/etc/dropbear" -mindepth 1 -print -quit)" || { echo 'Refusing packaged SSH identity' >&2; exit 1; }
 rmdir "$target/etc/dropbear"
fi
ln -sfn /overlay/dropbear "$target/etc/dropbear"
# This board's accepted filter policy only uses these matches. Other xtables
# plugins require absent kernel targets (NAT/mangle/etc.) and consume NOR space.
xtables="$target/usr/lib/xtables"
test -d "$xtables" && test ! -L "$xtables"
for plugin in "$xtables"/*; do
 case "${plugin##*/}" in
  libxt_conntrack.so|libxt_state.so|libxt_tcp.so|libxt_udp.so|libxt_standard.so|libipt_icmp.so|libip6t_icmp6.so) ;;
  *) rm -f "$plugin";;
 esac
done
for plugin in libxt_conntrack.so libxt_tcp.so libxt_udp.so libxt_standard.so libipt_icmp.so libip6t_icmp6.so; do
 test -s "$xtables/$plugin" || { echo "Firewall parser dependency missing: $plugin" >&2; exit 1; }
done
# A rootfs-only rollout can retain the deployed kernel's exact module set.
# The caller supplies a verified prior image, not modules from another kernel.
if [ -n "${T33_KERNEL_MODULES_DIR:-}" ]; then
 test -s "$T33_KERNEL_MODULES_DIR/4.4.94-lumi-t33gs/ingenic/lumi_motor.ko"
 test -s "$T33_KERNEL_MODULES_DIR/4.4.94-lumi-t33gs/ingenic/tnpu.ko"
 rm -rf "$target/lib/modules"
 cp -a "$T33_KERNEL_MODULES_DIR" "$target/lib/modules"
fi
test -s "$destination/camera-profile.json"
test -x "$destination/bin/utilization"
if [[ ${T33_RUNTIME_PREINSTALLED:-0} != 1 ]]; then
 bash "$(dirname "$0")/install-t33-runtime.sh" "$target"
fi
test -s "${T33_4494_OUTPUT_DIR:?}/aes-dma-client/lumi_dma_client"
test -s "$target/lib/modules/4.4.94-lumi-t33gs/ingenic/lumi_aes_dma4494_service.ko"
grep -q 'srtp=t33gs-dma-aes-' "$runtime/bin/ipc-stream-services.build-info"
install -m 755 "$T33_4494_OUTPUT_DIR/aes-dma-client/lumi_dma_client" "$destination/bin/lumi-aes-dma-client"
chmod 755 "$destination/bin/lumi-aes-dma-init"
printf 'aes-dma4494-required-no-fallback\n' > "$destination/aes-dma.required"
# mdev may process the add event after chown; keep the exact gateway metadata.
sed -i '/^lumi-aes-dma[[:space:]]/d' "$target/etc/mdev.conf"
printf '\nlumi-aes-dma 200:200 600\n' >> "$target/etc/mdev.conf"
# Preserve the SDK loader ABI while keeping a single physical library copy.
sdk="$target/opt/ingenic-t33/lib"
if [ -d "$sdk" ] && [ ! -L "$sdk" ]; then
 rm -rf "$destination/lib"
 mv "$sdk" "$destination/lib"
fi
test -s "$destination/lib/libimp.so"
ln -sfn /lumi/lib "$sdk"
for helper in lumi-t33gs-motor-gpio-init; do
 if [ -f "$target/usr/sbin/$helper" ]; then mv "$target/usr/sbin/$helper" "$destination/bin/$helper"; fi
done
for helper in t33-riscv-probe; do
 if [ -f "$target/usr/bin/$helper" ]; then mv "$target/usr/bin/$helper" "$destination/bin/$helper"; fi
done
for helper in t33-sensor-probe t33-frame-probe; do
 if [ -f "$target/opt/ingenic-t33/$helper" ]; then mv "$target/opt/ingenic-t33/$helper" "$destination/bin/$helper"; fi
done
# Avoid retaining removed tools from an incremental target or shared overlay.
rm -f "$target/usr/bin/ipctool" "$target/usr/bin/ipcinfo" "$target/usr/sbin/openipc-claim" "$target/usr/sbin/wireguard" "$target/etc/init.d/S98wireguard" "$target/etc/wireguard.conf" "$target/etc/network/interfaces.d/wg0" "$target/etc/init.d/S70vendor" "$target/usr/sbin/pqtools"
find "$target/usr/lib" -maxdepth 1 -name 'libipctool*' -delete
# Remove obsolete diagnostic branches without modifying GENERAL for other boards.
python3 - "$target/usr/sbin/extutils" <<'PYEXT'
from pathlib import Path
import re,sys
p=Path(sys.argv[1])
if p.exists():
 s=p.read_text()
 s=re.sub(r'\n\tipctool\)\n.*?\n\t\t;;', '', s, flags=re.S)
 s=re.sub(r'mac_from_flash\(\) \{.*?\n\}', 'mac_from_flash() { return 1; }', s, flags=re.S)
 s=s.replace('ipcinfo -ci', '/lumi/bin/lumi-config identity /lumi/camera-profile.json soc').replace('ipcinfo -s', '/lumi/bin/lumi-config identity /lumi/camera-profile.json sensor')
 p.write_text(s)
PYEXT
python3 "$(dirname "$0")/../../contrib/strip-t33gs-pdr.py" "$destination" \
 --objcopy "${T33GS_UCLIBC_TOOLCHAIN:?}/bin/mips-linux-uclibc-objcopy"
# The same debugger records also remain in system tools and vendor modules.
# Verify their allocated sections too; the 12 MiB rootfs must retain all runtime code.
python3 "$(dirname "$0")/../../contrib/strip-t33gs-pdr.py" "$target" \
 --objcopy "${T33GS_UCLIBC_TOOLCHAIN:?}/bin/mips-linux-uclibc-objcopy"
python3 "$(dirname "$0")/verify-t33-lumi-image.py" "$target" --write-manifest
