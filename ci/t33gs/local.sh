#!/usr/bin/env bash
# Snapshot local development sources before invoking the isolated firmware build.
set -euo pipefail
shopt -s inherit_errexit
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROLES=(firmware streamer linux uboot relay tflm opus buildroot kernel drivers aic)
DESTS=(lumi-ipc-firmware lumi-ipc-streamer lumi-ipc-linux lumi-u-boot-t33 iot-relay-cloud tflm opus buildroot local-inputs/sdk/kernel-4.4.94 local-inputs/sdk/drivers local-inputs/aic8800)
INPUT_VARS=(T33GS_UCLIBC_TOOLCHAIN T33GS_MUSL_TOOLCHAIN T33GS_IMP_HEADERS T33GS_VENDOR_LIBRARIES T33GS_SENSOR_TUNING T33GS_WIFI_FIRMWARE T33GS_RELAY_CERTIFICATE)
INPUT_DESTS=(uclibc musl imp/include board/opt/ingenic-t33/lib board/etc/sensor board/lib/firmware tunnel.cert)
if [[ ${T33GS_VOICE:-1} == 1 ]]; then
    INPUT_VARS+=(T33GS_RISCV_TOOLCHAIN)
    INPUT_DESTS+=(riscv)
fi
fail() { echo "ERROR: $*" >&2; exit 1; }

GENERATED=('*.o' '*.ko' '*.a' '*.so' '*.so.*' '*.cmd' '*.mod.c' '*.pyc' '.config*'
    Module.symvers modules.order System.map vmlinux vmlinux.bin vmlinux.symvers
    vmlinux.gz vmlinux.bz2 vmlinux.lzma 'uImage*' u-boot u-boot.bin u-boot-with-spl.bin
    'rootfs.squashfs*' '*-full.bin' '*-ota.tgz')
FILTERS=(--exclude=/.git --exclude=/output/ '--exclude=/output-*/' --exclude=/target/
    --exclude=/artifacts/ --exclude=__pycache__/ --exclude=.tmp_versions/
    --include=libPRJ008-firmware-4494-540.a)
