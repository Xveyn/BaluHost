#!/bin/bash
# BaluHost Production Migration Script
#
# One-time migration from /home/sven/projects/BaluHost to /opt/baluhost.
# PostgreSQL data is NOT moved (stays in /var/lib/postgresql/).
# Only application code, configs, and frontend build are migrated.
#
# Usage:
#   sudo ./migrate-to-opt.sh
#
# Prerequisites:
#   - PostgreSQL running with baluhost database
#   - All BaluHost services running from /home/sven/projects/BaluHost

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────

SOURCE_DIR="/home/sven/projects/BaluHost"
TARGET_DIR="/opt/baluhost"
OWNER="sven"
GROUP="sven"
DB_NAME="baluhost"
DB_USER="baluhost"
BACKUP_DIR="$TARGET_DIR/backups/migration"

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

# ─── Preflight Checks ────────────────────────────────────────────────

log_step "Preflight Checks"

if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (sudo)."
    exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
    log_error "Source directory not found: $SOURCE_DIR"
    exit 1
fi

if [[ -d "$TARGET_DIR" && -f "$TARGET_DIR/backend/app/main.py" ]]; then
    log_warn "Target directory already exists: $TARGET_DIR"
    read -p "Overwrite? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        log_info "Aborted."
        exit 0
    fi
fi

if ! pg_isready -h localhost -p 5432 -q; then
    log_error "PostgreSQL is not ready."
    exit 1
fi

# Document current state
log_step "Documenting Current State"

cd "$SOURCE_DIR/backend"
VENV_BIN="$SOURCE_DIR/backend/.venv/bin"
CURRENT_ALEMBIC=$("$VENV_BIN/alembic" current 2>/dev/null | head -1 | awk '{print $1}' || echo "unknown")
log_info "Current Alembic revision: $CURRENT_ALEMBIC"

USER_COUNT=$(sudo -u postgres psql -t -A -d "$DB_NAME" -c "SELECT count(*) FROM users;" 2>/dev/null || echo "?")
AUDIT_COUNT=$(sudo -u postgres psql -t -A -d "$DB_NAME" -c "SELECT count(*) FROM audit_logs;" 2>/dev/null || echo "?")
log_info "Users: $USER_COUNT, Audit logs: $AUDIT_COUNT"

# ─── 1. Database Backup ──────────────────────────────────────────────

log_step "Database Backup (Safety Net)"

mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/pre-migration-$(date +%Y%m%d-%H%M%S).sql.gz"

log_info "Creating full database backup..."
sudo -u postgres pg_dump "$DB_NAME" | gzip > "$BACKUP_FILE"

if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    log_error "Backup file corrupt! Aborting."
    exit 1
fi

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log_info "Backup OK: $BACKUP_FILE ($BACKUP_SIZE)"

# ─── 2. Stop All Services ────────────────────────────────────────────

log_step "Stopping Services"

for svc in baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav; do
    if systemctl is-active "$svc" &>/dev/null; then
        systemctl stop "$svc"
        log_info "Stopped $svc"
    else
        log_info "$svc was not running (systemd)"
    fi
done

# Kill any manually started uvicorn processes (legacy from pre-systemd setup)
if pgrep -f "uvicorn app.main:app" &>/dev/null; then
    log_warn "Found manually started uvicorn process — killing it"
    pkill -f "uvicorn app.main:app" || true
    sleep 2
    if pgrep -f "uvicorn app.main:app" &>/dev/null; then
        pkill -9 -f "uvicorn app.main:app" || true
    fi
    log_info "Manually started uvicorn stopped."
fi

# ─── 3. Rsync Application Code ───────────────────────────────────────

log_step "Copying Application Code"

mkdir -p "$TARGET_DIR"

log_info "rsync $SOURCE_DIR/ -> $TARGET_DIR/"
rsync -a --delete \
    --exclude='dev-storage/' \
    --exclude='node_modules/' \
    --exclude='__pycache__/' \
    --exclude='.venv/' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache/' \
    --exclude='client/dist/' \
    --exclude='backend/baluhost.db' \
    --exclude='backend/baluhost.db-journal' \
    "$SOURCE_DIR/" "$TARGET_DIR/"

