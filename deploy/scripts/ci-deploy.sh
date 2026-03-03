#!/bin/bash
# BaluHost CI/CD Deploy Script
#
# Triggered by GitHub Actions on push to main, or manually.
# Performs: pre-checks → DB backup → git pull → backend update →
#           alembic migration → frontend build → service restart → health check.
#
# On failure: automatic rollback to previous commit + alembic downgrade.
#
# Usage:
#   ./ci-deploy.sh              # Normal deploy (git pull + build + restart)
#   ./ci-deploy.sh --rollback   # Manual rollback to previous deploy state

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────

INSTALL_DIR="${INSTALL_DIR:-/opt/baluhost}"
BACKUP_DIR="$INSTALL_DIR/backups/deploys"
DEPLOY_STATE="$INSTALL_DIR/.deploy-state"
LOG_DIR="/var/log/baluhost/deploys"
VENV_BIN="$INSTALL_DIR/backend/.venv/bin"
HEALTH_URL="http://localhost/api/system/health"
HEALTH_RETRIES=5
HEALTH_DELAY=3
DB_NAME="baluhost"
DB_USER="baluhost"
BACKUP_RETENTION=10

# Services to restart (order matters)
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

# ─── Logging ──────────────────────────────────────────────────────────

DEPLOY_START=$(date +%s)
DEPLOY_TIMESTAMP=$(date -Iseconds)

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}━━━ $* ━━━${NC}"; }

# ─── Deploy Log ───────────────────────────────────────────────────────

DEPLOY_LOG=""
deploy_log_init() {
    mkdir -p "$LOG_DIR"
    DEPLOY_LOG="$LOG_DIR/deploy-$(date +%Y%m%d-%H%M%S).json"
}

deploy_log_write() {
    local status="$1"
    local duration=$(( $(date +%s) - DEPLOY_START ))
    cat > "$DEPLOY_LOG" <<EOF
{
  "timestamp": "$DEPLOY_TIMESTAMP",
  "status": "$status",
  "duration_seconds": $duration,
  "commit_before": "${OLD_COMMIT:-unknown}",
  "commit_after": "${NEW_COMMIT:-unknown}",
  "db_revision_before": "${OLD_DB_REV:-unknown}",
  "db_revision_after": "${NEW_DB_REV:-unknown}",
  "backup_file": "${BACKUP_FILE:-none}",
  "deployed_by": "${GITHUB_ACTOR:-manual}"
}
EOF
    log_info "Deploy log: $DEPLOY_LOG"
}

# ─── State Management ─────────────────────────────────────────────────

save_deploy_state() {
    cat > "$DEPLOY_STATE" <<EOF
{
  "current_commit": "${NEW_COMMIT:-unknown}",
  "previous_commit": "${OLD_COMMIT:-unknown}",
  "deployed_at": "$DEPLOY_TIMESTAMP",
  "deployed_by": "${GITHUB_ACTOR:-manual}",
  "db_revision_before": "${OLD_DB_REV:-unknown}",
  "db_revision_after": "${NEW_DB_REV:-unknown}",
  "backup_file": "${BACKUP_FILE:-none}"
}
EOF
    log_info "Deploy state saved to $DEPLOY_STATE"
}

load_deploy_state() {
    if [[ -f "$DEPLOY_STATE" ]]; then
        # Parse JSON with python (available in venv)
        PREV_COMMIT=$(python3 -c "import json; print(json.load(open('$DEPLOY_STATE'))['current_commit'])" 2>/dev/null || echo "unknown")
        PREV_DB_REV=$(python3 -c "import json; print(json.load(open('$DEPLOY_STATE'))['db_revision_after'])" 2>/dev/null || echo "unknown")
        PREV_BACKUP=$(python3 -c "import json; print(json.load(open('$DEPLOY_STATE'))['backup_file'])" 2>/dev/null || echo "none")
        log_info "Loaded previous deploy state: commit=$PREV_COMMIT, db_rev=$PREV_DB_REV"
    else
        log_warn "No previous deploy state found."
        PREV_COMMIT="unknown"
        PREV_DB_REV="unknown"
        PREV_BACKUP="none"
    fi
}

# ─── Health Check ─────────────────────────────────────────────────────