for pattern in "${GENERATED[@]}"; do FILTERS+=("--exclude=$pattern"); done
source_included() {
    local name=$1 pattern
    case $name in
        .git|.git/*|output/*|output-*/*|target/*|artifacts/*|*/__pycache__/*|__pycache__/*|*/.tmp_versions/*|.tmp_versions/*) return 1 ;;
        */libPRJ008-firmware-4494-540.a|libPRJ008-firmware-4494-540.a) return 0 ;;
    esac
    for pattern in "${GENERATED[@]}"; do [[ ${name##*/} != $pattern ]] || return 1; done
}

validate_links() {
    local root=$1 overlays=${2:-0} file name target resolved
    while IFS= read -r -d '' file; do
        name=${file#"$root"/}
        if [[ $overlays == 1 ]]; then
            case "$name" in
                general/overlay/*|lumi/overlay/*|lumi/board/*/overlay/*|package/skeleton-*/skeleton/*|board/*/rootfs_overlay/*) continue ;;
            esac
        fi
        target=$(readlink -- "$file")
        resolved=$(realpath -m -- "$file")
        [[ $target != /* && $resolved == "$root/"* ]] || fail "symlink escapes snapshot: $file -> $target"
    done < <(find "$root" -name .git -prune -o -type l -print0)
}

snapshot() {
    local root=$1 dest=$2 status='' head='' list name parent
    [[ ! -e $dest && ! -L $dest ]] || fail "Snapshot already exists: $dest"
    mkdir -p -- "$(dirname -- "$dest")"
    if [[ -e $root/.git ]]; then
        [[ $(git -C "$root" rev-parse --show-toplevel) == "$root" ]] || fail "Select Git repository root: $root"
        status=$(git -C "$root" status --porcelain --untracked-files=all)
        head=$(git -C "$root" rev-parse HEAD)
        git clone --quiet --no-hardlinks --no-checkout -- "$root" "$dest"
        git -C "$dest" read-tree HEAD
        list=$(mktemp "$dest/.git/lumi-source-list.XXXXXX")
        # Validate the file list before rsync; never traverse a directory link
        # supplied by a modified working tree, even in a rootfs overlay.
        git -C "$root" ls-files -z --cached --others --exclude-standard | sort -zu > "$list.all"
        while IFS= read -r -d '' name; do
            source_included "$name" || continue
            [[ -e $root/$name || -L $root/$name ]] || continue
            parent=$(realpath -m -- "$(dirname -- "$root/$name")")
            [[ $parent == "$root" || $parent == "$root/"* ]] || fail "Source path escapes repository: $name"
            [[ -f $root/$name || -L $root/$name ]] || fail "Unsupported source entry (including submodule): $name"
            printf '%s\0' "$name" >> "$list"
        done < "$list.all"
        rsync -a --from0 --files-from="$list" "${FILTERS[@]}" -- "$root/" "$dest/"
        rm -- "$list" "$list.all"
        [[ $(git -C "$root" status --porcelain --untracked-files=all) == "$status" && $(git -C "$root" rev-parse HEAD) == "$head" ]] || fail "Source changed during snapshot: $root"
    else
        mkdir -- "$dest"
        rsync -a "${FILTERS[@]}" -- "$root/" "$dest/"
    fi
    validate_links "$dest" 1
    # Hash link nodes rather than their camera-absolute targets.
    local sum count
    sum=$(tree_digest "$dest")
    count=$(find "$dest" -name .git -prune -o \( -type f -o -type l \) -printf '.\n' | wc -l)
    jq -n --arg path "${dest#"$WORKSPACE"/}" --arg local "$root" --arg commit "$head" \
        --arg hash "$sum" --argjson files "$count" --arg status "$status" \
        '{path:$path,local:$local,snapshot_sha256:$hash,files:$files} +
         (if $commit == "" then {source_tree:true} else {commit:$commit,dirty:($status != "")} end)'
}

tree_digest() {
(
    cd -- "$1"
    # Batch hashing avoids spawning stat and sha256sum for every kernel file.
    printf 'metadata\0'
    find . -name .git -prune -o \( -type f -o -type l \) -printf '%p\t%m\t%y\0' | LC_ALL=C sort -z
    printf 'links\0'
    find . -name .git -prune -o -type l -printf '%p\t%l\0' | LC_ALL=C sort -z
    printf 'contents\0'
    find . -name .git -prune -o -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum -z --
) | sha256sum | cut -d ' ' -f 1
}

validate_config() {
    local role var value marker
    for role in "${ROLES[@]}"; do
        var=T33GS_${role^^}_SRC
        value=${!var:-}
        [[ $value == /* && -d $value ]] || fail "$var must name an existing absolute source directory: $value"
        printf -v "$var" '%s' "$(realpath -- "$value")"
        case $role in
            firmware|streamer|linux|tflm) [[ -e ${!var}/.git ]] || fail "$role requires a Git checkout" ;;
        esac
        printf '%-27s %s\n' "$var" "${!var}"
    done
    for var in "${INPUT_VARS[@]}"; do
        value=${!var:-}
        [[ $value == /* && -e $value ]] || fail "$var must name an existing absolute SDK path: $value"
        if [[ $var == T33GS_RELAY_CERTIFICATE ]]; then
            [[ -f $value ]] || fail "Certificate must be a file: $value"
        else
            [[ -d $value ]] || fail "SDK input must be a directory: $value"
        fi
        printf -v "$var" '%s' "$(realpath -- "$value")"
        printf '%-27s %s\n' "$var" "${!var}"
    done
    [[ ${T33GS_JOBS:-4} =~ ^[1-9][0-9]*$ ]] || fail 'T33GS_JOBS must be a positive integer'
    [[ ${T33GS_VOICE:-1} =~ ^[01]$ ]] || fail 'T33GS_VOICE must be 0 or 1'
    [[ -x $T33GS_UCLIBC_TOOLCHAIN/bin/mips-linux-uclibc-gcc ]] || fail 'Missing uClibc compiler'
    [[ -x $T33GS_MUSL_TOOLCHAIN/bin/mipsel-linux-muslsf-gcc ]] || fail 'Missing musl compiler'
    if [[ ${T33GS_VOICE:-1} == 1 ]]; then
        [[ -x $T33GS_RISCV_TOOLCHAIN/bin/riscv-none-embed-gcc &&
           -x $T33GS_RISCV_TOOLCHAIN/bin/riscv-none-embed-g++ ]] || fail 'Missing RV32IMC/newlib compiler'
    fi
    for marker in "$T33GS_KERNEL_SRC/Makefile" "$T33GS_DRIVERS_SRC/isp/tx-isp" \
        "$T33GS_DRIVERS_SRC/sensors/sc4336" "$T33GS_DRIVERS_SRC/audio/oss3" \
        "$T33GS_AIC_SRC/Makefile" "$T33GS_AIC_SRC/aic8800_fdrv"; do
        [[ -e $marker ]] || fail "Missing source input: $marker"
    done
}

new_workspace() {
    local var value role allocated=0
    if [[ -n ${T33GS_WORKSPACE:-} ]]; then
        WORKSPACE=$T33GS_WORKSPACE
    else
        mkdir -p -- "$T33GS_FIRMWARE_SRC/output"
        WORKSPACE=$(mktemp -d "$T33GS_FIRMWARE_SRC/output/t33gs-local-XXXXXX")
        allocated=1
    fi
    [[ $WORKSPACE == /* ]] || fail 'T33GS_WORKSPACE must be absolute'
    WORKSPACE=$(realpath -m -- "$WORKSPACE")
    for role in "${ROLES[@]}"; do
        var=T33GS_${role^^}_SRC
        value=${!var}
        if [[ $WORKSPACE == "$value" || $WORKSPACE == "$value/"* ]]; then
            # Firmware output/ is excluded from every source snapshot. Other
            # source trees must never contain a workspace being populated.
            [[ $var == T33GS_FIRMWARE_SRC && $WORKSPACE == "$value/output/"* ]] || fail "Workspace must be outside sources: $value"
        fi
    done
    for var in "${INPUT_VARS[@]}"; do
        value=${!var}
        [[ $WORKSPACE != "$value" && $WORKSPACE != "$value/"* ]] || fail "Workspace must be outside SDK inputs: $value"
    done
    if [[ $allocated == 0 ]]; then
        [[ ! -e $WORKSPACE && ! -L $WORKSPACE ]] || fail "Workspace already exists: $WORKSPACE"
        mkdir -p -- "$(dirname -- "$WORKSPACE")"
        mkdir -- "$WORKSPACE"
    fi
}

relocate_musl_loader() {
    local loader=$1/musl/mipsel-linux-muslsf/lib/ld-musl-mipsel-sf.so.1
    if [[ -L $loader && $(readlink -- "$loader") == /lib/libc.so ]]; then
        [[ -f ${loader%/*}/libc.so && ! -L ${loader%/*}/libc.so ]] || fail 'Missing regular musl sysroot libc.so'
        ln -sfn libc.so "$loader"
    fi
}

stage_sdk_input() {
    local source=$1 destination=$2
    if [[ -d $source ]]; then
        mkdir -p -- "$destination"
        # Toolchains may come from repo-managed SDKs. Git metadata is not an
        # SDK input and can contain links outside the self-contained bundle.
        rsync -a --exclude=.git -- "$source/" "$destination/"
    else
        cp -a -- "$source" "$destination"
    fi
}

prepare_inputs() {
    local root=$WORKSPACE/local-inputs i var dest checksum
    for i in "${!INPUT_VARS[@]}"; do
        var=${INPUT_VARS[$i]}
        dest=$root/${INPUT_DESTS[$i]}
        echo "Staging SDK: ${!var}" >&2
        mkdir -p -- "$(dirname -- "$dest")"
        stage_sdk_input "${!var}" "$dest"
    done
    python3 "$HERE/../../lumi/board/t33gs-prj008/fix-xsym-links.py" "$root/board/opt/ingenic-t33/lib" >&2
    relocate_musl_loader "$root"
    # Source overlays contain camera links; SDK inputs must stay inside the SDK.
    validate_links "$root"
    printf '# Local SDK provenance\n' > "$root/PROVENANCE.md"
    for var in "${INPUT_VARS[@]}"; do printf '%s: %s\n' "$var" "${!var}" >> "$root/PROVENANCE.md"; done
    (cd -- "$root"; find . -xtype f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS)
    checksum=$(sha256sum "$root/SHA256SUMS" | cut -d ' ' -f 1)
    python3 "$HERE/firmware.py" check-inputs "$root" --sha256 "$checksum" >&2
    printf '%s' "$checksum"
}

main() {
    local action=${1:-} i role var record checksum image build_hash
    case $action in t33gs-plan|t33gs-prepare|t33gs-full) ;; *) fail 'Use make t33gs-plan, t33gs-prepare or t33gs-full' ;; esac
    for var in git rsync jq sha256sum realpath; do command -v "$var" >/dev/null || fail "Missing host command: $var"; done
    validate_config
    [[ $action != t33gs-plan ]] || return 0
    new_workspace
    printf '{}\n' > "$WORKSPACE/sources.json"
    for i in "${!ROLES[@]}"; do
        role=${ROLES[$i]}
        var=T33GS_${role^^}_SRC
        echo "Preparing $role: ${!var}"
        record=$(snapshot "${!var}" "$WORKSPACE/${DESTS[$i]}")
        jq --arg role "$role" --argjson record "$record" '. + {($role):$record}' \
            "$WORKSPACE/sources.json" > "$WORKSPACE/sources.json.tmp"
        mv -- "$WORKSPACE/sources.json.tmp" "$WORKSPACE/sources.json"
    done
    echo "Workspace: $WORKSPACE"
    [[ $action != t33gs-prepare ]] || return 0
    checksum=$(prepare_inputs)
    image=${T33GS_BUILDER_IMAGE:-lumi-t33gs-builder:local}
    docker build -t "$image" "$WORKSPACE/lumi-ipc-firmware/ci/t33gs"
    build_hash=$(sha256sum "$WORKSPACE/sources.json" | cut -c 1-12)
    docker run --rm --user "$(id -u):$(id -g)" \
        --env HOME=/work/build-home --env LUMI_INPUTS=/inputs \
        --env "LUMI_T33GS_INPUTS_SHA256=$checksum" --env "LUMI_BUILD_VOICE=${T33GS_VOICE:-1}" \
        --env "LUMI_BUILD_JOBS=${T33GS_JOBS:-4}" --env "BUILD_ID=lumi-t33gs-local-$build_hash" \
        --mount "type=bind,src=$WORKSPACE,dst=/work" \
        --mount "type=bind,src=$WORKSPACE/local-inputs,dst=/inputs,readonly" \
        "$image" bash "/work/lumi-ipc-firmware/ci/t33gs/${LUMI_T33_BUILD_SCRIPT:-build-board.sh}"
    echo "Firmware and OTA: $WORKSPACE/artifacts"
}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