chown -R "$OWNER:$GROUP" "$TARGET_DIR"
log_info "Application code copied."

# ─── 4. Copy .env.production ─────────────────────────────────────────

log_step "Environment Configuration"

if [[ -f "$SOURCE_DIR/.env.production" ]]; then
    cp "$SOURCE_DIR/.env.production" "$TARGET_DIR/.env.production"
    chown "$OWNER:$GROUP" "$TARGET_DIR/.env.production"
    chmod 600 "$TARGET_DIR/.env.production"
    log_info "Copied .env.production (DATABASE_URL unchanged — PostgreSQL stays in place)"
else
    log_error ".env.production not found in $SOURCE_DIR"
    log_error "You must create $TARGET_DIR/.env.production manually."
fi

# ─── 5. Create Python Virtual Environment ─────────────────────────────

log_step "Python Virtual Environment"

cd "$TARGET_DIR/backend"
sudo -u "$OWNER" python3 -m venv .venv
sudo -u "$OWNER" .venv/bin/pip install -q --upgrade pip
sudo -u "$OWNER" .venv/bin/pip install -q -e ".[scheduler]"
log_info "Virtual environment created and dependencies installed."

# ─── 6. Frontend Build ────────────────────────────────────────────────

log_step "Frontend Build"

cd "$TARGET_DIR/client"
sudo -u "$OWNER" npm ci
sudo -u "$OWNER" npm run build
log_info "Frontend built: $TARGET_DIR/client/dist/"

# ─── 7. Install Systemd Templates ────────────────────────────────────

log_step "Systemd Service Templates"

TEMPLATE_DIR="$TARGET_DIR/deploy/install/templates"
SYSTEMD_DIR="/etc/systemd/system"
VENV_BIN_NEW="$TARGET_DIR/backend/.venv/bin"

for service in baluhost-backend baluhost-scheduler baluhost-webdav baluhost-monitoring; do
    TEMPLATE="$TEMPLATE_DIR/${service}.service"
    if [[ -f "$TEMPLATE" ]]; then
        sed -e "s|@@BALUHOST_USER@@|$OWNER|g" \
            -e "s|@@INSTALL_DIR@@|$TARGET_DIR|g" \
            -e "s|@@VENV_BIN@@|$VENV_BIN_NEW|g" \
            "$TEMPLATE" > "$SYSTEMD_DIR/${service}.service"
        chmod 644 "$SYSTEMD_DIR/${service}.service"
        log_info "Installed $service.service"
    else
        log_warn "Template not found: $TEMPLATE"
    fi
done

# Install sudoers rules
for sudoers_tmpl in baluhost-update-sudoers baluhost-deploy-sudoers; do
    TMPL="$TEMPLATE_DIR/$sudoers_tmpl"
    OUTPUT="/etc/sudoers.d/${sudoers_tmpl}"
    if [[ -f "$TMPL" ]]; then
        sed -e "s|@@BALUHOST_USER@@|$OWNER|g" \
            -e "s|@@INSTALL_DIR@@|$TARGET_DIR|g" \
            "$TMPL" > "$OUTPUT"
        chmod 440 "$OUTPUT"
        if visudo -cf "$OUTPUT" &>/dev/null; then
            log_info "Installed $OUTPUT"
        else
            log_error "Sudoers syntax invalid: $OUTPUT — removing"
            rm -f "$OUTPUT"
        fi
    fi
done

systemctl daemon-reload
log_info "systemd reloaded."

# ─── 8. Update Nginx Configuration ───────────────────────────────────

log_step "Nginx Configuration"

NGINX_TEMPLATE="$TEMPLATE_DIR/baluhost-nginx-http.conf"
NGINX_CONF="/etc/nginx/sites-available/baluhost"

