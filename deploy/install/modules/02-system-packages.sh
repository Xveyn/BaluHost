#!/bin/bash
# BaluHost Install - Module 02: System Packages
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Package List ───────────────────────────────────────────────────

PACKAGES=(
    postgresql
    postgresql-contrib
    nginx
    python3-venv
    python3-dev
    python3-pip
    nodejs
    npm
    git
    build-essential
    curl
    lsb-release
)

# ─── Main ───────────────────────────────────────────────────────────

log_step "System Packages"

require_root

# --- Update package index ---
log_info "Updating package index..."
apt-get update -qq

# --- Install packages ---
log_info "Installing packages: ${PACKAGES[*]}"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${PACKAGES[@]}"
log_info "Package installation complete."

# --- Verify critical services ---
log_step "Verifying Services"

for service in postgresql nginx; do
    if systemctl is-enabled "$service" &>/dev/null; then
        log_info "$service is enabled"
    else
        log_warn "$service is installed but not enabled. Enabling..."
        systemctl enable "$service"
    fi
done

# --- Log installed versions ---
log_step "Installed Versions"

declare -A VERSION_CMDS=(
    [postgresql]="psql --version"
    [nginx]="nginx -v 2>&1"
    [python3]="python3 --version"
    [node]="node --version"
    [npm]="npm --version"
    [git]="git --version"
    [gcc]="gcc --version | head -1"
    [curl]="curl --version | head -1"
)

for name in postgresql nginx python3 node npm git gcc curl; do
    CMD="${VERSION_CMDS[$name]}"
    if VERSION=$(eval "$CMD" 2>&1 | head -1); then
        log_info "$name: $VERSION"
    else
        log_warn "Could not determine version for $name"
    fi
done

log_info "System packages module complete."

exit 0
