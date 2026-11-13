#!/usr/bin/env bash
# Keep dry-run/diagnostic flags, but give Buildroot its own per-package job limit.
# A jobserver cannot be shared with Cargo/CMake across the Docker boundary.
set -euo pipefail
MAKEFLAGS=$(printf '%s\n' "${MAKEFLAGS:-}" | sed -E \
  -e 's/(^| )-j[0-9]*( |$)/ /g' \
  -e 's/(^| )--jobs(=[0-9]+)?( |$)/ /g' \
  -e 's/(^| )--jobserver[^ ]*( |$)/ /g')
# Root BOARD/TARGET overrides belong to the outer Makefile. Besides leaking
# variables, names such as prj008 contain "j" and fool Buildroot's flag check.
MAKEFLAGS=${MAKEFLAGS%% -- *}
unset MAKEOVERRIDES
export MAKEFLAGS
exec "$@"
