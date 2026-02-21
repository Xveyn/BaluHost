#!/bin/bash
# BaluHost Install - Module 05: Python Virtual Environment
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Variables ──────────────────────────────────────────────────────

VENV_DIR="$INSTALL_DIR/backend/.venv"
BACKEND_DIR="$INSTALL_DIR/backend"

# ─── Main ───────────────────────────────────────────────────────────

log_step "Python Virtual Environment"

require_root

# --- Create venv if not exists ---
if [[ -d "$VENV_DIR" && -f "$VENV_DIR/bin/python" ]]; then
    log_info "Virtual environment already exists at $VENV_DIR, reusing."
else
    log_info "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    log_info "Virtual environment created."
fi

# --- Upgrade pip ---
log_info "Upgrading pip..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip --quiet
PIP_VERSION=$("$VENV_DIR/bin/pip" --version | awk '{print $2}')
log_info "pip upgraded to $PIP_VERSION."

# --- Install application dependencies ---
log_step "Installing Dependencies"

if [[ ! -f "$BACKEND_DIR/pyproject.toml" ]]; then
    log_error "pyproject.toml not found at $BACKEND_DIR/pyproject.toml"
    exit 1
fi

log_info "Installing BaluHost backend with [scheduler] extras..."
"$VENV_DIR/bin/pip" install -e "$BACKEND_DIR[scheduler]" --quiet
log_info "Dependencies installed."

# --- Verify uvicorn ---
log_step "Verification"

if "$VENV_DIR/bin/python" -c "import uvicorn" 2>/dev/null; then
    UVICORN_VERSION=$("$VENV_DIR/bin/python" -c "import uvicorn; print(uvicorn.__version__)")
    log_info "uvicorn is available: $UVICORN_VERSION"
else
    log_error "uvicorn is NOT installed in the virtual environment."
    log_error "The installation may have failed. Check the output above."
    exit 1
fi

# --- Also verify FastAPI is present ---
if "$VENV_DIR/bin/python" -c "import fastapi" 2>/dev/null; then
    FASTAPI_VERSION=$("$VENV_DIR/bin/python" -c "import fastapi; print(fastapi.__version__)")
    log_info "FastAPI is available: $FASTAPI_VERSION"
else
    log_error "FastAPI is NOT installed in the virtual environment."
    exit 1
fi

# --- Set ownership ---
log_info "Setting venv ownership to $BALUHOST_USER:$BALUHOST_GROUP..."
chown -R "$BALUHOST_USER":"$BALUHOST_GROUP" "$VENV_DIR"
log_info "Ownership set."

# --- Export for later modules ---
export VENV_BIN="$VENV_DIR/bin"

# --- Summary ---
log_step "Python Environment Summary"
log_info "Venv:     $VENV_DIR"
log_info "Python:   $("$VENV_DIR/bin/python" --version 2>&1)"
log_info "pip:      $PIP_VERSION"
log_info "uvicorn:  $UVICORN_VERSION"
log_info "FastAPI:  $FASTAPI_VERSION"
log_info "VENV_BIN: $VENV_BIN"
log_info "Python virtual environment setup complete."

exit 0
