#!/bin/bash
# BaluHost Install - Module 08: Database Migration
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Variables ──────────────────────────────────────────────────────

BACKEND_DIR="$INSTALL_DIR/backend"
VENV_BIN="${VENV_BIN:-$INSTALL_DIR/backend/.venv/bin}"
ALEMBIC="$VENV_BIN/alembic"

# ─── Main ───────────────────────────────────────────────────────────

log_step "Database Migration"

require_root

# --- Verify prerequisites ---
if [[ ! -d "$BACKEND_DIR" ]]; then
    log_error "Backend directory not found: $BACKEND_DIR"
    exit 1
fi

if [[ ! -f "$ALEMBIC" ]]; then
    log_error "Alembic not found at $ALEMBIC"
    log_error "Ensure the Python virtual environment is set up (module 05)."
    exit 1
fi

if [[ ! -f "$BACKEND_DIR/alembic.ini" ]]; then
    log_error "alembic.ini not found in $BACKEND_DIR"
    exit 1
fi

# --- Run migrations ---
log_info "Running Alembic migrations..."

cd "$BACKEND_DIR"

# Export DATABASE_URL so Alembic can find it (via env.py)
if [[ -f "$INSTALL_DIR/.env.production" ]]; then
    set -a
    # shellcheck source=/dev/null
    . "$INSTALL_DIR/.env.production"
    set +a
fi

if sudo -u "$BALUHOST_USER" \
    DATABASE_URL="${DATABASE_URL:-}" \
    "$ALEMBIC" upgrade head 2>&1; then
    log_info "Alembic migrations completed successfully."
else
    log_error "Alembic migration failed."
    log_error ""
    log_error "Troubleshooting:"
    log_error "  1. Check DATABASE_URL is correct:"
    log_error "     postgresql://${POSTGRES_USER:-baluhost}:****@localhost:5432/${POSTGRES_DB:-baluhost}"
    log_error "  2. Verify PostgreSQL is running:"
    log_error "     systemctl status postgresql"
    log_error "  3. Test database connectivity:"
    log_error "     sudo -u ${BALUHOST_USER} psql -h localhost -U ${POSTGRES_USER:-baluhost} -d ${POSTGRES_DB:-baluhost}"
    log_error "  4. Check Alembic output above for specific errors."
    exit 1
fi

# --- Verify migration state ---
log_step "Migration Verification"

CURRENT_REV=$(sudo -u "$BALUHOST_USER" \
    DATABASE_URL="${DATABASE_URL:-}" \
    "$ALEMBIC" current 2>&1 | grep -oP '[a-f0-9]+(?= \(head\))' || echo "unknown")

if [[ "$CURRENT_REV" != "unknown" && -n "$CURRENT_REV" ]]; then
    log_info "Current migration revision: $CURRENT_REV (head)"
else
    log_warn "Could not determine current migration revision."
    log_warn "This may be normal for a fresh installation."
fi

# --- Summary ---
log_step "Migration Summary"
log_info "Backend dir: $BACKEND_DIR"
log_info "Alembic:     $ALEMBIC"
log_info "Revision:    ${CURRENT_REV:-unknown}"
log_info "Database migration complete."

exit 0
