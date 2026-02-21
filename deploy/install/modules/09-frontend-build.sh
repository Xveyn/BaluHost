#!/bin/bash
# BaluHost Install - Module 09: Frontend Build
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Variables ──────────────────────────────────────────────────────

CLIENT_DIR="$INSTALL_DIR/client"

# ─── Main ───────────────────────────────────────────────────────────

log_step "Frontend Build"

require_root

# --- Verify prerequisites ---
if [[ ! -d "$CLIENT_DIR" ]]; then
    log_error "Client directory not found: $CLIENT_DIR"
    exit 1
fi

if [[ ! -f "$CLIENT_DIR/package.json" ]]; then
    log_error "package.json not found in $CLIENT_DIR"
    exit 1
fi

if ! command -v npm &>/dev/null; then
    log_error "npm is not installed. Install Node.js first (module 02)."
    exit 1
fi

NODE_VERSION=$(node --version 2>&1)
NPM_VERSION=$(npm --version 2>&1)
log_info "Node.js: $NODE_VERSION"
log_info "npm:     $NPM_VERSION"

# --- Install dependencies ---
log_step "Installing Dependencies"

cd "$CLIENT_DIR"

log_info "Running npm install..."
npm install --no-optional 2>&1 | tail -5
log_info "npm dependencies installed."

# --- Build production bundle ---
log_step "Building Production Bundle"

log_info "Running npm run build..."
npm run build 2>&1 | tail -10
log_info "Frontend build completed."

# --- Verify build output ---
if [[ ! -d "$CLIENT_DIR/dist" ]]; then
    log_error "Build output directory not found: $CLIENT_DIR/dist"
    log_error "The build may have failed. Check the output above."
    exit 1
fi

if [[ ! -f "$CLIENT_DIR/dist/index.html" ]]; then
    log_error "index.html not found in build output."
    exit 1
fi

BUILD_SIZE=$(du -sh "$CLIENT_DIR/dist" | cut -f1)
log_info "Build output size: $BUILD_SIZE"

# --- Deploy to static directory ---
log_step "Deploying to $FRONTEND_STATIC_DIR"

mkdir -p "$FRONTEND_STATIC_DIR"

# Clear existing content and copy fresh build
rm -rf "${FRONTEND_STATIC_DIR:?}"/*
cp -r "$CLIENT_DIR/dist/"* "$FRONTEND_STATIC_DIR/"
log_info "Build output copied to $FRONTEND_STATIC_DIR."

# --- Set ownership ---
chown -R "$BALUHOST_USER":"$BALUHOST_GROUP" "$FRONTEND_STATIC_DIR"
log_info "Ownership set to $BALUHOST_USER:$BALUHOST_GROUP."

# --- Final verification ---
if [[ ! -f "$FRONTEND_STATIC_DIR/index.html" ]]; then
    log_error "index.html not found in $FRONTEND_STATIC_DIR after deployment."
    exit 1
fi

DEPLOYED_SIZE=$(du -sh "$FRONTEND_STATIC_DIR" | cut -f1)
FILE_COUNT=$(find "$FRONTEND_STATIC_DIR" -type f | wc -l)

# --- Summary ---
log_step "Frontend Summary"
log_info "Source:     $CLIENT_DIR"
log_info "Output:     $FRONTEND_STATIC_DIR"
log_info "Size:       $DEPLOYED_SIZE"
log_info "Files:      $FILE_COUNT"
log_info "index.html: present"
log_info "Frontend build and deployment complete."

exit 0
