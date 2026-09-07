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
HEALTH_URL="http://localhost/api/health"
HEALTH_RETRIES=5
HEALTH_DELAY=3
DB_NAME="baluhost"
DB_USER="baluhost"
BACKUP_RETENTION=10

# Re-apply OS-level permission grants (udev rules, polkit, sudoers) on every
# deploy. Off by default so a normal deploy never touches /etc/udev or
# /etc/polkit-1. Enable via:
#   - GitHub: workflow_dispatch input "sync_permissions" = true
#   - Manual: SYNC_PERMISSIONS=1 ./ci-deploy.sh
# Database handling is unaffected — alembic still runs, no schema reset.
SYNC_PERMISSIONS="${SYNC_PERMISSIONS:-0}"

# Build the Tauri Companion app from source on this host and install it
# system-wide (.deb). Off by default so a routine deploy never pays the Rust
# compile cost. Enable via:
#   - GitHub: workflow_dispatch input "install_companion" = true
#   - Manual: INSTALL_COMPANION=1 ./ci-deploy.sh
# Runs only after a successful deploy + health check, and is fully non-fatal:
# a companion build/install failure never rolls back a healthy backend deploy.
INSTALL_COMPANION="${INSTALL_COMPANION:-0}"

# Load .env.production into environment (needed by Alembic/Pydantic)
load_env_production() {
    local env_file="$INSTALL_DIR/.env.production"
    if [[ ! -f "$env_file" ]]; then
        echo "ERROR: $env_file not found" >&2
        exit 1
    fi
    # Export all KEY=VALUE lines (skip comments and empty lines)
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "$env_file" | grep -v '^\s*$')
    set +a

    # Extract PGPASSWORD from DATABASE_URL for pg_dump.
    # Parsed with python3 instead of sed (#339): the password inside a
    # DATABASE_URL is percent-encoded, and SQLAlchemy decodes it on connect. A
    # sed capture hands pg_dump the still-encoded string, so a password
    # containing '@' (arriving as '%40') would fail authentication and take the
    # pre-deploy backup with it. The URL is passed as argv, not interpolated
    # into the Python source.
    export PGPASSWORD
    PGPASSWORD=$(python3 -c 'import sys, urllib.parse as u; print(u.unquote(u.urlsplit(sys.argv[1]).password or ""))' "$DATABASE_URL")
    if [[ -z "${PGPASSWORD:-}" ]]; then
        echo "ERROR: Could not extract database password from DATABASE_URL" >&2
        exit 1
    fi
}
load_env_production

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

