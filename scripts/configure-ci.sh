#!/usr/bin/env bash
# configure-ci.sh — apply a local ci-config.conf as GitHub Repository Variables.
#
# Usage: scripts/configure-ci.sh [--repo <owner>/<repo>] [--dry-run] [config-file]
#   config-file defaults to ./ci-config.conf (copy of ci-config.example.conf).
#   --dry-run prints the gh commands instead of executing them.
#   Requires an authenticated gh CLI (except --dry-run together with --repo).
#
# Variables equal to their fork-safe default are deleted, not set.
# Refuses to run against the canonical repo (its behavior is hardcoded).
set -euo pipefail

usage() {
    grep '^#' "$0" | sed -n '2,9p' | sed 's/^# \{0,1\}//'
}

CONFIG_FILE="ci-config.conf"
REPO=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo) REPO="${2:?--repo needs a value}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 1 ;;
        *) CONFIG_FILE="$1"; shift ;;
    esac
done

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$CONFIG_FILE" ]] || die "config file not found: $CONFIG_FILE (copy ci-config.example.conf)"

# Reject anything that is not a comment, blank line, or plain KEY=VALUE.
if grep -Evq '^[[:space:]]*(#|$)|^[A-Z0-9_]+=[A-Za-z0-9 ,./_-]*$' "$CONFIG_FILE"; then
    grep -Env '^[[:space:]]*(#|$)|^[A-Z0-9_]+=[A-Za-z0-9 ,./_-]*$' "$CONFIG_FILE" >&2
    die "config may only contain comments and KEY=VALUE lines (letters, digits, ',./_- ')"
fi

declare -A CFG
while IFS='=' read -r key value; do
    CFG[$key]="$value"
done < <(grep -E '^[A-Z0-9_]+=' "$CONFIG_FILE")

KNOWN_KEYS="BACKEND_TEST_RUNNER BACKEND_TEST_RUNNER_LABELS FRONTEND_BUILD_RUNNER \
FRONTEND_BUILD_RUNNER_LABELS E2E_RUNNER E2E_RUNNER_LABELS ENABLE_PLAYWRIGHT_E2E \
ENABLE_RAID_LOOPBACK ENABLE_TAURI_BUILD ENABLE_TUI_BUILD ENABLE_DEPLOY_PI \
ENABLE_RELEASE_STABLE ENABLE_DEPLOY_FORK DEPLOY_FORK_RUNNER_LABELS DEPLOY_FORK_INSTALL_DIR"
for key in "${!CFG[@]}"; do
    [[ " $KNOWN_KEYS " == *" $key "* ]] || die "unknown config key: $key"
done

if [[ -z "$REPO" ]]; then
    REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner) \
        || die "could not detect repo — pass --repo <owner>/<repo>"
fi
[[ "$REPO" != "Xveyn/BaluHost" ]] \
    || die "refusing to configure the canonical repo: its pipeline behavior is hardcoded"

set_var() {
    if [[ "$DRY_RUN" == 1 ]]; then
        echo "[dry-run] gh variable set $1 --repo $REPO --body '$2'"
    else
        gh variable set "$1" --repo "$REPO" --body "$2"
        echo "set    $1 = $2"
    fi
}

del_var() {
    if [[ "$DRY_RUN" == 1 ]]; then
        echo "[dry-run] gh variable delete $1 --repo $REPO (default — variable removed)"
        return
    fi
    local err
    if err=$(gh variable delete "$1" --repo "$REPO" 2>&1); then
        echo "default $1 (variable removed)"
    elif grep -qiE 'not found|404' <<< "$err"; then
        echo "default $1 (was not set)"
    else
        die "could not delete variable $1: $err"
    fi
}

