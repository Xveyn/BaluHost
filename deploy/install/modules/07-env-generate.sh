#!/bin/bash
# BaluHost Install - Module 07: Environment File Generation
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Main ───────────────────────────────────────────────────────────

log_step "Environment File Generation"

require_root

ENV_FILE="$INSTALL_DIR/.env.production"
TEMPLATE="$SCRIPT_DIR/templates/env.production"

# --- Generate secrets if not already set ---
log_step "Generating Secrets"

if [[ -z "${SECRET_KEY:-}" ]]; then
    SECRET_KEY=$(generate_secret)
    export SECRET_KEY
    log_info "Generated SECRET_KEY."
else
    log_info "SECRET_KEY already set, reusing."
fi

if [[ -z "${TOKEN_SECRET:-}" ]]; then
    TOKEN_SECRET=$(generate_secret)
    export TOKEN_SECRET
    log_info "Generated TOKEN_SECRET."
else
    log_info "TOKEN_SECRET already set, reusing."
fi

if [[ -z "${VPN_ENCRYPTION_KEY:-}" ]]; then
    VPN_ENCRYPTION_KEY=$(generate_fernet_key)
    export VPN_ENCRYPTION_KEY
    log_info "Generated VPN_ENCRYPTION_KEY."
else
    log_info "VPN_ENCRYPTION_KEY already set, reusing."
fi

# --- Build DATABASE_URL ---
if [[ -z "${DATABASE_URL:-}" ]]; then
    if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
        log_error "POSTGRES_PASSWORD is not set. Run module 06 (PostgreSQL) first."
        exit 1
    fi
    DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}"
    export DATABASE_URL
    log_info "Built DATABASE_URL from PostgreSQL configuration."
else
    log_info "DATABASE_URL already set, reusing."
fi

# --- Render template ---
log_step "Writing Environment File"

if [[ ! -f "$TEMPLATE" ]]; then
    log_error "Template not found: $TEMPLATE"
    exit 1
fi

process_template "$TEMPLATE" "$ENV_FILE" \
    "SECRET_KEY=$SECRET_KEY" \
    "TOKEN_SECRET=$TOKEN_SECRET" \
    "VPN_ENCRYPTION_KEY=$VPN_ENCRYPTION_KEY" \
    "DATABASE_URL=$DATABASE_URL" \
    "ADMIN_USERNAME=$ADMIN_USERNAME" \
    "ADMIN_PASSWORD=$ADMIN_PASSWORD" \
    "ADMIN_EMAIL=$ADMIN_EMAIL"

log_info "Environment file written to $ENV_FILE."

# --- Set secure permissions ---
chmod 600 "$ENV_FILE"
chown "$BALUHOST_USER":"$BALUHOST_GROUP" "$ENV_FILE"
log_info "Permissions set to 600, owned by $BALUHOST_USER:$BALUHOST_GROUP."

# --- Verify ---
if [[ ! -s "$ENV_FILE" ]]; then
    log_error "Environment file is empty or missing: $ENV_FILE"
    exit 1
fi

# Check that no unresolved placeholders remain
if grep -q '@@.*@@' "$ENV_FILE"; then
    UNRESOLVED=$(grep -o '@@[A-Z_]*@@' "$ENV_FILE" | sort -u | tr '\n' ' ')
    log_error "Unresolved placeholders in $ENV_FILE: $UNRESOLVED"
    exit 1
fi

# --- Summary ---
log_step "Environment Summary"
log_info "File:       $ENV_FILE"
log_info "Owner:      $BALUHOST_USER:$BALUHOST_GROUP"
log_info "Mode:       600"
log_info "Secrets:    generated (values not logged)"
log_info "DB URL:     postgresql://${POSTGRES_USER}:****@localhost:5432/${POSTGRES_DB}"
log_info "Environment file generation complete."

exit 0
