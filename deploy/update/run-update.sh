#!/bin/bash
# BaluHost Update Runner
# Runs as a detached systemd-run unit so it survives backend restarts.
# Re-uses the existing install modules for actual work.
#
# Usage (called by ProdUpdateBackend.launch_update_script):
#   sudo systemd-run --unit=baluhost-update --remain-after-exit \
#       /opt/baluhost/deploy/update/run-update.sh \
#       --update-id 42 --from-commit abc1234 --to-commit def5678 \
#       --from-version 1.8.2 --to-version 1.9.0

set -euo pipefail

# ─── Parse arguments ────────────────────────────────────────────────

UPDATE_ID=""
FROM_COMMIT=""
TO_COMMIT=""
FROM_VERSION=""
TO_VERSION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --update-id)    UPDATE_ID="$2";    shift 2 ;;
        --from-commit)  FROM_COMMIT="$2";  shift 2 ;;
        --to-commit)    TO_COMMIT="$2";    shift 2 ;;
        --from-version) FROM_VERSION="$2"; shift 2 ;;
        --to-version)   TO_VERSION="$2";   shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$UPDATE_ID" || -z "$TO_COMMIT" || -z "$FROM_COMMIT" ]]; then
    echo "Required: --update-id, --from-commit, --to-commit" >&2
    exit 1
fi

# ─── Load install system ────────────────────────────────────────────

# Locate the install directory relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_LIB_DIR="$(cd "$SCRIPT_DIR/../install" && pwd)"

source "$INSTALL_LIB_DIR/lib/common.sh"
source "$INSTALL_LIB_DIR/lib/config.sh"
load_config

# Force non-interactive mode for all modules
export NON_INTERACTIVE=true

# ─── Status file management ─────────────────────────────────────────

STATUS_DIR="/var/lib/baluhost/update-status"
STATUS_FILE="$STATUS_DIR/${UPDATE_ID}.json"
STARTED_AT=$(date -Iseconds)