# ─── Companion (Tauri) Build + Install ────────────────────────────────
#
# Opt-in (INSTALL_COMPANION=1). Builds the BaluHost Companion desktop app from
# source on this host — Rust must be installed — and installs the resulting
# .deb system-wide. Build runs as the unprivileged deploy user; only the final
# dpkg/apt install needs root, and that goes through the pinned-path sudoers
# entry for install-companion.sh. Every failure path is non-fatal: the backend
# deploy has already succeeded and must not be rolled back by a companion issue.
build_install_companion() {
    log_step "BaluHost Companion (Tauri) Build + Install"

    local client_dir="$INSTALL_DIR/client"
    local deb_glob="$INSTALL_DIR/client/src-tauri/target/release/bundle/deb/*.deb"
    local stage_dir="$INSTALL_DIR/.companion"
    local staged_deb="$stage_dir/baluhost-companion.deb"

    if ! command -v cargo >/dev/null 2>&1; then
        log_warn "Rust/cargo not found on this host — cannot build companion. Skipping."
        log_warn "Install Rust (see docs) then re-run with INSTALL_COMPANION=1."
        return 0
    fi

    # node_modules are already populated by the Frontend Build step (npm ci),
    # so the tauri CLI from devDependencies is available without a second install.
    cd "$client_dir"
    log_info "Building companion .deb from source (cold builds take several minutes)..."
    if ! VITE_TAURI=1 npm run tauri:build -- --bundles deb; then
        log_warn "Companion build failed — backend deploy is unaffected. Skipping install."
        return 0
    fi

    # Stage the freshly built .deb at a FIXED path. The installer's sudoers
    # entry pins this exact, non-user-controlled path, so the version-stamped
    # build filename never reaches a sudo command line.
    mkdir -p "$stage_dir"
    local built
    # shellcheck disable=SC2086
    built=$(ls -t $deb_glob 2>/dev/null | head -1 || true)
    if [[ -z "$built" ]]; then
        log_warn "Build reported success but no .deb was found at $deb_glob — skipping install."
        return 0
    fi
    cp -f "$built" "$staged_deb"
    log_info "Staged: $(basename "$built") -> $staged_deb"

    if sudo bash "$INSTALL_DIR/deploy/scripts/install-companion.sh"; then
        log_info "Companion installed/updated system-wide."
    else
        log_warn "Companion install failed (non-fatal — deploy stays green)."
    fi
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
    # Force-reset rather than `git checkout`: the failed build may have left a
    # tracked file dirty (same hazard as the forward update, #138), and a plain
    # checkout would refuse it — exactly when the rollback is needed most.
    # `--hard` discards those build artifacts; untracked files are left intact.
    git reset --hard "$PREV_COMMIT" 2>/dev/null || {
        log_error "git reset --hard $PREV_COMMIT failed"
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
# Hard-sync to the remote instead of `git pull`. The prod box is a pure deploy
# target (0 commits ahead of origin/main), so any local change to a tracked file
# is a build artifact — e.g. client/package-lock.json normalized by `npm ci` —
# that a plain `git pull` refuses to overwrite, aborting the deploy (#138).
# `checkout -f` also re-attaches to main from a detached HEAD left by a prior
# rollback. Untracked files (.env.production, backups/) are NOT touched — no
# `git clean` is run, so deploy-local state is preserved.
git fetch --all --prune
git checkout -f main
git reset --hard origin/main

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

# ─── 4b. OS Permission Grants (opt-in) ───────────────────────────────
#
# Idempotent re-install of OS-level permission rules that ship with the
# repo (udev / polkit / sudoers). Skipped by default so a routine deploy
# does not touch /etc files. The database is never re-initialised here —
# this block is independent of the alembic step that follows.
#
# Enable via:
#   - GitHub: workflow_dispatch input "sync_permissions" = true
#   - Manual: SYNC_PERMISSIONS=1 ./ci-deploy.sh

# Fuehrt eines der Permission-Skripte als root aus -- mit Vorabpruefung, ob der
# Aufruf ueberhaupt erlaubt ist (#570).
#
# Der Grund fuer die Pruefung: /etc/sudoers.d/baluhost-deploy ist die einzige
# der vier sudoers-Dateien, die dieser Deploy nicht neu rendern kann -- sie
# enthaelt genau die Erlaubnis, mit der die anderen drei installiert werden.
# Neue Zeilen der Vorlage erreichen eine bereits installierte Box deshalb nie,
# und der Aufruf scheiterte dann mit "sudo: a password is required" hinter
# einer nichtssagenden WARN-Zeile.
#
# `sudo -n -l <cmd>` endet mit 0 genau dann, wenn der Aufruf erlaubt waere --
# ohne ihn auszufuehren. Es laeuft passwortlos, solange listpw auf Debians
# Standard "any" steht und der Benutzer mindestens einen NOPASSWD-Eintrag hat
# (beides gilt hier). Bei listpw=all waere die Pruefung falsch negativ und der
# Sync uebersprungen.
run_permission_script() {
    local label="$1" script="$2"
    if [[ ! -f "$script" ]]; then
        log_warn "$label script not found at $script (skipping)."
        return 0
    fi
    log_info "Re-applying $label..."
    if ! sudo -n -l bash "$script" >/dev/null 2>&1; then
        log_warn "$label sync NOT PERMITTED: /etc/sudoers.d/baluhost-deploy on this box"
        log_warn "  predates the entry for $(basename "$script"). One-time fix:"
        # Der Benutzername wird HIER eingesetzt, nicht als $USER ausgegeben:
        # die Anweisung wird typischerweise in einer root-Shell ausgefuehrt, wo
        # $USER zu "root" wuerde. Die Datei wuerde dann fuer root gerendert, und
        # der Deploy-Benutzer verloere still alle NOPASSWD-Rechte -- der
        # naechste Deploy braeche beim Neustart der Dienste ab. `env` davor,
        # weil sudo Zuweisungen in der Kommandozeile ohne SETENV ablehnt.
        log_warn "    sudo env BALUHOST_USER=$(id -un) bash $INSTALL_DIR/deploy/scripts/install-deploy-sudoers.sh"
        log_warn "  Until then $label stays at its installed state."
        return 0
    fi
    if sudo bash "$script"; then
        log_info "$label sync OK."
    else
        log_warn "$label sync failed (non-fatal - deploy continues)."
    fi
}

if [[ "${SYNC_PERMISSIONS:-0}" == "1" || "${SYNC_PERMISSIONS,,}" == "true" ]]; then
    log_step "OS Permission Grants (sync requested)"

    # AMD GPU sysfs power nodes: chgrp video + g+w via udev rule.
    # The script defaults BALUHOST_USER=sven internally; sudoers rule
    # whitelists this exact bash invocation, so no env vars are passed.
    run_permission_script "AMD GPU permission"         "$INSTALL_DIR/deploy/scripts/install-amd-gpu-permissions.sh"

    # Hardware sudoers: RAID/SMART/fan/CPU-freq/suspend/rtcwake/ethtool grants.
    # Der Installer rendert @@BALUHOST_USER@@ aus dem laufenden Dienstbenutzer
    # und prueft mit visudo, bevor er die Live-Datei ersetzt.
    run_permission_script "Hardware sudoers"         "$INSTALL_DIR/deploy/scripts/install-hardware-sudoers.sh"

    # Power sudoers: power-profiles-daemon stop/start/mask/unmask + logind-idle
    # + sddm-Desktop-Toggle. Raeumt zusaetzlich die ueberholte
    # /etc/sudoers.d/baluhost-ppd-Zwischenloesung ab.
    run_permission_script "Power sudoers"         "$INSTALL_DIR/deploy/scripts/install-power-sudoers.sh"

    # Future permission scripts go here following the same pattern:
    # if [[ -f "$INSTALL_DIR/deploy/scripts/install-<thing>-permissions.sh" ]]; then ...
else
    log_info "OS permission sync skipped (set SYNC_PERMISSIONS=1 to enable)."
fi

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
npm ci
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

    # ─── 8b. Marketplace Signature Smoke-Check (non-fatal) ───────────────
    # Verify the live marketplace index is signed by a configured trusted key.
    # Never fails the deploy: the backend already fail-closes the (admin-only)
    # Marketplace listing, so a signing hiccup has no runtime-plugin impact.
    # The entrypoint always exits 0 and prints PASS/WARN; the `|| log_warn`
    # only catches a failure to launch python at all.
    log_step "Marketplace Signature Smoke-Check"
    ( cd "$INSTALL_DIR/backend" && "$VENV_BIN/python" -m app.plugins.verify_index_signature ) \
        || log_warn "Marketplace smoke-check could not run (non-fatal)."

    # Opt-in companion build+install runs last, after the deploy is already
    # marked successful, so it can never trigger a rollback of a healthy box.
    if [[ "${INSTALL_COMPANION:-0}" == "1" || "${INSTALL_COMPANION,,}" == "true" ]]; then
        build_install_companion
    else
        log_info "Companion build skipped (set INSTALL_COMPANION=1 to enable)."
    fi
else
    log_error "Health check failed after deploy!"
    rollback
fi
