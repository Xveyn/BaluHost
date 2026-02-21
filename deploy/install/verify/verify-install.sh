#!/bin/bash
# BaluHost Install - Post-Installation Verification
# Checks that all services are running and reachable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

log_step "Post-Installation Verification"

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" &>/dev/null; then
        log_info "PASS: $label"
        ((PASS++))
    else
        log_error "FAIL: $label"
        ((FAIL++))
    fi
}

# ─── Systemd Services ────────────────────────────────────────────────
log_step "Systemd Services"
for svc in baluhost-backend baluhost-scheduler baluhost-webdav; do
    check "$svc is active" systemctl is-active --quiet "$svc"
done

# ─── Backend Health ───────────────────────────────────────────────────
log_step "Backend Health"
check "Backend API responds on :8000" curl -sf --max-time 5 http://localhost:8000/api/health

# ─── Nginx / Frontend ────────────────────────────────────────────────
log_step "Nginx & Frontend"
check "Nginx is active" systemctl is-active --quiet nginx
check "Frontend responds on :80" curl -sf --max-time 5 http://localhost/ -o /dev/null

# ─── PostgreSQL ───────────────────────────────────────────────────────
log_step "PostgreSQL"
check "PostgreSQL is active" systemctl is-active --quiet postgresql
check "PostgreSQL is ready" pg_isready -q

# ─── Environment File ────────────────────────────────────────────────
log_step "Configuration"
INSTALL_DIR="${INSTALL_DIR:-/opt/baluhost}"
ENV_FILE="$INSTALL_DIR/.env.production"

check ".env.production exists" test -f "$ENV_FILE"

if [[ -f "$ENV_FILE" ]]; then
    local_perms=$(stat -c %a "$ENV_FILE" 2>/dev/null || echo "unknown")
    if [[ "$local_perms" == "600" ]]; then
        log_info "PASS: .env.production has mode 600"
        ((PASS++))
    else
        log_error "FAIL: .env.production has mode $local_perms (expected 600)"
        ((FAIL++))
    fi
fi

# ─── Summary ─────────────────────────────────────────────────────────
echo ""
log_step "Verification Summary"
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""

if [[ $FAIL -gt 0 ]]; then
    log_warn "$FAIL check(s) failed. Review the output above."
    exit 1
else
    log_info "All checks passed."
    exit 0
fi
