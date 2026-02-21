#!/bin/bash
# BaluHost Install System - Configuration Management
# Loads and saves installer configuration to a secure file.

# Default config path
BALUHOST_CONFIG="${BALUHOST_CONFIG:-/etc/baluhost/install.conf}"

# ─── Default Values ──────────────────────────────────────────────────

: "${INSTALL_DIR:=/opt/baluhost}"
: "${BALUHOST_USER:=baluhost}"
: "${BALUHOST_GROUP:=baluhost}"
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
EOF

    chmod 600 "$BALUHOST_CONFIG"
    log_info "Config saved to $BALUHOST_CONFIG (mode 600)"
}
