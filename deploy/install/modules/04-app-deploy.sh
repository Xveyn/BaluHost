#!/bin/bash
# BaluHost Install - Module 04: Application Deployment
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Main ───────────────────────────────────────────────────────────

log_step "Application Deployment"

require_root

# --- Clone or update repository ---
if [[ -d "$INSTALL_DIR/backend" ]]; then
    log_info "Existing installation found at $INSTALL_DIR/backend. Updating..."

    if sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" fetch --quiet 2>/dev/null; then
        CURRENT_BRANCH=$(sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
        if [[ "$CURRENT_BRANCH" != "$GIT_BRANCH" ]]; then
            log_warn "Current branch is '$CURRENT_BRANCH', expected '$GIT_BRANCH'. Switching..."
            sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" checkout "$GIT_BRANCH" 2>/dev/null || {
                log_warn "Could not switch to branch '$GIT_BRANCH'. Continuing on '$CURRENT_BRANCH'."
            }
        fi

        OLD_HEAD=$(sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null)
        if sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" pull --quiet 2>/dev/null; then
            NEW_HEAD=$(sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null)
            if [[ "$OLD_HEAD" == "$NEW_HEAD" ]]; then
                log_info "Already up to date at commit $NEW_HEAD."
            else
                log_info "Updated from $OLD_HEAD to $NEW_HEAD."
            fi
        else
            log_warn "git pull failed (local changes?). Continuing with existing code."
        fi
    else
        log_warn "git fetch failed. Continuing with existing code."
    fi
elif [[ -d "$INSTALL_DIR/.git" ]]; then
    # Repo exists but backend dir missing -- something is wrong
    log_error "$INSTALL_DIR exists as a git repo but backend/ is missing."
    exit 1
else
    log_info "Cloning BaluHost from $GIT_REPO (branch: $GIT_BRANCH)..."

    # Clone into a temp dir first, then move contents (INSTALL_DIR may already exist)
    TEMP_CLONE=$(mktemp -d)
    trap 'rm -rf "$TEMP_CLONE"' EXIT

    git clone --branch "$GIT_BRANCH" --single-branch "$GIT_REPO" "$TEMP_CLONE"

    # Move contents into INSTALL_DIR (which was created by module 03)
    if [[ -d "$INSTALL_DIR" ]]; then
        # Move everything including hidden files (.git, etc.)
        shopt -s dotglob
        mv "$TEMP_CLONE"/* "$INSTALL_DIR"/
        shopt -u dotglob
    else
        mv "$TEMP_CLONE" "$INSTALL_DIR"
    fi

    trap - EXIT
    rm -rf "$TEMP_CLONE" 2>/dev/null || true

    NEW_HEAD=$(git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    log_info "Cloned successfully at commit $NEW_HEAD."
fi

# --- Set ownership ---
log_info "Setting ownership to $BALUHOST_USER:$BALUHOST_GROUP..."
chown -R "$BALUHOST_USER":"$BALUHOST_GROUP" "$INSTALL_DIR"
log_info "Ownership set."

# --- Sanity check ---
log_step "Deployment Verification"

if [[ -f "$INSTALL_DIR/backend/app/main.py" ]]; then
    log_info "Sanity check passed: backend/app/main.py exists."
else
    log_error "Sanity check FAILED: $INSTALL_DIR/backend/app/main.py not found."
    log_error "The repository may be incomplete or the wrong branch was checked out."
    exit 1
fi

COMMIT=$(sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
BRANCH=$(sudo -u "$BALUHOST_USER" git -C "$INSTALL_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
log_info "Deployed: branch=$BRANCH commit=$COMMIT"
log_info "Application deployment complete."

exit 0
