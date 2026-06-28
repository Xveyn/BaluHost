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

# --- Create unprivileged plugin-sandbox user (Track B Phase 5a) ---
PLUGIN_USER="baluhost-plugin"
PLUGIN_GROUP="baluhost-plugin"

if group_exists "$PLUGIN_GROUP"; then
    log_info "Group '$PLUGIN_GROUP' already exists, skipping."
else
    groupadd --system "$PLUGIN_GROUP"
    log_info "Created system group '$PLUGIN_GROUP'."
fi

if user_exists "$PLUGIN_USER"; then
    log_info "User '$PLUGIN_USER' already exists, skipping."
else
    useradd --system --no-create-home --shell /usr/sbin/nologin \
            --gid "$PLUGIN_GROUP" "$PLUGIN_USER"
    log_info "Created unprivileged system user '$PLUGIN_USER' (nologin)."
fi

# Defensive: the plugin user must NOT be in privileged groups or the baluhost
# group (no NAS-storage / secret read). Remove if a prior run added them.
for grp in sudo wheel docker "$BALUHOST_GROUP"; do
    if id -nG "$PLUGIN_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$grp"; then
        gpasswd -d "$PLUGIN_USER" "$grp" || true
        log_warn "Removed '$PLUGIN_USER' from group '$grp' (isolation requirement)."
    fi
done

# Let the backend (baluhost) create a group-connectable UDS socket the worker
# can reach: add baluhost to the plugin group.
if id -nG "$BALUHOST_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$PLUGIN_GROUP"; then
    log_info "User '$BALUHOST_USER' already in group '$PLUGIN_GROUP'."
else
    usermod -aG "$PLUGIN_GROUP" "$BALUHOST_USER"
    log_info "Added '$BALUHOST_USER' to group '$PLUGIN_GROUP'."
fi

# --- Create directories ---
log_step "Creating Directories"

DIRECTORIES=(
    "$INSTALL_DIR"
    "$FRONTEND_STATIC_DIR"
    "/etc/baluhost"
    "/var/lib/baluhost/update-status"
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

chown root:"$BALUHOST_GROUP" /var/lib/baluhost/update-status
chmod 770 /var/lib/baluhost/update-status
log_info "Set ownership of /var/lib/baluhost/update-status to root:$BALUHOST_GROUP (mode 770)"

# External plugins dir: baluhost owns it; plugin user gets r-x (traverse + read
# code + connect the socket). No world access. (Track B Phase 5a)
if [[ ! -d /var/lib/baluhost/plugins ]]; then
    mkdir -p /var/lib/baluhost/plugins
    log_info "Created directory: /var/lib/baluhost/plugins"
fi
chown "$BALUHOST_USER":"$PLUGIN_GROUP" /var/lib/baluhost/plugins
chmod 750 /var/lib/baluhost/plugins
log_info "Set /var/lib/baluhost/plugins to $BALUHOST_USER:$PLUGIN_GROUP (mode 750)"

# --- Summary ---
log_step "User & Directory Summary"
log_info "User:    $BALUHOST_USER (uid=$(id -u "$BALUHOST_USER"))"
log_info "Group:   $BALUHOST_GROUP (gid=$(getent group "$BALUHOST_GROUP" | cut -d: -f3))"
log_info "Install: $INSTALL_DIR"
log_info "Static:  $FRONTEND_STATIC_DIR"
log_info "Config:  /etc/baluhost"
log_info "User & directory setup complete."

exit 0
