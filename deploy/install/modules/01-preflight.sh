#!/bin/bash
# BaluHost Install - Module 01: Preflight Checks
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Main ───────────────────────────────────────────────────────────

log_step "Preflight Checks"

# --- Root check ---
require_root

# --- Debian version ---
detect_debian_version
if [[ "$DEBIAN_VERSION" != "12" && "$DEBIAN_VERSION" != "13" ]]; then
    log_error "Debian $DEBIAN_VERSION is not supported. Only Debian 12 (bookworm) and 13 (trixie) are supported."
    exit 1
fi
log_info "Debian version check passed: $DEBIAN_VERSION ($DEBIAN_CODENAME)"

# --- Disk space ---
REQUIRED_KB=$((2 * 1024 * 1024))  # 2 GB in KB
AVAILABLE_KB=$(df --output=avail / | tail -1 | tr -d ' ')
AVAILABLE_MB=$((AVAILABLE_KB / 1024))
AVAILABLE_GB=$(awk "BEGIN { printf \"%.1f\", $AVAILABLE_KB / 1024 / 1024 }")

if [[ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]]; then
    log_error "Insufficient disk space on /: ${AVAILABLE_MB} MB available, 2048 MB required."
    exit 1
fi
log_info "Disk space check passed: ${AVAILABLE_GB} GB available on /"

# --- Port availability ---
PORTS_OK=true
for port in 80 8000; do
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        LISTENING_PROC=$(ss -tlnp 2>/dev/null | grep ":${port} " | awk '{print $NF}' | head -1)
        log_warn "Port $port is already in use by: $LISTENING_PROC"
        PORTS_OK=false
    else
        log_info "Port $port is available"
    fi
done
if [[ "$PORTS_OK" == "false" ]]; then
    log_warn "Some ports are in use. This may be fine if BaluHost services are already running."
fi

# --- Required commands ---
MISSING_CMDS=()
for cmd in python3 git; do
    if command -v "$cmd" &>/dev/null; then
        VERSION=$("$cmd" --version 2>&1 | head -1)
        log_info "Found $cmd: $VERSION"
    else
        MISSING_CMDS+=("$cmd")
        log_error "Required command not found: $cmd"
    fi
done

if [[ ${#MISSING_CMDS[@]} -gt 0 ]]; then
    log_error "Missing required commands: ${MISSING_CMDS[*]}"
    log_error "Install them with: apt-get install -y python3 git"
    exit 1
fi

# --- Summary ---
log_step "Preflight Summary"
log_info "OS:         Debian $DEBIAN_VERSION ($DEBIAN_CODENAME)"
log_info "Disk space: ${AVAILABLE_GB} GB free on /"
log_info "Ports:      $(if [[ "$PORTS_OK" == "true" ]]; then echo "80, 8000 available"; else echo "some in use (see warnings above)"; fi)"
log_info "Commands:   python3, git found"
log_info "Preflight checks passed."

exit 0
