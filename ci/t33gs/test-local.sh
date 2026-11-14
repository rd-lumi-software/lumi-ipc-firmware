#!/usr/bin/env bash
# Exercise snapshot boundaries without the SDK, network, Docker or camera.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$HERE/local.sh"
TEST_ROOT=$(mktemp -d)
trap 'rm -rf -- "$TEST_ROOT"' EXIT
WORKSPACE=$TEST_ROOT
mkdir "$TEST_ROOT/repo"
root=$TEST_ROOT/repo
git -C "$root" init -q
printf 'output/\n' > "$root/.gitignore"
printf committed > "$root/edited.c"
printf deleted > "$root/deleted.c"
git -C "$root" add .
git -C "$root" -c user.name=Test -c user.email=test@example.invalid commit -qm fixture
printf changed > "$root/edited.c"
rm "$root/deleted.c"
printf untracked > "$root/new source.c"
ln -s edited.c "$root/alias.c"
mkdir -p "$root/output" "$root/drivers/target" "$root/general/overlay/etc"
printf old > "$root/output/old.bin"
printf stale > "$root/old.o"
printf source > "$root/drivers/target/Makefile"
printf linker > "$root/vmlinux.lds.S"
printf vendor > "$root/libPRJ008-firmware-4494-540.a"
ln -s /tmp/resolv.conf "$root/general/overlay/etc/resolv.conf"
before=$(git -C "$root" status --porcelain)
record=$(snapshot "$root" "$TEST_ROOT/snapshot")
jq -e '.dirty == true and (.snapshot_sha256 | length == 64)' <<< "$record" >/dev/null
[[ $(cat "$TEST_ROOT/snapshot/edited.c") == changed ]]
[[ $(cat "$TEST_ROOT/snapshot/new source.c") == untracked ]]
[[ $(readlink "$TEST_ROOT/snapshot/alias.c") == edited.c ]]
[[ $(readlink "$TEST_ROOT/snapshot/general/overlay/etc/resolv.conf") == /tmp/resolv.conf ]]
[[ -f $TEST_ROOT/snapshot/drivers/target/Makefile && -f $TEST_ROOT/snapshot/vmlinux.lds.S ]]
[[ -f $TEST_ROOT/snapshot/libPRJ008-firmware-4494-540.a ]]
[[ ! -e $TEST_ROOT/snapshot/old.o && ! -e $TEST_ROOT/snapshot/deleted.c && ! -e $TEST_ROOT/snapshot/output ]]
[[ $(git -C "$TEST_ROOT/snapshot" rev-parse HEAD) == "$(git -C "$root" rev-parse HEAD)" ]]
[[ $(git -C "$root" status --porcelain) == "$before" ]]
second=$(snapshot "$root" "$TEST_ROOT/second")
[[ $(jq -r .snapshot_sha256 <<< "$record") == "$(jq -r .snapshot_sha256 <<< "$second")" ]]
printf different > "$root/edited.c"
third=$(snapshot "$root" "$TEST_ROOT/third")
[[ $(jq -r .snapshot_sha256 <<< "$record") != "$(jq -r .snapshot_sha256 <<< "$third")" ]]
mkdir "$TEST_ROOT/raw"
printf source > "$TEST_ROOT/raw/driver.c"
printf stale > "$TEST_ROOT/raw/driver.ko"
snapshot "$TEST_ROOT/raw" "$TEST_ROOT/raw-copy" >/dev/null
[[ -f $TEST_ROOT/raw-copy/driver.c && ! -e $TEST_ROOT/raw-copy/driver.ko ]]
ln -s /etc/shadow "$root/host-secret"
if (snapshot "$root" "$TEST_ROOT/rejected") > /dev/null 2>&1; then fail 'Accepted escaping source link'; fi
if (snapshot "$root" "$TEST_ROOT/snapshot") > /dev/null 2>&1; then fail 'Accepted existing snapshot'; fi
ROLES=(firmware)
INPUT_VARS=()
T33GS_FIRMWARE_SRC=$root
T33GS_WORKSPACE=$root/nested
if (new_workspace) > /dev/null 2>&1; then fail 'Accepted workspace inside source'; fi
T33GS_WORKSPACE=$TEST_ROOT/snapshot
if (new_workspace) > /dev/null 2>&1; then fail 'Accepted existing workspace'; fi
unset T33GS_WORKSPACE
generated=$(new_workspace; printf '%s' "$WORKSPACE")
[[ $generated == "$root/output/t33gs-local-"* && -d $generated ]]
printf old-build > "$generated/old-build.txt"
rm "$root/host-secret"
snapshot "$root" "$TEST_ROOT/without-build-workspace" > /dev/null
[[ ! -e $TEST_ROOT/without-build-workspace/output ]]
# The same output exception must not allow nested workspaces in other sources.
ROLES=(firmware streamer)
T33GS_STREAMER_SRC=$root/drivers
T33GS_WORKSPACE=$root/drivers/output/new-build
if (new_workspace) > /dev/null 2>&1; then fail 'Accepted workspace inside non-firmware source'; fi
mkdir -p "$TEST_ROOT/sdk-source/bin"
printf '#!/bin/sh\nexit 0\n' > "$TEST_ROOT/sdk-source/bin/compiler"
chmod 755 "$TEST_ROOT/sdk-source/bin/compiler"
ln -s compiler "$TEST_ROOT/sdk-source/bin/compiler-alias"
ln -s /outside/repo-metadata "$TEST_ROOT/sdk-source/.git"
stage_sdk_input "$TEST_ROOT/sdk-source" "$TEST_ROOT/sdk-staged"
[[ -x $TEST_ROOT/sdk-staged/bin/compiler ]]
[[ $(readlink "$TEST_ROOT/sdk-staged/bin/compiler-alias") == compiler ]]
[[ ! -e $TEST_ROOT/sdk-staged/.git && ! -L $TEST_ROOT/sdk-staged/.git ]]
validate_links "$TEST_ROOT/sdk-staged"
printf public-cert > "$TEST_ROOT/certificate"
stage_sdk_input "$TEST_ROOT/certificate" "$TEST_ROOT/certificate-staged"
cmp "$TEST_ROOT/certificate" "$TEST_ROOT/certificate-staged"
mkdir -p "$TEST_ROOT/sdk/musl/mipsel-linux-muslsf/lib"
lib=$TEST_ROOT/sdk/musl/mipsel-linux-muslsf/lib
ln -s /lib/libc.so "$lib/ld-musl-mipsel-sf.so.1"
if (relocate_musl_loader "$TEST_ROOT/sdk") > /dev/null 2>&1; then fail 'Accepted missing musl libc'; fi
printf target > "$lib/libc.so"
relocate_musl_loader "$TEST_ROOT/sdk"
[[ $(readlink "$lib/ld-musl-mipsel-sf.so.1") == libc.so ]]
source "$HERE/fetch-sources.sh"
export LUMI_STREAMER_REPOSITORY=owner/streamer LUMI_LINUX_REPOSITORY=owner/linux LUMI_UBOOT_REPOSITORY=owner/uboot
export LUMI_STREAMER_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export LUMI_LINUX_COMMIT=$LUMI_STREAMER_COMMIT LUMI_UBOOT_COMMIT=$LUMI_STREAMER_COMMIT LUMI_RELAY_COMMIT=$LUMI_STREAMER_COMMIT
resolve_sources > "$TEST_ROOT/plan.json"
jq -e '.streamer.repository == "owner/streamer" and (.tflm.commit | length == 40)' "$TEST_ROOT/plan.json" >/dev/null
export LUMI_STREAMER_COMMIT=main
if (resolve_sources) > /dev/null 2>&1; then fail 'Accepted mutable Git revision'; fi
export LUMI_STREAMER_COMMIT=$LUMI_LINUX_COMMIT LUMI_STREAMER_REPOSITORY=https://github.com/owner/repo
if (resolve_sources) > /dev/null 2>&1; then fail 'Accepted invalid repository'; fi
flags=$(MAKEFLAGS='nw -j4 --jobserver-auth=3,4 -- BOARD=test' bash "$HERE/run-buildroot.sh" bash -c 'printf "%s" "$MAKEFLAGS"')
[[ $flags == nw ]]
echo 'Local source snapshot and pinned fetch tests passed.'
