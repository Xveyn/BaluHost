#!/bin/bash
# BaluHost Database Restore Script
#
# Restores a PostgreSQL backup created by ci-deploy.sh or db-backup-daily.sh.
# Stops all services, drops and recreates the database, restores from backup,
# then restarts services.
#
# Usage:
#   ./db-restore.sh <backup-file.sql.gz>
#   ./db-restore.sh /opt/baluhost/backups/deploys/pre-deploy-20260302-143000.sql.gz

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────

INSTALL_DIR="${INSTALL_DIR:-/opt/baluhost}"
VENV_BIN="$INSTALL_DIR/backend/.venv/bin"
DB_NAME="baluhost"
DB_USER="baluhost"

# Extract PGPASSWORD from DATABASE_URL in .env.production
load_db_password() {
    local env_file="$INSTALL_DIR/.env.production"
    if [[ -f "$env_file" ]]; then
        local db_url
        db_url=$(grep -m1 '^DATABASE_URL=' "$env_file" | cut -d= -f2-)
        export PGPASSWORD
        PGPASSWORD=$(echo "$db_url" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    fi
    if [[ -z "${PGPASSWORD:-}" ]]; then
        log_warn "Could not extract database password. pg_dump/psql may prompt for password."
    fi
}
load_db_password

SERVICES=(
    baluhost-backend
    baluhost-scheduler
    baluhost-monitoring
    baluhost-webdav
)

# ─── Colors ───────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}━━━ $* ━━━${NC}"; }

# ─── Argument Validation ──────────────────────────────────────────────

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <backup-file.sql.gz>"
    echo ""
    echo "Available backups:"
    echo "  Deploy backups:  $INSTALL_DIR/backups/deploys/"
    echo "  Daily backups:   $INSTALL_DIR/backups/daily/"
    echo ""
    if [[ -d "$INSTALL_DIR/backups" ]]; then
        find "$INSTALL_DIR/backups" -name "*.sql.gz" -type f -printf '  %T+ %p\n' | sort -r | head -10
    fi
    exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "$BACKUP_FILE" ]]; then
    log_error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Verify backup integrity
log_step "Verifying Backup"
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    log_error "Backup file is corrupt: $BACKUP_FILE"
    exit 1
fi
log_info "Backup integrity OK: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# ─── Confirmation ─────────────────────────────────────────────────────

echo ""
echo -e "${YELLOW}WARNING: This will:${NC}"
echo "  1. Stop all BaluHost services"
echo "  2. Drop the '$DB_NAME' database"
echo "  3. Restore from: $BACKUP_FILE"
echo "  4. Restart all services"
echo ""
read -p "Continue? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    log_info "Aborted."
    exit 0
fi

# ─── 1. Stop Services ────────────────────────────────────────────────

log_step "Stopping Services"
for svc in "${SERVICES[@]}"; do
    if systemctl is-active "$svc" &>/dev/null; then
        sudo systemctl stop "$svc"
        log_info "Stopped $svc"
    else
        log_info "$svc was not running"
    fi
done

# ─── 2. Drop and Recreate Database ───────────────────────────────────

log_step "Restoring Database"

log_info "Dropping database: $DB_NAME"
sudo -u postgres dropdb --if-exists "$DB_NAME"

log_info "Creating database: $DB_NAME (owner: $DB_USER)"
sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"

log_info "Restoring from backup..."
gunzip -c "$BACKUP_FILE" | sudo -u postgres psql -q "$DB_NAME"
log_info "Database restored."

# ─── 3. Verify Alembic Revision ──────────────────────────────────────

log_step "Post-Restore Verification"

cd "$INSTALL_DIR/backend"
CURRENT_REV=$("$VENV_BIN/alembic" current 2>/dev/null | head -1 | awk '{print $1}' || echo "unknown")
log_info "Alembic revision after restore: $CURRENT_REV"

# Count key tables
USER_COUNT=$(sudo -u postgres psql -t -A -d "$DB_NAME" -c "SELECT count(*) FROM users;" 2>/dev/null || echo "?")
log_info "Users in database: $USER_COUNT"

# ─── 4. Restart Services ─────────────────────────────────────────────

log_step "Starting Services"
for svc in "${SERVICES[@]}"; do
    sudo systemctl start "$svc"
    log_info "Started $svc"
done

# ─── 5. Health Check ─────────────────────────────────────────────────

log_step "Health Check"
sleep 3
if curl -sf http://localhost/api/system/health > /dev/null 2>&1; then
    log_info "Health check passed."
else
    log_warn "Health check failed. Services may still be starting."
    log_warn "Check: sudo systemctl status baluhost-backend"
fi

log_step "Restore Complete"
log_info "Restored from: $BACKUP_FILE"
log_info "DB revision: $CURRENT_REV"
log_info "Users: $USER_COUNT"
