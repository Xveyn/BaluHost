#!/bin/bash
# Install (or update) the BaluHost Companion desktop app system-wide from the
# .deb that ci-deploy.sh built and staged at a fixed path.
#
# Why a dedicated root script (and not `sudo dpkg` directly in ci-deploy.sh):
# the deploy user has NOPASSWD sudo for exactly this pinned-path invocation
# (see deploy/install/templates/baluhost-deploy-sudoers). dpkg/apt are NOT
# whitelisted directly, so the deploy user cannot install arbitrary packages —
# only this version-controlled script, which installs only the staged .deb at a
# fixed, non-user-controlled path. Same isolation pattern as
# install-amd-gpu-permissions.sh / install-hardware-sudoers.sh.
#
# Run as root.

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/baluhost}"
# Fixed staging path written by ci-deploy.sh's build_install_companion().
# Pinning it here is what lets the sudoers entry pin a single, exact command.
DEB_PATH="$INSTALL_DIR/.companion/baluhost-companion.deb"

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: must run as root (use sudo)." >&2
    exit 1
fi

if [[ ! -f "$DEB_PATH" ]]; then
    echo "ERROR: staged companion package not found: $DEB_PATH" >&2
    echo "       ci-deploy.sh stages it after a successful Tauri build." >&2
    exit 1
fi

echo "  ..  installing $DEB_PATH"

# apt resolves runtime dependencies; a bare `dpkg -i` can leave them unmet.
# --reinstall forces a re-install when the version is unchanged (the common
# case for a routine re-deploy of the same companion version).
export DEBIAN_FRONTEND=noninteractive
if apt-get install -y --reinstall "$DEB_PATH"; then
    echo "  OK  BaluHost Companion installed via apt"
else
    echo "  WARN apt install failed — falling back to dpkg + apt -f install" >&2
    dpkg -i "$DEB_PATH" || true
    apt-get -f install -y
    echo "  OK  BaluHost Companion installed via dpkg fallback"
fi

echo "  OK  BaluHost Companion is installed/updated system-wide"