# "a, b" -> ["self-hosted","a","b"] ('self-hosted' always implied, deduped)
labels_to_json() {
    local out='["self-hosted"' part
    local -a parts
    IFS=',' read -ra parts <<< "${1:-}"
    for part in "${parts[@]}"; do
        part="${part#"${part%%[![:space:]]*}"}"; part="${part%"${part##*[![:space:]]}"}"
        [[ -z "$part" || "$part" == "self-hosted" ]] && continue
        out+=",\"$part\""
    done
    echo "$out]"
}

bool_var() {  # <name> <default>
    local name="$1" def="$2"
    local val="${CFG[$name]:-$def}"
    [[ "$val" == "true" || "$val" == "false" ]] || die "$name must be true or false (got: $val)"
    if [[ "$val" == "$def" ]]; then del_var "$name"; else set_var "$name" "$val"; fi
}

echo "Applying $CONFIG_FILE to $REPO ..."

case "${CFG[BACKEND_TEST_RUNNER]:-github}" in
    github)      del_var BACKEND_TEST_RUNNER ;;
    self-hosted) set_var BACKEND_TEST_RUNNER "$(labels_to_json "${CFG[BACKEND_TEST_RUNNER_LABELS]:-}")" ;;
    *) die "BACKEND_TEST_RUNNER must be 'github' or 'self-hosted'" ;;
esac
if [[ "${CFG[BACKEND_TEST_RUNNER]:-github}" != "self-hosted" && -n "${CFG[BACKEND_TEST_RUNNER_LABELS]:-}" ]]; then
    echo "WARNING: BACKEND_TEST_RUNNER_LABELS is set but BACKEND_TEST_RUNNER is not 'self-hosted' — labels ignored" >&2
fi

case "${CFG[FRONTEND_BUILD_RUNNER]:-github}" in
    github)      del_var FRONTEND_BUILD_RUNNER ;;
    self-hosted) set_var FRONTEND_BUILD_RUNNER "$(labels_to_json "${CFG[FRONTEND_BUILD_RUNNER_LABELS]:-}")" ;;
    *) die "FRONTEND_BUILD_RUNNER must be 'github' or 'self-hosted'" ;;
esac
if [[ "${CFG[FRONTEND_BUILD_RUNNER]:-github}" != "self-hosted" && -n "${CFG[FRONTEND_BUILD_RUNNER_LABELS]:-}" ]]; then
    echo "WARNING: FRONTEND_BUILD_RUNNER_LABELS is set but FRONTEND_BUILD_RUNNER is not 'self-hosted' — labels ignored" >&2
fi

case "${CFG[E2E_RUNNER]:-github}" in
    github)      del_var E2E_RUNNER ;;
    self-hosted) set_var E2E_RUNNER "$(labels_to_json "${CFG[E2E_RUNNER_LABELS]:-}")" ;;
    *) die "E2E_RUNNER must be 'github' or 'self-hosted'" ;;
esac
if [[ "${CFG[E2E_RUNNER]:-github}" != "self-hosted" && -n "${CFG[E2E_RUNNER_LABELS]:-}" ]]; then
    echo "WARNING: E2E_RUNNER_LABELS is set but E2E_RUNNER is not 'self-hosted' — labels ignored" >&2
fi

bool_var ENABLE_PLAYWRIGHT_E2E true
bool_var ENABLE_RAID_LOOPBACK true
bool_var ENABLE_TAURI_BUILD true
bool_var ENABLE_TUI_BUILD true
bool_var ENABLE_DEPLOY_PI false
bool_var ENABLE_RELEASE_STABLE false
bool_var ENABLE_DEPLOY_FORK false

if [[ "${CFG[ENABLE_DEPLOY_FORK]:-false}" == "true" ]]; then
    [[ -n "${CFG[DEPLOY_FORK_RUNNER_LABELS]:-}" ]] \
        || die "ENABLE_DEPLOY_FORK=true requires DEPLOY_FORK_RUNNER_LABELS"
    set_var DEPLOY_FORK_RUNNER "$(labels_to_json "${CFG[DEPLOY_FORK_RUNNER_LABELS]}")"
    INSTALL_DIR_VAL="${CFG[DEPLOY_FORK_INSTALL_DIR]:-/opt/baluhost}"
    if [[ "$INSTALL_DIR_VAL" == "/opt/baluhost" ]]; then
        del_var DEPLOY_FORK_INSTALL_DIR
    else
        set_var DEPLOY_FORK_INSTALL_DIR "$INSTALL_DIR_VAL"
    fi
else
    del_var DEPLOY_FORK_RUNNER
    del_var DEPLOY_FORK_INSTALL_DIR
fi

echo "Done."
