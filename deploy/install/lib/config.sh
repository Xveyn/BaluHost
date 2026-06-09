#!/bin/bash
# BaluHost Install System - Configuration Management
# Loads and saves installer configuration to a secure file.

# Default config path
BALUHOST_CONFIG="${BALUHOST_CONFIG:-/etc/baluhost/install.conf}"

# ─── Default Values ──────────────────────────────────────────────────

: "${INSTALL_DIR:=/opt/baluhost}"
# Derive the service user/group from the install directory owner when not
# explicitly set (env or install.conf). Without this, a host installed under a
# different account (e.g. "sven") falls back to a non-existent "baluhost" user,
# and every in-app update fails at the first `sudo -u "$BALUHOST_USER" ...`.
_balu_dir_owner="$(stat -c '%U' "$INSTALL_DIR" 2>/dev/null || true)"
_balu_dir_group="$(stat -c '%G' "$INSTALL_DIR" 2>/dev/null || true)"
: "${BALUHOST_USER:=${_balu_dir_owner:-baluhost}}"
: "${BALUHOST_GROUP:=${_balu_dir_group:-baluhost}}"
unset _balu_dir_owner _balu_dir_group
: "${FRONTEND_STATIC_DIR:=/var/www/baluhost}"
: "${POSTGRES_DB:=baluhost}"
: "${POSTGRES_USER:=baluhost}"
: "${POSTGRES_PASSWORD:=}"
: "${ADMIN_USERNAME:=admin}"
: "${ADMIN_PASSWORD:=}"
: "${ADMIN_EMAIL:=admin@baluhost.local}"
: "${SECRET_KEY:=}"
: "${TOKEN_SECRET:=}"
: "${VPN_ENCRYPTION_KEY:=}"
: "${GIT_REPO:=https://github.com/Xveyn/BaluHost.git}"
: "${GIT_BRANCH:=main}"

# ─── Optional Feature Flags ──────────────────────────────────────────
# Each gates a feature in module 14-optional-features. Default false so an
# install without explicit opt-in behaves exactly as before (core NAS only).
: "${ENABLE_RAID:=false}"
: "${ENABLE_SMART:=false}"
: "${ENABLE_VPN:=false}"
: "${ENABLE_CLOUD:=false}"
: "${ENABLE_SAMBA:=false}"
: "${ENABLE_NFS:=false}"
: "${ENABLE_WSDD:=false}"
: "${ENABLE_MDNS:=false}"

# ─── Load Config ─────────────────────────────────────────────────────

load_config() {
    if [[ -f "$BALUHOST_CONFIG" ]]; then
        log_info "Loading config from $BALUHOST_CONFIG"
        # shellcheck source=/dev/null
        set -a
        . "$BALUHOST_CONFIG"
        set +a
    else
        log_info "No existing config found, using defaults."
    fi
}

# ─── Save Config ─────────────────────────────────────────────────────

save_config() {
    local config_dir
    config_dir=$(dirname "$BALUHOST_CONFIG")
    mkdir -p "$config_dir"

    cat > "$BALUHOST_CONFIG" <<EOF
# BaluHost Install Configuration
# Generated: $(date -Iseconds)
# Mode 600 — do not share this file.

INSTALL_DIR=${INSTALL_DIR}
BALUHOST_USER=${BALUHOST_USER}
BALUHOST_GROUP=${BALUHOST_GROUP}
FRONTEND_STATIC_DIR=${FRONTEND_STATIC_DIR}
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
ADMIN_USERNAME=${ADMIN_USERNAME}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ADMIN_EMAIL=${ADMIN_EMAIL}
SECRET_KEY=${SECRET_KEY}
TOKEN_SECRET=${TOKEN_SECRET}
VPN_ENCRYPTION_KEY=${VPN_ENCRYPTION_KEY}
GIT_REPO=${GIT_REPO}
GIT_BRANCH=${GIT_BRANCH}
ENABLE_RAID=${ENABLE_RAID}
ENABLE_SMART=${ENABLE_SMART}
ENABLE_VPN=${ENABLE_VPN}
ENABLE_CLOUD=${ENABLE_CLOUD}
ENABLE_SAMBA=${ENABLE_SAMBA}
ENABLE_NFS=${ENABLE_NFS}
ENABLE_WSDD=${ENABLE_WSDD}
ENABLE_MDNS=${ENABLE_MDNS}
EOF

    chmod 600 "$BALUHOST_CONFIG"
    log_info "Config saved to $BALUHOST_CONFIG (mode 600)"
}