health_check() {
    log_step "Health Check"
    for i in $(seq 1 $HEALTH_RETRIES); do
        if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
            log_info "Health check passed (attempt $i/$HEALTH_RETRIES)"
            return 0
        fi
        log_warn "Health check failed (attempt $i/$HEALTH_RETRIES), waiting ${HEALTH_DELAY}s..."
        sleep "$HEALTH_DELAY"
    done
    log_error "Health check failed after $HEALTH_RETRIES attempts"
    return 1
}

# ─── Service Management ───────────────────────────────────────────────

restart_services() {
    log_step "Restarting Services"
    for svc in "${SERVICES[@]}"; do
        log_info "Restarting $svc..."
        sudo systemctl restart "$svc"
    done
    log_info "Reloading nginx..."
    sudo systemctl reload nginx
    log_info "All services restarted."
}

# ─── Rollback ─────────────────────────────────────────────────────────

rollback() {
    log_step "ROLLBACK"
    log_error "Deploy failed — initiating rollback"

    load_deploy_state

    if [[ "$PREV_COMMIT" == "unknown" ]]; then
        log_error "No previous commit to rollback to. Manual intervention required."
        log_error "Backups are in: $BACKUP_DIR"
        deploy_log_write "failed_no_rollback"
        exit 1
    fi

    log_info "Rolling back to commit: $PREV_COMMIT"

    cd "$INSTALL_DIR"
    git checkout "$PREV_COMMIT" 2>/dev/null || {
        log_error "git checkout $PREV_COMMIT failed"
        deploy_log_write "rollback_failed"
        exit 1
    }

    # Reinstall backend dependencies
    cd "$INSTALL_DIR/backend"
    "$VENV_BIN/pip" install -q -e ".[scheduler]"

    # Downgrade DB if migration ran
    if [[ -n "${OLD_DB_REV:-}" && "$OLD_DB_REV" != "unknown" ]]; then
        log_info "Downgrading database to revision: $OLD_DB_REV"
        "$VENV_BIN/alembic" downgrade "$OLD_DB_REV" || {
            log_error "Alembic downgrade failed. Manual DB restore may be needed."
            log_error "Backup file: $BACKUP_DIR/$BACKUP_FILE"
        }
    fi

    restart_services

    if health_check; then
        log_info "Rollback successful."
        deploy_log_write "rolled_back"
    else
        log_error "CRITICAL: Rollback health check also failed!"
        log_error "Manual intervention required."
        log_error "Database backup: $BACKUP_DIR/$BACKUP_FILE"
        log_error "Use deploy/scripts/db-restore.sh for database recovery."
        deploy_log_write "rollback_failed"
        exit 1
    fi
}

# ─── Manual Rollback Mode ────────────────────────────────────────────

if [[ "${1:-}" == "--rollback" ]]; then
    deploy_log_init
    rollback
    exit $?
fi

# ═══════════════════════════════════════════════════════════════════════
#  MAIN DEPLOY FLOW
# ═══════════════════════════════════════════════════════════════════════

deploy_log_init

log_step "BaluHost Deploy"
log_info "Timestamp: $DEPLOY_TIMESTAMP"
log_info "Install dir: $INSTALL_DIR"

# ─── 1. Pre-Deploy Checks ────────────────────────────────────────────

log_step "Pre-Deploy Checks"

if [[ ! -d "$INSTALL_DIR" ]]; then
    log_error "Install directory not found: $INSTALL_DIR"
    exit 1
fi

if [[ ! -f "$INSTALL_DIR/.env.production" ]]; then
    log_error ".env.production not found in $INSTALL_DIR"
    exit 1
fi

if ! grep -q "DATABASE_URL" "$INSTALL_DIR/.env.production"; then
    log_error "DATABASE_URL not found in .env.production"
    exit 1
fi

if ! pg_isready -h localhost -p 5432 -q; then
    log_error "PostgreSQL is not ready (pg_isready failed)"
    exit 1
fi

cd "$INSTALL_DIR"
OLD_COMMIT=$(git rev-parse HEAD)
log_info "Current commit: $OLD_COMMIT"

# Get current alembic revision
cd "$INSTALL_DIR/backend"
OLD_DB_REV=$("$VENV_BIN/alembic" current 2>/dev/null | head -1 | awk '{print $1}' || echo "unknown")
log_info "Current DB revision: $OLD_DB_REV"

log_info "Pre-deploy checks passed."

