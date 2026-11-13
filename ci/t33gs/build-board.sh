#!/usr/bin/env bash
# Prepare the environment; Buildroot owns all component builds and post-image.
set -euo pipefail
fw=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
export LUMI_WORKSPACE=$(dirname "$fw")
export PYTHONDONTWRITEBYTECODE=1
: "${LUMI_INPUTS:?}"
: "${LUMI_T33GS_INPUTS_SHA256:?}"
[[ ${LUMI_BUILD_JOBS:-4} =~ ^[1-9][0-9]*$ ]] || { echo 'LUMI_BUILD_JOBS must be a positive integer' >&2; exit 2; }
[[ ${LUMI_BUILD_VOICE:-1} =~ ^[01]$ ]] || { echo 'LUMI_BUILD_VOICE must be 0 or 1' >&2; exit 2; }
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$fw" show -s --format=%ct HEAD)}
export BUILD_SHA=$(git -C "$fw" rev-parse HEAD)
export GIT_HASH=${BUILD_SHA:0:12} GIT_BRANCH=lumi-ci BUILD_PLATFORM=t33_lite
export BUILD_ID=${BUILD_ID:-lumi-t33gs-${BUILD_SHA:0:12}}
export T33_SDK_ROOT="$LUMI_INPUTS/sdk" T33_TOOLCHAIN_ROOT="$LUMI_INPUTS/uclibc"
export T33GS_UCLIBC_TOOLCHAIN="$LUMI_INPUTS/uclibc" T33GS_MUSL_TOOLCHAIN="$LUMI_INPUTS/musl"
export T33GS_IMP_SDK="$LUMI_INPUTS/imp" T33GS_IMP_LIB_DIR="$LUMI_INPUTS/board/opt/ingenic-t33/lib"
export T33_AIC_SOURCE_ARCHIVE="$LUMI_INPUTS/aic8800.tar.gz"
[[ ! -d $LUMI_INPUTS/aic8800 ]] || export T33_AIC_SOURCE_DIR="$LUMI_INPUTS/aic8800"
export LUMI_BUILDROOT_SOURCE="$LUMI_WORKSPACE/buildroot"
export BR2_DL_DIR=${BR2_DL_DIR:-$LUMI_WORKSPACE/build/dl}
export LUMI_T33_IN_CONTAINER=1
mkdir -p "$HOME"
python3 "$fw/ci/t33gs/firmware.py" check-inputs "$LUMI_INPUTS" --sha256 "$LUMI_T33GS_INPUTS_SHA256"
# Local source trees and optional voice are configured before Buildroot resolves
# its dependency graph. No binaries from the legacy build are imported.
cd "$fw"
make BOARD=lumi_t33gs_prj008_sc4336 TARGET="$LUMI_WORKSPACE/build/userspace" \
  T33GS_JOBS="${LUMI_BUILD_JOBS:-4}" -j"${LUMI_BUILD_JOBS:-4}" "${LUMI_BUILD_GOAL:-all}"
