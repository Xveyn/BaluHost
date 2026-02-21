#!/bin/bash
# BaluHost Install - Module 11: Nginx Configuration
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Variables ──────────────────────────────────────────────────────

TEMPLATE="$SCRIPT_DIR/templates/baluhost-nginx-http.conf"
SITES_AVAILABLE="/etc/nginx/sites-available/baluhost"
SITES_ENABLED="/etc/nginx/sites-enabled/baluhost"
DEFAULT_SITE="/etc/nginx/sites-enabled/default"
SERVER_NAME="${SERVER_NAME:-baluhost.local localhost _}"

# ─── Main ───────────────────────────────────────────────────────────

log_step "Nginx Configuration"

require_root

# --- Verify nginx is installed ---
if ! command -v nginx &>/dev/null; then
    log_error "Nginx is not installed. Install it first (module 02)."
    exit 1
fi

NGINX_VERSION=$(nginx -v 2>&1 | awk -F'/' '{print $2}')
log_info "Nginx version: $NGINX_VERSION"

# --- Verify template ---
if [[ ! -f "$TEMPLATE" ]]; then
    log_error "Nginx template not found: $TEMPLATE"
    exit 1
fi

# --- Generate nginx config ---
log_step "Generating Nginx Config"

log_info "Server name: $SERVER_NAME"
log_info "Frontend root: $FRONTEND_STATIC_DIR"

process_template "$TEMPLATE" "$SITES_AVAILABLE" \
    "FRONTEND_ROOT=$FRONTEND_STATIC_DIR" \
    "SERVER_NAME=$SERVER_NAME"

log_info "Config written to $SITES_AVAILABLE."

# --- Create symlink ---
if [[ -L "$SITES_ENABLED" ]]; then
    log_info "Symlink $SITES_ENABLED already exists, updating."
    rm -f "$SITES_ENABLED"
fi

ln -s "$SITES_AVAILABLE" "$SITES_ENABLED"
log_info "Symlink created: $SITES_ENABLED -> $SITES_AVAILABLE"

# --- Remove default site ---
if [[ -e "$DEFAULT_SITE" ]]; then
    rm -f "$DEFAULT_SITE"
    log_info "Removed default Nginx site."
else
    log_info "Default Nginx site not present, skipping removal."
fi

# --- Test nginx config ---
log_step "Testing Nginx Configuration"

if nginx -t 2>&1; then
    log_info "Nginx configuration test passed."
else
    log_error "Nginx configuration test FAILED."
    log_error "Check the config file: $SITES_AVAILABLE"
    log_error "Test command: nginx -t"
    exit 1
fi

# --- Reload/restart nginx ---
log_step "Reloading Nginx"

if systemctl is-active nginx &>/dev/null; then
    systemctl reload nginx
    log_info "Nginx reloaded."
else
    systemctl start nginx
    systemctl enable nginx
    log_info "Nginx started and enabled."
fi

# --- Summary ---
log_step "Nginx Summary"
log_info "Config:      $SITES_AVAILABLE"
log_info "Enabled:     $SITES_ENABLED"
log_info "Server name: $SERVER_NAME"
log_info "Frontend:    $FRONTEND_STATIC_DIR"
log_info "Status:      $(systemctl is-active nginx 2>/dev/null || echo 'unknown')"
log_info "Nginx configuration complete."

exit 0