# ─── 2. Database Backup ──────────────────────────────────────────────

log_step "Database Backup"

mkdir -p "$BACKUP_DIR"
BACKUP_FILE="pre-deploy-$(date +%Y%m%d-%H%M%S).sql.gz"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_FILE"

log_info "Creating backup: $BACKUP_PATH"
pg_dump -U "$DB_USER" -h localhost "$DB_NAME" | gzip > "$BACKUP_PATH"

# Verify backup
if ! gzip -t "$BACKUP_PATH" 2>/dev/null; then
    log_error "Backup file is corrupt: $BACKUP_PATH"
    deploy_log_write "failed_backup_corrupt"
    exit 1
fi

BACKUP_SIZE=$(stat -c%s "$BACKUP_PATH" 2>/dev/null || stat -f%z "$BACKUP_PATH" 2>/dev/null || echo "0")
if [[ "$BACKUP_SIZE" -eq 0 ]]; then
    log_error "Backup file is empty. Aborting deploy."
    rm -f "$BACKUP_PATH"
    deploy_log_write "failed_backup_empty"
    exit 1
fi

log_info "Backup OK: $BACKUP_FILE ($(du -h "$BACKUP_PATH" | cut -f1))"

# Rotate old backups (keep last $BACKUP_RETENTION)
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "pre-deploy-*.sql.gz" -type f | wc -l)
if [[ "$BACKUP_COUNT" -gt "$BACKUP_RETENTION" ]]; then
    DELETE_COUNT=$((BACKUP_COUNT - BACKUP_RETENTION))
    find "$BACKUP_DIR" -name "pre-deploy-*.sql.gz" -type f -printf '%T@ %p\n' | \
        sort -n | head -n "$DELETE_COUNT" | awk '{print $2}' | xargs rm -f
    log_info "Rotated $DELETE_COUNT old backup(s), keeping $BACKUP_RETENTION."
fi

# ─── 3. Git Update ───────────────────────────────────────────────────

log_step "Git Update"

cd "$INSTALL_DIR"
git fetch --all --prune
git checkout main
git pull origin main

NEW_COMMIT=$(git rev-parse HEAD)
log_info "Updated: $OLD_COMMIT -> $NEW_COMMIT"

if [[ "$OLD_COMMIT" == "$NEW_COMMIT" ]]; then
    log_info "No new commits. Continuing with rebuild anyway."
fi

# ─── 4. Backend Update ───────────────────────────────────────────────

log_step "Backend Update"

cd "$INSTALL_DIR/backend"
"$VENV_BIN/pip" install -q -e ".[scheduler]"
log_info "Backend dependencies updated."

# ─── 5. Database Migration ───────────────────────────────────────────

log_step "Database Migration"

cd "$INSTALL_DIR/backend"
log_info "Running alembic upgrade head..."
if ! "$VENV_BIN/alembic" upgrade head; then
    log_error "Alembic migration failed!"
    log_info "Attempting downgrade to: $OLD_DB_REV"
    "$VENV_BIN/alembic" downgrade "$OLD_DB_REV" || true

    log_info "Reverting git to: $OLD_COMMIT"
    cd "$INSTALL_DIR"
    git checkout "$OLD_COMMIT"

    deploy_log_write "failed_migration"
    exit 1
fi

NEW_DB_REV=$("$VENV_BIN/alembic" current 2>/dev/null | head -1 | awk '{print $1}' || echo "unknown")
log_info "Migration: $OLD_DB_REV -> $NEW_DB_REV"

# ─── 6. Frontend Build ───────────────────────────────────────────────

log_step "Frontend Build"

cd "$INSTALL_DIR/client"
npm ci --omit=dev
npm run build

log_info "Frontend build complete."

# ─── 7. Service Restart ──────────────────────────────────────────────

restart_services

# ─── 8. Health Check ─────────────────────────────────────────────────

if health_check; then
    save_deploy_state
    deploy_log_write "success"

    DURATION=$(( $(date +%s) - DEPLOY_START ))
    log_step "Deploy Complete"
    log_info "Commit: $NEW_COMMIT"
    log_info "DB: $OLD_DB_REV -> $NEW_DB_REV"
    log_info "Duration: ${DURATION}s"
    log_info "Backup: $BACKUP_FILE"
else
    log_error "Health check failed after deploy!"
    rollback
fi
