#!/usr/bin/env bash
# Re-enter an existing immutable snapshot without importing legacy artifacts.
set -euo pipefail
: "${T33GS_WORKSPACE:?Set T33GS_WORKSPACE to a completed/prepared unified build}"
goal=${1:?}
[[ $goal =~ ^br-[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid package goal' >&2; exit 2; }
root=$(realpath "$T33GS_WORKSPACE")
[[ -f $root/sources.json && -f $root/build/userspace/.config ]] || { echo 'Not a unified build workspace' >&2; exit 1; }
grep -qx 'BR2_PACKAGE_LUMI_T33_PLATFORM=y' "$root/build/userspace/.config"
checksum=$(sha256sum "$root/local-inputs/SHA256SUMS" | cut -d ' ' -f 1)
docker run --rm --user "$(id -u):$(id -g)" \
  --env HOME=/work/build-home --env LUMI_INPUTS=/inputs \
  --env "LUMI_T33GS_INPUTS_SHA256=$checksum" --env "LUMI_BUILD_GOAL=$goal" \
  --env "LUMI_BUILD_JOBS=${T33GS_JOBS:-4}" --env "LUMI_BUILD_VOICE=${T33GS_VOICE:-1}" \
  --mount "type=bind,src=$root,dst=/work" \
  --mount "type=bind,src=$root/local-inputs,dst=/inputs,readonly" \
  "${T33GS_BUILDER_IMAGE:-lumi-t33gs-builder:local}" bash /work/lumi-ipc-firmware/ci/t33gs/build-board.sh
