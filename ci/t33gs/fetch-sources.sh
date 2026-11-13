#!/usr/bin/env bash
# Fetch only immutable Git revisions into a fresh CI workspace.
set -euo pipefail
shopt -s inherit_errexit
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
fail() { echo "ERROR: $*" >&2; exit 1; }
resolve_sources() {
    local role repo commit path repo_env commit_env result='{}'
    while IFS=$'\t' read -r role path repo_env commit_env; do
        repo=$(jq -r --arg role "$role" '.[$role].repository // ""' "$HERE/sources.json")
        commit=$(jq -r --arg role "$role" '.[$role].commit // ""' "$HERE/sources.json")
        [[ -n $repo ]] || repo=${!repo_env:-}
        [[ -n $commit ]] || commit=${!commit_env:-}
        [[ $repo =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail "$role: set repository to owner/repo"
        [[ $commit =~ ^[a-f0-9]{40}$ ]] || fail "$role: set commit to a full commit SHA"
        [[ $path =~ ^[A-Za-z0-9_.-]+$ && $path != . && $path != .. && $path != lumi-ipc-firmware ]] || fail "$role: invalid checkout path"
        result=$(jq --arg role "$role" --arg repository "$repo" --arg commit "$commit" --arg path "$path" \
            '. + {($role):{repository:$repository,commit:$commit,path:$path}}' <<< "$result")
    done < <(jq -r 'to_entries[] | [.key,.value.path,(.value.repository_env // "UNUSED_REPOSITORY"),(.value.commit_env // "UNUSED_COMMIT")] | @tsv' "$HERE/sources.json")
    jq -e '[.[].path] | length == (unique | length)' <<< "$result" >/dev/null || fail 'Duplicate checkout paths'
    printf '%s\n' "$result"
}
main() {
    local workspace='' plan=0 sources firmware root commit role path repository sha
    while (($#)); do
        case $1 in
            --workspace) [[ $# -ge 2 ]] || fail 'Missing workspace'; workspace=$2; shift 2 ;;
            --plan) plan=1; shift ;;
            *) fail "Unknown argument: $1" ;;
        esac
    done
    [[ -n $workspace ]] || fail '--workspace is required'
    sources=$(resolve_sources)
    if [[ $plan == 1 ]]; then printf '%s\n' "$sources"; return; fi
    firmware=$(realpath "$HERE/../..")
    [[ -z $(git -C "$firmware" status --porcelain) ]] || fail 'Commit firmware changes before building from a clean checkout'
    root=$(realpath -m -- "$workspace")
    [[ ! -e $root && ! -L $root ]] || fail 'Workspace already exists; choose a new directory'
    mkdir -p -- "$root"
    export GIT_TERMINAL_PROMPT=0
    if [[ -n ${LUMI_SOURCE_READ_TOKEN:-} ]]; then
        # Authentication lives only in this process environment, never in a URL/config file.
        export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.https://github.com/.extraheader
        GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$LUMI_SOURCE_READ_TOKEN" | base64 -w0)"
        export GIT_CONFIG_VALUE_0
    fi
    commit=$(git -C "$firmware" rev-parse HEAD)
    git clone --quiet --no-hardlinks --no-checkout -- "$firmware" "$root/lumi-ipc-firmware"
    git -C "$root/lumi-ipc-firmware" checkout --quiet --detach "$commit"
    while IFS=$'\t' read -r role path repository sha; do
        echo "Fetching $role: $repository@$sha"
        git init --quiet "$root/$path"
        git -C "$root/$path" remote add origin "https://github.com/$repository.git"
        git -C "$root/$path" fetch --depth=1 origin "$sha"
        git -C "$root/$path" checkout --quiet --detach FETCH_HEAD
        [[ $(git -C "$root/$path" rev-parse HEAD) == "$sha" ]] || fail "Wrong checkout identity: $role"
    done < <(jq -r 'to_entries[] | [.key,.value.path,.value.repository,.value.commit] | @tsv' <<< "$sources")
    jq --arg commit "$commit" '. + {firmware:{path:"lumi-ipc-firmware",commit:$commit}}' <<< "$sources" > "$root/sources.json"
    echo "Sources ready: $root"
}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
