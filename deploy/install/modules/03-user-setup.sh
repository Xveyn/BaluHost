#!/bin/bash
# BaluHost Install - Module 03: User & Directory Setup
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Main ───────────────────────────────────────────────────────────

log_step "User & Directory Setup"

require_root

# --- Create group ---
if group_exists "$BALUHOST_GROUP"; then
    log_info "Group '$BALUHOST_GROUP' already exists, skipping."
else
    groupadd --system "$BALUHOST_GROUP"
    log_info "Created system group '$BALUHOST_GROUP'."
fi

# --- Create user ---
if user_exists "$BALUHOST_USER"; then
    log_info "User '$BALUHOST_USER' already exists, skipping."
else
    useradd \
        --system \
        --create-home \
        --shell /bin/bash \
        --gid "$BALUHOST_GROUP" \
        "$BALUHOST_USER"
    log_info "Created system user '$BALUHOST_USER' with home directory."
fi

# --- Ensure user is in group (idempotent) ---
if id -nG "$BALUHOST_USER" 2>/dev/null | grep -qw "$BALUHOST_GROUP"; then
    log_info "User '$BALUHOST_USER' is already in group '$BALUHOST_GROUP'."
else
    usermod -aG "$BALUHOST_GROUP" "$BALUHOST_USER"
    log_info "Added user '$BALUHOST_USER' to group '$BALUHOST_GROUP'."
fi

# --- Create directories ---
log_step "Creating Directories"

DIRECTORIES=(
    "$INSTALL_DIR"
    "$FRONTEND_STATIC_DIR"
    "/etc/baluhost"
)

for dir in "${DIRECTORIES[@]}"; do
    if [[ -d "$dir" ]]; then
        log_info "Directory already exists: $dir"
    else
        mkdir -p "$dir"
        log_info "Created directory: $dir"
    fi
done

# --- Set ownership ---
log_step "Setting Ownership"

chown "$BALUHOST_USER":"$BALUHOST_GROUP" "$INSTALL_DIR"
log_info "Set ownership of $INSTALL_DIR to $BALUHOST_USER:$BALUHOST_GROUP"

chown "$BALUHOST_USER":"$BALUHOST_GROUP" "$FRONTEND_STATIC_DIR"
log_info "Set ownership of $FRONTEND_STATIC_DIR to $BALUHOST_USER:$BALUHOST_GROUP"

chown root:"$BALUHOST_GROUP" /etc/baluhost
chmod 750 /etc/baluhost
log_info "Set ownership of /etc/baluhost to root:$BALUHOST_GROUP (mode 750)"

# --- Summary ---
log_step "User & Directory Summary"
log_info "User:    $BALUHOST_USER (uid=$(id -u "$BALUHOST_USER"))"
log_info "Group:   $BALUHOST_GROUP (gid=$(getent group "$BALUHOST_GROUP" | cut -d: -f3))"
log_info "Install: $INSTALL_DIR"
log_info "Static:  $FRONTEND_STATIC_DIR"
log_info "Config:  /etc/baluhost"
log_info "User & directory setup complete."

exit 0