if [[ -f "$NGINX_TEMPLATE" ]]; then
    FRONTEND_ROOT="$TARGET_DIR/client/dist"
    sed -e "s|@@FRONTEND_ROOT@@|$FRONTEND_ROOT|g" \
        -e "s|@@SERVER_NAME@@|baluhost.local localhost _|g" \
        "$NGINX_TEMPLATE" > "$NGINX_CONF"

    # Ensure symlink
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/baluhost

    if nginx -t 2>&1; then
        systemctl reload nginx
        log_info "Nginx updated: frontend root = $FRONTEND_ROOT"
    else
        log_error "Nginx config test failed! Check: nginx -t"
    fi
else
    log_warn "Nginx template not found. Update /etc/nginx/sites-available/baluhost manually."
fi

# ─── 9. Start Services ───────────────────────────────────────────────

log_step "Starting Services"

for svc in baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav; do
    systemctl enable "$svc"
    systemctl start "$svc"
    log_info "Started $svc"
done

# ─── 10. Verification ────────────────────────────────────────────────

log_step "Verification"

sleep 3

# Alembic revision check
cd "$TARGET_DIR/backend"
NEW_ALEMBIC=$(sudo -u "$OWNER" .venv/bin/alembic current 2>/dev/null | head -1 | awk '{print $1}' || echo "unknown")
if [[ "$NEW_ALEMBIC" == "$CURRENT_ALEMBIC" ]]; then
    log_info "Alembic revision: $NEW_ALEMBIC (matches pre-migration)"
else
    log_warn "Alembic revision mismatch: was $CURRENT_ALEMBIC, now $NEW_ALEMBIC"
fi

# Data count check
NEW_USER_COUNT=$(sudo -u postgres psql -t -A -d "$DB_NAME" -c "SELECT count(*) FROM users;" 2>/dev/null || echo "?")
if [[ "$NEW_USER_COUNT" == "$USER_COUNT" ]]; then
    log_info "User count: $NEW_USER_COUNT (matches pre-migration)"
else
    log_warn "User count mismatch: was $USER_COUNT, now $NEW_USER_COUNT"
fi

# Health check
if curl -sf http://localhost/api/system/health > /dev/null 2>&1; then
    log_info "Health check: PASSED"
else
    log_warn "Health check: FAILED (services may still be starting)"
    log_warn "Check: sudo systemctl status baluhost-backend"
fi

# Frontend check
if curl -sf http://localhost/ > /dev/null 2>&1; then
    log_info "Frontend: ACCESSIBLE"
else
    log_warn "Frontend: NOT ACCESSIBLE"
fi

# ─── 11. Install Daily Backup Cron ───────────────────────────────────

log_step "Daily Backup Cron"

CRON_CMD="0 3 * * * $TARGET_DIR/deploy/scripts/db-backup-daily.sh >> /var/log/baluhost/db-backup.log 2>&1"
if crontab -u "$OWNER" -l 2>/dev/null | grep -q "db-backup-daily.sh"; then
    log_info "Daily backup cron already installed."
else
    mkdir -p /var/log/baluhost
    chown "$OWNER:$GROUP" /var/log/baluhost
    (crontab -u "$OWNER" -l 2>/dev/null; echo "$CRON_CMD") | crontab -u "$OWNER" -
    log_info "Installed daily backup cron (03:00)."
fi

# ─── Summary ──────────────────────────────────────────────────────────

log_step "Migration Complete"
echo ""
log_info "Source:       $SOURCE_DIR (keep as dev workspace)"
log_info "Production:   $TARGET_DIR"
log_info "Database:     unchanged (PostgreSQL at localhost:5432)"
log_info "Alembic:      $NEW_ALEMBIC"
log_info "Backup:       $BACKUP_FILE"
log_info "Frontend:     $TARGET_DIR/client/dist/"
echo ""
log_info "Next steps:"
log_info "  1. Verify login: curl -X POST http://localhost/api/auth/login ..."
log_info "  2. Check all services: sudo systemctl status 'baluhost-*'"
log_info "  3. Set up GitHub Actions runner: see deploy/runner/README.md"
log_info "  4. After 1 week stable: keep $SOURCE_DIR as dev workspace"