write_status() {
    local status="$1"
    local progress="$2"
    local step="$3"
    local error="${4:-}"
    local rollback="${5:-}"
    local completed="${6:-}"

    local tmp="$STATUS_FILE.tmp"
    cat > "$tmp" <<STATUSEOF
{
  "update_id": $UPDATE_ID,
  "status": "$status",
  "progress_percent": $progress,
  "current_step": "$step",
  "from_version": "$FROM_VERSION",
  "to_version": "$TO_VERSION",
  "from_commit": "$FROM_COMMIT",
  "to_commit": "$TO_COMMIT",
  "started_at": "$STARTED_AT",
  "completed_at": ${completed:+\"$completed\"}${completed:-null},
  "error_message": ${error:+\"$error\"}${error:-null},
  "rollback_commit": ${rollback:+\"$rollback\"}${rollback:-null}
}
STATUSEOF
    mv "$tmp" "$STATUS_FILE"
}

# ─── Error handler (rollback on failure) ────────────────────────────

on_error() {
    local exit_code=$?
    local line_no="${BASH_LINENO[0]}"
    local error_msg="Update failed at line $line_no (exit code $exit_code)"
    log_error "$error_msg"

    write_status "failed" "$CURRENT_PROGRESS" "$error_msg" \
        "$error_msg" "" "$(date -Iseconds)"

    # Attempt rollback to original commit
    if [[ -n "$FROM_COMMIT" ]]; then
        log_warn "Attempting rollback to $FROM_COMMIT..."
        if sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" checkout "$FROM_COMMIT" 2>/dev/null; then
            chown -R "$BALUHOST_USER":"$BALUHOST_GROUP" "$INSTALL_DIR"
            write_status "failed" "$CURRENT_PROGRESS" "$error_msg" \
                "$error_msg" "$FROM_COMMIT" "$(date -Iseconds)"
            log_info "Rolled back to $FROM_COMMIT"

            # Restart services after rollback
            for svc in baluhost-backend baluhost-scheduler baluhost-webdav; do
                systemctl restart "$svc" 2>/dev/null || true
            done
        else
            log_error "Rollback also failed!"
        fi
    fi

    exit "$exit_code"
}

trap on_error ERR

# Track current progress for error handler
CURRENT_PROGRESS=0

# ─── Ensure status directory exists ─────────────────────────────────

mkdir -p "$STATUS_DIR"
chmod 770 "$STATUS_DIR"
chown root:"$BALUHOST_GROUP" "$STATUS_DIR"

# ─── Module runner helper ───────────────────────────────────────────

run_module() {
    local module_num="$1"
    local module_name="$2"
    local progress_start="$3"
    local progress_end="$4"

    local module_path="$INSTALL_LIB_DIR/modules/${module_num}-${module_name}.sh"

    if [[ ! -f "$module_path" ]]; then
        log_error "Module not found: $module_path"
        return 1
    fi

    CURRENT_PROGRESS=$progress_start
    write_status "installing" "$progress_start" "Running module $module_num: $module_name..."
    log_step "Module $module_num: $module_name"

    # Source the module (it uses our loaded config + common.sh)
    bash "$module_path"

    CURRENT_PROGRESS=$progress_end
    log_info "Module $module_num completed."
}

# ─── Start update ───────────────────────────────────────────────────

log_step "BaluHost Update Runner (ID: $UPDATE_ID)"
log_info "From: $FROM_VERSION ($FROM_COMMIT)"
log_info "To:   $TO_VERSION ($TO_COMMIT)"
log_info "Install dir: $INSTALL_DIR"

write_status "downloading" 5 "Starting update..."

# ─── Step 1: Git pull (Module 04) ───────────────────────────────────
# Module 04 does git fetch + pull + chown.
# But we need to checkout the specific target commit, not just pull.
# So we do a targeted checkout here instead of using module 04 directly.

CURRENT_PROGRESS=10
write_status "downloading" 10 "Fetching updates from remote..."

cd "$INSTALL_DIR"

# Fetch all refs
sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" fetch --all --tags --prune
log_info "Git fetch complete."

CURRENT_PROGRESS=20
write_status "downloading" 20 "Checking out target version..."

# Stash local changes if any
sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" stash push -m "pre-update-stash" 2>/dev/null || true

# Checkout target commit
sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" checkout "$TO_COMMIT"
log_info "Checked out $TO_COMMIT"

# If it's a branch reference, pull to latest
CURRENT_BRANCH=$(sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")
if [[ "$CURRENT_BRANCH" != "HEAD" ]]; then
    sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" pull --rebase 2>/dev/null || true
fi

# Fix ownership after git operations
chown -R "$BALUHOST_USER":"$BALUHOST_GROUP" "$INSTALL_DIR"
log_info "Git checkout and ownership fix complete."

CURRENT_PROGRESS=30
write_status "installing" 30 "Installing Python dependencies..."

# ─── Step 2: Python dependencies (Module 05) ────────────────────────

run_module "05" "python-venv" 30 45

# ─── Step 3: Database migrations (Module 08) ────────────────────────

write_status "migrating" 45 "Running database migrations..."
run_module "08" "database-migrate" 45 55

# ─── Step 4: Frontend build + deploy (Module 09) ────────────────────

write_status "installing" 55 "Building frontend..."
run_module "09" "frontend-build" 55 70

# ─── Step 5: Systemd service files (Module 10) ──────────────────────

write_status "installing" 70 "Updating systemd service files..."
run_module "10" "systemd-services" 70 75

# ─── Step 6: Nginx config (Module 11) ───────────────────────────────

write_status "installing" 75 "Updating Nginx configuration..."
run_module "11" "nginx" 75 80

# ─── Step 7: Restart all services (Module 12) ───────────────────────

write_status "restarting" 80 "Restarting all services..."
run_module "12" "start-services" 80 95

# ─── Step 8: Final status ───────────────────────────────────────────

CURRENT_PROGRESS=100
COMPLETED_AT=$(date -Iseconds)

write_status "completed" 100 "Update completed successfully" \
    "" "" "$COMPLETED_AT"

log_step "Update Complete"
log_info "Updated from $FROM_VERSION to $TO_VERSION"
log_info "Commit: $FROM_COMMIT -> $TO_COMMIT"
log_info "Duration: $STARTED_AT -> $COMPLETED_AT"

exit 0
