#!/bin/bash
# BaluHost Install - Module 12: Start Services
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Variables ──────────────────────────────────────────────────────

SERVICES=(
    "baluhost-backend"
    "baluhost-scheduler"
    "baluhost-webdav"
)
HEALTH_URL="http://localhost:8000/api/health"
HEALTH_TIMEOUT=10

# ─── Main ───────────────────────────────────────────────────────────

log_step "Starting BaluHost Services"

require_root

# --- Start all services ---
for service in "${SERVICES[@]}"; do
    if systemctl is-active "$service" &>/dev/null; then
        log_info "$service is already running, restarting..."
        systemctl restart "$service"
    else
        log_info "Starting $service..."
        systemctl start "$service"
    fi
done

log_info "All services started."

# --- Wait for backend to be ready ---
log_step "Health Check"

log_info "Waiting for backend to become ready (timeout: ${HEALTH_TIMEOUT}s)..."

READY=false
for i in $(seq 1 "$HEALTH_TIMEOUT"); do
    if curl -sf --max-time 2 "$HEALTH_URL" &>/dev/null; then
        READY=true
        log_info "Backend is healthy after ${i}s."
        break
    fi
    sleep 1
done

if [[ "$READY" != "true" ]]; then
    log_error "Backend health check failed after ${HEALTH_TIMEOUT}s."
    log_error ""
    log_error "Troubleshooting:"
    log_error "  1. Check backend logs:"
    log_error "     sudo journalctl -u baluhost-backend -n 50 --no-pager"
    log_error "  2. Check if port 8000 is listening:"
    log_error "     ss -tlnp | grep :8000"
    log_error "  3. Check service status:"
    log_error "     sudo systemctl status baluhost-backend"
    log_error "  4. Check environment file:"
    log_error "     ls -la $INSTALL_DIR/.env.production"
    exit 1
fi

# --- Report service status ---
log_step "Service Status"

ALL_OK=true
for service in "${SERVICES[@]}"; do
    STATUS=$(systemctl is-active "$service" 2>/dev/null || echo "inactive")
    if [[ "$STATUS" == "active" ]]; then
        log_info "$service: active (running)"
    else
        log_warn "$service: $STATUS"
        ALL_OK=false
    fi
done

# Also report nginx status
NGINX_STATUS=$(systemctl is-active nginx 2>/dev/null || echo "inactive")
log_info "nginx: $NGINX_STATUS"

if [[ "$ALL_OK" != "true" ]]; then
    log_warn "One or more services are not running. Check logs with:"
    log_warn "  sudo journalctl -u <service-name> -n 50 --no-pager"
fi

# --- Summary ---
log_step "Startup Summary"
log_info "Backend:   $(systemctl is-active baluhost-backend 2>/dev/null || echo 'unknown')"
log_info "Scheduler: $(systemctl is-active baluhost-scheduler 2>/dev/null || echo 'unknown')"
log_info "WebDAV:    $(systemctl is-active baluhost-webdav 2>/dev/null || echo 'unknown')"
log_info "Nginx:     $NGINX_STATUS"
log_info "Health:    $HEALTH_URL -> OK"
log_info ""
log_info "BaluHost is ready!"
log_info "  Web UI:  http://localhost"
log_info "  API:     http://localhost:8000/docs"
log_info "Service startup complete."

exit 0
